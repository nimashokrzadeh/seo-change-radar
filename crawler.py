import time
import json
import os
import re
from urllib.parse import urlparse, urljoin, parse_qs, urlencode, urlunparse
import requests
from bs4 import BeautifulSoup
from seo_analyzer import extract_seo_data, extract_links_for_discovery, normalize_url, is_valid_url, parse_robots_txt

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SEO-Radar/2.0"
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 1.0
MAX_CRAWL_PER_RUN = 50

DISCOVERED_URLS_PATH = "data/discovered_urls.json"


def load_discovered_urls():
    if not os.path.exists(DISCOVERED_URLS_PATH):
        return {}
    try:
        with open(DISCOVERED_URLS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_discovered_urls(data):
    os.makedirs(os.path.dirname(DISCOVERED_URLS_PATH), exist_ok=True)
    with open(DISCOVERED_URLS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def crawl_url(url):
    headers = {"User-Agent": USER_AGENT}
    result = {
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "html_size_bytes": None,
        "redirect_url": None,
        "redirect_chain": None,
        "html": None,
        "headers": None,
        "error": None,
    }

    try:
        start_time = time.time()
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        result["status_code"] = response.status_code
        result["response_time_ms"] = elapsed_ms
        result["html_size_bytes"] = len(response.text)
        result["headers"] = dict(response.headers)

        if response.history:
            redirect_urls = [r.url for r in response.history]
            result["redirect_chain"] = " -> ".join(redirect_urls)
            result["redirect_url"] = response.url
        else:
            result["redirect_url"] = None
            result["redirect_chain"] = None

        if response.status_code == 200:
            result["html"] = response.text

    except requests.Timeout:
        result["error"] = "Timeout"
        result["status_code"] = 0
    except requests.ConnectionError:
        result["error"] = "Connection Error"
        result["status_code"] = 0
    except requests.RequestException as e:
        result["error"] = str(e)
        result["status_code"] = 0

    return result


def fetch_robots_txt(domain):
    url = f"https://{domain}/robots.txt"
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        return None
    except requests.RequestException:
        return None


def fetch_sitemap(domain):
    robots_content = fetch_robots_txt(domain)
    robots_data = parse_robots_txt(robots_content)
    sitemap_url = robots_data.get("sitemap_url")

    if not sitemap_url:
        sitemap_url = f"https://{domain}/sitemap.xml"

    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(sitemap_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        return None
    except requests.RequestException:
        return None


def parse_sitemap(xml_content):
    if not xml_content:
        return []

    urls = []
    soup = BeautifulSoup(xml_content, "xml")

    url_tags = soup.find_all("url")
    for url_tag in url_tags:
        loc = url_tag.find("loc")
        if loc:
            urls.append(loc.get_text(strip=True))

    sitemap_tags = soup.find_all("sitemap")
    for sitemap_tag in sitemap_tags:
        loc = sitemap_tag.find("loc")
        if loc:
            urls.append(loc.get_text(strip=True))

    return urls


def normalize_and_filter_url(url, base_domain):
    normalized = normalize_url(url)
    parsed = urlparse(normalized)

    link_domain = parsed.netloc

    base_without_www = base_domain.replace("www.", "")
    link_domain_without_www = link_domain.replace("www.", "")

    if link_domain_without_www != base_without_www:
        return None

    if not is_valid_url(normalized, base_domain):
        return None

    canonical_domain = "www." + base_without_www if not base_domain.startswith("www.") else base_domain
    normalized = f"{parsed.scheme}://{canonical_domain}{parsed.path}"

    clean_url = remove_query_params(normalized)

    return clean_url


def remove_query_params(url):
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    filtered_params = {k: v for k, v in query_params.items()
                       if not k.lower().startswith("utm_")}

    clean_query = urlencode(filtered_params, doseq=True) if filtered_params else ""

    clean_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path.rstrip("/") or "/",
        parsed.params,
        clean_query,
        ""
    ))

    return clean_url


def discover_urls_from_page(url, html, base_domain):
    raw_links = extract_links_for_discovery(html, url)
    valid_links = []

    for link in raw_links:
        normalized = normalize_and_filter_url(link, base_domain)
        if normalized and normalized not in valid_links:
            valid_links.append(normalized)

    return valid_links


def discover_urls_from_sitemap(domain):
    xml_content = fetch_sitemap(domain)
    sitemap_urls = parse_sitemap(xml_content)

    valid_urls = []
    for url in sitemap_urls:
        normalized = normalize_and_filter_url(url, domain)
        if normalized and normalized not in valid_urls:
            valid_urls.append(normalized)

    return valid_urls


def add_discovered_urls(new_urls, domain):
    discovered = load_discovered_urls()

    if domain not in discovered:
        discovered[domain] = {"urls": [], "last_updated": None}

    existing_urls = set(discovered[domain]["urls"])
    added_count = 0

    for url in new_urls:
        if url not in existing_urls:
            discovered[domain]["urls"].append(url)
            existing_urls.add(url)
            added_count += 1

    from datetime import datetime
    discovered[domain]["last_updated"] = datetime.utcnow().isoformat()

    save_discovered_urls(discovered)
    return added_count


def get_discovered_urls_for_domain(domain):
    discovered = load_discovered_urls()
    return discovered.get(domain, {}).get("urls", [])


def crawl_and_discover(seed_urls, max_crawl=MAX_CRAWL_PER_RUN):
    all_results = []
    new_urls_found = []
    domains_crawled = set()

    urls_to_crawl = list(seed_urls[:max_crawl])

    for i, url in enumerate(urls_to_crawl):
        print(f"  [{i+1}/{len(urls_to_crawl)}] Crawling: {url}")

        result = crawl_url(url)
        all_results.append(result)

        parsed = urlparse(url)
        domain = parsed.netloc

        if result["html"] and domain not in domains_crawled:
            domains_crawled.add(domain)

            page_links = discover_urls_from_page(url, result["html"], domain)
            added = add_discovered_urls(page_links, domain)
            if added > 0:
                new_urls_found.extend(page_links[:added])
                print(f"    Found {added} new URLs from page")

        if i < len(urls_to_crawl) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    return all_results, new_urls_found


if __name__ == "__main__":
    print("Testing crawler...")

    result = crawl_url("https://bluvira.com")
    print(f"Status: {result['status_code']}")
    print(f"Response time: {result['response_time_ms']}ms")
    print(f"HTML size: {result['html_size_bytes']} bytes")
    print(f"Redirect: {result['redirect_url']}")

    if result["html"]:
        links = discover_urls_from_page(
            "https://bluvira.com",
            result["html"],
            "bluvira.com"
        )
        print(f"Discovered {len(links)} links")
        for link in links[:5]:
            print(f"  {link}")

    print("Crawler test PASSED")
