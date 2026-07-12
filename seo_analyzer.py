import hashlib
import json
import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


def extract_seo_data(html, url, response_headers=None):
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    parsed_url = urlparse(url)
    base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

    data = {}

    data.update(_extract_technical_seo(soup, url, response_headers))
    data.update(_extract_on_page_seo(soup, url, base_domain))
    data.update(_extract_internal_linking(soup, url, base_domain))
    data.update(_extract_content_hash(html))
    data.update(_extract_security_headers(response_headers))

    return data


def _extract_technical_seo(soup, url, headers):
    data = {}

    canonical_tag = soup.find("link", rel="canonical")
    data["canonical"] = canonical_tag["href"].strip() if canonical_tag and canonical_tag.get("href") else None

    robots_tag = soup.find("meta", attrs={"name": "robots"})
    data["meta_robots"] = robots_tag["content"].lower().strip() if robots_tag and robots_tag.get("content") else "index, follow"

    data["x_robots_tag"] = (headers or {}).get("X-Robots-Tag", None)

    return data


def _extract_on_page_seo(soup, url, base_domain):
    data = {}

    title_tag = soup.find("title")
    data["title"] = title_tag.get_text(strip=True) if title_tag else None

    meta_desc = soup.find("meta", attrs={"name": "description"})
    data["meta_description"] = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else None

    h1_tags = soup.find_all("h1")
    data["h1_count"] = len(h1_tags)
    data["h1_text"] = " | ".join([h.get_text(strip=True) for h in h1_tags[:5]]) if h1_tags else None

    h2_tags = soup.find_all("h2")
    data["h2_count"] = len(h2_tags)

    images = soup.find_all("img")
    data["image_count"] = len(images)
    data["images_without_alt"] = len([img for img in images if not img.get("alt", "").strip()])

    og_title = soup.find("meta", property="og:title")
    data["og_title"] = og_title["content"].strip() if og_title and og_title.get("content") else None

    og_desc = soup.find("meta", property="og:description")
    data["og_description"] = og_desc["content"].strip() if og_desc and og_desc.get("content") else None

    og_image = soup.find("meta", property="og:image")
    data["og_image"] = og_image["content"].strip() if og_image and og_image.get("content") else None

    twitter_card = soup.find("meta", attrs={"name": "twitter:card"})
    data["twitter_card"] = twitter_card["content"].strip() if twitter_card and twitter_card.get("content") else None

    jsonld_scripts = soup.find_all("script", type="application/ld+json")
    if jsonld_scripts:
        schemas = []
        for script in jsonld_scripts:
            try:
                schema_data = json.loads(script.string)
                if isinstance(schema_data, dict):
                    schemas.append(schema_data.get("@type", "Unknown"))
                elif isinstance(schema_data, list):
                    for item in schema_data:
                        if isinstance(item, dict):
                            schemas.append(item.get("@type", "Unknown"))
            except (json.JSONDecodeError, TypeError):
                pass
        data["jsonld_schema"] = json.dumps(schemas) if schemas else None
        data["schema_type"] = ", ".join(set(schemas)) if schemas else None
    else:
        data["jsonld_schema"] = None
        data["schema_type"] = None

    hreflang_tags = soup.find_all("link", rel="alternate", hreflang=True)
    if hreflang_tags:
        hreflang_map = {}
        for tag in hreflang_tags:
            lang = tag.get("hreflang", "")
            href = tag.get("href", "")
            if lang and href:
                hreflang_map[lang] = href
        data["hreflang"] = json.dumps(hreflang_map)
    else:
        data["hreflang"] = None

    return data


def _extract_internal_linking(soup, url, base_domain):
    data = {}

    parsed_url = urlparse(url)
    base_domain_parsed = urlparse(base_domain)
    base_domain_name = base_domain_parsed.netloc

    links = soup.find_all("a", href=True)
    internal_links = 0
    external_links = 0
    broken_links = 0

    for link in links:
        href = link["href"]

        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        if href.startswith("/"):
            internal_links += 1
            continue

        if href.startswith("http"):
            link_domain = urlparse(href).netloc
            if link_domain == base_domain_name:
                internal_links += 1
            else:
                external_links += 1
        else:
            internal_links += 1

    data["internal_links"] = internal_links
    data["external_links"] = external_links
    data["broken_links"] = broken_links

    return data


def _extract_content_hash(html):
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"content_hash": content_hash}


def _extract_security_headers(headers):
    if not headers:
        return {
            "hsts": None,
            "csp": None,
            "x_frame_options": None,
            "x_content_type_options": None,
        }

    return {
        "hsts": headers.get("Strict-Transport-Security", None),
        "csp": headers.get("Content-Security-Policy", None),
        "x_frame_options": headers.get("X-Frame-Options", None),
        "x_content_type_options": headers.get("X-Content-Type-Options", None),
    }


def compare_seo_data(old_data, new_data):
    changes = []
    if not old_data or not new_data:
        return changes

    mappings = [
        ("canonical", "Technical", "info"),
        ("meta_robots", "Technical", "warning"),
        ("x_robots_tag", "Technical", "info"),
        ("title", "On-Page", "info"),
        ("meta_description", "On-Page", "info"),
        ("h1_count", "On-Page", "warning"),
        ("h1_text", "On-Page", "info"),
        ("h2_count", "On-Page", "info"),
        ("og_title", "On-Page", "info"),
        ("og_description", "On-Page", "info"),
        ("og_image", "On-Page", "info"),
        ("twitter_card", "On-Page", "info"),
        ("schema_type", "Technical", "info"),
        ("hreflang", "Technical", "info"),
    ]

    for field, category, severity in mappings:
        old_val = old_data.get(field)
        new_val = new_data.get(field)

        if old_val != new_val:
            if old_val is None and new_val is not None:
                change_type = f"{field} اضافه شد"
                severity = "info"
            elif old_val is not None and new_val is None:
                change_type = f"{field} حذف شد"
                severity = "warning"
            else:
                change_type = f"{field} تغییر کرد"

            changes.append({
                "type": change_type,
                "category": category,
                "old_value": str(old_val) if old_val else "N/A",
                "new_value": str(new_val) if new_val else "N/A",
                "severity": severity,
            })

    if old_data.get("content_hash") and new_data.get("content_hash"):
        if old_data["content_hash"] != new_data["content_hash"]:
            changes.append({
                "type": "محتوای صفحه تغییر کرد",
                "category": "Content",
                "old_value": old_data["content_hash"][:16] + "...",
                "new_value": new_data["content_hash"][:16] + "...",
                "severity": "info",
            })

    old_internal = old_data.get("internal_links", 0)
    new_internal = new_data.get("internal_links", 0)
    if abs(old_internal - new_internal) > 2:
        changes.append({
            "type": f"تعداد لینک‌های داخلی تغییر کرد",
            "category": "Internal Linking",
            "old_value": str(old_internal),
            "old_value": str(old_internal),
            "new_value": str(new_internal),
            "severity": "info",
        })

    old_external = old_data.get("external_links", 0)
    new_external = new_data.get("external_links", 0)
    if abs(old_external - new_external) > 2:
        changes.append({
            "type": f"تعداد لینک‌های خارجی تغییر کرد",
            "category": "Internal Linking",
            "old_value": str(old_external),
            "new_value": str(new_external),
            "severity": "info",
        })

    return changes


def compare_crawl_data(old_data, new_data):
    changes = []
    if not old_data or not new_data:
        return changes

    if old_data.get("status_code") != new_data.get("status_code"):
        changes.append({
            "type": "Status Code تغییر کرد",
            "category": "Technical",
            "old_value": str(old_data.get("status_code")),
            "new_value": str(new_data.get("status_code")),
            "severity": "critical" if new_data.get("status_code") not in [200, 301, 302] else "warning",
        })

    if old_data.get("redirect_url") != new_data.get("redirect_url"):
        changes.append({
            "type": "Redirect تغییر کرد",
            "category": "Technical",
            "old_value": str(old_data.get("redirect_url", "None")),
            "new_value": str(new_data.get("redirect_url", "None")),
            "severity": "warning",
        })

    return changes


def compare_security_headers(old_data, new_data):
    changes = []
    if not old_data or not new_data:
        return changes

    fields = ["hsts", "csp", "x_frame_options", "x_content_type_options"]
    for field in fields:
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        if old_val != new_val:
            if old_val is None and new_val is not None:
                change_type = f"{field} اضافه شد"
            elif old_val is not None and new_val is None:
                change_type = f"{field} حذف شد"
            else:
                change_type = f"{field} تغییر کرد"

            changes.append({
                "type": change_type,
                "category": "Security",
                "old_value": str(old_val) if old_val else "N/A",
                "new_value": str(new_val) if new_val else "N/A",
                "severity": "warning",
            })

    return changes


def parse_robots_txt(content):
    if not content:
        return {"raw": None, "disallow_count": 0, "sitemap_url": None, "disallow_rules": []}

    lines = content.strip().split("\n")
    disallow_rules = []
    sitemap_url = None

    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("disallow:"):
            rule = stripped.split(":", 1)[1].strip()
            if rule:
                disallow_rules.append(rule)
        elif stripped.lower().startswith("sitemap:"):
            sitemap_url = stripped.split(":", 1)[1].strip()

    return {
        "raw": content,
        "disallow_count": len(disallow_rules),
        "sitemap_url": sitemap_url,
        "disallow_rules": disallow_rules,
    }


def compare_robots(old_data, new_data):
    changes = []
    if not old_data or not new_data:
        return changes

    old_rules = set(old_data.get("disallow_rules", []))
    new_rules = set(new_data.get("disallow_rules", []))

    added = new_rules - old_rules
    removed = old_rules - new_rules

    if added:
        changes.append(f"🚫 قوانین Disallow جدید اضافه شد:\n" + "\n".join(f"  + `{r}`" for r in added))

    if removed:
        changes.append(f"✅ قوانین Disallow حذف شد:\n" + "\n".join(f"  - `{r}`" for r in removed))

    if old_data.get("sitemap_url") != new_data.get("sitemap_url"):
        changes.append(f"🗺️ Sitemap تغییر کرد:\n  قبل: `{old_data.get('sitemap_url')}`\n  بعد: `{new_data.get('sitemap_url')}`")

    if not old_data.get("raw") and new_data.get("raw"):
        changes.append("📄 فایل robots.txt ایجاد شد (قبلاً وجود نداشت)")

    if old_data.get("raw") and not new_data.get("raw"):
        changes.append("🚨 فایل robots.txt حذف شد!")

    return changes


def extract_links_for_discovery(html, url):
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc

    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()

        if not href or href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        if href.startswith("/"):
            full_url = f"{parsed_url.scheme}://{base_domain}{href}"
        elif href.startswith("http"):
            full_url = href
        else:
            full_url = urljoin(url, href)

        links.append(full_url)

    return list(set(links))


FILTERED_EXTENSIONS = {'.pdf', '.zip', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.mp4', '.mp3', '.avi', '.mov', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.css', '.js'}

FILTERED_PATHS = {'/login', '/admin', '/cart', '/checkout', '/search', '/tag', '/tags', '/archive', '/wp-admin', '/wp-login', '/wp-content', '/api', '/feed', '/rss'}


def normalize_url(url):
    parsed = urlparse(url)

    path = parsed.path.rstrip("/")
    if not path:
        path = "/"

    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"

    return normalized


def is_valid_url(url, base_domain):
    try:
        parsed = urlparse(url)

        if not parsed.scheme in ("http", "https"):
            return False

        if parsed.netloc:
            link_domain = parsed.netloc
            base_without_www = base_domain.replace("www.", "")
            link_without_www = link_domain.replace("www.", "")
            if link_without_www != base_without_www:
                return False

        path_lower = parsed.path.lower()
        for ext in FILTERED_EXTENSIONS:
            if path_lower.endswith(ext):
                return False

        for filtered_path in FILTERED_PATHS:
            if path_lower.startswith(filtered_path):
                return False

        return True
    except Exception:
        return False
