#!/usr/bin/env python3
"""
Swedish Media Scraper - Firecrawl-based pipeline
Targets: SVD, DN, Aftonbladet, Expressen, GP, SR, SVT
Goal: 780,000+ articles for Constitutional RAG
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# Would use firecrawl-py in production, but we're using MCP
# This script is for reference and local testing


@dataclass
class Article:
    """Scraped article data"""

    url: str
    source: str
    title: str
    author: str | None
    published_date: str | None
    category: str | None
    summary: str | None
    content: str
    tags: list[str]
    scraped_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class MediaScraper:
    """Swedish media scraper using Firecrawl"""

    def __init__(self, output_dir: str = "./data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"mapped": 0, "filtered": 0, "scraped": 0, "failed": 0}

    def filter_article_urls(self, urls: list[dict], pattern: str) -> list[str]:
        """Filter URLs matching article pattern"""
        article_urls = []
        regex = re.compile(pattern)

        for url_obj in urls:
            url = url_obj.get("url", "")
            if regex.search(url) and not any(
                x in url for x in ["/sitemaps/", "/tagg/", "/story/", "/av/", "/lyssna/"]
            ):
                article_urls.append(url)

        return article_urls

    def save_batch(self, articles: list[Article], source: str, batch_num: int):
        """Save a batch of articles to JSONL"""
        filename = self.output_dir / f"{source}_batch_{batch_num:04d}.jsonl"
        with open(filename, "w", encoding="utf-8") as f:
            for article in articles:
                f.write(json.dumps(article.to_dict(), ensure_ascii=False) + "\n")
        print(f"Saved {len(articles)} articles to {filename}")

    def get_progress(self) -> dict:
        """Get current scraping progress"""
        return {**self.stats, "timestamp": datetime.now().isoformat()}


# URL patterns for each source (for filtering)
URL_PATTERNS = {
    "svd": r"/a/[a-zA-Z0-9]+",
    "dn": r"/(ekonomi|kultur|ledare|sthlm|sport)/[a-z0-9-]+$",
    "aftonbladet": r"/nyheter/a/[a-zA-Z0-9]+",
    "expressen": r"/(nyheter|sport|noje)/[a-z0-9-]+$",
    "gp": r"/(nyheter|ekonomi|kultur|sport)/[0-9.]+",
    "sr": r"/artikel/\d+$",
    "svt": r"/nyheter/[a-z-]+/[a-z0-9-]+$",
}


def main():
    """Main entry point for CLI usage"""
    print("Swedish Media Scraper")
    print("=" * 50)
    print("\nThis script is designed to work with Firecrawl MCP.")
    print("Use Claude Code with the following workflow:")
    print()
    print("1. MAP: firecrawl_map({url}, limit=1000)")
    print("2. FILTER: Use URL_PATTERNS to filter articles")
    print("3. SCRAPE: firecrawl_scrape or batch_scrape")
    print("4. EXTRACT: Use ARTICLE_SCHEMA for structured data")
    print()
    print("Target sources:")
    for source, pattern in URL_PATTERNS.items():
        print(f"  - {source}: {pattern}")


if __name__ == "__main__":
    main()
