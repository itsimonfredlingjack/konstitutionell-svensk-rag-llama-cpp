"""
Swedish Media Scraper Configuration
Target: 780,000+ articles from Swedish news sites
"""

from dataclasses import dataclass, field


@dataclass
class MediaSource:
    """Configuration for a Swedish news source"""

    name: str
    base_url: str
    article_pattern: str  # Regex pattern to identify article URLs
    sections: list[str] = field(default_factory=list)
    estimated_articles: int = 0
    rate_limit_seconds: float = 1.0  # Delay between requests


# Swedish News Sources
SOURCES: dict[str, MediaSource] = {
    "svd": MediaSource(
        name="Svenska Dagbladet",
        base_url="https://www.svd.se",
        article_pattern=r"/a/[a-zA-Z0-9]+",
        sections=["/naringsliv", "/kultur", "/ledare", "/varlden", "/debatt"],
        estimated_articles=100_000,
        rate_limit_seconds=1.5,
    ),
    "dn": MediaSource(
        name="Dagens Nyheter",
        base_url="https://www.dn.se",
        article_pattern=r"/[a-z-]+/[a-z0-9-]+",
        sections=["/ekonomi", "/kultur-noje", "/ledare", "/sthlm", "/sport"],
        estimated_articles=100_000,
        rate_limit_seconds=1.5,
    ),
    "aftonbladet": MediaSource(
        name="Aftonbladet",
        base_url="https://www.aftonbladet.se",
        article_pattern=r"/nyheter/a/[a-zA-Z0-9]+",
        sections=["/nyheter", "/sportbladet", "/nojesbladet", "/debatt"],
        estimated_articles=200_000,
        rate_limit_seconds=1.0,
    ),
    "expressen": MediaSource(
        name="Expressen",
        base_url="https://www.expressen.se",
        article_pattern=r"/[a-z-]+/[a-z0-9-]+",
        sections=["/nyheter", "/sport", "/noje", "/debatt", "/ledare"],
        estimated_articles=150_000,
        rate_limit_seconds=1.0,
    ),
    "gp": MediaSource(
        name="Göteborgs-Posten",
        base_url="https://www.gp.se",
        article_pattern=r"/[a-z-]+/[a-z0-9.-]+",
        sections=["/nyheter", "/ekonomi", "/kultur", "/sport", "/ledare"],
        estimated_articles=80_000,
        rate_limit_seconds=1.5,
    ),
    "sr": MediaSource(
        name="Sveriges Radio",
        base_url="https://sverigesradio.se",
        article_pattern=r"/artikel/\d+",
        sections=["/ekot", "/p1", "/p3", "/p4"],
        estimated_articles=100_000,
        rate_limit_seconds=0.5,
    ),
    "svt": MediaSource(
        name="SVT Nyheter",
        base_url="https://www.svt.se",
        article_pattern=r"/nyheter/[a-z-]+/[a-z0-9-]+",
        sections=["/nyheter/inrikes", "/nyheter/utrikes", "/nyheter/ekonomi", "/nyheter/vetenskap"],
        estimated_articles=50_000,
        rate_limit_seconds=0.5,
    ),
}

# Output configuration
OUTPUT_DIR = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/media_scraper/data"
BATCH_SIZE = 50  # Articles per batch
MAX_CONCURRENT = 5  # Concurrent scrapes

# Extraction schema for structured data
ARTICLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "author": {"type": "string"},
        "published_date": {"type": "string"},
        "category": {"type": "string"},
        "summary": {"type": "string"},
        "content": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "content"],
}
