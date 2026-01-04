#!/usr/bin/env python3
"""
Domstolsverket Court Decision Scraper

Scrapes published court decisions from Swedish courts via domstol.se.
Implements GDPR-compliant anonymization checks and ChromaDB indexing.

Sources:
- Högsta domstolen (Supreme Court) - since 1981
- Högsta förvaltningsdomstolen (Supreme Administrative Court) - since 1993
- Hovrätter (Courts of Appeal) - since 1993
- Kammarrätter (Administrative Courts of Appeal)
- Tingsrätter (District Courts)

API: https://rattspraxis.etjanst.domstol.se/
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CourtLevel(str, Enum):
    """Swedish court hierarchy"""

    HOGSTA_DOMSTOLEN = "HDO"  # Supreme Court
    HOGSTA_FORVALTNINGSDOMSTOLEN = "HFD"  # Supreme Administrative Court
    HOVRATTERNA = "HOVR"  # Courts of Appeal
    KAMMARRATTERNA = "KAMR"  # Administrative Courts of Appeal
    ARBETSDOMSTOLEN = "AD"  # Labour Court
    MARK_MILJO_OVERDOMSTOLEN = "MMD"  # Land and Environment Court of Appeal
    PATENT_MARKNADS_OVERDOMSTOLEN = "PMO"  # Patent and Market Court of Appeal


# GDPR patterns to detect potentially non-anonymized content
GDPR_PATTERNS = {
    "personnummer": re.compile(r"\b\d{6}[-\s]?\d{4}\b"),  # YYMMDD-XXXX
    "full_address": re.compile(r"\d{3}\s?\d{2}\s+[A-ZÅÄÖ][a-zåäö]+"),  # Postal code + city
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b0\d{1,3}[-\s]?\d{5,8}\b"),
}


@dataclass
class CourtDecision:
    """Represents a court decision from Domstolsverket"""

    case_number: str
    court: str
    decision_date: Optional[str] = None
    legal_area: Optional[str] = None
    summary: Optional[str] = None
    full_text: Optional[str] = None
    url: Optional[str] = None
    keywords: list[str] = None
    anonymized: bool = True
    gdpr_warnings: list[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class DomstolScraper:
    """
    Scraper for Swedish court decisions from domstol.se

    Implements:
    - Rate limiting (15s default, as per instructions)
    - GDPR anonymization checks
    - Resume capability
    - Multiple court levels
    """

    BASE_URL = "https://rattspraxis.etjanst.domstol.se"
    SEARCH_ENDPOINT = "/sok/sokning"
    RATE_LIMIT_DELAY = 15.0  # 15 seconds as specified

    def __init__(
        self,
        base_dir: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data/domstol",
        rate_limit_delay: float = RATE_LIMIT_DELAY,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize Domstol scraper

        Args:
            base_dir: Base directory for saving decisions
            rate_limit_delay: Delay between requests (default 15s)
            timeout: Request timeout
            max_retries: Max retries for failed requests
        """
        self.base_dir = Path(base_dir)
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Setup session with retries
        self.session = self._create_session()

        # Track state
        self.last_request_time = 0
        self.session_log_file = self.base_dir / "session.log"

    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy"""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set user agent
        session.headers.update({"User-Agent": "JuridikAI/1.0 (Research; +https://github.com/)"})

        return session

    def _rate_limit(self) -> None:
        """Apply rate limiting - CRITICAL for court servers"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - elapsed
            logger.info(f"⏰ Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _log_session(self, action: str, details: dict[str, Any]) -> None:
        """Log session activity"""
        with open(self.session_log_file, "a") as f:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "details": details,
            }
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _check_gdpr_compliance(self, text: str) -> tuple[bool, list[str]]:
        """
        Check if text appears properly anonymized

        Returns:
            (is_safe, warnings)
        """
        if not text:
            return True, []

        warnings = []

        for pattern_name, pattern in GDPR_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                warnings.append(f"{pattern_name}: {len(matches)} potential matches")
                logger.warning(f"⚠️  GDPR: Found {pattern_name} in text: {matches[:3]}")

        # Check for capitalized names that might not be anonymized
        # Swedish anonymization typically uses A, B, C or [käranden], [svaranden]
        name_pattern = re.compile(r"\b[A-ZÅÄÖ][a-zåäö]+\s+[A-ZÅÄÖ][a-zåäö]+\b")
        potential_names = name_pattern.findall(text)

        # Filter out common legal terms
        legal_terms = {
            "Högsta Domstolen",
            "Högsta Förvaltningsdomstolen",
            "Justitieråd",
            "Hovrättsråd",
            "Lagman",
            "Tingsrätt",
            "Hovrätt",
            "Kammarrätt",
        }
        potential_names = [name for name in potential_names if name not in legal_terms]

        if len(potential_names) > 5:  # Threshold for suspicion
            warnings.append(f"potential_names: {len(potential_names)} names found")
            logger.warning(f"⚠️  GDPR: Found {len(potential_names)} potential names")

        is_safe = len(warnings) == 0
        return is_safe, warnings

    def search_decisions(
        self,
        court_code: str = "HDO",
        year_from: int = 2023,
        year_to: int = 2024,
        max_results: Optional[int] = None,
    ) -> list[CourtDecision]:
        """
        Search for court decisions

        Note: The actual API structure may differ. This is a template
        that needs to be adapted based on actual API responses.

        Args:
            court_code: Court code (HDO, HFD, etc.)
            year_from: Start year
            year_to: End year
            max_results: Max results to fetch

        Returns:
            List of CourtDecision objects
        """
        logger.info(f"Searching {court_code} decisions ({year_from}-{year_to})")

        decisions = []

        # Note: This is a TEMPLATE. Real implementation requires
        # inspection of actual API structure via browser DevTools

        self._rate_limit()

        try:
            params = {
                "domstolskod": court_code,
                # Add other parameters based on actual API
            }

            response = self.session.get(
                f"{self.BASE_URL}{self.SEARCH_ENDPOINT}", params=params, timeout=self.timeout
            )
            response.raise_for_status()

            # Parse response
            # This needs to be adapted based on actual response format
            logger.warning(
                "⚠️  API response parsing not yet implemented - requires manual inspection"
            )

            self._log_session(
                "search_success",
                {
                    "court_code": court_code,
                    "year_from": year_from,
                    "year_to": year_to,
                    "results": len(decisions),
                },
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Search failed: {e}")
            self._log_session("search_failed", {"court_code": court_code, "error": str(e)})

        return decisions

    def fetch_decision_text(self, decision_url: str) -> Optional[str]:
        """
        Fetch full text of a decision

        Args:
            decision_url: URL to decision

        Returns:
            Full text or None
        """
        self._rate_limit()

        try:
            response = self.session.get(decision_url, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract text - adapt selectors based on actual structure
            # This is a TEMPLATE
            text_container = soup.find("div", class_="decision-text")
            if text_container:
                return text_container.get_text(separator="\n", strip=True)

            return None

        except Exception as e:
            logger.error(f"Failed to fetch decision text: {e}")
            return None

    def export_to_json(
        self, decisions: list[CourtDecision], output_file: Optional[str] = None
    ) -> str:
        """
        Export decisions to JSON

        Args:
            decisions: List of decisions
            output_file: Output path

        Returns:
            Path to output file
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(self.base_dir / f"domstol_export_{timestamp}.json")

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        export_data = {
            "myndighet": "Domstolsverket",
            "exported": datetime.now().isoformat(),
            "total": len(decisions),
            "decisions": [d.to_dict() for d in decisions],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(decisions)} decisions to {output_path}")
        return str(output_path)

    def get_statistics(self) -> dict[str, Any]:
        """Get scraping statistics"""
        stats = {
            "base_dir": str(self.base_dir),
            "total_decisions": 0,
            "courts": {},
        }

        if not self.base_dir.exists():
            return stats

        # Count JSON exports
        for json_file in self.base_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    if "decisions" in data:
                        stats["total_decisions"] += len(data["decisions"])
            except Exception as e:
                logger.warning(f"Failed to read {json_file}: {e}")

        return stats


def main():
    """Example usage"""

    logger.info("=" * 70)
    logger.info("DOMSTOLSVERKET SCRAPER - PILOT MODE")
    logger.info("=" * 70)
    logger.info("")
    logger.info("⚠️  IMPORTANT: This is a TEMPLATE implementation")
    logger.info("⚠️  Requires manual API inspection before production use")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Visit https://rattspraxis.etjanst.domstol.se/")
    logger.info("2. Open DevTools Network tab")
    logger.info("3. Perform a search")
    logger.info("4. Identify actual API endpoints and parameters")
    logger.info("5. Update search_decisions() method")
    logger.info("")
    logger.info("=" * 70)

    # Initialize scraper
    scraper = DomstolScraper()

    # Test search (will not work until API is mapped)
    decisions = scraper.search_decisions(
        court_code="HDO", year_from=2024, year_to=2024, max_results=10
    )

    logger.info(f"Found {len(decisions)} decisions (template mode)")

    # Export
    if decisions:
        scraper.export_to_json(decisions)

    # Stats
    stats = scraper.get_statistics()
    logger.info(f"Statistics: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
