import json
import os
import sys
from urllib.parse import urlparse
from datetime import datetime, timezone

from database import (
    init_db, get_or_create_url, update_url_crawl, add_crawl,
    add_seo_data, add_security_headers, add_change,
    add_robots_snapshot, add_ssl_info, get_url_id,
    get_latest_seo_data, get_latest_robots, get_urls_to_crawl,
    get_stats
)
from crawler import (
    crawl_url, fetch_robots_txt, discover_urls_from_sitemap,
    add_discovered_urls, get_discovered_urls_for_domain,
    crawl_and_discover, MAX_CRAWL_PER_RUN
)
from seo_analyzer import (
    extract_seo_data, compare_seo_data, compare_crawl_data,
    compare_security_headers, parse_robots_txt, compare_robots
)
from notifier import (
    alert_seo_changes, alert_new_urls, alert_robots_changes,
    alert_sitemap_changes, alert_summary, alert_error
)

SEED_CONFIG_PATH = "config/seed_urls.json"


def load_seed_urls():
    if not os.path.exists(SEED_CONFIG_PATH):
        print(f"Error: Seed config not found at {SEED_CONFIG_PATH}")
        sys.exit(1)
    with open(SEED_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("urls", [])


def process_crawl_result(url, result):
    domain = urlparse(url).netloc

    url_id = get_or_create_url(url, domain)

    old_seo_data = get_latest_seo_data(url_id)

    crawl_id = add_crawl(
        url_id=url_id,
        status_code=result["status_code"],
        response_time_ms=result["response_time_ms"],
        html_size_bytes=result["html_size_bytes"],
        redirect_url=result.get("redirect_url"),
        redirect_chain=result.get("redirect_chain")
    )

    new_seo_data = None
    if result["html"] and result["status_code"] == 200:
        new_seo_data = extract_seo_data(result["html"], url, result["headers"])

        add_seo_data(crawl_id, new_seo_data)

        security_headers = {
            "hsts": new_seo_data.get("hsts"),
            "csp": new_seo_data.get("csp"),
            "x_frame_options": new_seo_data.get("x_frame_options"),
            "x_content_type_options": new_seo_data.get("x_content_type_options"),
        }
        add_security_headers(crawl_id, security_headers)

    update_url_crawl(url_id)

    if old_seo_data:
        crawl_changes = compare_crawl_data(old_seo_data, {
            "status_code": result["status_code"],
            "redirect_url": result.get("redirect_url"),
        })
        if crawl_changes:
            alert_seo_changes(url, domain, crawl_changes)
            for change in crawl_changes:
                add_change(url_id, change["type"], change["category"],
                          change.get("old_value"), change.get("new_value"),
                          change.get("severity", "info"))

        if new_seo_data:
            seo_changes = compare_seo_data(old_seo_data, new_seo_data)
            if seo_changes:
                alert_seo_changes(url, domain, seo_changes)
                for change in seo_changes:
                    add_change(url_id, change["type"], change["category"],
                              change.get("old_value"), change.get("new_value"),
                              change.get("severity", "info"))

            old_security = {
                "hsts": old_seo_data.get("hsts"),
                "csp": old_seo_data.get("csp"),
                "x_frame_options": old_seo_data.get("x_frame_options"),
                "x_content_type_options": old_seo_data.get("x_content_type_options"),
            }
            sec_changes = compare_security_headers(old_security, {
                "hsts": new_seo_data.get("hsts"),
                "csp": new_seo_data.get("csp"),
                "x_frame_options": new_seo_data.get("x_frame_options"),
                "x_content_type_options": new_seo_data.get("x_content_type_options"),
            })
            if sec_changes:
                alert_seo_changes(url, domain, sec_changes)
                for change in sec_changes:
                    add_change(url_id, change["type"], change["category"],
                              change.get("old_value"), change.get("new_value"),
                              change.get("severity", "info"))

            if old_seo_data.get("content_hash") and new_seo_data.get("content_hash"):
                if old_seo_data["content_hash"] != new_seo_data["content_hash"]:
                    from notifier import alert_content_change
                    alert_content_change(url, domain,
                                        old_seo_data["content_hash"],
                                        new_seo_data["content_hash"])
                    add_change(url_id, "محتوای صفحه تغییر کرد", "Content",
                              old_seo_data["content_hash"][:16],
                              new_seo_data["content_hash"][:16], "info")
    else:
        print(f"  First time crawling {url}. Baseline saved.")

    return url_id


def process_robots(domain):
    old_robots = get_latest_robots(domain)

    robots_content = fetch_robots_txt(domain)
    new_robots = parse_robots_txt(robots_content)

    add_robots_snapshot(domain, robots_content,
                       new_robots["disallow_count"],
                       new_robots.get("sitemap_url"))

    if old_robots:
        old_robots_data = parse_robots_txt(old_robots.get("content"))
        robot_changes = compare_robots(old_robots_data, new_robots)
        if robot_changes:
            alert_robots_changes(domain, robot_changes)
            url_id = get_or_create_url(f"https://{domain}/robots.txt", domain)
            for change in robot_changes:
                add_change(url_id, "robots.txt تغییر کرد", "Robots",
                          str(old_robots_data), str(new_robots), "warning")
    else:
        print(f"  First time monitoring robots.txt for {domain}")

    return new_robots.get("sitemap_url")


def process_sitemap(domain, sitemap_url):
    sitemap_urls = discover_urls_from_sitemap(domain)
    added = add_discovered_urls(sitemap_urls, domain)

    if added > 0:
        print(f"  Found {added} new URLs from sitemap for {domain}")

    return sitemap_urls


def main():
    print("=" * 60)
    print(f"SEO Change Radar - {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    init_db()

    seed_urls = load_seed_urls()
    print(f"\nLoaded {len(seed_urls)} seed URLs")

    all_urls = list(seed_urls)
    for domain in set(urlparse(u).netloc for u in seed_urls):
        discovered = get_discovered_urls_for_domain(domain)
        all_urls.extend(discovered)

    all_urls = list(set(all_urls))
    print(f"Total URLs to crawl: {len(all_urls)}")

    crawl_limit = min(MAX_CRAWL_PER_RUN, len(all_urls))
    urls_to_crawl = all_urls[:crawl_limit]

    print(f"\nCrawling {crawl_limit} URLs (max per run: {MAX_CRAWL_PER_RUN})")

    all_new_urls = []
    domains_to_check = set()

    for i, url in enumerate(urls_to_crawl):
        print(f"\n[{i+1}/{crawl_limit}] Processing: {url}")

        result = crawl_url(url)

        if result["error"]:
            print(f"  Error: {result['error']}")
            continue

        process_crawl_result(url, result)

        domain = urlparse(url).netloc
        domains_to_check.add(domain)

        if result["html"] and result["status_code"] == 200:
            from crawler import discover_urls_from_page
            page_links = discover_urls_from_page(url, result["html"], domain)
            added = add_discovered_urls(page_links, domain)
            if added > 0:
                all_new_urls.extend(page_links[:added])
                print(f"  Discovered {added} new URLs from page")

        import time
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("Processing robots.txt and sitemaps...")
    print("=" * 60)

    for domain in domains_to_check:
        print(f"\nChecking {domain}...")
        sitemap_url = process_robots(domain)
        if sitemap_url:
            process_sitemap(domain, sitemap_url)

    if all_new_urls:
        alert_new_urls(all_new_urls, len(all_new_urls))

    stats = get_stats()
    alert_summary(stats)

    print("\n" + "=" * 60)
    print("Execution Summary")
    print("=" * 60)
    print(f"Total URLs crawled: {crawl_limit}")
    print(f"New URLs discovered: {len(all_new_urls)}")
    print(f"Domains checked: {len(domains_to_check)}")
    print(f"Stats: {stats}")
    print("=" * 60)
    print("SEO Radar execution finished successfully.")


if __name__ == "__main__":
    main()
