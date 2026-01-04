#!/usr/bin/env python3
"""
News Article Embedder for Qdrant
Reads JSONL articles and adds them to existing Qdrant collection.

Integration with existing 965K vectors in Qdrant.
Uses same embedding model as kommun/diva pipeline.
"""

import json
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# Sentence transformers for Swedish embeddings
from sentence_transformers import SentenceTransformer

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "documents"  # Same as existing collection
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"  # Swedish BERT
EMBEDDING_DIM = 768
BATCH_SIZE = 100

DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/media_scraper/data")


@dataclass
class ArticlePayload:
    """Qdrant payload structure for news articles"""

    source: str = "media"  # Always "media" for news
    outlet: str = ""  # sr, svt, svd, dn, etc.
    title: str = ""
    description: str = ""
    date: str = ""
    category: str = ""
    url: str = ""
    author: str = ""


def load_articles_from_jsonl(filepath: Path) -> Generator[dict, None, None]:
    """Load articles from JSONL file"""
    if not filepath.exists():
        return
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def article_to_embedding_text(article: dict) -> str:
    """Convert article to text for embedding"""
    parts = []
    if article.get("title"):
        parts.append(article["title"])
    if article.get("description"):
        parts.append(article["description"])
    if article.get("section"):
        parts.append(f"Kategori: {article['section']}")
    if article.get("tags"):
        parts.append(f"Ämnen: {', '.join(article['tags'][:5])}")
    return "\n".join(parts)


def article_to_payload(article: dict) -> dict:
    """Convert article to Qdrant payload"""
    return {
        "source": "media",
        "outlet": article.get("source", "unknown"),
        "title": article.get("title", ""),
        "description": article.get("description", ""),
        "date": article.get("published_date", ""),
        "category": article.get("section", ""),
        "url": article.get("url", ""),
        "author": article.get("author", ""),
        "scraped_at": article.get("scraped_at", ""),
        "tags": article.get("tags", []),
    }


class NewsEmbedder:
    """Embeds news articles into Qdrant"""

    def __init__(self):
        print(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

        print(f"Loading embedding model: {EMBEDDING_MODEL}...")
        self.model = SentenceTransformer(EMBEDDING_MODEL)

        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist"""
        collections = self.client.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)

        if not exists:
            print(f"Creating collection: {COLLECTION_NAME}")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
        else:
            info = self.client.get_collection(COLLECTION_NAME)
            print(f"Collection exists: {info.points_count} points")

    def embed_articles(self, articles: list[dict]) -> int:
        """Embed and upsert articles to Qdrant"""
        if not articles:
            return 0

        # Generate embedding texts
        texts = [article_to_embedding_text(a) for a in articles]

        # Generate embeddings
        embeddings = self.model.encode(texts, show_progress_bar=True)

        # Create points
        points = []
        for i, (article, embedding) in enumerate(zip(articles, embeddings)):
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id, vector=embedding.tolist(), payload=article_to_payload(article)
                )
            )

        # Upsert to Qdrant
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)

        return len(points)

    def embed_source(self, source: str) -> int:
        """Embed all articles from a source"""
        filepath = DATA_DIR / f"{source}_articles.jsonl"
        if not filepath.exists():
            print(f"No file found: {filepath}")
            return 0

        articles = list(load_articles_from_jsonl(filepath))
        print(f"Found {len(articles)} articles from {source}")

        total = 0
        for i in range(0, len(articles), BATCH_SIZE):
            batch = articles[i : i + BATCH_SIZE]
            embedded = self.embed_articles(batch)
            total += embedded
            print(f"  Embedded batch {i//BATCH_SIZE + 1}: {embedded} articles")

        return total

    def embed_all_sources(self) -> dict[str, int]:
        """Embed articles from all sources"""
        sources = ["sr", "svt", "svd", "dn", "aftonbladet", "expressen", "gp"]
        results = {}

        for source in sources:
            count = self.embed_source(source)
            if count > 0:
                results[source] = count

        return results

    def get_stats(self) -> dict:
        """Get collection statistics"""
        info = self.client.get_collection(COLLECTION_NAME)
        return {
            "collection": COLLECTION_NAME,
            "total_points": info.points_count,
            "status": info.status,
        }


def main():
    """Main entry point"""
    print("=" * 60)
    print("News Article Embedder for Qdrant")
    print("=" * 60)

    embedder = NewsEmbedder()

    # Show current stats
    stats = embedder.get_stats()
    print("\nCurrent collection stats:")
    print(f"  Total points: {stats['total_points']:,}")

    # Embed all sources
    print("\nEmbedding articles...")
    results = embedder.embed_all_sources()

    if results:
        print("\nResults:")
        total = 0
        for source, count in results.items():
            print(f"  {source}: {count} articles embedded")
            total += count
        print(f"  TOTAL: {total} articles embedded")
    else:
        print("\nNo articles to embed.")

    # Show final stats
    stats = embedder.get_stats()
    print("\nFinal collection stats:")
    print(f"  Total points: {stats['total_points']:,}")


if __name__ == "__main__":
    main()
