import json
import os
import sys
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

CONFIG_PATH = "config/urls.json"
STATE_PATH = "data/state.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Config file not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("urls", [])


def load_state():
    if not os.path.exists(STATE_PATH):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_state(state_data):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state_data, f, ensure_ascii=False, indent=2)


def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"Telegram credentials missing. Alert payload:\n{message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Failed to send Telegram alert: {response.text}")
        else:
            print("Telegram alert sent successfully.")
    except Exception as e:
        print(f"Telegram API Connection Error: {e}")


def fetch_and_extract_seo(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SEO-Radar/1.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        status_code = response.status_code
        x_robots_tag = response.headers.get("X-Robots-Tag", "Not Found")

        canonical = "Not Found"
        meta_robots = "index, follow"

        if status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            canonical_tag = soup.find("link", rel="canonical")
            if canonical_tag and canonical_tag.get("href"):
                canonical = canonical_tag["href"].strip()

            robots_tag = soup.find("meta", attrs={"name": "robots"})
            if robots_tag and robots_tag.get("content"):
                meta_robots = robots_tag["content"].lower().strip()

        return {
            "status_code": status_code,
            "canonical": canonical,
            "meta_robots": meta_robots,
            "x_robots_tag": x_robots_tag,
        }

    except requests.RequestException as e:
        return {
            "status_code": "CRASHED/TIMEOUT",
            "canonical": "N/A",
            "meta_robots": "N/A",
            "x_robots_tag": "N/A",
            "error_msg": str(e),
        }


def fetch_robots_txt(domain):
    url = f"https://{domain}/robots.txt"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SEO-Radar/1.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        return None
    except requests.RequestException:
        return None


def parse_robots_txt(content):
    if not content:
        return {"raw": None, "disallow_all": False, "sitemap": None, "lines": []}

    lines = content.strip().split("\n")
    disallow_lines = [l.strip() for l in lines if l.strip().lower().startswith("disallow")]
    sitemap = None
    for line in lines:
        if line.strip().lower().startswith("sitemap:"):
            sitemap = line.split(":", 1)[1].strip()

    return {
        "raw": content,
        "disallow_all": any("Disallow: /" in l and len(l.split(":", 1)[1].strip()) == 0 for l in disallow_lines),
        "sitemap": sitemap,
        "lines": lines,
    }


def analyze_robots_changes(old_domain, new_content):
    old_data = parse_robots_txt(old_content_map.get(old_domain))
    new_data = parse_robots_txt(new_content)
    changes = []

    old_lines = set(l.strip().lower() for l in old_data["lines"] if l.strip())
    new_lines = set(l.strip().lower() for l in new_data["lines"] if l.strip())

    added = new_lines - old_lines
    removed = old_lines - new_lines

    if old_data.get("sitemap") != new_data.get("sitemap"):
        changes.append(
            f"🗺️ *Sitemap:* Changed from\n`{old_data.get('sitemap')}`\nto\n`{new_data.get('sitemap')}`"
        )

    if old_data.get("disallow_all") != new_data.get("disallow_all"):
        if new_data.get("disallow_all"):
            changes.append("🚨 *CRITICAL:* robots.txt now Disallows ALL crawlers!")
        else:
            changes.append("✅ *robots.txt:* Disallow All removed")

    disallow_added = [l for l in added if "disallow" in l]
    disallow_removed = [l for l in removed if "disallow" in l]

    if disallow_added:
        changes.append(f"🚫 *New Disallow rules added:*\n" + "\n".join(f"`{l}`" for l in disallow_added))

    if disallow_removed:
        changes.append(f"✅ *Disallow rules removed:*\n" + "\n".join(f"`{l}`" for l in disallow_removed))

    if not old_data.get("raw") and new_data.get("raw"):
        changes.append("📄 *robots.txt* file appeared (was missing before)")

    if old_data.get("raw") and not new_data.get("raw"):
        changes.append("🚨 *robots.txt* file REMOVED!")

    return changes


old_content_map = {}


def analyze_changes(url, old_data, new_data):
    changes = []

    if old_data.get("status_code") != new_data.get("status_code"):
        changes.append(
            f"❌ *Status Code:* `{old_data.get('status_code')}` → `{new_data.get('status_code')}`"
        )

    if old_data.get("canonical") != new_data.get("canonical"):
        changes.append(
            f"🔗 *Canonical:* `{old_data.get('canonical')}` → `{new_data.get('canonical')}`"
        )

    if old_data.get("meta_robots") != new_data.get("meta_robots"):
        changes.append(
            f"🤖 *Meta Robots:* `{old_data.get('meta_robots')}` → `{new_data.get('meta_robots')}`"
        )
        if "noindex" in new_data.get("meta_robots", ""):
            changes.append("⚠️ *WARNING:* Page is now *NOINDEX*!")

    if old_data.get("x_robots_tag") != new_data.get("x_robots_tag"):
        changes.append(
            f"📡 *X-Robots-Tag:* `{old_data.get('x_robots_tag')}` → `{new_data.get('x_robots_tag')}`"
        )

    return changes


def main():
    global old_content_map

    urls = load_config()
    current_state = load_state()
    new_state = {}
    old_content_map = current_state.get("_robots_txt", {})

    print(f"Starting SEO Radar for {len(urls)} URLs...")

    domains_to_check = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.hostname:
            domains_to_check.add(parsed.hostname)

    new_robots_txt = {}

    for domain in domains_to_check:
        print(f"Checking robots.txt for: {domain}")
        robots_content = fetch_robots_txt(domain)
        new_robots_txt[domain] = robots_content

        if domain in old_content_map:
            robot_changes = analyze_robots_changes(domain, robots_content)
            if robot_changes:
                alert_msg = f"🚨 *robots.txt Change Detected!*\n\n"
                alert_msg += f"🌐 *Domain:* {domain}\n"
                alert_msg += f"📄 *File:* https://{domain}/robots.txt\n\n"
                alert_msg += "\n".join(robot_changes)
                send_telegram_alert(alert_msg)
        else:
            print(f"First time monitoring robots.txt for {domain}. Baseline saved.")

    for url in urls:
        print(f"Crawling: {url}")
        new_data = fetch_and_extract_seo(url)
        new_state[url] = new_data

        if url in current_state:
            old_data = current_state[url]
            detected_changes = analyze_changes(url, old_data, new_data)

            if detected_changes:
                domain = urlparse(url).netloc
                alert_msg = f"🚨 *SEO Change Detected!*\n\n"
                alert_msg += f"🌐 *Domain:* {domain}\n"
                alert_msg += f"📄 *URL:* {url}\n\n"
                alert_msg += "\n".join(detected_changes)
                send_telegram_alert(alert_msg)
        else:
            print(f"First time monitoring for {url}. Baseline saved.")

    new_state["_robots_txt"] = new_robots_txt
    save_state(new_state)
    print("SEO Radar execution finished successfully.")


if __name__ == "__main__":
    main()
