#!/usr/bin/env python3
"""
DiVA Direct Embedding Pipeline

Embeds 1M+ triggered DiVA documents directly to Qdrant,
bypassing the n8n webhook that never processed them.

Usage:
    python diva_direct_embed.py                    # Process all triggered
    python diva_direct_embed.py --batch-size 200   # Custom batch size
    python diva_direct_embed.py --limit 10000      # Test run
    python diva_direct_embed.py --status           # Show progress
"""

import argparse
import json
import sqlite3
import sys
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

# Rich for progress display
try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Qdrant
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models
except ImportError:
    print("ERROR: pip install qdrant-client")
    sys.exit(1)

# Configuration
CONFIG = {
    "bridge_db": Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_bridge.db"),
    "data_dir": Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data"),
    "qdrant_host": "localhost",
    "qdrant_port": 6333,
    "qdrant_timeout": 120,
    "collection_name": "documents",
    "ollama_url": "http://localhost:11434/api/embeddings",
    "embed_model": "nomic-embed-text",
    "embedding_dim": 768,
    "chunk_tokens": 500,
    "chunk_overlap": 50,
    "batch_size": 100,
    "upsert_batch": 50,
}

console = Console() if RICH_AVAILABLE else None


@dataclass
class DiVADocument:
    """Represents a DiVA document to embed."""

    doc_id: str
    source: str
    source_file: str
    title: str
    abstract: str
    university: str
    year: str | None
    language: str
    doc_type: str
    metadata: dict


class OllamaEmbedder:
    """Embed text using Ollama's nomic-embed-text model."""

    def __init__(self, model: str = CONFIG["embed_model"], url: str = CONFIG["ollama_url"]):
        self.model = model
        self.url = url
        self._verify_model()

    def _verify_model(self):
        """Verify model is available."""
        try:
            resp = requests.post(self.url, json={"model": self.model, "prompt": "test"}, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama returned {resp.status_code}")
        except Exception as e:
            print(f"ERROR: Cannot connect to Ollama: {e}")
            print(f"Make sure Ollama is running with {self.model}")
            sys.exit(1)

    def embed(self, text: str) -> list[float]:
        """Embed single text."""
        resp = requests.post(self.url, json={"model": self.model, "prompt": text}, timeout=60)
        resp.raise_for_status()
        return resp.json()["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed batch of texts (sequential for Ollama)."""
        embeddings = []
        for text in texts:
            embeddings.append(self.embed(text))
        return embeddings


class TextChunker:
    """Simple token-based text chunker."""

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_tokens = max_tokens
        self.overlap = overlap
        # Approximate: 1 token ≈ 4 chars for English, 3.5 for Swedish
        self.chars_per_token = 3.5

    def chunk(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if not text or not text.strip():
            return []

        max_chars = int(self.max_tokens * self.chars_per_token)
        overlap_chars = int(self.overlap * self.chars_per_token)

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + max_chars

            # Find sentence boundary if possible
            if end < text_len:
                # Look for sentence end in last 20% of chunk
                search_start = end - int(max_chars * 0.2)
                best_break = end

                for sep in [". ", ".\n", "! ", "? ", "\n\n"]:
                    pos = text.rfind(sep, search_start, end)
                    if pos > search_start:
                        best_break = pos + len(sep)
                        break

                end = best_break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start with overlap
            start = end - overlap_chars
            if start >= text_len - overlap_chars:
                break

        return chunks


class DiVAEmbedder:
    """Main embedding pipeline for DiVA documents."""

    def __init__(self, config: dict = CONFIG):
        self.config = config
        self.db_path = config["bridge_db"]

        # Initialize components
        print("Initializing Ollama embedder...")
        self.embedder = OllamaEmbedder(model=config["embed_model"], url=config["ollama_url"])

        print("Connecting to Qdrant...")
        self.qdrant = QdrantClient(
            host=config["qdrant_host"], port=config["qdrant_port"], timeout=config["qdrant_timeout"]
        )
        self._ensure_collection()

        self.chunker = TextChunker(
            max_tokens=config["chunk_tokens"], overlap=config["chunk_overlap"]
        )

        # Cache loaded JSON files
        self._json_cache: dict[str, dict] = {}

        # Stats
        self.stats = {
            "docs_processed": 0,
            "docs_skipped": 0,
            "chunks_created": 0,
            "chunks_embedded": 0,
            "errors": 0,
            "start_time": None,
        }

    def _ensure_collection(self):
        """Ensure Qdrant collection exists."""
        collections = [c.name for c in self.qdrant.get_collections().collections]

        if self.config["collection_name"] not in collections:
            print(f"Creating collection: {self.config['collection_name']}")
            self.qdrant.create_collection(
                collection_name=self.config["collection_name"],
                vectors_config=qdrant_models.VectorParams(
                    size=self.config["embedding_dim"], distance=qdrant_models.Distance.COSINE
                ),
            )
        else:
            info = self.qdrant.get_collection(self.config["collection_name"])
            print(f"Collection exists: {info.points_count:,} points")

    def _load_json_file(self, source_file: str) -> dict:
        """Load and cache DiVA JSON file."""
        if source_file in self._json_cache:
            return self._json_cache[source_file]

        path = Path(source_file)
        if not path.exists():
            return {}

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Handle both formats: list at root or dict with "records" key
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("records", [])
        else:
            records = []

        # Index records by identifier for fast lookup
        indexed = {}

        # Get source code from filename: diva_full_du.json -> du
        source_code = path.stem.replace("diva_full_", "").replace("diva_", "")

        for idx, record in enumerate(records):
            # Format 1: Array index based (diva_du_2683 = record[2683])
            # This is how the corpus_bridge inventory was built
            index_key = f"diva_{source_code}_{idx}"
            indexed[index_key] = record

            # Format 2: identifiers dict/list (older format)
            ids = record.get("identifiers", {})
            if isinstance(ids, dict):
                for _key, val in ids.items():
                    indexed[str(val)] = record
            elif isinstance(ids, list):
                for id_val in ids:
                    indexed[str(id_val)] = record

            # Format 3: identifier field
            if "identifier" in record:
                indexed[str(record["identifier"])] = record

            # Format 4: oai_id field (newer diva_full_*.json format)
            if "oai_id" in record:
                oai_id = record["oai_id"]
                indexed[oai_id] = record

            # Format 5: id_uri field
            if record.get("id_uri"):
                indexed[record["id_uri"]] = record

        self._json_cache[source_file] = indexed
        return indexed

    def _extract_university(self, source: str) -> str:
        """Extract university code from source name."""
        # source format: diva_gu, diva_batch2_kth, etc.
        parts = source.replace("diva_", "").replace("batch2_", "").replace("batch1_", "")
        return parts.split("_")[0] if parts else "unknown"

    def _find_record_data(self, doc: dict, source_file: str) -> tuple[str, str]:
        """Find title and abstract from original JSON file.

        Returns:
            Tuple of (title, abstract)
        """
        indexed = self._load_json_file(source_file)
        doc_id = doc.get("doc_id", "")

        record = None

        # Handle list-formatted doc_ids
        if doc_id.startswith("["):
            try:
                id_list = eval(doc_id)  # Safe since it's our own data
                for id_val in id_list:
                    if str(id_val) in indexed:
                        record = indexed[str(id_val)]
                        break
            except Exception:
                pass

        # Direct lookup
        if not record and doc_id in indexed:
            record = indexed[doc_id]

        if not record:
            return "", ""

        # Extract title - handle multiple formats
        title = ""
        if "title" in record:
            title = record["title"]
        elif "titles" in record:
            titles = record["titles"]
            if isinstance(titles, list) and titles:
                title = titles[0] if isinstance(titles[0], str) else titles[0].get("title", "")
            elif isinstance(titles, dict):
                title = titles.get("title", "")
            elif isinstance(titles, str):
                title = titles

        # Extract abstract - handle multiple formats
        abstract = ""
        if "abstract" in record:
            abstract = record["abstract"]
        elif "descriptions" in record:
            descs = record["descriptions"]
            if isinstance(descs, list) and descs:
                abstract = (
                    descs[0] if isinstance(descs[0], str) else descs[0].get("description", "")
                )
            elif isinstance(descs, dict):
                abstract = descs.get("description", "")
            elif isinstance(descs, str):
                abstract = descs

        return str(title) if title else "", str(abstract) if abstract else ""

    def get_triggered_docs(self, limit: int | None = None) -> Generator[dict, None, None]:
        """Yield triggered documents from corpus_bridge.db."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        query = """
            SELECT
                ie.id,
                ie.doc_id,
                ie.payload_json,
                ie.status,
                di.source,
                di.source_file,
                di.title,
                di.metadata_json
            FROM inbox_events ie
            JOIN document_inventory di ON ie.doc_id = di.doc_id
            WHERE ie.status = 'triggered'
            ORDER BY ie.id
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor = conn.execute(query)

        for row in cursor:
            yield dict(row)

        conn.close()

    def count_triggered(self) -> int:
        """Count triggered documents."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM inbox_events WHERE status = 'triggered'")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def count_embedded(self) -> int:
        """Count already embedded documents."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM inbox_events WHERE status = 'embedded'")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def mark_embedded(self, doc_ids: list[int]):
        """Mark documents as embedded in database."""
        conn = sqlite3.connect(self.db_path)
        placeholders = ",".join("?" * len(doc_ids))
        conn.execute(
            f"UPDATE inbox_events SET status = 'embedded', processed_at = ? WHERE id IN ({placeholders})",
            [datetime.utcnow().isoformat()] + doc_ids,
        )
        conn.commit()
        conn.close()

    def process_document(self, doc: dict) -> list[dict]:
        """Process single document into chunks with embeddings."""
        try:
            # Parse metadata - gracefully handle truncated/malformed JSON
            try:
                metadata = json.loads(doc.get("metadata_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                metadata = {}

            try:
                json.loads(doc.get("payload_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

            source = doc.get("source", "")
            source_file = doc.get("source_file", "")

            # Get title and abstract from original JSON file
            json_title, abstract = self._find_record_data(doc, source_file)

            # Use database title if available, otherwise JSON title
            title = doc.get("title") or metadata.get("title", "") or json_title

            # Build text to embed
            text_parts = []
            if title:
                text_parts.append(f"Title: {title}")
            if abstract:
                text_parts.append(f"Abstract: {abstract}")

            full_text = "\n\n".join(text_parts)

            if not full_text.strip():
                return []

            # Chunk the text
            chunks = self.chunker.chunk(full_text)

            if not chunks:
                return []

            # Extract metadata for payload
            university = self._extract_university(source)
            year = metadata.get("date", "")
            if isinstance(year, str) and len(year) >= 4:
                year = year[:4]

            language = metadata.get("language", "unknown")
            doc_type = metadata.get("type", ["unknown"])
            if isinstance(doc_type, list):
                doc_type = doc_type[0] if doc_type else "unknown"

            # Create chunk records
            chunk_records = []
            for i, chunk_text in enumerate(chunks):
                chunk_records.append(
                    {
                        "text": chunk_text,
                        "payload": {
                            "source": "diva",
                            "university": university,
                            "doc_id": doc.get("doc_id", ""),
                            "title": title[:500] if title else "",
                            "year": year,
                            "language": language,
                            "doc_type": doc_type,
                            "chunk_index": i,
                            "content": chunk_text,
                        },
                        "db_id": doc.get("id"),
                    }
                )

            return chunk_records

        except Exception as e:
            self.stats["errors"] += 1
            print(f"ERROR in process_document: {type(e).__name__}: {e}")
            print(f"  doc_id: {doc.get('doc_id', 'unknown')}")
            return []

    def embed_and_upsert(self, chunks: list[dict]):
        """Embed chunks and upsert to Qdrant."""
        if not chunks:
            return

        texts = [c["text"] for c in chunks]

        # Embed all chunks
        embeddings = self.embedder.embed_batch(texts)

        # Build Qdrant points
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            points.append(
                qdrant_models.PointStruct(
                    id=str(uuid.uuid4()), vector=embedding, payload=chunk["payload"]
                )
            )

        # Upsert in batches
        batch_size = self.config["upsert_batch"]
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.qdrant.upsert(collection_name=self.config["collection_name"], points=batch)

        self.stats["chunks_embedded"] += len(chunks)

    def run(self, limit: int | None = None, batch_size: int = 100):
        """Run the embedding pipeline."""
        self.stats["start_time"] = time.time()

        total = self.count_triggered()
        if limit:
            total = min(total, limit)

        print(f"\nProcessing {total:,} triggered DiVA documents...")
        print(f"Batch size: {batch_size}, Target: ~50 docs/sec\n")

        docs_generator = self.get_triggered_docs(limit=limit)

        if RICH_AVAILABLE:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Embedding DiVA docs", total=total)

                batch_chunks = []
                batch_db_ids = []

                for doc in docs_generator:
                    chunks = self.process_document(doc)

                    if chunks:
                        batch_chunks.extend(chunks)
                        batch_db_ids.append(doc["id"])
                        self.stats["chunks_created"] += len(chunks)
                    else:
                        self.stats["docs_skipped"] += 1

                    self.stats["docs_processed"] += 1

                    # Process batch when full
                    if len(batch_chunks) >= batch_size:
                        self.embed_and_upsert(batch_chunks)
                        self.mark_embedded(batch_db_ids)
                        batch_chunks = []
                        batch_db_ids = []

                    progress.update(task, advance=1)

                # Process remaining
                if batch_chunks:
                    self.embed_and_upsert(batch_chunks)
                    self.mark_embedded(batch_db_ids)

        else:
            # Fallback without Rich
            batch_chunks = []
            batch_db_ids = []
            last_report = time.time()

            for _i, doc in enumerate(docs_generator):
                chunks = self.process_document(doc)

                if chunks:
                    batch_chunks.extend(chunks)
                    batch_db_ids.append(doc["id"])
                    self.stats["chunks_created"] += len(chunks)
                else:
                    self.stats["docs_skipped"] += 1

                self.stats["docs_processed"] += 1

                if len(batch_chunks) >= batch_size:
                    self.embed_and_upsert(batch_chunks)
                    self.mark_embedded(batch_db_ids)
                    batch_chunks = []
                    batch_db_ids = []

                # Progress report every 10 seconds
                if time.time() - last_report > 10:
                    elapsed = time.time() - self.stats["start_time"]
                    rate = self.stats["docs_processed"] / elapsed if elapsed > 0 else 0
                    print(
                        f"Progress: {self.stats['docs_processed']:,}/{total:,} "
                        f"({100 * self.stats['docs_processed'] / total:.1f}%) "
                        f"| Rate: {rate:.1f} docs/sec "
                        f"| Chunks: {self.stats['chunks_embedded']:,}"
                    )
                    last_report = time.time()

            if batch_chunks:
                self.embed_and_upsert(batch_chunks)
                self.mark_embedded(batch_db_ids)

        # Final stats
        self._print_summary()

    def _print_summary(self):
        """Print final statistics."""
        elapsed = time.time() - self.stats["start_time"]

        print("\n" + "=" * 60)
        print("DIVA EMBEDDING COMPLETE")
        print("=" * 60)
        print(f"Documents processed: {self.stats['docs_processed']:,}")
        print(f"Documents skipped:   {self.stats['docs_skipped']:,}")
        print(f"Chunks created:      {self.stats['chunks_created']:,}")
        print(f"Chunks embedded:     {self.stats['chunks_embedded']:,}")
        print(f"Errors:              {self.stats['errors']:,}")
        print(f"Time:                {elapsed / 60:.1f} minutes")
        print(f"Rate:                {self.stats['docs_processed'] / elapsed:.1f} docs/sec")

        # Qdrant final count
        info = self.qdrant.get_collection(self.config["collection_name"])
        print(f"\nQdrant collection:   {info.points_count:,} total points")


def show_status():
    """Show current embedding status."""
    db_path = CONFIG["bridge_db"]
    conn = sqlite3.connect(db_path)

    # Get counts by status
    cursor = conn.execute("""
        SELECT status, COUNT(*) as count
        FROM inbox_events
        GROUP BY status
    """)

    if RICH_AVAILABLE:
        table = Table(title="DiVA Embedding Status")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right", style="green")

        total = 0
        for row in cursor:
            table.add_row(row[0], f"{row[1]:,}")
            total += row[1]

        table.add_row("─" * 10, "─" * 10)
        table.add_row("TOTAL", f"{total:,}")

        console.print(table)

        # Qdrant status
        try:
            client = QdrantClient(host=CONFIG["qdrant_host"], port=CONFIG["qdrant_port"])
            info = client.get_collection(CONFIG["collection_name"])
            console.print(
                f"\n[bold]Qdrant '{CONFIG['collection_name']}':[/bold] {info.points_count:,} vectors"
            )
        except Exception as e:
            console.print(f"\n[red]Qdrant error: {e}[/red]")

    else:
        print("\nDiVA Embedding Status:")
        print("-" * 30)
        total = 0
        for row in cursor:
            print(f"{row[0]:15} {row[1]:>10,}")
            total += row[1]
        print("-" * 30)
        print(f"{'TOTAL':15} {total:>10,}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="DiVA Direct Embedding Pipeline")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for embedding")
    parser.add_argument("--limit", type=int, help="Limit number of documents to process")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    embedder = DiVAEmbedder()
    embedder.run(limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
