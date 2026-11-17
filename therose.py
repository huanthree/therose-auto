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
SERVER_URL = (os.environ.get("SERVER_URL") or "https://therose.cloud/dashboard").strip()
BASE_URL = "https://therose.cloud/login"
DASHBOARD_URL = "https://therose.cloud/dashboard"

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
    print("⚠️ 达到最大等待时间，Turnstile Token 仍未检测到，尝试继续提交")
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


def click_renew_or_restore(sb):
    print("🔍 正在 Dashboard 页面寻找【Renew / Restore】按钮...")
    if "/dashboard" not in sb.get_current_url():
        sb.open(DASHBOARD_URL)
        sb.wait_for_ready_state_complete()
        time.sleep(3)

    # 1. 常规 SeleniumBase 选择器匹配新版按钮
    selectors = [
        'button:contains("Renew and restore")',
        'a:contains("Renew and restore")',
        'button:contains("Renew for another")',
        'a:contains("Renew for another")',
        'button:contains("Renew")',
        'a:contains("Renew")',
        'span:contains("Renew")',
        'button:contains("Extend")',
        'span:contains("Extend")'
    ]

    for sel in selectors:
        try:
            if sb.is_element_visible(sel):
                btn_text = sb.get_text(sel).strip()
                print(f"✅ 找到续期/恢复按钮: [{btn_text}] (选择器: {sel})")
                sb.uc_click(sel, timeout=5)
                return True, btn_text
        except Exception:
            continue

    # 2. JavaScript 深度遍历匹配（应对特殊自定义标签或嵌套结构）
    try:
        clicked_text = sb.driver.execute_script("""
            const elements = Array.from(document.querySelectorAll('button, a, div[role="button"], span'));
            for (let el of elements) {
                let text = (el.innerText || el.textContent || "").trim();
                if ((text.includes('Renew and restore') || text.includes('Renew for another') || text.startsWith('↻ Renew') || text === 'Renew' || text.includes('Extend')) && el.offsetParent !== null) {
                    if (!el.disabled) {
                        el.click();
                        return text;
                    }
                }
            }
            return null;
        """)
        if clicked_text:
            print(f"✅ 通过 JavaScript 成功点击按钮: [{clicked_text}]")
            return True, clicked_text
    except Exception as e:
        print(f"⚠️ JS 搜索 Renew 按钮异常: {e}")

    return False, "未找到可用的 Renew / Restore 按钮（可能尚未到续期开放时间）"


def try_click_start_on_current_page(sb):
    print("🔍 正在当前页面寻找并点击【Start / 启动】按钮...")
    start_selectors = [
        'button:contains("Start")',
        'a:contains("Start")',
        'button:contains("启动")',
        'button[data-action="start"]',
        'button[title*="Start" i]',
        'button i.fa-play',
        'button svg.fa-play'
    ]

    for sel in start_selectors:
        try:
            if sb.is_element_visible(sel) and sb.is_element_enabled(sel):
                btn_text = sb.get_text(sel).strip() or "Start"
                print(f"✅ 找到可用【Start】按钮: [{btn_text}] (选择器: {sel})")
                sb.uc_click(sel)
                time.sleep(3)
                return True, f"已点击 [{btn_text}] 按钮"
        except Exception:
            continue

    # JS 深度查找 Start 按钮（包括带播放图标的按钮或包含 Start 文本的按钮）
    try:
        js_clicked = sb.driver.execute_script("""
            const candidates = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
            for (let btn of candidates) {
                if (btn.offsetParent === null || btn.disabled) continue;
                let text = (btn.innerText || btn.textContent || "").trim();
                let title = (btn.getAttribute('title') || btn.getAttribute('aria-label') || "").trim();
                let html = btn.innerHTML || "";
                if (
                    text === 'Start' ||
                    text.includes('Start server') ||
                    text.includes('启动') ||
                    title.toLowerCase().includes('start') ||
                    btn.getAttribute('data-action') === 'start' ||
                    html.includes('fa-play')
                ) {
                    btn.click();
                    return text || title || 'Start(图标按钮)';
                }
            }
            return null;
        """)
        if js_clicked:
            print(f"✅ 通过 JavaScript 成功点击了【{js_clicked}】按钮")
            time.sleep(3)
            return True, f"已通过 JS 点击 [{js_clicked}]"
    except Exception as e:
        print(f"⚠️ JS 查找 Start 按钮异常: {e}")

    return False, "当前页面未检测到可用的 Start 按钮"


def start_or_reboot_server(sb, url):
    print("🔄 步骤 1: 先在当前 Dashboard 页面检查并尝试点击 Start 按钮...")
    ok_dash, msg_dash = try_click_start_on_current_page(sb)
    if ok_dash:
        return True, f"在 Dashboard 页面直接启动成功 ({msg_dash})"

    # 如果 Dashboard 上点击了服务器卡片能进入详情页，或者用户配置了独立的 SERVER_URL
    print("🔄 步骤 2: 尝试进入服务器详情页/控制面板启动服务器...")
    try:
        # 尝试在 Dashboard 点击服务器卡片标题（如 linglong 或 #96ac0384）进入内页
        entered_detail = sb.driver.execute_script("""
            const links = Array.from(document.querySelectorAll('a'));
            for (let a of links) {
                let href = a.getAttribute('href') || "";
                if (href.includes('/server') || href.includes('/panel')) {
                    a.click();
                    return href;
                }
            }
            return null;
        """)
        if entered_detail:
            print(f"🔀 已通过卡片链接进入详情页: {entered_detail}")
            time.sleep(5)
            ok_detail, msg_detail = try_click_start_on_current_page(sb)
            if ok_detail:
                return True, f"在服务器详情页启动成功 ({msg_detail})"

        # 如果配置了非 dashboard 的独立 SERVER_URL，则打开该地址尝试启动
        if url and "therose.cloud/dashboard" not in url:
            print(f"🌐 打开独立面板地址: {url}")
            sb.open(url)
            sb.wait_for_ready_state_complete()
            time.sleep(5)

            if sb.is_element_visible('input[type="password"]'):
                print("🔒 检测到控制面板需要独立登录，正在自动输入账号密码...")
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
                time.sleep(6)

            ok_panel, msg_panel = try_click_start_on_current_page(sb)
            if ok_panel:
                return True, f"在独立控制面板启动成功 ({msg_panel})"

        return False, "Dashboard 与面板内均未检测到可用的 Start 按钮（服务器可能已在运行中）"

    except Exception as e:
        return False, f"启动维护操作发生异常: {e}"


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

            print("📄 开始续期 / 恢复挂起流程...")
            ok_renew, renew_info = click_renew_or_restore(sb)

            if ok_renew:
                print(f"⏳ 已点击 [{renew_info}]，等待 6 秒让状态刷新...")
                time.sleep(6)

                # 检查点击 Renew 后是否弹出了需要二次确认的弹窗或验证码
                try:
                    if sb.is_element_visible('button:contains("Confirm")'):
                        sb.uc_click('button:contains("Confirm")')
                        time.sleep(4)
                    elif sb.is_element_visible('button:contains("Order now")'):
                        sb.uc_click('button:contains("Order now")')
                        time.sleep(4)
                except Exception:
                    pass

                sb.save_screenshot("renewal_success.png")
                msg_renewal = f"✅ 成功触发续期/恢复按钮: [{renew_info}]"
            else:
                msg_renewal = f"⏳ 本次未触发续期: {renew_info}"
            print(msg_renewal)

            print("🔄 开始检查并执行服务器 Start 启动维护...")
            reboot_ok, reboot_msg = start_or_reboot_server(sb, SERVER_URL)

            if reboot_ok:
                msg_reboot = f"✅ 自动启动成功: {reboot_msg}"
            else:
                msg_reboot = f"ℹ️ 启动状态说明: {reboot_msg}"
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
