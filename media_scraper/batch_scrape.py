#!/usr/bin/env python3
"""
Batch Scraper for Swedish News Sites
Uses Firecrawl MCP for large-scale article collection.

Usage with Claude Code:
  1. Run firecrawl_map() to discover URLs
  2. Filter using this script's patterns
  3. Batch scrape with firecrawl_scrape()
  4. Save metadata to JSONL

Target: 780,000+ articles across 7 sources
"""

import json
import re
from datetime import datetime
from pathlib import Path

# Output directory
DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/media_scraper/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Source configurations
SOURCES = {
    "svd": {
        "name": "Svenska Dagbladet",
        "base_url": "https://www.svd.se",
        "article_pattern": r"/a/[a-zA-Z0-9]+",
        "exclude_patterns": ["/sitemaps/", "/tagg/", "/story/", "/av/", "/lyssna/"],
        "estimated_count": 100000,
        "has_paywall": True,
    },
    "dn": {
        "name": "Dagens Nyheter",
        "base_url": "https://www.dn.se",
        "article_pattern": r"/(ekonomi|kultur|ledare|sthlm|sport)/[a-z0-9-]+$",
        "exclude_patterns": ["/tagg/", "/story/"],
        "estimated_count": 100000,
        "has_paywall": True,
    },
    "sr": {
        "name": "Sveriges Radio",
        "base_url": "https://sverigesradio.se",
        "article_pattern": r"/artikel/",
        "exclude_patterns": ["/avsnitt/", "/grupp/", "/amne/"],
        "estimated_count": 100000,
        "has_paywall": False,
    },
    "svt": {
        "name": "SVT Nyheter",
        "base_url": "https://www.svt.se",
        "article_pattern": r"/nyheter/[a-z-]+/[a-z0-9-]+",
        "exclude_patterns": ["/video/", "/live/"],
        "estimated_count": 50000,
        "has_paywall": False,
    },
    "aftonbladet": {
        "name": "Aftonbladet",
        "base_url": "https://www.aftonbladet.se",
        "article_pattern": r"/nyheter/a/[a-zA-Z0-9]+",
        "exclude_patterns": [],
        "estimated_count": 200000,
        "has_paywall": True,
    },
    "expressen": {
        "name": "Expressen",
        "base_url": "https://www.expressen.se",
        "article_pattern": r"/(nyheter|sport|noje)/[a-z0-9-]+$",
        "exclude_patterns": [],
        "estimated_count": 150000,
        "has_paywall": True,
    },
    "gp": {
        "name": "Göteborgs-Posten",
        "base_url": "https://www.gp.se",
        "article_pattern": r"/(nyheter|ekonomi|kultur|sport)/[0-9.]+",
        "exclude_patterns": [],
        "estimated_count": 80000,
        "has_paywall": True,
    },
}


def filter_urls_for_source(urls: list[dict], source_key: str) -> list[str]:
    """Filter mapped URLs to only article URLs for a source"""
    config = SOURCES.get(source_key)
    if not config:
        return []

    pattern = re.compile(config["article_pattern"])
    article_urls = []

    for url_obj in urls:
        url = url_obj.get("url", "")

        # Must match article pattern
        if not pattern.search(url):
            continue

        # Must not match any exclude pattern
        excluded = False
        for exclude in config["exclude_patterns"]:
            if exclude in url:
                excluded = True
                break

        if not excluded:
            article_urls.append(url)

    return article_urls


def create_batch_file(source_key: str, urls: list[str], batch_num: int) -> Path:
    """Create a batch file with URLs to scrape"""
    filepath = DATA_DIR / f"{source_key}_batch_{batch_num:04d}_urls.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": source_key,
                "batch": batch_num,
                "count": len(urls),
                "urls": urls,
                "created_at": datetime.now().isoformat(),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    return filepath


def load_batch_file(filepath: Path) -> dict:
    """Load a batch file"""
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def get_progress() -> dict:
    """Get current scraping progress"""
    progress = {}
    for source_key in SOURCES:
        # Count JSONL files
        jsonl_files = list(DATA_DIR.glob(f"{source_key}_*.jsonl"))
        article_count = 0
        for f in jsonl_files:
            with open(f, encoding="utf-8") as file:
                article_count += sum(1 for _ in file)

        progress[source_key] = {
            "name": SOURCES[source_key]["name"],
            "articles_scraped": article_count,
            "estimated_total": SOURCES[source_key]["estimated_count"],
            "progress_pct": round(article_count / SOURCES[source_key]["estimated_count"] * 100, 2),
        }

    return progress


# Firecrawl MCP workflow helpers
FIRECRAWL_WORKFLOW = """
# Firecrawl MCP Workflow for Batch Scraping

## Step 1: Map the source
```
firecrawl_map({
    "url": "https://www.svd.se",
    "limit": 1000
})
```

## Step 2: Filter URLs (in Python or manually)
Use filter_urls_for_source(map_result['links'], 'svd')

## Step 3: Batch scrape articles
For each URL:
```
firecrawl_scrape({
    "url": "https://www.svd.se/a/xyz123/article-title",
    "formats": ["markdown"],
    "onlyMainContent": true
})
```

## Step 4: Extract from metadata
The metadata field contains:
- ogTitle, ogDescription
- author, article:author
- publishdate, article:published_time
- article:section
- ogImage

## Step 5: Save to JSONL
Append each article as JSON line to {source}_articles.jsonl
"""


if __name__ == "__main__":
    print("Swedish News Batch Scraper")
    print("=" * 60)
    print()

    # Show current progress
    progress = get_progress()
    total_scraped = 0
    total_target = 0

    print("Source Progress:")
    print("-" * 60)
    for source_key, stats in progress.items():
        total_scraped += stats["articles_scraped"]
        total_target += stats["estimated_total"]
        print(
            f"  {stats['name']:25} {stats['articles_scraped']:>8} / {stats['estimated_total']:>8} ({stats['progress_pct']:>5.1f}%)"
        )

    print("-" * 60)
    print(
        f"  {'TOTAL':25} {total_scraped:>8} / {total_target:>8} ({total_scraped/total_target*100:>5.1f}%)"
    )
    print()
    print(FIRECRAWL_WORKFLOW)
