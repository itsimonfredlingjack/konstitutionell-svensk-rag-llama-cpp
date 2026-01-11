#!/usr/bin/env python3
"""
Swedish News Extractor - Practical metadata extraction
Works with: SVD, DN, SR, SVT, Omni, etc.

Strategy: Extract metadata + summaries (available without paywall)
This gives us searchable content for RAG even without full articles.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class NewsArticle:
    """News article metadata"""

    url: str
    source: str
    title: str
    description: str  # Summary/ingress - usually available
    author: str | None = None
    published_date: str | None = None
    section: str | None = None
    image_url: str | None = None
    tags: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    def to_embedding_text(self) -> str:
        """Generate text for embedding"""
        parts = [self.title]
        if self.description:
            parts.append(self.description)
        if self.tags:
            parts.append(f"Ämnen: {', '.join(self.tags)}")
        if self.section:
            parts.append(f"Kategori: {self.section}")
        return "\n".join(parts)


def extract_from_svd_metadata(metadata: dict, url: str) -> NewsArticle:
    """Extract article info from SVD metadata"""
    return NewsArticle(
        url=url,
        source="svd",
        title=metadata.get("ogTitle", metadata.get("title", "")),
        description=metadata.get("ogDescription", metadata.get("description", "")),
        author=metadata.get("author", metadata.get("article:author")),
        published_date=metadata.get("publishdate", metadata.get("article:published_time")),
        section=metadata.get("article:section", metadata.get("lp:section")),
        image_url=metadata.get("ogImage"),
        tags=[],  # Would need to parse from content
    )


def extract_from_sr_metadata(metadata: dict, url: str) -> NewsArticle:
    """Extract article info from Sveriges Radio metadata"""
    # Extract program name from title
    title = metadata.get("title", "")
    program = None
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        title = parts[0]
        program = parts[1].replace(" | Sveriges Radio", "")

    return NewsArticle(
        url=url,
        source="sr",
        title=title,
        description=metadata.get("ogDescription", metadata.get("description", "")),
        author=metadata.get("author", "Sveriges Radio"),
        section=program,
        image_url=metadata.get("ogImage"),
        tags=metadata.get("keywords", "").split(",") if metadata.get("keywords") else [],
    )


def extract_from_dn_metadata(metadata: dict, url: str) -> NewsArticle:
    """Extract article info from DN metadata"""
    return NewsArticle(
        url=url,
        source="dn",
        title=metadata.get("ogTitle", metadata.get("title", "")),
        description=metadata.get("ogDescription", metadata.get("description", "")),
        author=metadata.get("author"),
        published_date=metadata.get("article:published_time"),
        section=metadata.get("article:section"),
        image_url=metadata.get("ogImage"),
        tags=[],
    )


def extract_from_svt_metadata(metadata: dict, url: str) -> NewsArticle:
    """Extract article info from SVT metadata"""
    return NewsArticle(
        url=url,
        source="svt",
        title=metadata.get("ogTitle", metadata.get("title", "")),
        description=metadata.get("ogDescription", metadata.get("description", "")),
        author=metadata.get("author", "SVT"),
        published_date=metadata.get("article:published_time"),
        section=metadata.get("article:section"),
        image_url=metadata.get("ogImage"),
        tags=[],
    )


EXTRACTORS = {
    "svd.se": extract_from_svd_metadata,
    "sverigesradio.se": extract_from_sr_metadata,
    "dn.se": extract_from_dn_metadata,
    "svt.se": extract_from_svt_metadata,
}


def get_extractor(url: str):
    """Get appropriate extractor for URL"""
    for domain, extractor in EXTRACTORS.items():
        if domain in url:
            return extractor
    return None


def save_articles_jsonl(articles: list[NewsArticle], filepath: Path):
    """Save articles to JSONL format"""
    with open(filepath, "a", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(article.to_dict(), ensure_ascii=False) + "\n")


def load_articles_jsonl(filepath: Path) -> list[NewsArticle]:
    """Load articles from JSONL"""
    articles = []
    if filepath.exists():
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                articles.append(NewsArticle(**data))
    return articles


# URL patterns for article detection
ARTICLE_PATTERNS = {
    "svd": re.compile(r"svd\.se/a/[a-zA-Z0-9]+"),
    "sr": re.compile(r"sverigesradio\.se/artikel/"),
    "dn": re.compile(r"dn\.se/[a-z-]+/[a-z0-9-]+(?!\.xml)"),
    "svt": re.compile(r"svt\.se/nyheter/[a-z-]+/[a-z0-9-]+"),
    "aftonbladet": re.compile(r"aftonbladet\.se/nyheter/a/[a-zA-Z0-9]+"),
}


def is_article_url(url: str) -> bool:
    """Check if URL is likely an article"""
    return any(pattern.search(url) for pattern in ARTICLE_PATTERNS.values())


def filter_article_urls(urls: list[dict]) -> list[str]:
    """Filter list of URLs to only articles"""
    article_urls = []
    for url_obj in urls:
        url = url_obj.get("url", "")
        if is_article_url(url):
            # Exclude sitemaps, tags, etc.
            exclude = [
                "/sitemaps/",
                "/tagg/",
                "/story/",
                "/av/",
                "/lyssna/",
                "/amne/",
                "/grupp/",
                "/avsnitt/",
                ".xml",
            ]
            if not any(x in url for x in exclude):
                article_urls.append(url)
    return article_urls


if __name__ == "__main__":
    print("Swedish News Extractor")
    print("=" * 50)
    print("\nUsage with Firecrawl MCP:")
    print("1. Map source: firecrawl_map(url, limit=1000)")
    print("2. Filter URLs: filter_article_urls(map_result['links'])")
    print("3. Scrape: firecrawl_scrape(url) -> metadata")
    print("4. Extract: extractor(metadata, url) -> NewsArticle")
    print("5. Save: save_articles_jsonl(articles, path)")
    print()
    print("Example patterns:")
    for source, pattern in ARTICLE_PATTERNS.items():
        print(f"  {source}: {pattern.pattern}")
