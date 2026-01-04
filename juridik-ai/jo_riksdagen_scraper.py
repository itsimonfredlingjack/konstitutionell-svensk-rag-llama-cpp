#!/usr/bin/env python3
"""
JO RIKSDAGEN SCRAPER
Downloads JO ämbetsberättelser from Riksdagen and indexes to ChromaDB

Uses the links we found from WebFetch:
- https://data.riksdagen.se/fil/F16AE8EA-EF61-40E9-B9CA-1BFAB601A753 (2024)
- etc.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ChromaDB
try:
    import chromadb
    from chromadb.utils import embedding_functions

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

# PDF processing
sys.path.insert(0, str(Path(__file__).parent))
from pipelines.pdf_processor import PDFProcessor

# Config
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data/jo")
CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
COLLECTION_NAME = "swedish_gov_docs"

# Known JO reports from Riksdagen (from our WebFetch results)
RIKSDAGEN_REPORTS = [
    {"year": 2024, "url": "https://data.riksdagen.se/fil/F16AE8EA-EF61-40E9-B9CA-1BFAB601A753"},
    {"year": 2023, "url": "https://data.riksdagen.se/fil/189F04C1-7581-489B-971A-93A236E360DC"},
    {"year": 2022, "url": "https://data.riksdagen.se/fil/2356E145-54F2-4389-A626-A899D315C31C"},
]


def download_pdf(url: str, save_path: Path, delay: float = 5.0) -> bool:
    """Download PDF with rate limiting"""
    try:
        if save_path.exists():
            logger.info(f"Already exists: {save_path.name}")
            return True

        logger.info(f"Downloading from {url}")
        time.sleep(delay)

        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = save_path.stat().st_size
        logger.info(f"Downloaded {save_path.name} ({file_size / 1024 / 1024:.1f} MB)")

        return file_size > 1000

    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def index_to_chromadb(pdf_path: Path, metadata: dict, processor: PDFProcessor) -> int:
    """Index PDF to ChromaDB"""

    if not CHROMA_AVAILABLE:
        logger.error("ChromaDB not available")
        return 0

    try:
        # Connect to ChromaDB - use EXISTING collection without specifying embedding function
        client = chromadb.PersistentClient(path=str(CHROMADB_PATH))

        # Get existing collection (don't specify embedding function to avoid conflict)
        try:
            collection = client.get_collection(name=COLLECTION_NAME)
            logger.info(f"Using existing collection: {COLLECTION_NAME}")
        except:
            # Collection doesn't exist, create it
            logger.info(f"Creating new collection: {COLLECTION_NAME}")
            # Use default embedding function
            collection = client.create_collection(name=COLLECTION_NAME)

        # Check if already indexed
        doc_id_prefix = f"jo_{pdf_path.stem}_"
        try:
            existing = collection.get(ids=[f"{doc_id_prefix}0"], limit=1)
            if existing and existing.get("ids"):
                logger.info(f"Already indexed: {pdf_path.name}")
                return 0
        except:
            pass  # Doesn't exist, continue

        # Extract text
        logger.info(f"Extracting text from {pdf_path.name}")
        text, pdf_type = processor.extract_text(str(pdf_path))

        if not text.strip():
            logger.warning(f"No text extracted from {pdf_path}")
            return 0

        # Chunk
        chunks = processor.chunk_document(text, pdf_source=str(pdf_path))
        if not chunks:
            logger.warning("No chunks created")
            return 0

        # Prepare for indexing
        documents = [chunk.content for chunk in chunks]
        ids = [f"{doc_id_prefix}{i}" for i in range(len(chunks))]

        metadatas = []
        for i, chunk in enumerate(chunks):
            chunk_meta = {
                "source": "jo",
                "source_file": str(pdf_path),
                "chunk_index": i,
                "page": chunk.source_page,
                "pdf_type": pdf_type.value,
                **metadata,
            }
            metadatas.append(chunk_meta)

        # Add to ChromaDB
        logger.info(f"Indexing {len(chunks)} chunks to ChromaDB")
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

        logger.info(f"✅ Indexed {pdf_path.name}: {len(chunks)} chunks")
        return len(chunks)

    except Exception as e:
        logger.error(f"Failed to index {pdf_path}: {e}", exc_info=True)
        return 0


def main():
    """Main function"""

    print("=" * 80)
    print("JO RIKSDAGEN SCRAPER")
    print("=" * 80)
    print()

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    stats = {
        "myndighet": "JO",
        "status": "OK",
        "docs_found": 0,
        "docs_indexed": 0,
        "chunks_indexed": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
    }

    try:
        # Step 1: Download PDFs from Riksdagen
        logger.info("STEP 1: Downloading JO reports from Riksdagen")

        downloaded = []
        for report in RIKSDAGEN_REPORTS:
            filename = f"jo_ambetsberattelse_{report['year']}.pdf"
            save_path = DATA_DIR / filename

            if download_pdf(report["url"], save_path, delay=5.0):
                downloaded.append({"path": save_path, "year": report["year"]})
                stats["docs_found"] += 1

        logger.info(f"Downloaded {len(downloaded)} reports")

        # Step 2: Index to ChromaDB
        logger.info("STEP 2: Indexing to ChromaDB")

        processor = PDFProcessor(max_tokens=1000, chunk_overlap=100)

        total_chunks = 0
        for doc in downloaded:
            metadata = {
                "document_type": "ambetsberattelse",
                "year": doc["year"],
                "authority": "JO",
            }

            chunks = index_to_chromadb(doc["path"], metadata, processor)
            if chunks > 0:
                total_chunks += chunks
                stats["docs_indexed"] += 1

        stats["chunks_indexed"] = total_chunks

        # Check if we should flag
        if stats["docs_found"] < 100:
            stats["status"] = "FLAGGAD"
            stats["errors"].append(
                f'SIMON: JO verkar ha problem - bara {stats["docs_found"]} dokument hittade'
            )
            logger.warning(f"FLAGGED: Only {stats['docs_found']} documents (expected >100)")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        stats["status"] = "ERROR"
        stats["errors"].append(str(e))

    # Final stats
    stats["completed_at"] = datetime.now().isoformat()

    # Get ChromaDB count
    if CHROMA_AVAILABLE:
        try:
            client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
            collection = client.get_collection(name=COLLECTION_NAME)
            stats["chromadb_total"] = collection.count()
        except:
            stats["chromadb_total"] = 0

    # Print summary
    print()
    print("=" * 80)
    print("OPERATION COMPLETE")
    print("=" * 80)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print("=" * 80)

    # Save stats
    stats_file = DATA_DIR / "scrape_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info(f"Stats saved to {stats_file}")

    return stats


if __name__ == "__main__":
    stats = main()

    # Exit with error code if flagged or error
    if stats["status"] in ["FLAGGAD", "ERROR"]:
        sys.exit(1)

    sys.exit(0)
