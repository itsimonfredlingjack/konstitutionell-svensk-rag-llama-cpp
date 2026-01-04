#!/usr/bin/env python3
"""
TEST VERSION - JO Scraper
Tests functionality with limited scope (2020-2024 only)
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import existing tools
from pipelines.jo_downloader import JODownloader
from pipelines.pdf_processor import PDFProcessor

# ChromaDB imports
try:
    import chromadb
    from chromadb.utils import embedding_functions

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("WARNING: ChromaDB not available")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Config
BASE_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai")
DATA_DIR = BASE_DIR / "data" / "jo"
CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
COLLECTION_NAME = "swedish_gov_docs"

# JO URLs
JO_BASE = "https://www.jo.se"
JO_SEARCH = f"{JO_BASE}/jo-beslut/sokresultat/"

# Rate limiting
RATE_LIMIT_DELAY = 5  # Faster for testing


def test_web_scraping():
    """Test web scraping functionality"""
    logger.info("Testing web scraping...")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})

    try:
        logger.info(f"Fetching: {JO_SEARCH}")
        response = session.get(JO_SEARCH, timeout=30)
        response.raise_for_status()

        # Save HTML for inspection
        debug_file = DATA_DIR / "debug_search_page.html"
        debug_file.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(response.text)

        logger.info(f"Saved debug HTML to {debug_file}")

        # Parse
        soup = BeautifulSoup(response.text, "html.parser")

        # Try to find any decision-related links
        all_links = soup.find_all("a")
        pdf_links = [link for link in all_links if link.get("href", "").endswith(".pdf")]

        logger.info(f"Found {len(all_links)} total links")
        logger.info(f"Found {len(pdf_links)} PDF links")

        for i, link in enumerate(pdf_links[:5], 1):  # Show first 5
            logger.info(f"  PDF {i}: {link.get('href')} - {link.get_text(strip=True)[:50]}")

        return len(pdf_links) > 0

    except Exception as e:
        logger.error(f"Web scraping test failed: {e}", exc_info=True)
        return False


def test_download():
    """Test downloading a few annual reports"""
    logger.info("Testing PDF downloads (2020-2024)...")

    try:
        downloader = JODownloader(
            output_dir=str(DATA_DIR),
            rate_limit_delay=2.0,  # Faster for testing
        )

        stats = downloader.download_range(2020, 2024)

        logger.info(f"Download stats: {stats}")
        return stats["successful"] > 0

    except Exception as e:
        logger.error(f"Download test failed: {e}", exc_info=True)
        return False


def test_chromadb():
    """Test ChromaDB connection and indexing"""
    logger.info("Testing ChromaDB...")

    if not CHROMA_AVAILABLE:
        logger.error("ChromaDB not available!")
        return False

    try:
        # Connect
        client = chromadb.PersistentClient(path=str(CHROMADB_PATH))

        # Try to use Swedish BERT
        try:
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="KBLab/sentence-bert-swedish-cased"
            )
            logger.info("Using Swedish BERT model")
        except:
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"
            )
            logger.info("Using default multilingual model")

        # Get or create collection
        collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)

        current_count = collection.count()
        logger.info(f"Current documents in collection: {current_count}")

        # Test indexing with a sample document
        test_doc = "JO kritiserade Migrationsverket för lång handläggningstid i asylärenden."
        test_id = "jo_test_" + datetime.now().strftime("%Y%m%d%H%M%S")

        collection.upsert(
            documents=[test_doc], metadatas=[{"source": "jo", "test": True}], ids=[test_id]
        )

        logger.info(f"Successfully indexed test document: {test_id}")

        # Verify
        new_count = collection.count()
        logger.info(f"New count: {new_count}")

        return new_count > current_count

    except Exception as e:
        logger.error(f"ChromaDB test failed: {e}", exc_info=True)
        return False


def test_pdf_processing():
    """Test PDF processing if any PDFs exist"""
    logger.info("Testing PDF processing...")

    try:
        pdf_files = list(DATA_DIR.glob("*.pdf"))

        if not pdf_files:
            logger.warning("No PDFs to test")
            return None

        processor = PDFProcessor(max_tokens=1000, chunk_overlap=100)

        # Test first PDF
        test_pdf = pdf_files[0]
        logger.info(f"Testing with: {test_pdf}")

        text, pdf_type = processor.extract_text(str(test_pdf))
        logger.info(f"Extracted {len(text)} characters, type: {pdf_type}")

        chunks = processor.chunk_document(text, pdf_source=str(test_pdf))
        logger.info(f"Created {len(chunks)} chunks")

        return len(chunks) > 0

    except Exception as e:
        logger.error(f"PDF processing test failed: {e}", exc_info=True)
        return False


def main():
    """Run all tests"""
    print("=" * 80)
    print("JO SCRAPER TEST SUITE")
    print("=" * 80)
    print()

    results = {}

    # Test 1: Web scraping
    print("[1/4] Testing web scraping...")
    results["web_scraping"] = test_web_scraping()
    print(f"Result: {'✅ PASS' if results['web_scraping'] else '❌ FAIL'}")
    print()

    # Test 2: PDF downloads
    print("[2/4] Testing PDF downloads...")
    results["downloads"] = test_download()
    print(f"Result: {'✅ PASS' if results['downloads'] else '❌ FAIL'}")
    print()

    # Test 3: PDF processing
    print("[3/4] Testing PDF processing...")
    results["pdf_processing"] = test_pdf_processing()
    print(
        f"Result: {'✅ PASS' if results['pdf_processing'] else '⏭️  SKIP' if results['pdf_processing'] is None else '❌ FAIL'}"
    )
    print()

    # Test 4: ChromaDB
    print("[4/4] Testing ChromaDB...")
    results["chromadb"] = test_chromadb()
    print(f"Result: {'✅ PASS' if results['chromadb'] else '❌ FAIL'}")
    print()

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    for test, result in results.items():
        status = "✅ PASS" if result else ("⏭️  SKIP" if result is None else "❌ FAIL")
        print(f"{test:20s} {status}")
    print("=" * 80)

    # Overall result
    passed = sum(1 for r in results.values() if r is True)
    total = len([r for r in results.values() if r is not None])

    print(f"\nPassed: {passed}/{total}")

    return 0 if all(r for r in results.values() if r is not None) else 1


if __name__ == "__main__":
    sys.exit(main())
