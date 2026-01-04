"""
Sitemap crawler for Swedish news sites - WORKING VERSION
"""

import asyncio
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import aiohttp

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


async def fetch_url(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch URL content"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SvenskaAI/1.0)"}
    async with session.get(url, headers=headers, timeout=30) as resp:
        return await resp.text()


async def parse_sr_news_sitemap(session: aiohttp.ClientSession) -> list[dict]:
    """Parse SR news sitemap - returns list of articles with metadata"""
    print("🔍 Parsing SR news sitemap...")

    url = "https://www.sverigesradio.se/newssitemap"
    xml_text = await fetch_url(session, url)

    # Parse XML
    root = ET.fromstring(xml_text)
    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }

    articles = []
    for url_elem in root.findall(".//sm:url", ns):
        loc = url_elem.find("sm:loc", ns)
        if loc is None:
            continue

        article_url = loc.text
        if "/artikel/" not in article_url:
            continue

        # Extract news metadata
        news_elem = url_elem.find(".//news:news", ns)
        title = ""
        pub_date = ""

        if news_elem is not None:
            title_elem = news_elem.find("news:title", ns)
            date_elem = news_elem.find("news:publication_date", ns)
            if title_elem is not None:
                title = title_elem.text
            if date_elem is not None:
                pub_date = date_elem.text

        articles.append(
            {"url": article_url, "title": title, "published_date": pub_date, "source": "sr"}
        )

    print(f"  ✅ Found {len(articles)} SR articles")
    return articles


async def get_existing_urls(source: str) -> set:
    """Get already scraped URLs"""
    filepath = DATA_DIR / f"{source}_articles.jsonl"
    urls = set()
    if filepath.exists():
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    art = json.loads(line)
                    urls.add(art.get("url", ""))
    return urls


async def save_articles(articles: list[dict], source: str) -> int:
    """Save new articles to JSONL"""
    filepath = DATA_DIR / f"{source}_articles.jsonl"
    existing = await get_existing_urls(source)

    saved = 0
    with open(filepath, "a", encoding="utf-8") as f:
        for art in articles:
            if art["url"] not in existing:
                full_article = {
                    "url": art["url"],
                    "source": source,
                    "title": art.get("title", ""),
                    "description": "",  # Will fill from WebFetch later
                    "author": "Sveriges Radio" if source == "sr" else "SVT Nyheter",
                    "published_date": art.get("published_date"),
                    "section": "",
                    "tags": [],
                    "scraped_at": datetime.now().isoformat(),
                }
                f.write(json.dumps(full_article, ensure_ascii=False) + "\n")
                saved += 1

    return saved


async def main():
    """Crawl SR news sitemap and save articles"""
    async with aiohttp.ClientSession() as session:
        # Get SR articles from sitemap
        articles = await parse_sr_news_sitemap(session)

        if articles:
            saved = await save_articles(articles, "sr")
            print(f"\n✅ Saved {saved} NEW SR articles")
            print(f"   Sample: {articles[0]['title'][:50]}...")

            # Show total count
            existing = await get_existing_urls("sr")
            print(f"   Total SR articles now: {len(existing) + saved}")
        else:
            print("❌ No articles found")


if __name__ == "__main__":
    asyncio.run(main())

# All SVT RSS feeds - national and regional
SVT_RSS_FEEDS = [
    ("https://www.svt.se/rss.xml", "main"),
    ("https://www.svt.se/nyheter/rss.xml", "nyheter"),
    ("https://www.svt.se/sport/rss.xml", "sport"),
    ("https://www.svt.se/kultur/rss.xml", "kultur"),
    ("https://www.svt.se/nyheter/utrikes/rss.xml", "utrikes"),
    ("https://www.svt.se/nyheter/inrikes/rss.xml", "inrikes"),
    ("https://www.svt.se/nyheter/lokalt/stockholm/rss.xml", "stockholm"),
    ("https://www.svt.se/nyheter/lokalt/skane/rss.xml", "skane"),
    ("https://www.svt.se/nyheter/lokalt/vast/rss.xml", "vast"),
    ("https://www.svt.se/nyheter/lokalt/norrbotten/rss.xml", "norrbotten"),
    ("https://www.svt.se/nyheter/lokalt/gavleborg/rss.xml", "gavleborg"),
    ("https://www.svt.se/nyheter/lokalt/vasterbotten/rss.xml", "vasterbotten"),
    ("https://www.svt.se/nyheter/lokalt/smaland/rss.xml", "smaland"),
    ("https://www.svt.se/nyheter/lokalt/dalarna/rss.xml", "dalarna"),
    ("https://www.svt.se/nyheter/lokalt/ost/rss.xml", "ost"),
    ("https://www.svt.se/nyheter/lokalt/orebro/rss.xml", "orebro"),
    ("https://www.svt.se/nyheter/lokalt/jamtland/rss.xml", "jamtland"),
    ("https://www.svt.se/nyheter/lokalt/halland/rss.xml", "halland"),
    ("https://www.svt.se/nyheter/lokalt/blekinge/rss.xml", "blekinge"),
    ("https://www.svt.se/nyheter/lokalt/uppland/rss.xml", "uppland"),
    ("https://www.svt.se/nyheter/lokalt/sodertalje/rss.xml", "sodertalje"),
    ("https://www.svt.se/nyheter/lokalt/helsingborg/rss.xml", "helsingborg"),
]


async def parse_single_rss(session: aiohttp.ClientSession, url: str, section: str) -> list[dict]:
    """Parse a single RSS feed"""
    try:
        xml_text = await fetch_url(session, url)
        root = ET.fromstring(xml_text)

        articles = []
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            date_elem = item.find("pubDate")

            if link_elem is None:
                continue

            articles.append(
                {
                    "url": link_elem.text,
                    "title": title_elem.text if title_elem is not None else "",
                    "description": desc_elem.text if desc_elem is not None else "",
                    "published_date": date_elem.text if date_elem is not None else "",
                    "source": "svt",
                    "section": section,
                }
            )
        return articles
    except Exception as e:
        print(f"    ⚠️ Failed {section}: {e}")
        return []


async def parse_svt_rss(session: aiohttp.ClientSession) -> list[dict]:
    """Parse ALL SVT RSS feeds"""
    print("🔍 Parsing SVT RSS feeds (22 sources)...")

    all_articles = []
    seen_urls = set()

    for url, section in SVT_RSS_FEEDS:
        articles = await parse_single_rss(session, url, section)
        new_count = 0
        for art in articles:
            if art["url"] not in seen_urls:
                seen_urls.add(art["url"])
                all_articles.append(art)
                new_count += 1
        if new_count > 0:
            print(f"    ✅ {section}: {new_count} unique")

    print(f"  ✅ Total unique SVT articles: {len(all_articles)}")
    return all_articles


async def save_svt_articles(articles: list[dict]) -> int:
    """Save SVT articles to JSONL"""
    filepath = DATA_DIR / "svt_articles.jsonl"
    existing = await get_existing_urls("svt")

    saved = 0
    with open(filepath, "a", encoding="utf-8") as f:
        for art in articles:
            if art["url"] not in existing:
                full_article = {
                    "url": art["url"],
                    "source": "svt",
                    "title": art.get("title", ""),
                    "description": art.get("description", ""),
                    "author": "SVT Nyheter",
                    "published_date": art.get("published_date"),
                    "section": "",
                    "tags": [],
                    "scraped_at": datetime.now().isoformat(),
                }
                f.write(json.dumps(full_article, ensure_ascii=False) + "\n")
                saved += 1
                existing.add(art["url"])

    return saved


async def crawl_svt():
    """Crawl SVT RSS"""
    async with aiohttp.ClientSession() as session:
        articles = await parse_svt_rss(session)
        saved = await save_svt_articles(articles)
        print(f"\n✅ Saved {saved} NEW SVT articles")

        existing = await get_existing_urls("svt")
        print(f"   Total SVT articles now: {len(existing)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "svt":
        asyncio.run(crawl_svt())
    else:
        asyncio.run(main())
