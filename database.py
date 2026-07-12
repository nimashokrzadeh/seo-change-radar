import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = "data/radar.db"


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            domain TEXT NOT NULL,
            discovered_date TEXT NOT NULL,
            last_crawled TEXT,
            crawl_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crawls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_id INTEGER NOT NULL,
            crawl_date TEXT NOT NULL,
            status_code INTEGER,
            response_time_ms INTEGER,
            html_size_bytes INTEGER,
            redirect_url TEXT,
            redirect_chain TEXT,
            FOREIGN KEY (url_id) REFERENCES urls(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seo_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_id INTEGER NOT NULL,
            canonical TEXT,
            meta_robots TEXT,
            x_robots_tag TEXT,
            title TEXT,
            meta_description TEXT,
            h1_count INTEGER DEFAULT 0,
            h1_text TEXT,
            h2_count INTEGER DEFAULT 0,
            image_count INTEGER DEFAULT 0,
            images_without_alt INTEGER DEFAULT 0,
            internal_links INTEGER DEFAULT 0,
            external_links INTEGER DEFAULT 0,
            broken_links INTEGER DEFAULT 0,
            og_title TEXT,
            og_description TEXT,
            og_image TEXT,
            twitter_card TEXT,
            jsonld_schema TEXT,
            schema_type TEXT,
            hreflang TEXT,
            content_hash TEXT,
            FOREIGN KEY (crawl_id) REFERENCES crawls(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_id INTEGER NOT NULL,
            change_date TEXT NOT NULL,
            change_type TEXT NOT NULL,
            category TEXT,
            old_value TEXT,
            new_value TEXT,
            severity TEXT DEFAULT 'info',
            FOREIGN KEY (url_id) REFERENCES urls(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS robots_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            crawl_date TEXT NOT NULL,
            content TEXT,
            disallow_count INTEGER DEFAULT 0,
            sitemap_url TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS security_headers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_id INTEGER NOT NULL,
            hsts TEXT,
            csp TEXT,
            x_frame_options TEXT,
            x_content_type_options TEXT,
            strict_transport_security TEXT,
            FOREIGN KEY (crawl_id) REFERENCES crawls(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ssl_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            check_date TEXT NOT NULL,
            issuer TEXT,
            expiry_date TEXT,
            days_until_expiry INTEGER,
            serial_number TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def get_or_create_url(url, domain):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("SELECT id FROM urls WHERE url = ?", (url,))
    row = cursor.fetchone()

    if row:
        url_id = row["id"]
    else:
        cursor.execute(
            "INSERT INTO urls (url, domain, discovered_date) VALUES (?, ?, ?)",
            (url, domain, now)
        )
        url_id = cursor.lastrowid
        conn.commit()

    conn.close()
    return url_id


def update_url_crawl(url_id):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE urls SET last_crawled = ?, crawl_count = crawl_count + 1 WHERE id = ?",
        (now, url_id)
    )
    conn.commit()
    conn.close()


def add_crawl(url_id, status_code, response_time_ms, html_size_bytes,
              redirect_url=None, redirect_chain=None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO crawls (url_id, crawl_date, status_code, response_time_ms,
                           html_size_bytes, redirect_url, redirect_chain)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url_id, now, status_code, response_time_ms, html_size_bytes,
          redirect_url, redirect_chain))

    crawl_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return crawl_id


def add_seo_data(crawl_id, data):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO seo_data (crawl_id, canonical, meta_robots, x_robots_tag,
                             title, meta_description, h1_count, h1_text, h2_count,
                             image_count, images_without_alt, internal_links,
                             external_links, broken_links, og_title, og_description,
                             og_image, twitter_card, jsonld_schema, schema_type,
                             hreflang, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        crawl_id, data.get("canonical"), data.get("meta_robots"),
        data.get("x_robots_tag"), data.get("title"), data.get("meta_description"),
        data.get("h1_count", 0), data.get("h1_text"), data.get("h2_count", 0),
        data.get("image_count", 0), data.get("images_without_alt", 0),
        data.get("internal_links", 0), data.get("external_links", 0),
        data.get("broken_links", 0), data.get("og_title"), data.get("og_description"),
        data.get("og_image"), data.get("twitter_card"), data.get("jsonld_schema"),
        data.get("schema_type"), data.get("hreflang"), data.get("content_hash")
    ))

    conn.commit()
    conn.close()


def add_security_headers(crawl_id, headers):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO security_headers (crawl_id, hsts, csp, x_frame_options,
                                     x_content_type_options, strict_transport_security)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        crawl_id, headers.get("hsts"), headers.get("csp"),
        headers.get("x_frame_options"), headers.get("x_content_type_options"),
        headers.get("strict_transport_security")
    ))

    conn.commit()
    conn.close()


def add_change(url_id, change_type, category, old_value, new_value, severity="info"):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("""
        INSERT INTO changes (url_id, change_date, change_type, category,
                            old_value, new_value, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url_id, now, change_type, category, old_value, new_value, severity))

    conn.commit()
    conn.close()


def add_robots_snapshot(domain, content, disallow_count, sitemap_url):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("""
        INSERT INTO robots_snapshots (domain, crawl_date, content, disallow_count, sitemap_url)
        VALUES (?, ?, ?, ?, ?)
    """, (domain, now, content, disallow_count, sitemap_url))

    conn.commit()
    conn.close()


def add_ssl_info(domain, issuer, expiry_date, days_until_expiry, serial_number):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("""
        INSERT INTO ssl_info (domain, check_date, issuer, expiry_date,
                             days_until_expiry, serial_number)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (domain, now, issuer, expiry_date, days_until_expiry, serial_number))

    conn.commit()
    conn.close()


def get_url_id(url):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM urls WHERE url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    return row["id"] if row else None


def get_latest_seo_data(url_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sd.*, c.status_code, c.response_time_ms, c.html_size_bytes,
               c.redirect_url, c.redirect_chain
        FROM seo_data sd
        JOIN crawls c ON sd.crawl_id = c.id
        WHERE c.url_id = ?
        ORDER BY c.crawl_date DESC
        LIMIT 1
    """, (url_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_latest_robots(domain):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM robots_snapshots
        WHERE domain = ?
        ORDER BY crawl_date DESC
        LIMIT 1
    """, (domain,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_recent_changes(url_id=None, limit=50):
    conn = get_connection()
    cursor = conn.cursor()

    if url_id:
        cursor.execute("""
            SELECT c.*, u.url FROM changes c
            JOIN urls u ON c.url_id = u.id
            WHERE c.url_id = ?
            ORDER BY c.change_date DESC
            LIMIT ?
        """, (url_id, limit))
    else:
        cursor.execute("""
            SELECT c.*, u.url FROM changes c
            JOIN urls u ON c.url_id = u.id
            ORDER BY c.change_date DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_urls_to_crawl(limit=100):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, url, domain FROM urls
        WHERE is_active = 1
        ORDER BY last_crawled ASC NULLS FIRST
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_active_urls():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, domain FROM urls WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_url(url_id):
    conn = get_connection()
    conn.execute("UPDATE urls SET is_active = 0 WHERE id = ?", (url_id,))
    conn.commit()
    conn.close()


def get_url_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM urls WHERE is_active = 1")
    row = cursor.fetchone()
    conn.close()
    return row["count"]


def get_stats():
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) as count FROM urls WHERE is_active = 1")
    stats["total_urls"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM crawls")
    stats["total_crawls"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM changes")
    stats["total_changes"] = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*) as count FROM changes
        WHERE change_date > datetime('now', '-24 hours')
    """)
    stats["changes_last_24h"] = cursor.fetchone()["count"]

    conn.close()
    return stats


if __name__ == "__main__":
    init_db()
    print("Database test passed!")
