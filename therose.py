#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import traceback
import requests
from seleniumbase import SB

# 环境变量
EMAIL = (os.environ.get("EMAIL") or "").strip()
PASSWORD = (os.environ.get("PASSWORD") or "").strip()
TG_BOT_TOKEN = (os.environ.get("TG_BOT_TOKEN") or "").strip()
TG_CHAT_ID = (os.environ.get("TG_CHAT_ID") or "").strip()

# 目标服务器面板地址
SERVER_URL = os.environ.get("SERVER_URL") or "https://panel.therose.cloud/server/1ce3ddfb"
BASE_URL = "https://therose.cloud/login"

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

# --- 代理配置 ---
IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None

if not EMAIL or not PASSWORD:
    print("❌ 请设置环境变量 EMAIL 和 PASSWORD")
    sys.exit(1)


def get_current_ip(proxy_server=None):
    proxies = {"http": proxy_server, "https": proxy_server} if (proxy_server and IS_PROXY) else None
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
        if resp.status_code == 200:
            return resp.text.strip()
        return "获取失败"
    except Exception as e:
        print(f"❌ 获取出口IP失败: {e}")
        return "获取失败"


def send_tg(token, chat_id, message, image_path=None):
    if not token or not chat_id:
        return
    message = f"【TheRose Cloud】\n{message}"
    target_image = image_path if (image_path and os.path.exists(image_path)) else (LOGO_PATH if os.path.exists(LOGO_PATH) else None)

    if target_image:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(target_image, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": message},
                    files={"photo": f},
                    timeout=15,
                    proxies=REQUESTS_PROXIES,
                )
            if resp.status_code == 200:
                print(f"📨 Telegram 通知已发送（附带图片: {target_image}）")
                return
            else:
                print(f"⚠️ 带图发送失败，回退为纯文字: {resp.text}")
        except Exception as e:
            print(f"⚠️ 带图发送异常，回退为纯文字: {e}")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10, proxies=REQUESTS_PROXIES)
        if resp.status_code == 200:
            print("📨 Telegram 通知已发送（纯文字）")
        else:
            print(f"❌ Telegram 发送失败: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")


def wait_for_turnstile_token(sb, max_wait=20):
    print("⏳ 等待 Turnstile 验证生成 Token...")
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            token = sb.execute_script("""
                const el = document.querySelector('[name="cf-turnstile-response"]');
                return el ? el.value : "";
            """)
            if token and len(token.strip()) > 10:
                print(f"✅ 检测到 Turnstile Token 已生成 (长度: {len(token)})")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("⚠️ 达到最大等待时间，Turnstile Token 仍未检测到，尝试强行提交")
    return False


def fill_input_safely(sb, field_type, value):
    if field_type == "email":
        selectors = [
            'input[type="email"]',
            'input[name="email"]',
            '#email',
            '#login_form_email',
            'input[autocomplete="email"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="邮箱" i]'
        ]
    else:
        selectors = [
            'input[type="password"]',
            'input[name="password"]',
            '#password',
            '#login_form_password',
            'input[autocomplete="current-password"]',
            'input[placeholder*="password" i]',
            'input[placeholder*="密码" i]'
        ]

    for sel in selectors:
        try:
            if sb.is_element_visible(sel):
                sb.clear(sel)
                sb.type(sel, value)
                print(f"✅ 成功填入 {field_type} (选择器: {sel})")
                return True
        except Exception:
            continue

    try:
        script = f"""
            const inputs = Array.from(document.querySelectorAll('input'));
            let target = null;
            if ('{field_type}' === 'email') {{
                target = inputs.find(i => i.type === 'email' || i.name.includes('email') || i.id.includes('email'));
            }} else {{
                target = inputs.find(i => i.type === 'password' || i.name.includes('password') || i.id.includes('password'));
            }}
            if (target) {{
                target.value = '{value}';
                target.dispatchEvent(new Event('input', {{ bubbles: true }}));
                target.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        """
        if sb.execute_script(script):
            print(f"✅ 通过 JS 脚本成功填入 {field_type}")
            return True
    except Exception as e:
        print(f"⚠️ JS 填入 {field_type} 异常: {e}")

    return False


def login(sb, email, password):
    print("🌐 打开登录页面...")
    try:
        sb.open(BASE_URL)
        sb.wait_for_ready_state_complete()
        sb.sleep(3)
    except Exception as e:
        print(f"❌ 页面打开失败: {e}")
        sb.save_screenshot("login_failed.png")
        return False, sb.get_current_url()

    sb.save_screenshot("page_opened.png")

    print("📧 填写邮箱...")
    if not fill_input_safely(sb, "email", email):
        print("❌ 未能找到邮箱输入框")
        sb.save_screenshot("login_failed.png")
        return False, sb.get_current_url()

    print("🔑 填写密码...")
    if not fill_input_safely(sb, "password", password):
        print("❌ 未能找到密码输入框")
        sb.save_screenshot("login_failed.png")
        return False, sb.get_current_url()

    time.sleep(1)

    print("🛡 处理 Turnstile 验证码...")
    try:
        sb.uc_gui_click_captcha()
    except Exception as e:
        print(f"⚠️ uc_gui_click_captcha 执行提示: {e}")

    wait_for_turnstile_token(sb, max_wait=20)
    time.sleep(1)

    for attempt in range(3):
        print(f"🔑 点击登录按钮...(第 {attempt + 1} 次)")
        clicked = False
        btn_selectors = [
            'button[type="submit"]',
            'button:contains("Sign in")',
            'button:contains("Log in")',
            'button:contains("登录")',
            'input[type="submit"]'
        ]
        for btn_sel in btn_selectors:
            try:
                if sb.is_element_visible(btn_sel):
                    sb.uc_click(btn_sel)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            try:
                sb.execute_script("""
                    const btn = document.querySelector('button[type="submit"]') || Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Sign') || b.innerText.includes('Log'));
                    if (btn) btn.click();
                """)
            except Exception:
                pass

        for _ in range(6):
            current_url = sb.get_current_url()
            if "/dashboard" in current_url or "/panel" in current_url or "/server" in current_url:
                print(f"✅ 登录成功，当前 URL: {current_url}")
                return True, current_url

            err_selectors = ['.alert-danger', 'div[role="alert"]', '.text-danger', 'span.text-red-500']
            for sel in err_selectors:
                try:
                    if sb.is_element_visible(sel):
                        err_text = sb.get_text(sel).strip()
                        if err_text:
                            print(f"❌ 登录出现明确错误提示: {err_text}")
                            sb.save_screenshot("login_failed.png")
                            return False, sb.get_current_url()
                except Exception:
                    pass
            time.sleep(1)

        print("⚠️ 未完成跳转，准备重试...")

    print(f"❌ 登录超时或失败，当前 URL: {sb.get_current_url()}")
    sb.save_screenshot("login_failed.png")
    return False, sb.get_current_url()


def click_extend_button(sb):
    selectors = [
        'span:contains("Extend")',
        'button:contains(title="Extend")',
        'button:contains("Extend")',
        'a:contains("Extend")'
    ]
    for sel in selectors:
        try:
            if sb.find_element(sel, timeout=2):
                print(f"✅ 找到按钮，选择器: {sel}")
                sb.uc_click(sel, timeout=5)
                print("✅ 点击成功")
                return True, {}
        except Exception:
            continue
    try:
        btn = sb.find_element('button:contains("Extend")', timeout=2)
        sb.driver.execute_script("arguments[0].click();", btn)
        print("✅ 通过 JavaScript 点击成功")
        return True, {}
    except Exception as e:
        err = str(e)
        not_time = "was not found" in err or "NoSuchElement" in err
        return False, {"error": err, "not_time": not_time}


def check_renewal_success(sb):
    success_selectors = [
        '.alert-success',
        '.alert.alert-success',
        'div[role="alert"].alert-success',
        'div.alert-success',
        'span:contains("successfully purchased")',
        'div:contains("successfully purchased")'
    ]

    print("⏳ 等待5秒检查续期结果...")
    time.sleep(5)

    for selector in success_selectors:
        try:
            element = sb.find_element(selector, timeout=2)
            if element:
                text = element.text
                print(f"✅ 发现成功提示！选择器: {selector}")
                return True, text
        except Exception:
            continue

    try:
        page_source = sb.get_page_source()
        if "successfully purchased" in page_source.lower():
            print("✅ 页面源码中发现 'successfully purchased' 关键词")
            return True, "服务器已成功续期"
    except Exception:
        pass

    return False, "未检测到续期成功提示"


def start_or_reboot_server(sb, url):
    print(f"🔄 准备进入服务器面板进行启动/重启: {url}")
    try:
        sb.open(url)
        sb.wait_for_ready_state_complete()
        time.sleep(5)

        if sb.is_element_visible('input[type="password"]'):
            print("🔒 检测到控制面板需要独立登录，正在尝试自动输入账号密码...")
            try:
                fill_input_safely(sb, "email", EMAIL)
                fill_input_safely(sb, "password", PASSWORD)
                time.sleep(1)
                try:
                    sb.uc_gui_click_captcha()
                except Exception:
                    pass
                time.sleep(3)
                try:
                    sb.click('button:contains("Login")')
                except Exception:
                    sb.click('button[type="submit"]')
                time.sleep(8)
            except Exception as e:
                print(f"⚠️ 自动登录控制面板发生错误: {e}")

        current_url = sb.get_current_url()
        if "/server/" not in current_url:
            print("🔀 检测到停留在主列表页，正在强制进入目标服务器控制台...")
            sb.open(url)
            sb.wait_for_ready_state_complete()
            time.sleep(6)

        btn_clicked = False
        action_name = ""

        start_selectors = [
            'button:contains("启动")',
            'button:contains("Start")',
            'button[data-action="start"]',
            'button i.fa-play'
        ]
        for sel in start_selectors:
            try:
                if sb.is_element_visible(sel) and sb.is_element_enabled(sel):
                    print(f"✅ 找到可用【启动】按钮: {sel}")
                    sb.uc_click(sel)
                    btn_clicked = True
                    action_name = "启动"
                    break
            except Exception:
                continue

        if not btn_clicked:
            reboot_selectors = [
                'button:contains("重启")',
                'button:contains("Restart")',
                'button[data-action="restart"]',
                'button i.fa-redo',
                'button i.fa-sync'
            ]
            for sel in reboot_selectors:
                try:
                    if sb.is_element_visible(sel) and sb.is_element_enabled(sel):
                        print(f"✅ 找到可用【重启】按钮: {sel}")
                        sb.uc_click(sel)
                        btn_clicked = True
                        action_name = "重启"
                        break
                except Exception:
                    continue

        if not btn_clicked:
            print("⚠️ 未能通过常规选择器找到可用按钮，正在使用 JavaScript 定位...")
            try:
                js_result = sb.driver.execute_script("""
                    const buttons = document.querySelectorAll('button');
                    for (let btn of buttons) {
                        let text = btn.innerText || "";
                        let html = btn.innerHTML || "";
                        let action = btn.getAttribute('data-action') || "";
                        if ((action === 'start' || html.includes('fa-play') || text.includes('Start') || text.includes('启动')) && !btn.disabled) {
                            btn.click(); return '启动';
                        }
                    }
                    for (let btn of buttons) {
                        let text = btn.innerText || "";
                        let html = btn.innerHTML || "";
                        let action = btn.getAttribute('data-action') || "";
                        if ((action === 'restart' || html.includes('fa-redo') || html.includes('fa-sync') || text.includes('Restart') || text.includes('重启')) && !btn.disabled) {
                            btn.click(); return '重启';
                        }
                    }
                    return null;
                """)
                if js_result:
                    btn_clicked = True
                    action_name = js_result
                    print(f"✅ 通过 JavaScript 成功点击了【{action_name}】按钮")
            except Exception as ex:
                print(f"⚠️ JS 降级点击失败: {ex}")

        if btn_clicked:
            print(f"⏳ 等待 {action_name} 命令发送...")
            time.sleep(3)
            return True, f"已成功发送 [{action_name}] 指令"
        else:
            return False, "页面上未检测到可用的启动或重启按钮"

    except Exception as e:
        return False, f"维护操作发生异常: {e}"


def main():
    print("🚀 启动浏览器")

    if IS_PROXY:
        print(f"⚙️ 代理已启用: {PROXY_SERVER}")
    else:
        print("🌐 直连模式（未使用代理）")

    current_ip = get_current_ip(PROXY_SERVER)
    print(f"🎯 当前出口IP: {current_ip}")

    sb_kwargs = {"uc": True, "headless": False}
    if IS_PROXY:
        sb_kwargs["proxy"] = PROXY_SERVER

    with SB(**sb_kwargs) as sb:
        try:
            success, url = login(sb, EMAIL, PASSWORD)

            if not success:
                msg = "❌ 登录失败，请检查账号密码或验证码拦截情况。"
                print(msg)
                send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="login_failed.png")
                return

            print("📄 开始续期流程...")
            ok, info = click_extend_button(sb)

            if not ok:
                if info.get("not_time"):
                    msg_renewal = "⏳ 未到续期时间，Extend 按钮尚未出现（一般到期前半小时开放），本次跳过。"
                else:
                    msg_renewal = f"❌ 续期失败，未找到 Extend 按钮 ({info.get('error')})。"
                print(msg_renewal)
            else:
                time.sleep(1)
                try:
                    button = sb.find_element('button:contains("Order now")', timeout=5)
                    if button:
                        print("🛒 点击 Order now 按钮...")
                        sb.uc_click('button:contains("Order now")')
                    else:
                        msg_renewal = "❌ 续期异常，未找到 Order now 按钮。"
                        print(msg_renewal)
                except Exception as e:
                    msg_renewal = f"❌ 点击 Order now 发生错误: {e}。"
                    print(msg_renewal)

                print("🔍 检查续期结果...")
                renewal_success, renewal_msg = check_renewal_success(sb)
                if renewal_success:
                    msg_renewal = f"✅ 续期成功！{renewal_msg}"
                    sb.save_screenshot("renewal_success.png")
                else:
                    msg_renewal = f"❌ 续期可能失败: {renewal_msg}"
                    sb.save_screenshot("renewal_failed.png")
                print(msg_renewal)

            print("🔄 开始检查并执行服务器启动/重启维护...")
            reboot_ok, reboot_msg = start_or_reboot_server(sb, SERVER_URL)

            if reboot_ok:
                msg_reboot = f"✅ 自动状态维护成功: {reboot_msg}"
            else:
                msg_reboot = f"⚠️ 状态维护失败: {reboot_msg}"
            print(msg_reboot)

            final_image = "final_result.png"
            sb.save_screenshot(final_image)
            final_msg = f"IP: {current_ip}\n\n{msg_renewal}\n---\n{msg_reboot}"
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, final_msg, image_path=final_image)

        except Exception as crash_err:
            print(f"🔥 发生未捕获致命异常: {crash_err}")
            traceback.print_exc()
            crash_screenshot = "crash_exception.png"
            try:
                sb.save_screenshot(crash_screenshot)
                print(f"📸 已强制保存崩溃存证截图: {crash_screenshot}")
            except Exception:
                pass
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, f"🔥 运行崩溃: {crash_err}", image_path=crash_screenshot)
            sys.exit(1)

    print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()
