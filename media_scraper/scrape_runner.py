#!/usr/bin/env python3
"""
Media Scrape Runner - Processes firecrawl results into structured articles
Run from Claude Code to save scraped articles to JSONL
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/media_scraper/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def extract_sr_article(scrape_result: dict) -> Optional[dict]:
    """Extract article from Sveriges Radio scrape result"""
    metadata = scrape_result.get("metadata", {})

    # Skip 404s
    if metadata.get("statusCode") == 404:
        return None

    # Extract title from ogTitle (format: "Title - Program")
    title = metadata.get("ogTitle", metadata.get("title", ""))
    program = None
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        title = parts[0]
        program = parts[1].replace(" | Sveriges Radio", "")

    # Parse keywords to tags
    keywords = metadata.get("keywords", "")
    tags = [k.strip() for k in keywords.split(",") if k.strip()][:5]  # Max 5 tags

    return {
        "url": metadata.get("sourceURL", metadata.get("url", "")),
        "source": "sr",
        "title": title,
        "description": metadata.get("ogDescription", metadata.get("description", "")),
        "author": "Sveriges Radio",
        "published_date": None,  # SR doesn't expose this in metadata
        "section": program,
        "image_url": metadata.get("ogImage"),
        "tags": tags,
        "scraped_at": datetime.now().isoformat(),
    }


def extract_svt_article(scrape_result: dict) -> Optional[dict]:
    """Extract article from SVT Nyheter scrape result"""
    metadata = scrape_result.get("metadata", {})

    if metadata.get("statusCode") == 404:
        return None

    title = metadata.get("ogTitle", metadata.get("title", ""))
    # Remove " | SVT Nyheter" suffix
    title = re.sub(r"\s*\|\s*SVT\s*(Nyheter)?$", "", title)

    # Extract section from URL
    url = metadata.get("sourceURL", "")
    section = None
    match = re.search(r"/nyheter/([a-z-]+)/", url)
    if match:
        section = match.group(1).replace("-", " ").title()

    return {
        "url": url,
        "source": "svt",
        "title": title,
        "description": metadata.get("ogDescription", metadata.get("description", "")),
        "author": "SVT Nyheter",
        "published_date": metadata.get("article:published_time"),
        "section": section,
        "image_url": metadata.get("ogImage"),
        "tags": [],
        "scraped_at": datetime.now().isoformat(),
    }


def extract_svd_article(scrape_result: dict) -> Optional[dict]:
    """Extract article from SVD scrape result"""
    metadata = scrape_result.get("metadata", {})

    if metadata.get("statusCode") == 404:
        return None

    return {
        "url": metadata.get("sourceURL", metadata.get("url", "")),
        "source": "svd",
        "title": metadata.get("ogTitle", metadata.get("title", "")),
        "description": metadata.get("ogDescription", metadata.get("description", "")),
        "author": metadata.get("author", metadata.get("article:author")),
        "published_date": metadata.get("publishdate", metadata.get("article:published_time")),
        "section": metadata.get("article:section", metadata.get("lp:section")),
        "image_url": metadata.get("ogImage"),
        "tags": [],
        "scraped_at": datetime.now().isoformat(),
    }


EXTRACTORS = {
    "sr": extract_sr_article,
    "svt": extract_svt_article,
    "svd": extract_svd_article,
}


def save_article(article: dict, source: str):
    """Append article to JSONL file"""
    filepath = DATA_DIR / f"{source}_articles.jsonl"
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(article, ensure_ascii=False) + "\n")
    return filepath


def process_scrape_results(results: list[dict], source: str) -> int:
    """Process multiple scrape results and save to JSONL"""
    extractor = EXTRACTORS.get(source)
    if not extractor:
        print(f"No extractor for source: {source}")
        return 0

    saved = 0
    for result in results:
        article = extractor(result)
        if article and article.get("title"):
            save_article(article, source)
            saved += 1
            print(f"  ✓ {article['title'][:60]}...")

    return saved


def get_stats() -> dict:
    """Get current article counts"""
    stats = {}
    for source in ["sr", "svt", "svd", "dn", "aftonbladet", "expressen", "gp"]:
        filepath = DATA_DIR / f"{source}_articles.jsonl"
        if filepath.exists():
            with open(filepath) as f:
                count = sum(1 for _ in f)
            stats[source] = count
        else:
            stats[source] = 0
    return stats


if __name__ == "__main__":
    print("Media Scrape Runner")
    print("=" * 50)
    print("\nCurrent stats:")
    stats = get_stats()
    total = 0
    for source, count in stats.items():
        print(f"  {source:15} {count:>6} articles")
        total += count
    print(f"  {'TOTAL':15} {total:>6} articles")
