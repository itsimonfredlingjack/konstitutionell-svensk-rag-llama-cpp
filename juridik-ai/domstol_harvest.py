#!/usr/bin/env python3
"""
OPERATION: DOMSTOLSVERKET HARVEST
Scrapa domstolsavgöranden från domstol.se och indexera till ChromaDB.

Mission:
- Scrapa anonymiserade domar från svenska domstolar
- Implementera GDPR-kontroller
- Indexera till ChromaDB med source="domstolsverket"
- Flagga om <100 domar hittas

GDPR-VARNING: Detta script kontrollerar aktivt för personuppgifter.
Om personuppgifter hittas FLAGGAS dokumentet och indexeras INTE.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from cli.brain import get_brain
from pipelines.domstol_scraper import CourtDecision, DomstolScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)-8s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("domstol_harvest.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Config
BASE_DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data")
DOMSTOL_DIR = BASE_DATA_DIR / "domstol"
MIN_DOCUMENTS_THRESHOLD = 100  # Flagga om färre än detta


class DomstolHarvestStats:
    """Track harvest statistics for Domstolsverket"""

    def __init__(self):
        self.docs_found = 0
        self.docs_indexed = 0
        self.docs_flagged_gdpr = 0
        self.errors = []
        self.start_time = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "myndighet": "Domstolsverket",
            "status": "FLAGGAD" if self.docs_found < MIN_DOCUMENTS_THRESHOLD else "OK",
            "docs_found": self.docs_found,
            "docs_indexed": self.docs_indexed,
            "docs_flagged_gdpr": self.docs_flagged_gdpr,
            "errors": self.errors,
            "elapsed_seconds": (datetime.now() - self.start_time).total_seconds(),
            "flag_reason": f"Only {self.docs_found} documents found (threshold: {MIN_DOCUMENTS_THRESHOLD})"
            if self.docs_found < MIN_DOCUMENTS_THRESHOLD
            else None,
        }


def index_decision_to_chromadb(decision: CourtDecision, brain, stats: DomstolHarvestStats) -> bool:
    """
    Index a court decision to ChromaDB

    Args:
        decision: CourtDecision object
        brain: Brain instance with ChromaDB collection
        stats: Statistics tracker

    Returns:
        True if indexed, False if skipped/failed
    """

    # GDPR check
    if not decision.anonymized or decision.gdpr_warnings:
        logger.warning(f"⚠️  GDPR: Skipping {decision.case_number} - not properly anonymized")
        logger.warning(f"    Warnings: {decision.gdpr_warnings}")
        stats.docs_flagged_gdpr += 1
        return False

    # Check if text exists
    if not decision.full_text or len(decision.full_text.strip()) < 100:
        logger.warning(f"⚠️  No substantial text for {decision.case_number}")
        return False

    try:
        # Create document ID
        doc_id = f"domstol_{decision.court}_{decision.case_number}".replace("/", "_").replace(
            " ", "_"
        )

        # Check if already indexed
        existing = brain.collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            logger.debug(f"⏭️  Skipping {decision.case_number} (already in ChromaDB)")
            return False

        # Prepare document for indexing
        document_text = f"{decision.summary or ''}\n\n{decision.full_text}"

        metadata = {
            "source": "domstolsverket",
            "court": decision.court,
            "case_number": decision.case_number,
            "decision_date": decision.decision_date or "unknown",
            "legal_area": decision.legal_area or "unknown",
            "url": decision.url or "",
            "keywords": ",".join(decision.keywords) if decision.keywords else "",
            "indexed_at": datetime.now().isoformat(),
        }

        # Add to ChromaDB
        brain.collection.upsert(documents=[document_text], metadatas=[metadata], ids=[doc_id])

        logger.info(f"✅ Indexed {decision.case_number} to ChromaDB")
        stats.docs_indexed += 1
        return True

    except Exception as e:
        logger.error(f"❌ Failed to index {decision.case_number}: {e}")
        stats.errors.append(f"{decision.case_number}: {e!s}")
        return False


def harvest_court_level(
    scraper: DomstolScraper,
    brain,
    court_code: str,
    court_name: str,
    year_from: int,
    year_to: int,
    stats: DomstolHarvestStats,
) -> int:
    """
    Harvest decisions from a specific court level

    Args:
        scraper: DomstolScraper instance
        brain: Brain instance
        court_code: Court code (e.g., "HDO")
        court_name: Human-readable court name
        year_from: Start year
        year_to: End year
        stats: Statistics tracker

    Returns:
        Number of documents indexed
    """
    logger.info(f"🏛️  Harvesting {court_name} ({court_code}) from {year_from}-{year_to}")

    indexed_count = 0

    try:
        # Search for decisions
        decisions = scraper.search_decisions(
            court_code=court_code, year_from=year_from, year_to=year_to
        )

        logger.info(f"Found {len(decisions)} decisions from {court_name}")
        stats.docs_found += len(decisions)

        # Index each decision
        for decision in decisions:
            if index_decision_to_chromadb(decision, brain, stats):
                indexed_count += 1

        logger.info(f"✅ {court_name}: indexed {indexed_count}/{len(decisions)} decisions")

    except Exception as e:
        logger.error(f"❌ Failed to harvest {court_name}: {e}")
        stats.errors.append(f"{court_name}: {e!s}")

    return indexed_count


def main():
    """Main harvest orchestration"""
    print("=" * 70)
    print("OPERATION: DOMSTOLSVERKET HARVEST")
    print("=" * 70)
    print("Target: Scrape court decisions from domstol.se")
    print("GDPR: Active anonymization checks")
    print(f"Threshold: {MIN_DOCUMENTS_THRESHOLD} documents")
    print("=" * 70)
    print()

    # Initialize components
    logger.info("Initializing components...")

    brain = get_brain()
    if not brain or not brain.collection:
        logger.error("❌ ChromaDB not available!")
        return json.dumps(
            {
                "myndighet": "Domstolsverket",
                "status": "FLAGGAD",
                "docs_found": 0,
                "docs_indexed": 0,
                "errors": ["ChromaDB not available"],
            },
            indent=2,
        )

    scraper = DomstolScraper(
        base_dir=str(DOMSTOL_DIR),
        rate_limit_delay=15.0,  # 15 seconds as specified
    )

    stats = DomstolHarvestStats()

    # Court levels to harvest (prioritized)
    courts_to_harvest = [
        ("HDO", "Högsta domstolen", 2023, 2024),
        ("HFD", "Högsta förvaltningsdomstolen", 2023, 2024),
        ("HOVR", "Hovrätter", 2023, 2024),
    ]

    # Execute harvest
    try:
        for court_code, court_name, year_from, year_to in courts_to_harvest:
            harvest_court_level(scraper, brain, court_code, court_name, year_from, year_to, stats)

    except KeyboardInterrupt:
        logger.info("Harvest interrupted by user")

    except Exception as e:
        logger.error(f"Harvest failed: {e}", exc_info=True)
        stats.errors.append(f"Fatal error: {e!s}")

    # Generate report
    report = stats.to_dict()

    # Check threshold and flag if needed
    if stats.docs_found < MIN_DOCUMENTS_THRESHOLD:
        logger.warning("=" * 70)
        logger.warning("⚠️  SIMON: Domstolsverket verkar ha problem")
        logger.warning(
            f"   Only {stats.docs_found} documents found (threshold: {MIN_DOCUMENTS_THRESHOLD})"
        )
        logger.warning("=" * 70)

    # Print final report
    print()
    print("=" * 70)
    print("HARVEST COMPLETE - DOMSTOLSVERKET")
    print("=" * 70)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("=" * 70)

    # Save report
    report_file = DOMSTOL_DIR / f"harvest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    DOMSTOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Report saved to {report_file}")

    # Return JSON for orchestrator
    return json.dumps(report, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    result = main()
    print(result)
