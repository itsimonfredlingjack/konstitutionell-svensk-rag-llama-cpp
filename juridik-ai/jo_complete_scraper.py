#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - JO (JUSTITIEOMBUDSMANNEN)

Complete JO scraper that:
1. Downloads ämbetsberättelser (annual reports) 1971-2024
2. Scrapes modern decisions from jo.se database (2001+)
3. Indexes all content to ChromaDB
4. Returns JSON status report

ChromaDB:
- Path: /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data
- Collection: swedish_gov_docs
- Embedding: KBLab/sentence-bert-swedish-cased
- Metadata source: "jo"
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

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
    print(
        "WARNING: ChromaDB not available. Install with: pip install chromadb sentence-transformers"
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data/jo/jo_scraper.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Config
BASE_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai")
DATA_DIR = BASE_DIR / "data" / "jo"
CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
COLLECTION_NAME = "swedish_gov_docs"
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"

# JO URLs
JO_BASE = "https://www.jo.se"
JO_SEARCH = f"{JO_BASE}/jo-beslut/sokresultat/"
JO_ANNUAL_REPORTS_PAGE = f"{JO_BASE}/om-jo/ambetsberattelser/"

# Rate limiting
RATE_LIMIT_DELAY = 15  # seconds between requests


class JOWebScraper:
    """Scrape modern JO decisions from the web database"""

    def __init__(self, delay: float = 15.0):
        """Initialize web scraper with rate limiting"""
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            }
        )
        self.decisions = []

    def scrape_search_results(
        self, query: str = "", year_from: int = 2001, year_to: int = 2024
    ) -> list[dict[str, Any]]:
        """
        Scrape JO decisions from search results

        Args:
            query: Search query (empty for all)
            year_from: Start year
            year_to: End year

        Returns:
            List of decision dictionaries
        """
        decisions = []

        # Try different search strategies
        strategies = [
            {"query": "", "desc": "all decisions"},
            {"query": "kritik", "desc": "decisions with criticism"},
            {"query": "uttalande", "desc": "statements"},
        ]

        for strategy in strategies:
            logger.info(f"Trying strategy: {strategy['desc']}")

            # Try to fetch search page
            try:
                time.sleep(self.delay)

                # Build query parameters
                params = {}
                if strategy["query"]:
                    params["query"] = strategy["query"]

                url = JO_SEARCH
                if params:
                    url += "?" + urlencode(params)

                logger.info(f"Fetching: {url}")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.text, "html.parser")

                # Try to find decision entries
                # Note: This is a best-effort parser. JO's HTML structure may vary.
                decision_links = soup.find_all(
                    "a", href=lambda h: h and "/jo-beslut/" in h and h.endswith(".pdf")
                )

                for link in decision_links:
                    pdf_url = urljoin(JO_BASE, link.get("href"))

                    # Extract metadata from link text or parent elements
                    text = link.get_text(strip=True)
                    parent_text = link.parent.get_text(strip=True) if link.parent else ""

                    decision = {
                        "url_pdf": pdf_url,
                        "title": text or "Okänd",
                        "context": parent_text,
                        "source": "jo_web_scrape",
                        "strategy": strategy["desc"],
                        "scraped_at": datetime.now().isoformat(),
                    }

                    decisions.append(decision)
                    logger.info(f"Found decision: {decision['title']}")

                logger.info(f"Strategy '{strategy['desc']}' found {len(decision_links)} decisions")

            except requests.RequestException as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error parsing search results: {e}", exc_info=True)
                continue

        # Deduplicate by URL
        unique_decisions = {}
        for dec in decisions:
            unique_decisions[dec["url_pdf"]] = dec

        self.decisions = list(unique_decisions.values())
        logger.info(f"Total unique decisions found: {len(self.decisions)}")

        return self.decisions

    def scrape_annual_reports_page(self) -> list[dict[str, Any]]:
        """
        Scrape the ämbetsberättelser page for all PDF links

        Returns:
            List of annual report metadata
        """
        reports = []

        try:
            time.sleep(self.delay)
            logger.info(f"Fetching annual reports page: {JO_ANNUAL_REPORTS_PAGE}")

            response = self.session.get(JO_ANNUAL_REPORTS_PAGE, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find all links to riksdagen.se PDFs (annual reports are hosted there)
            pdf_links = soup.find_all("a", href=lambda h: h and "riksdagen.se" in h and "fil/" in h)

            for link in pdf_links:
                url = link.get("href")

                # Try to extract year from link text or nearby text
                text = link.get_text(strip=True)
                year = None

                # Try to extract year (format: "2024", "2023/24", etc.)
                import re

                year_match = re.search(r"(19|20)\d{2}", text)
                if year_match:
                    year = int(year_match.group(0))

                report = {
                    "url_pdf": url,
                    "year": year,
                    "title": text or "Ämbetsberättelse",
                    "source": "jo_annual_report",
                    "scraped_at": datetime.now().isoformat(),
                }

                reports.append(report)
                logger.info(f"Found annual report: {year} - {url}")

            logger.info(f"Total annual reports found: {len(reports)}")

        except Exception as e:
            logger.error(f"Failed to scrape annual reports page: {e}", exc_info=True)

        return reports


class JOChromaDBIndexer:
    """Index JO content to ChromaDB"""

    def __init__(self, db_path: Path = CHROMADB_PATH, collection_name: str = COLLECTION_NAME):
        """Initialize ChromaDB client"""
        if not CHROMA_AVAILABLE:
            logger.error("ChromaDB not available!")
            self.client = None
            self.collection = None
            return

        # Create persistent client
        db_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(db_path))

        # Try to use Swedish BERT model for embeddings
        try:
            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            )
            logger.info(f"Using embedding model: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.warning(f"Failed to load {EMBEDDING_MODEL}, using default: {e}")
            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"
            )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.ef,
            metadata={"description": "Swedish government documents - JO decisions and reports"},
        )

        logger.info(f"Connected to ChromaDB collection: {collection_name}")
        logger.info(f"Current document count: {self.collection.count()}")

    def index_pdf(self, pdf_path: Path, metadata: dict[str, Any], processor: PDFProcessor) -> int:
        """
        Extract text from PDF and index to ChromaDB

        Args:
            pdf_path: Path to PDF file
            metadata: Metadata about the document
            processor: PDF processor instance

        Returns:
            Number of chunks indexed
        """
        if not self.collection:
            return 0

        try:
            # Check if already indexed (simple check based on filename)
            doc_id_prefix = f"jo_{pdf_path.stem}_"
            existing = self.collection.get(ids=[f"{doc_id_prefix}0"])
            if existing and existing["ids"]:
                logger.debug(f"Skipping {pdf_path.name} (already indexed)")
                return 0

            # Extract text
            text, pdf_type = processor.extract_text(str(pdf_path))
            if not text.strip():
                logger.warning(f"No text extracted from {pdf_path}")
                return 0

            # Chunk text
            chunks = processor.chunk_document(text, pdf_source=str(pdf_path))
            if not chunks:
                logger.warning(f"No chunks created from {pdf_path}")
                return 0

            # Prepare for ChromaDB
            documents = [chunk.content for chunk in chunks]
            ids = [f"{doc_id_prefix}{i}" for i in range(len(chunks))]

            # Merge metadata
            metadatas = []
            for i, chunk in enumerate(chunks):
                chunk_meta = {
                    "source": "jo",
                    "source_file": str(pdf_path),
                    "chunk_index": i,
                    "page": chunk.source_page,
                    "pdf_type": pdf_type.value,
                    **metadata,  # Add custom metadata
                }
                metadatas.append(chunk_meta)

            # Index to ChromaDB
            self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

            logger.info(f"Indexed {pdf_path.name}: {len(chunks)} chunks")
            return len(chunks)

        except Exception as e:
            logger.error(f"Failed to index {pdf_path}: {e}", exc_info=True)
            return 0


def main():
    """Main orchestration function"""

    print("=" * 80)
    print("OPERATION MYNDIGHETS-SWEEP - JO (JUSTITIEOMBUDSMANNEN)")
    print("=" * 80)
    print()

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize stats
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
        # Step 1: Download ämbetsberättelser (1971-2024)
        logger.info("STEP 1: Downloading ämbetsberättelser (1971-2024)")

        downloader = JODownloader(output_dir=str(DATA_DIR), rate_limit_delay=RATE_LIMIT_DELAY)

        download_stats = downloader.download_range(1971, 2024)
        logger.info(f"Downloaded: {download_stats['successful']} reports")

        # Step 2: Scrape modern decisions from web
        logger.info("STEP 2: Scraping modern decisions from jo.se")

        web_scraper = JOWebScraper(delay=RATE_LIMIT_DELAY)
        web_decisions = web_scraper.scrape_search_results(year_from=2001, year_to=2024)

        # Also scrape the annual reports page
        annual_reports = web_scraper.scrape_annual_reports_page()

        logger.info(f"Found {len(web_decisions)} web decisions")
        logger.info(f"Found {len(annual_reports)} annual report links")

        # Step 3: Initialize ChromaDB indexer
        logger.info("STEP 3: Initializing ChromaDB indexer")

        indexer = JOChromaDBIndexer()
        if not indexer.collection:
            stats["status"] = "FLAGGAD"
            stats["errors"].append("ChromaDB not available")
            logger.error("Cannot continue without ChromaDB")
            return stats

        processor = PDFProcessor(max_tokens=1000, chunk_overlap=100)

        # Step 4: Index all PDFs to ChromaDB
        logger.info("STEP 4: Indexing PDFs to ChromaDB")

        total_chunks = 0
        indexed_docs = 0

        # Index downloaded ämbetsberättelser
        for pdf_path in sorted(DATA_DIR.glob("jo_ambetsberattelse_*.pdf")):
            year = pdf_path.stem.split("_")[-1]
            metadata = {
                "document_type": "ambetsberattelse",
                "year": year,
                "authority": "JO",
            }

            chunks = indexer.index_pdf(pdf_path, metadata, processor)
            if chunks > 0:
                total_chunks += chunks
                indexed_docs += 1

        stats["docs_found"] = len(list(DATA_DIR.glob("*.pdf")))
        stats["docs_indexed"] = indexed_docs
        stats["chunks_indexed"] = total_chunks

        # Step 5: Check if we should flag
        if stats["docs_found"] < 100:
            stats["status"] = "FLAGGAD"
            stats["errors"].append(
                f'SIMON: JO verkar ha problem - bara {stats["docs_found"]} dokument hittade'
            )
            logger.warning(f"FLAGGED: Only found {stats['docs_found']} documents (expected >100)")

        # Save web scraped metadata for future reference
        web_data_file = DATA_DIR / "web_scraped_decisions.json"
        with open(web_data_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "decisions": web_decisions,
                    "annual_reports": annual_reports,
                    "scraped_at": datetime.now().isoformat(),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info(f"Saved web metadata to {web_data_file}")

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        stats["status"] = "INTERRUPTED"
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        stats["status"] = "ERROR"
        stats["errors"].append(str(e))

    # Final stats
    stats["completed_at"] = datetime.now().isoformat()
    stats["chromadb_total"] = indexer.collection.count() if indexer and indexer.collection else 0

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
