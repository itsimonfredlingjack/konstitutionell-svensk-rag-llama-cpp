#!/usr/bin/env python3
"""
Kommun Document Scraper
Harvests municipal documents (protokoll, beslut, styrdokument) from Swedish municipalities.
Downloads PDFs and tracks in SQLite database.
"""

import hashlib
import json
import logging
import re

# Import state tracking
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from sqlite_state import Dokument, add_dokument, dokument_exists, log_fel

# Configuration
BASE_DIR = Path(__file__).parent
PDF_CACHE_DIR = BASE_DIR / "pdf_cache" / "kommun"
CHROMADB_PATH = BASE_DIR / "chromadb_data"

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Document section patterns (Swedish municipalities)
SECTION_PATTERNS = {
    "protokoll": [
        "/politik/",
        "/sammantraden/",
        "/protokoll/",
        "/moten/",
        "/kommunfullmaktige/",
        "/kommunstyrelsen/",
        "/namnder/",
        "/kallelser-och-protokoll/",
        "/politiska-beslut/",
    ],
    "beslut": ["/beslut/", "/delegationsbeslut/", "/namndbeslut/", "/arenden/", "/diarium/"],
    "styrdokument": [
        "/styrdokument/",
        "/policy/",
        "/riktlinjer/",
        "/regler/",
        "/foreskrifter/",
        "/reglementen/",
        "/planer/",
    ],
    "rapport": [
        "/rapporter/",
        "/utredningar/",
        "/granskningar/",
        "/arsredovisning/",
        "/budget/",
        "/revision/",
    ],
    "upphandling": ["/upphandling/", "/inkop/", "/anbudsinbjudan/", "/forfragningsunderlag/"],
}

# File extensions to download
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt", ".xlsx", ".xls"}


@dataclass
class ScraperResult:
    """Result from scraping a kommun."""

    kommun_kod: str
    namn: str
    url: str
    dokument_hamtade: int
    storlek_bytes: int
    dokumenttyper: dict[str, int]
    flaggade_for_maskning: int
    fel: list[str]
    tid_sekunder: float


class RateLimiter:
    """Simple rate limiter for respectful scraping."""

    def __init__(self, delay: float = 5.0):
        self.delay = delay
        self.last_request = 0.0

    def wait(self):
        """Wait if necessary to respect rate limit."""
        elapsed = time.time() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request = time.time()


class KommunDocumentScraper:
    """Scraper for Swedish municipal documents."""

    def __init__(
        self, kommun_kod: str, namn: str, url: str, delay: float = 7.0, max_requests: int = 100
    ):
        self.kommun_kod = kommun_kod
        self.namn = namn
        self.base_url = url if url.startswith("http") else f"https://{url}"
        self.delay = delay
        self.max_requests = max_requests
        self.request_count = 0

        # Setup
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "KommunDokumentBot/1.0 (Constitutional AI Research; kontakt@example.se)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            }
        )

        self.rate_limiter = RateLimiter(delay)
        self.documents: list[Dokument] = []
        self.errors: list[str] = []
        self.visited_urls: set = set()

        # PDF storage directory
        self.pdf_dir = (
            PDF_CACHE_DIR
            / f"{kommun_kod}_{namn.lower().replace(' ', '_').replace('å', 'a').replace('ä', 'a').replace('ö', 'o')}"
        )
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        # Robots.txt parser
        self.robots = RobotFileParser()
        self._load_robots_txt()

    def _load_robots_txt(self):
        """Load and parse robots.txt."""
        try:
            robots_url = urljoin(self.base_url, "/robots.txt")
            self.robots.set_url(robots_url)
            self.robots.read()
            logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"Could not load robots.txt: {e}")

    def can_fetch(self, url: str) -> bool:
        """Check if we're allowed to fetch this URL."""
        try:
            return self.robots.can_fetch("*", url)
        except Exception:
            return True  # Default to allowing if robots.txt failed

    def fetch_page(self, url: str, timeout: int = 30) -> str | None:
        """Fetch a page with rate limiting and robots.txt respect."""
        if self.request_count >= self.max_requests:
            logger.warning(f"Max requests ({self.max_requests}) reached for {self.namn}")
            return None

        if url in self.visited_urls:
            return None

        if not self.can_fetch(url):
            logger.info(f"Blocked by robots.txt: {url}")
            return None

        self.rate_limiter.wait()
        self.request_count += 1
        self.visited_urls.add(url)

        try:
            response = self.session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            self.errors.append(f"Timeout: {url}")
            log_fel(self.kommun_kod, url, "timeout", "Request timed out")
            return None
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            self.errors.append(f"HTTP {status}: {url}")
            log_fel(self.kommun_kod, url, f"http_{status}", str(e))
            return None
        except Exception as e:
            self.errors.append(f"Error: {url} - {e}")
            log_fel(self.kommun_kod, url, "other", str(e))
            return None

    def download_document(self, url: str, doc_type: str) -> dict | None:
        """Download a document (PDF, etc.) and return metadata."""
        if self.request_count >= self.max_requests:
            return None

        if not self.can_fetch(url):
            return None

        # Check if already downloaded (by URL)
        if url in self.visited_urls:
            return None

        self.rate_limiter.wait()
        self.request_count += 1
        self.visited_urls.add(url)

        try:
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()

            # Get content
            content = response.content

            # Calculate hash for deduplication
            sha256 = hashlib.sha256(content).hexdigest()

            # Check if document already exists
            if dokument_exists(sha256):
                logger.info(f"Skipping duplicate: {url}")
                return None

            # Determine file extension
            content_type = response.headers.get("Content-Type", "")
            ext = self._get_extension(url, content_type)

            # Generate filename
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{doc_type}_{date_str}_{sha256[:8]}{ext}"

            # Create subdirectory for doc type
            type_dir = self.pdf_dir / doc_type
            type_dir.mkdir(exist_ok=True)

            # Save file
            filepath = type_dir / filename
            filepath.write_bytes(content)

            logger.info(f"Downloaded: {filename} ({len(content)} bytes)")

            return {
                "url": url,
                "filepath": str(filepath),
                "sha256": sha256,
                "size": len(content),
                "extension": ext,
                "doc_type": doc_type,
            }

        except Exception as e:
            self.errors.append(f"Download error: {url} - {e}")
            log_fel(self.kommun_kod, url, "download_error", str(e))
            return None

    def _get_extension(self, url: str, content_type: str) -> str:
        """Determine file extension from URL or content type."""
        # Try URL first
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in DOCUMENT_EXTENSIONS:
            if path.endswith(ext):
                return ext

        # Try content type
        if "pdf" in content_type:
            return ".pdf"
        elif "word" in content_type or "msword" in content_type:
            return ".docx"
        elif "excel" in content_type or "spreadsheet" in content_type:
            return ".xlsx"

        return ".pdf"  # Default

    def find_document_sections(self) -> dict[str, list[str]]:
        """Find document section URLs on the kommun website."""
        sections = {dtype: [] for dtype in SECTION_PATTERNS}

        # Fetch homepage
        html = self.fetch_page(self.base_url)
        if not html:
            return sections

        soup = BeautifulSoup(html, "html.parser")

        # Find all links
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            full_url = urljoin(self.base_url, link["href"])

            # Check against patterns
            for doc_type, patterns in SECTION_PATTERNS.items():
                for pattern in patterns:
                    if pattern in href:
                        if full_url not in sections[doc_type]:
                            sections[doc_type].append(full_url)
                        break

        # Log findings
        for doc_type, urls in sections.items():
            if urls:
                logger.info(f"Found {len(urls)} {doc_type} sections for {self.namn}")

        return sections

    def scrape_section(self, url: str, doc_type: str, depth: int = 2) -> list[str]:
        """Scrape a section for document links. Returns list of document URLs."""
        doc_urls = []

        html = self.fetch_page(url)
        if not html:
            return doc_urls

        soup = BeautifulSoup(html, "html.parser")

        # Find all links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(url, href)

            # Check if it's a document
            parsed = urlparse(full_url)
            path = parsed.path.lower()

            is_document = any(path.endswith(ext) for ext in DOCUMENT_EXTENSIONS)

            if is_document:
                if full_url not in doc_urls:
                    doc_urls.append(full_url)
            elif depth > 0:
                # Follow sub-pages within the same domain
                if urlparse(full_url).netloc == urlparse(self.base_url).netloc:
                    # Check if it looks like a document listing page
                    link_text = link.get_text().lower()
                    if any(
                        kw in link_text
                        for kw in ["protokoll", "beslut", "pdf", "dokument", "ladda", "visa"]
                    ):
                        sub_docs = self.scrape_section(full_url, doc_type, depth - 1)
                        doc_urls.extend(sub_docs)

        return list(set(doc_urls))  # Deduplicate

    def check_sensitive_content(self, text: str) -> bool:
        """Check if text contains potentially sensitive personal data."""
        # Swedish personnummer pattern
        pnr_pattern = r"\b(19|20)\d{6}[-]?\d{4}\b"
        if re.search(pnr_pattern, text):
            return True

        # Other sensitive patterns (simplified)
        sensitive_keywords = [
            "personnummer",
            "socialförsäkring",
            "patientjournal",
            "diagno",
            "sjukdom",
            "vårdnad",
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in sensitive_keywords)

    def extract_document_date(self, url: str, title: str) -> str | None:
        """Try to extract document date from URL or title."""
        # Pattern: YYYY-MM-DD
        date_pattern = r"(\d{4})-(\d{2})-(\d{2})"

        for source in [url, title]:
            match = re.search(date_pattern, source)
            if match:
                return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        # Pattern: YYYYMMDD
        date_pattern2 = r"(\d{4})(\d{2})(\d{2})"
        for source in [url, title]:
            match = re.search(date_pattern2, source)
            if match:
                year, month, day = match.groups()
                if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    return f"{year}-{month}-{day}"

        return None

    def extract_title_from_url(self, url: str) -> str:
        """Extract a title from the URL path."""
        parsed = urlparse(url)
        path = parsed.path

        # Get filename without extension
        filename = Path(path).stem

        # Clean up
        title = filename.replace("-", " ").replace("_", " ")
        title = re.sub(r"\d{8}", "", title)  # Remove date-like numbers
        title = " ".join(title.split())  # Normalize whitespace

        return title.title() if title else "Dokument"

    def run(self) -> ScraperResult:
        """Main scraping loop."""
        start_time = time.time()
        doc_type_counts = dict.fromkeys(SECTION_PATTERNS, 0)
        flagged_count = 0
        total_bytes = 0

        logger.info(f"Starting scrape of {self.namn} ({self.kommun_kod})")
        logger.info(f"Base URL: {self.base_url}")

        # Find document sections
        sections = self.find_document_sections()

        # Scrape each section type
        for doc_type, section_urls in sections.items():
            if not section_urls:
                continue

            logger.info(f"Scraping {doc_type} sections ({len(section_urls)} found)")

            for section_url in section_urls[:5]:  # Limit sections per type
                if self.request_count >= self.max_requests:
                    break

                # Find documents in this section
                doc_urls = self.scrape_section(section_url, doc_type)

                logger.info(f"Found {len(doc_urls)} documents in {section_url}")

                # Download documents
                for doc_url in doc_urls[:20]:  # Limit per section
                    if self.request_count >= self.max_requests:
                        break

                    result = self.download_document(doc_url, doc_type)

                    if result:
                        # Extract metadata
                        title = self.extract_title_from_url(doc_url)
                        doc_date = self.extract_document_date(doc_url, title)

                        # Check for sensitive content (from filename/URL)
                        needs_masking = self.check_sensitive_content(doc_url + title)

                        # Create document record
                        doc = Dokument(
                            kommun_kod=self.kommun_kod,
                            kalla_url=doc_url,
                            titel=title,
                            dokument_datum=doc_date,
                            filtyp=result["extension"],
                            storlek_bytes=result["size"],
                            sha256=result["sha256"],
                            relevans_tagg=doc_type,
                            kraver_maskning=needs_masking,
                            kvalitet_score=3,  # Default medium quality
                            hamtat=datetime.now().isoformat(),
                            lokal_sokvag=result["filepath"],
                            indexerad=False,
                        )

                        # Add to database
                        add_dokument(doc)
                        self.documents.append(doc)

                        doc_type_counts[doc_type] += 1
                        total_bytes += result["size"]

                        if needs_masking:
                            flagged_count += 1

        elapsed = time.time() - start_time

        result = ScraperResult(
            kommun_kod=self.kommun_kod,
            namn=self.namn,
            url=self.base_url,
            dokument_hamtade=len(self.documents),
            storlek_bytes=total_bytes,
            dokumenttyper=doc_type_counts,
            flaggade_for_maskning=flagged_count,
            fel=self.errors[:10],  # Limit error list
            tid_sekunder=round(elapsed, 1),
        )

        logger.info(
            f"Completed {self.namn}: {len(self.documents)} docs, {total_bytes / 1024:.1f}KB, {elapsed:.1f}s"
        )

        return result


def scrape_kommun(
    kommun_kod: str, namn: str, url: str, delay: float = 7.0, max_requests: int = 100
) -> ScraperResult:
    """Convenience function to scrape a single kommun."""
    scraper = KommunDocumentScraper(kommun_kod, namn, url, delay, max_requests)
    return scraper.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape documents from Swedish municipality")
    parser.add_argument("--kommun", "-k", help="Kommun code (e.g., 0180 for Stockholm)")
    parser.add_argument("--namn", "-n", help="Kommun name")
    parser.add_argument("--url", "-u", help="Kommun website URL")
    parser.add_argument(
        "--delay", "-d", type=float, default=7.0, help="Delay between requests (seconds)"
    )
    parser.add_argument("--max-requests", "-m", type=int, default=100, help="Max HTTP requests")
    parser.add_argument("--test-stockholm", action="store_true", help="Test with Stockholm")

    args = parser.parse_args()

    if args.test_stockholm:
        result = scrape_kommun(
            "0180",
            "Stockholm",
            "https://stockholm.se",
            delay=args.delay,
            max_requests=args.max_requests,
        )
    elif args.kommun and args.namn and args.url:
        result = scrape_kommun(
            args.kommun, args.namn, args.url, delay=args.delay, max_requests=args.max_requests
        )
    else:
        parser.print_help()
        sys.exit(1)

    # Print result
    print("\n" + "=" * 60)
    print(f"RESULTAT: {result.namn} ({result.kommun_kod})")
    print("=" * 60)
    print(f"Dokument hämtade: {result.dokument_hamtade}")
    print(f"Total storlek: {result.storlek_bytes / 1024:.1f} KB")
    print(f"Tid: {result.tid_sekunder} sekunder")
    print("\nPer dokumenttyp:")
    for dtype, count in result.dokumenttyper.items():
        if count > 0:
            print(f"  {dtype}: {count}")
    print(f"\nFlaggade för maskning: {result.flaggade_for_maskning}")
    if result.fel:
        print(f"\nFel ({len(result.fel)}):")
        for fel in result.fel[:5]:
            print(f"  - {fel}")

    # Save result to JSON
    output_file = BASE_DIR / f"kommun_harvest_{result.kommun_kod}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)
    print(f"\nResultat sparat till: {output_file}")
