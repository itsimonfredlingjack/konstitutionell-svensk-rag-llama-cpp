#!/usr/bin/env python3
"""
Local Embedding Pipeline for Swedish Government Documents

Processes PDFs from pdf_cache/, chunks them optimally for Swedish BERT,
embeds with KBLab model, and pushes directly to Qdrant.

Based on research:
- 380 tokens per chunk (optimal for Swedish BERT 512 max)
- 20% overlap (76 tokens ~= 300 chars)
- KBLab/sentence-bert-swedish-cased (768-dim)

Usage:
  python embed_documents.py --source pdf_cache/kommun/
  python embed_documents.py --source pdf_cache/kommun/ --batch-size 50 --workers 4
  python embed_documents.py --resume  # Resume from last checkpoint
"""

import argparse
import hashlib
import logging
import sqlite3
import sys
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import torch

# PDF text extraction (kept self-contained; no juridik-ai dependency)
try:
    import pdfplumber

    _PDF_EXTRACTOR = "pdfplumber"
except ImportError:  # pragma: no cover
    pdfplumber = None
    _PDF_EXTRACTOR = ""

try:
    from PyPDF2 import PdfReader

    _HAS_PYPDF2 = True
except ImportError:  # pragma: no cover
    PdfReader = None
    _HAS_PYPDF2 = False

# Sentence transformers
try:
    from sentence_transformers import SentenceTransformer

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("ERROR: sentence-transformers not installed. Run: pip install sentence-transformers")
    sys.exit(1)

# Qdrant
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    print("ERROR: qdrant-client not installed. Run: pip install qdrant-client")
    sys.exit(1)

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
QDRANT_TIMEOUT = 120  # Longer timeout for large upserts
COLLECTION_NAME = "documents"
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"
EMBEDDING_DIM = 768
CHUNK_TOKENS = 380  # Optimal for Swedish BERT (512 max - room for special tokens)
CHUNK_OVERLAP = 300  # ~20% overlap in characters
UPSERT_BATCH_SIZE = 50  # Smaller batches for Qdrant upserts

# Paths
BASE_DIR = Path(__file__).parent
STATE_DB = BASE_DIR / "data" / "embedding_state.db"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ProcessingStats:
    """Track processing statistics"""

    pdfs_processed: int = 0
    pdfs_failed: int = 0
    chunks_created: int = 0
    chunks_embedded: int = 0
    total_bytes: int = 0
    start_time: float = 0

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time if self.start_time else 0

    @property
    def pdfs_per_minute(self) -> float:
        if self.elapsed_seconds < 1:
            return 0
        return self.pdfs_processed / (self.elapsed_seconds / 60)


class EmbeddingStateDB:
    """SQLite state tracking for resume capability"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                file_hash TEXT PRIMARY KEY,
                file_path TEXT,
                chunks_count INT,
                processed_at TEXT,
                source TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                source_dir TEXT,
                pdfs_processed INT DEFAULT 0,
                chunks_embedded INT DEFAULT 0,
                status TEXT DEFAULT 'running'
            )
        """)
        conn.commit()
        conn.close()

    def is_processed(self, file_hash: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM processed_files WHERE file_hash = ?", (file_hash,))
        result = cur.fetchone()
        conn.close()
        return result is not None

    def mark_processed(self, file_hash: str, file_path: str, chunks_count: int, source: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO processed_files (file_hash, file_path, chunks_count, processed_at, source)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_hash, file_path, chunks_count, datetime.now().isoformat(), source),
        )
        conn.commit()
        conn.close()

    def get_processed_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM processed_files")
        count = cur.fetchone()[0]
        conn.close()
        return count

    def start_run(self, source_dir: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO embedding_runs (started_at, source_dir, status)
            VALUES (?, ?, 'running')
        """,
            (datetime.now().isoformat(), source_dir),
        )
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def finish_run(self, run_id: int, pdfs: int, chunks: int, status: str = "completed"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            UPDATE embedding_runs
            SET finished_at = ?, pdfs_processed = ?, chunks_embedded = ?, status = ?
            WHERE id = ?
        """,
            (datetime.now().isoformat(), pdfs, chunks, status, run_id),
        )
        conn.commit()
        conn.close()


class DocumentEmbedder:
    """Main embedding pipeline"""

    def __init__(
        self,
        qdrant_host: str = QDRANT_HOST,
        qdrant_port: int = QDRANT_PORT,
        collection_name: str = COLLECTION_NAME,
        batch_size: int = 32,
    ):
        self.batch_size = batch_size
        self.collection_name = collection_name

        # Initialize Qdrant
        logger.info(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port}")
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=QDRANT_TIMEOUT)
        self._ensure_collection()

        # Initialize embedding model
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(EMBEDDING_MODEL, device=self.device)
        logger.info(f"Model loaded on {self.device}")

        # Chunking configuration for PDF processing
        self.chunk_tokens = CHUNK_TOKENS
        self.chunk_overlap_chars = CHUNK_OVERLAP

        # State tracking
        self.state_db = EmbeddingStateDB(STATE_DB)
        self.stats = ProcessingStats()

    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist"""
        collections = self.qdrant.get_collections().collections
        collection_names = [c.name for c in collections]

        if self.collection_name not in collection_names:
            logger.info(f"Creating collection: {self.collection_name}")
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=EMBEDDING_DIM, distance=qdrant_models.Distance.COSINE
                ),
            )
        else:
            info = self.qdrant.get_collection(self.collection_name)
            logger.info(f"Collection exists: {info.points_count} points")

    def _file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file for deduplication"""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _extract_source_metadata(self, pdf_path: Path) -> dict:
        """Extract metadata from PDF path structure"""
        parts = pdf_path.parts

        # Try to extract kommun from path like pdf_cache/kommun/0180_stockholm/...
        metadata = {
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
        }

        for i, part in enumerate(parts):
            if part == "kommun" and i + 1 < len(parts):
                kommun_dir = parts[i + 1]
                # Parse kommun code and name: 0180_stockholm -> (0180, stockholm)
                if "_" in kommun_dir:
                    code, name = kommun_dir.split("_", 1)
                    metadata["kommun_code"] = code
                    metadata["kommun_name"] = name.replace("-", " ").title()
                    metadata["source"] = f"kommun:{name}"
                break
            elif part == "myndighet" and i + 1 < len(parts):
                metadata["myndighet"] = parts[i + 1]
                metadata["source"] = f"myndighet:{parts[i + 1]}"
                break

        if "source" not in metadata:
            metadata["source"] = "unknown"

        return metadata

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts"""
        embeddings = self.model.encode(
            texts, batch_size=self.batch_size, show_progress_bar=False, convert_to_tensor=False
        )
        return [emb.tolist() for emb in embeddings]

    def process_pdf(self, pdf_path: Path) -> list[dict]:
        """Process a single PDF and return chunks with metadata."""
        try:
            pages = self._extract_pdf_pages(pdf_path)
            if not pages:
                return []

            # Get metadata from path
            metadata = self._extract_source_metadata(pdf_path)

            # Chunk per page to preserve rough source_page attribution
            results: list[dict] = []
            for page_num, page_text in pages:
                for chunk_index, chunk_text in enumerate(
                    self._chunk_text(
                        page_text,
                        max_tokens=self.chunk_tokens,
                        overlap_chars=self.chunk_overlap_chars,
                    ),
                    start=0,
                ):
                    results.append(
                        {
                            "content": chunk_text,
                            "chunk_index": chunk_index,
                            "source_page": page_num,
                            "token_estimate": self._estimate_tokens(chunk_text),
                            **metadata,
                            "chunk_id": str(uuid.uuid4()),
                        }
                    )

            return results

        except Exception as e:
            logger.warning(f"Failed to process {pdf_path}: {e}")
            return []

    def _estimate_tokens(self, text: str) -> int:
        # Rough heuristic: ~4 chars/token for Latin scripts.
        return max(1, int(len(text) / 4))

    def _chunk_text(self, text: str, max_tokens: int, overlap_chars: int) -> list[str]:
        # Convert token budget to approximate char budget.
        max_chars = max(200, max_tokens * 4)
        if not text:
            return []

        chunks: list[str] = []
        step = max(1, max_chars - overlap_chars)
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(text_len, start + max_chars)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            start += step

        return chunks

    def _extract_pdf_pages(self, pdf_path: Path) -> list[tuple[int, str]]:
        """Return list of (1-based page_number, text)."""
        if pdfplumber is not None and _PDF_EXTRACTOR == "pdfplumber":
            pages: list[tuple[int, str]] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    pages.append((idx, (page.extract_text() or "")))
            return pages

        if _HAS_PYPDF2 and PdfReader is not None:
            pages = []
            reader = PdfReader(str(pdf_path))
            for idx, page in enumerate(reader.pages, start=1):
                pages.append((idx, (page.extract_text() or "")))
            return pages

        raise RuntimeError(
            "No PDF extractor available. Install 'pdfplumber' or 'PyPDF2' to process PDFs."
        )

    def find_pdfs(
        self, source_dir: Path, skip_processed: bool = True
    ) -> Generator[Path, None, None]:
        """Find all PDFs in source directory, optionally skipping processed ones"""
        for pdf_path in source_dir.rglob("*.pdf"):
            if skip_processed:
                file_hash = self._file_hash(pdf_path)
                if self.state_db.is_processed(file_hash):
                    continue
            yield pdf_path

    def upsert_to_qdrant(self, chunks: list[dict], embeddings: list[list[float]]):
        """Upsert chunks with embeddings to Qdrant"""
        points = []

        for chunk, embedding in zip(chunks, embeddings):
            point_id = str(uuid.uuid4())

            # Prepare payload (everything except the embedding)
            payload = {
                "content": chunk["content"],
                "source": chunk.get("source", "unknown"),
                "file_name": chunk.get("file_name", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "source_page": chunk.get("source_page", 1),
                "token_estimate": chunk.get("token_estimate", 0),
            }

            # Add optional metadata
            for key in ["kommun_code", "kommun_name", "myndighet", "section_header"]:
                if chunk.get(key):
                    payload[key] = chunk[key]

            points.append(qdrant_models.PointStruct(id=point_id, vector=embedding, payload=payload))

        # Upsert in smaller batches to avoid timeouts
        for i in range(0, len(points), UPSERT_BATCH_SIZE):
            batch = points[i : i + UPSERT_BATCH_SIZE]
            self.qdrant.upsert(collection_name=self.collection_name, points=batch)

    def process_directory(
        self, source_dir: Path, max_files: int | None = None, skip_processed: bool = True
    ):
        """Process all PDFs in a directory"""
        self.stats = ProcessingStats()
        self.stats.start_time = time.time()

        run_id = self.state_db.start_run(str(source_dir))
        logger.info(f"Starting embedding run #{run_id}")
        logger.info(f"Source: {source_dir}")
        logger.info(f"Skip processed: {skip_processed}")

        # Collect PDFs
        pdfs = list(self.find_pdfs(source_dir, skip_processed))
        total_pdfs = len(pdfs)

        if max_files:
            pdfs = pdfs[:max_files]

        logger.info(f"Found {total_pdfs} PDFs, processing {len(pdfs)}")

        # Process in batches for embedding efficiency
        chunk_buffer = []
        processed_files = []  # Track files for state update

        try:
            for i, pdf_path in enumerate(pdfs):
                # Process PDF
                file_hash = self._file_hash(pdf_path)
                chunks = self.process_pdf(pdf_path)

                if chunks:
                    chunk_buffer.extend(chunks)
                    processed_files.append((file_hash, str(pdf_path), len(chunks)))
                    self.stats.pdfs_processed += 1
                    self.stats.chunks_created += len(chunks)
                    self.stats.total_bytes += pdf_path.stat().st_size
                else:
                    self.stats.pdfs_failed += 1

                # Embed and upsert when buffer is full
                if len(chunk_buffer) >= self.batch_size * 2:
                    self._flush_buffer(chunk_buffer, processed_files)
                    chunk_buffer = []
                    processed_files = []

                # Progress logging
                if (i + 1) % 10 == 0:
                    pct = (i + 1) / len(pdfs) * 100
                    rate = self.stats.pdfs_per_minute
                    logger.info(
                        f"Progress: {i + 1}/{len(pdfs)} ({pct:.1f}%) | "
                        f"Chunks: {self.stats.chunks_embedded} | "
                        f"Rate: {rate:.1f} PDFs/min"
                    )

            # Flush remaining
            if chunk_buffer:
                self._flush_buffer(chunk_buffer, processed_files)

            self.state_db.finish_run(
                run_id, self.stats.pdfs_processed, self.stats.chunks_embedded, "completed"
            )

        except KeyboardInterrupt:
            logger.info("Interrupted! Saving state...")
            if chunk_buffer:
                self._flush_buffer(chunk_buffer, processed_files)
            self.state_db.finish_run(
                run_id, self.stats.pdfs_processed, self.stats.chunks_embedded, "interrupted"
            )
            raise

        except Exception as e:
            logger.error(f"Error during processing: {e}")
            self.state_db.finish_run(
                run_id, self.stats.pdfs_processed, self.stats.chunks_embedded, f"failed: {e!s}"
            )
            raise

        # Final summary
        elapsed = self.stats.elapsed_seconds
        logger.info("=" * 60)
        logger.info("EMBEDDING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"PDFs processed: {self.stats.pdfs_processed}")
        logger.info(f"PDFs failed: {self.stats.pdfs_failed}")
        logger.info(f"Chunks embedded: {self.stats.chunks_embedded}")
        logger.info(f"Total size: {self.stats.total_bytes / 1024 / 1024:.1f} MB")
        logger.info(f"Time: {elapsed / 60:.1f} minutes")
        logger.info(f"Rate: {self.stats.pdfs_per_minute:.1f} PDFs/min")

        # Verify collection
        info = self.qdrant.get_collection(self.collection_name)
        logger.info(f"Collection now has {info.points_count} total points")

    def _flush_buffer(self, chunks: list[dict], processed_files: list[tuple]):
        """Embed and upsert chunk buffer"""
        if not chunks:
            return

        # Extract texts
        texts = [c["content"] for c in chunks]

        # Embed
        logger.debug(f"Embedding {len(texts)} chunks...")
        embeddings = self.embed_batch(texts)

        # Upsert to Qdrant
        self.upsert_to_qdrant(chunks, embeddings)
        self.stats.chunks_embedded += len(chunks)

        # Mark files as processed
        for file_hash, file_path, chunk_count in processed_files:
            source = chunks[0].get("source", "unknown") if chunks else "unknown"
            self.state_db.mark_processed(file_hash, file_path, chunk_count, source)


def main():
    parser = argparse.ArgumentParser(description="Embed Swedish government documents into Qdrant")
    parser.add_argument(
        "--source",
        type=Path,
        default=BASE_DIR / "pdf_cache" / "kommun",
        help="Source directory containing PDFs",
    )
    parser.add_argument(
        "--batch-size", type=int, default=32, help="Batch size for embeddings (default: 32)"
    )
    parser.add_argument(
        "--max-files", type=int, default=None, help="Maximum number of files to process"
    )
    parser.add_argument(
        "--no-resume", action="store_true", help="Don't skip already processed files"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=COLLECTION_NAME,
        help=f"Qdrant collection name (default: {COLLECTION_NAME})",
    )
    parser.add_argument("--stats", action="store_true", help="Show processing statistics and exit")

    args = parser.parse_args()

    # Stats mode
    if args.stats:
        state_db = EmbeddingStateDB(STATE_DB)
        processed = state_db.get_processed_count()
        print(f"Processed files: {processed}")

        if QDRANT_AVAILABLE:
            try:
                client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
                info = client.get_collection(args.collection)
                print(f"Qdrant collection '{args.collection}': {info.points_count} points")
            except Exception as e:
                print(f"Qdrant error: {e}")
        return

    # Validate source
    if not args.source.exists():
        print(f"ERROR: Source directory not found: {args.source}")
        sys.exit(1)

    # Run embedding
    embedder = DocumentEmbedder(collection_name=args.collection, batch_size=args.batch_size)

    embedder.process_directory(
        source_dir=args.source, max_files=args.max_files, skip_processed=not args.no_resume
    )


if __name__ == "__main__":
    main()
