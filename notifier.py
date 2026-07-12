import os
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MAX_MESSAGE_LENGTH = 4000


def send_telegram(message, parse_mode="Markdown"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        try:
            print(f"[TELEGRAM] Credentials missing. Message:\n{message}")
        except UnicodeEncodeError:
            print(f"[TELEGRAM] Credentials missing. (message contains unicode, skipped print)")
        return False

    if len(message) > MAX_MESSAGE_LENGTH:
        parts = []
        while len(message) > MAX_MESSAGE_LENGTH:
            split_idx = message.rfind("\n", 0, MAX_MESSAGE_LENGTH)
            if split_idx == -1:
                split_idx = MAX_MESSAGE_LENGTH
            parts.append(message[:split_idx])
            message = message[split_idx:].lstrip("\n")
        parts.append(message)

        for part in parts:
            send_single(part, parse_mode)
        return True

    return send_single(message, parse_mode)


def send_single(message, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True
        else:
            print(f"[TELEGRAM] Error: {response.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM] Connection Error: {e}")
        return False


def alert_seo_changes(url, domain, changes):
    if not changes:
        return

    severity_icons = {
        "critical": "🔴",
        "warning": "🟡",
        "info": "🔵",
    }

    msg = "🚨 *تغییر SEO شناسایی شد!*\n\n"
    msg += f"🌐 *دامنه:* `{domain}`\n"
    msg += f"📄 *آدرس:* `{url}`\n"
    msg += "─" * 30 + "\n\n"

    for change in changes:
        icon = severity_icons.get(change.get("severity", "info"), "🔵")
        category = change.get("category", "عمومی")
        change_type = change.get("type", "")
        old_val = change.get("old_value", "N/A")
        new_val = change.get("new_value", "N/A")

        msg += f"{icon} *[{category}]* {change_type}\n"
        msg += f"   قبل: `{old_val}`\n"
        msg += f"   بعد: `{new_val}`\n\n"

    send_telegram(msg)


def alert_new_urls(urls, count):
    if not urls:
        return

    msg = f"✅ *{count} آدرس جدید کشف شد*\n\n"

    for i, url in enumerate(urls[:20], 1):
        msg += f"{i}. `{url}`\n"

    if count > 20:
        msg += f"\n... و {count - 20} آدرس دیگر"

    send_telegram(msg)


def alert_removed_urls(urls, count):
    if not urls:
        return

    msg = f"❌ *{count} آدرس حذف شد*\n\n"

    for i, url in enumerate(urls[:20], 1):
        msg += f"{i}. `{url}`\n"

    if count > 20:
        msg += f"\n... و {count - 20} آدرس دیگر"

    send_telegram(msg)


def alert_robots_changes(domain, changes):
    if not changes:
        return

    msg = "🤖 *تغییر robots.txt شناسایی شد!*\n\n"
    msg += f"🌐 *دامنه:* `{domain}`\n"
    msg += "─" * 30 + "\n\n"

    for change in changes:
        msg += f"• {change}\n\n"

    send_telegram(msg)


def alert_sitemap_changes(domain, new_urls, removed_urls):
    if not new_urls and not removed_urls:
        return

    msg = "🗺️ *تغییر sitemap.xml شناسایی شد!*\n\n"
    msg += f"🌐 *دامنه:* `{domain}`\n"
    msg += "─" * 30 + "\n\n"

    if new_urls:
        msg += f"✅ *{len(new_urls)} آدرس جدید در sitemap:*\n"
        for url in new_urls[:10]:
            msg += f"   + `{url}`\n"
        if len(new_urls) > 10:
            msg += f"   ... و {len(new_urls) - 10} مورد دیگر\n"

    if removed_urls:
        msg += f"\n❌ *{len(removed_urls)} آدرس حذف شده از sitemap:*\n"
        for url in removed_urls[:10]:
            msg += f"   - `{url}`\n"
        if len(removed_urls) > 10:
            msg += f"   ... و {len(removed_urls) - 10} مورد دیگر\n"

    send_telegram(msg)


def alert_ssl_changes(domain, changes):
    if not changes:
        return

    msg = "🔒 *تغییر SSL شناسایی شد!*\n\n"
    msg += f"🌐 *دامنه:* `{domain}`\n"
    msg += "─" * 30 + "\n\n"

    for change in changes:
        msg += f"• {change}\n"

    send_telegram(msg)


def alert_security_changes(url, domain, changes):
    if not changes:
        return

    msg = "🛡️ *تغییر امنیتی شناسایی شد!*\n\n"
    msg += f"🌐 *دامنه:* `{domain}`\n"
    msg += f"📄 *آدرس:* `{url}`\n"
    msg += "─" * 30 + "\n\n"

    for change in changes:
        msg += f"• {change}\n"

    send_telegram(msg)


def alert_content_change(url, domain, old_hash, new_hash):
    msg = "📝 *تغییر محتوا شناسایی شد!*\n\n"
    msg += f"🌐 *دامنه:* `{domain}`\n"
    msg += f"📄 *آدرس:* `{url}`\n"
    msg += "─" * 30 + "\n\n"
    msg += f"محتوای صفحه تغییر کرده است.\n"
    msg += f"Hash قبل: `{old_hash[:16]}...`\n"
    msg += f"Hash بعد: `{new_hash[:16]}...`"

    send_telegram(msg)


def alert_summary(stats):
    msg = "📊 *گزارش روزانه SEO Radar*\n\n"
    msg += "─" * 30 + "\n\n"
    msg += f"🔗 *کل URLهای فعال:* {stats.get('total_urls', 0)}\n"
    msg += f"🔍 *کل کراول‌ها:* {stats.get('total_crawls', 0)}\n"
    msg += f"📝 *کل تغییرات:* {stats.get('total_changes', 0)}\n"
    msg += f"⏰ *تغییرات ۲۴ ساعت اخیر:* {stats.get('changes_last_24h', 0)}\n"

    send_telegram(msg)


def alert_error(error_msg):
    msg = "⚠️ *خطا در اجرای SEO Radar*\n\n"
    msg += f"```\n{error_msg}\n```"
    send_telegram(msg)


if __name__ == "__main__":
    print("Testing notifier...")
    print(f"Bot Token: {'Set' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    print(f"Chat ID: {'Set' if TELEGRAM_CHAT_ID else 'NOT SET'}")
    print("Notifier module loaded successfully.")
