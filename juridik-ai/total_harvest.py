#!/usr/bin/env python3
"""
OPERATION: TOTAL HARVEST
Massiv parallell crawl-operation för att nå 100,000 dokument i ChromaDB.

Prioritetsordning:
1. SOU (kritiskt för juridisk research)
2. Interpellationer (politisk kontext)
3. Motioner (2000-2014, äldre)
4. JO-beslut (myndighetskritik)
5. Skriftliga frågor (volym-fyllnad)
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from cli.brain import get_brain
from pipelines.jo_downloader import JODownloader
from pipelines.pdf_processor import PDFProcessor
from pipelines.riksdagen_client import RiksdagenClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)-8s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("total_harvest.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Config
BASE_DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data")
RIKSDAGEN_DIR = BASE_DATA_DIR / "riksdagen"
JO_DIR = BASE_DATA_DIR / "jo"
TARGET_DOCUMENTS = 100_000
REPORT_INTERVAL = 5_000  # Report every 5k documents


class HarvestStats:
    """Track harvest statistics"""

    def __init__(self):
        self.total_downloaded = 0
        self.total_processed = 0
        self.total_chunks = 0
        self.failed = 0
        self.start_time = datetime.now()
        self.last_report = 0

    def update(self, downloaded: int, processed: int, chunks: int, failed: int = 0):
        self.total_downloaded += downloaded
        self.total_processed += processed
        self.total_chunks += chunks
        self.failed += failed

    def should_report(self) -> bool:
        """Check if we should report progress"""
        if self.total_chunks - self.last_report >= REPORT_INTERVAL:
            self.last_report = self.total_chunks
            return True
        return False

    def get_status(self) -> dict:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "downloaded": self.total_downloaded,
            "processed": self.total_processed,
            "chunks": self.total_chunks,
            "failed": self.failed,
            "elapsed_seconds": elapsed,
            "chunks_per_second": self.total_chunks / max(1, elapsed),
            "estimated_time_to_100k": (TARGET_DOCUMENTS - self.total_chunks)
            / max(0.1, self.total_chunks / max(1, elapsed)),
        }


def process_pdf_to_chromadb(pdf_path: Path, brain, processor: PDFProcessor) -> int:
    """Process a single PDF and add chunks to ChromaDB"""
    try:
        # Check if already processed (simple check - could be improved)
        doc_id_prefix = f"{pdf_path.stem}_"
        existing = brain.collection.get(ids=[f"{doc_id_prefix}0"])  # Check first chunk
        if existing and existing["ids"]:
            logger.debug(f"⏭️  Skipping {pdf_path.name} (already in ChromaDB)")
            return 0

        # Extract text
        text, pdf_type = processor.extract_text(str(pdf_path))
        if not text.strip():
            logger.warning(f"⚠️  No text extracted from {pdf_path}")
            return 0

        # Chunk text
        chunks = processor.chunk_document(text, pdf_source=str(pdf_path))
        if not chunks:
            logger.warning(f"⚠️  No chunks created from {pdf_path}")
            return 0

        # Add to ChromaDB
        documents = [chunk.content for chunk in chunks]
        ids = [f"{pdf_path.stem}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source": str(pdf_path),
                "chunk_index": chunk.chunk_index,
                "page": chunk.source_page,
                "pdf_type": pdf_type.value,
                "doktyp": pdf_path.parent.name
                if pdf_path.parent.name != "riksdagen"
                else "unknown",
            }
            for chunk in chunks
        ]

        brain.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

        logger.info(f"✅ Processed {pdf_path.name}: {len(chunks)} chunks")
        return len(chunks)

    except Exception as e:
        logger.error(f"❌ Failed to process {pdf_path}: {e}", exc_info=True)
        return 0


def harvest_sou(
    client: RiksdagenClient, brain, processor: PDFProcessor, stats: HarvestStats
) -> int:
    """Harvest SOU documents (PRIORITY 1)"""
    logger.info("🎯 PRIORITY 1: Starting SOU harvest (2000-2024)")

    # Search for SOU documents
    documents = client.search_documents(doktyp="sou", year_from=2000, year_to=2024, page_size=500)

    logger.info(f"Found {len(documents)} SOU documents")

    sou_dir = RIKSDAGEN_DIR / "sou"
    sou_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    processed = 0
    chunks = 0

    for i, doc in enumerate(documents, 1):
        if stats.total_chunks >= TARGET_DOCUMENTS:
            logger.info("Target reached, stopping SOU harvest")
            break

        try:
            # Download PDF
            pdf_path = client.download_document(doc, file_format="pdf")
            if pdf_path:
                downloaded += 1
                # Process to ChromaDB
                chunks_added = process_pdf_to_chromadb(pdf_path, brain, processor)
                if chunks_added > 0:
                    processed += 1
                    chunks += chunks_added
                    stats.update(1, 1, chunks_added)

                    if stats.should_report():
                        status = stats.get_status()
                        logger.info(
                            f"📊 PROGRESS: {status['chunks']:,} chunks | {status['chunks_per_second']:.1f} chunks/sec | ETA: {status['estimated_time_to_100k']/3600:.1f}h"
                        )
        except Exception as e:
            logger.error(f"Error processing SOU doc {doc.dokid}: {e}")
            stats.update(0, 0, 0, 1)

    logger.info(
        f"✅ SOU harvest complete: {downloaded} downloaded, {processed} processed, {chunks} chunks"
    )
    return chunks


def harvest_interpellationer(
    client: RiksdagenClient, brain, processor: PDFProcessor, stats: HarvestStats
) -> int:
    """Harvest interpellationer (PRIORITY 2)"""
    logger.info("🎯 PRIORITY 2: Starting interpellationer harvest (2000-2024)")

    documents = client.search_documents(doktyp="ip", year_from=2000, year_to=2024, page_size=500)

    logger.info(f"Found {len(documents)} interpellationer")

    ip_dir = RIKSDAGEN_DIR / "ip"
    ip_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    processed = 0
    chunks = 0

    for i, doc in enumerate(documents, 1):
        if stats.total_chunks >= TARGET_DOCUMENTS:
            break

        try:
            pdf_path = client.download_document(doc, file_format="pdf")
            if pdf_path:
                downloaded += 1
                chunks_added = process_pdf_to_chromadb(pdf_path, brain, processor)
                if chunks_added > 0:
                    processed += 1
                    chunks += chunks_added
                    stats.update(1, 1, chunks_added)

                    if stats.should_report():
                        status = stats.get_status()
                        logger.info(
                            f"📊 PROGRESS: {status['chunks']:,} chunks | {status['chunks_per_second']:.1f} chunks/sec"
                        )
        except Exception as e:
            logger.error(f"Error processing interpellation {doc.dokid}: {e}")
            stats.update(0, 0, 0, 1)

    logger.info(
        f"✅ Interpellationer harvest complete: {downloaded} downloaded, {processed} processed, {chunks} chunks"
    )
    return chunks


def harvest_motioner(
    client: RiksdagenClient,
    brain,
    processor: PDFProcessor,
    stats: HarvestStats,
    year_from: int = 2000,
    year_to: int = 2014,
) -> int:
    """Harvest motioner (PRIORITY 3) - older years first"""
    logger.info(f"🎯 PRIORITY 3: Starting motioner harvest ({year_from}-{year_to})")

    documents = client.search_documents(
        doktyp="mot", year_from=year_from, year_to=year_to, page_size=500
    )

    logger.info(f"Found {len(documents)} motioner")

    mot_dir = RIKSDAGEN_DIR / "mot"
    mot_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    processed = 0
    chunks = 0

    for i, doc in enumerate(documents, 1):
        if stats.total_chunks >= TARGET_DOCUMENTS:
            break

        try:
            pdf_path = client.download_document(doc, file_format="pdf")
            if pdf_path:
                downloaded += 1
                chunks_added = process_pdf_to_chromadb(pdf_path, brain, processor)
                if chunks_added > 0:
                    processed += 1
                    chunks += chunks_added
                    stats.update(1, 1, chunks_added)

                    if stats.should_report():
                        status = stats.get_status()
                        logger.info(
                            f"📊 PROGRESS: {status['chunks']:,} chunks | {status['chunks_per_second']:.1f} chunks/sec"
                        )
        except Exception as e:
            logger.error(f"Error processing motion {doc.dokid}: {e}")
            stats.update(0, 0, 0, 1)

    logger.info(
        f"✅ Motioner harvest complete: {downloaded} downloaded, {processed} processed, {chunks} chunks"
    )
    return chunks


def harvest_jo_beslut(brain, processor: PDFProcessor, stats: HarvestStats) -> int:
    """Harvest JO-beslut (PRIORITY 4)"""
    logger.info("🎯 PRIORITY 4: Starting JO-beslut harvest (2010-2024)")

    downloader = JODownloader(output_dir=str(JO_DIR))

    # Download JO reports for years 2010-2024
    stats_jo = downloader.download_range(2010, 2024)

    logger.info(f"Downloaded {stats_jo['successful']} JO reports")

    processed = 0
    chunks = 0

    # Process downloaded PDFs
    for pdf_path in JO_DIR.glob("*.pdf"):
        if stats.total_chunks >= TARGET_DOCUMENTS:
            break

        try:
            chunks_added = process_pdf_to_chromadb(pdf_path, brain, processor)
            if chunks_added > 0:
                processed += 1
                chunks += chunks_added
                stats.update(0, 1, chunks_added)

                if stats.should_report():
                    status = stats.get_status()
                    logger.info(
                        f"📊 PROGRESS: {status['chunks']:,} chunks | {status['chunks_per_second']:.1f} chunks/sec"
                    )
        except Exception as e:
            logger.error(f"Error processing JO PDF {pdf_path}: {e}")
            stats.update(0, 0, 0, 1)

    logger.info(f"✅ JO-beslut harvest complete: {processed} processed, {chunks} chunks")
    return chunks


def harvest_skriftliga_fragor(
    client: RiksdagenClient, brain, processor: PDFProcessor, stats: HarvestStats
) -> int:
    """Harvest skriftliga frågor (PRIORITY 5) - volume filler"""
    logger.info("🎯 PRIORITY 5: Starting skriftliga frågor harvest (2000-2024)")

    documents = client.search_documents(
        doktyp="fsk",  # Fråga utan svar
        year_from=2000,
        year_to=2024,
        page_size=500,
    )

    logger.info(f"Found {len(documents)} skriftliga frågor")

    fsk_dir = RIKSDAGEN_DIR / "fsk"
    fsk_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    processed = 0
    chunks = 0

    for i, doc in enumerate(documents, 1):
        if stats.total_chunks >= TARGET_DOCUMENTS:
            break

        try:
            pdf_path = client.download_document(doc, file_format="pdf")
            if pdf_path:
                downloaded += 1
                chunks_added = process_pdf_to_chromadb(pdf_path, brain, processor)
                if chunks_added > 0:
                    processed += 1
                    chunks += chunks_added
                    stats.update(1, 1, chunks_added)

                    if stats.should_report():
                        status = stats.get_status()
                        logger.info(
                            f"📊 PROGRESS: {status['chunks']:,} chunks | {status['chunks_per_second']:.1f} chunks/sec"
                        )
        except Exception as e:
            logger.error(f"Error processing fråga {doc.dokid}: {e}")
            stats.update(0, 0, 0, 1)

    logger.info(
        f"✅ Skriftliga frågor harvest complete: {downloaded} downloaded, {processed} processed, {chunks} chunks"
    )
    return chunks


def main():
    """Main harvest orchestration"""
    print("=" * 70)
    print("OPERATION: TOTAL HARVEST")
    print("=" * 70)
    print(f"Target: {TARGET_DOCUMENTS:,} documents in ChromaDB")
    print("Disk space: 717 GB available")
    print("=" * 70)
    print()

    # Initialize components
    logger.info("Initializing components...")
    brain = get_brain()
    if not brain.collection:
        logger.error("ChromaDB not available!")
        return 1

    current_count = brain.collection.count()
    logger.info(f"Current documents in ChromaDB: {current_count:,}")

    if current_count >= TARGET_DOCUMENTS:
        logger.info("✅ Target already reached!")
        return 0

    processor = PDFProcessor(max_tokens=1000, chunk_overlap=100)
    client = RiksdagenClient(
        base_dir=str(RIKSDAGEN_DIR),
        rate_limit_delay=0.3,  # Aggressive rate limit for harvest
    )

    stats = HarvestStats()

    # Execute harvest in priority order
    try:
        # PRIORITY 1: SOU
        if stats.total_chunks < TARGET_DOCUMENTS:
            harvest_sou(client, brain, processor, stats)

        # PRIORITY 2: Interpellationer
        if stats.total_chunks < TARGET_DOCUMENTS:
            harvest_interpellationer(client, brain, processor, stats)

        # PRIORITY 3: Motioner (older years first)
        if stats.total_chunks < TARGET_DOCUMENTS:
            harvest_motioner(client, brain, processor, stats, year_from=2000, year_to=2014)

        # PRIORITY 4: JO-beslut
        if stats.total_chunks < TARGET_DOCUMENTS:
            harvest_jo_beslut(brain, processor, stats)

        # PRIORITY 5: Skriftliga frågor (volume filler)
        if stats.total_chunks < TARGET_DOCUMENTS:
            harvest_skriftliga_fragor(client, brain, processor, stats)

    except KeyboardInterrupt:
        logger.info("Harvest interrupted by user")

    # Final report
    final_status = stats.get_status()
    final_count = brain.collection.count()

    print()
    print("=" * 70)
    print("HARVEST COMPLETE")
    print("=" * 70)
    print(f"Total chunks added: {final_status['chunks']:,}")
    print(f"Total documents in ChromaDB: {final_count:,}")
    print(f"Downloaded: {final_status['downloaded']:,}")
    print(f"Processed: {final_status['processed']:,}")
    print(f"Failed: {final_status['failed']:,}")
    print(f"Elapsed time: {final_status['elapsed_seconds']/3600:.2f} hours")
    print(f"Average throughput: {final_status['chunks_per_second']:.1f} chunks/sec")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
