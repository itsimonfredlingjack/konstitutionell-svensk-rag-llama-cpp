#!/usr/bin/env python3
"""
Playwright-based Kommun Document Scraper
Handles JavaScript-heavy municipal websites (Sitevision, custom diarium systems).
Uses headless Chromium for full page rendering.
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
from urllib.parse import urljoin

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from sqlite_state import Dokument, add_dokument, dokument_exists, log_fel

# Configuration
BASE_DIR = Path(__file__).parent
PDF_CACHE_DIR = BASE_DIR / "pdf_cache" / "kommun"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Document patterns
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt", ".xlsx", ".xls"}

# Swedish document keywords
DOC_KEYWORDS = [
    "protokoll",
    "beslut",
    "kallelse",
    "handlingar",
    "sammanträde",
    "styrdokument",
    "policy",
    "riktlinjer",
    "rapport",
    "utredning",
    "budget",
    "årsredovisning",
    "upphandling",
    "förfrågningsunderlag",
]


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


class PlaywrightKommunScraper:
    """Playwright-based scraper for JS-heavy kommun websites."""

    def __init__(
        self,
        kommun_kod: str,
        namn: str,
        url: str,
        delay: float = 5.0,
        max_pages: int = 50,
        headless: bool = True,
    ):
        self.kommun_kod = kommun_kod
        self.namn = namn
        self.base_url = url if url.startswith("http") else f"https://{url}"
        self.delay = delay
        self.max_pages = max_pages
        self.headless = headless

        self.page_count = 0
        self.documents: list[Dokument] = []
        self.errors: list[str] = []
        self.visited_urls: set = set()
        self.doc_urls_found: set = set()

        # PDF storage
        safe_name = (
            namn.lower().replace(" ", "_").replace("å", "a").replace("ä", "a").replace("ö", "o")
        )
        self.pdf_dir = PDF_CACHE_DIR / f"{kommun_kod}_{safe_name}"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.browser: Browser | None = None
        self.page: Page | None = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            user_agent="KommunDokumentBot/1.0 (Constitutional AI Research)", locale="sv-SE"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)  # 30 seconds
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def navigate(self, url: str) -> bool:
        """Navigate to URL with rate limiting."""
        if self.page_count >= self.max_pages:
            logger.warning(f"Max pages ({self.max_pages}) reached")
            return False

        if url in self.visited_urls:
            return False

        time.sleep(self.delay)
        self.page_count += 1
        self.visited_urls.add(url)

        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)
            return True
        except PlaywrightTimeout:
            self.errors.append(f"Timeout: {url}")
            log_fel(self.kommun_kod, url, "timeout", "Page load timeout")
            return False
        except Exception as e:
            self.errors.append(f"Error: {url} - {e}")
            log_fel(self.kommun_kod, url, "navigation_error", str(e))
            return False

    def find_document_links(self) -> list[dict]:
        """Find all document links on current page."""
        docs = []

        # Find all links
        links = self.page.query_selector_all("a[href]")

        for link in links:
            try:
                href = link.get_attribute("href")
                if not href:
                    continue

                full_url = urljoin(self.page.url, href)
                text = link.inner_text().strip().lower()

                # Check if it's a document
                is_doc = any(full_url.lower().endswith(ext) for ext in DOCUMENT_EXTENSIONS)

                # Check if link text suggests a document
                is_doc_link = any(kw in text for kw in DOC_KEYWORDS)

                if is_doc:
                    doc_type = self._classify_document(full_url, text)
                    docs.append(
                        {"url": full_url, "text": text[:100], "type": doc_type, "is_direct": True}
                    )
                elif is_doc_link and full_url not in self.visited_urls:
                    docs.append(
                        {"url": full_url, "text": text[:100], "type": "page", "is_direct": False}
                    )

            except Exception as e:
                logger.debug(f"Error processing link: {e}")

        return docs

    def _classify_document(self, url: str, text: str) -> str:
        """Classify document type based on URL and text."""
        combined = (url + " " + text).lower()

        if any(kw in combined for kw in ["protokoll", "sammanträde", "möte"]):
            return "protokoll"
        elif any(kw in combined for kw in ["beslut", "delegation"]):
            return "beslut"
        elif any(kw in combined for kw in ["policy", "riktlinje", "styrdokument", "reglemente"]):
            return "styrdokument"
        elif any(kw in combined for kw in ["rapport", "utredning", "granskning"]):
            return "rapport"
        elif any(kw in combined for kw in ["upphandling", "anbud", "förfrågning"]):
            return "upphandling"
        elif any(kw in combined for kw in ["budget", "årsredovisning", "ekonomi"]):
            return "ekonomi"
        else:
            return "ovrigt"

    def download_document(self, url: str, doc_type: str) -> dict | None:
        """Download a document."""
        if url in self.doc_urls_found:
            return None

        self.doc_urls_found.add(url)

        try:
            # Use page context for download
            with self.page.expect_download(timeout=60000) as download_info:
                self.page.goto(url)

            download = download_info.value

            # Read content
            path = download.path()
            if not path:
                return None

            content = Path(path).read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()

            # Check for duplicates
            if dokument_exists(sha256):
                logger.info(f"Skipping duplicate: {url}")
                return None

            # Save file
            ext = self._get_extension(url, download.suggested_filename)
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{doc_type}_{date_str}_{sha256[:8]}{ext}"

            type_dir = self.pdf_dir / doc_type
            type_dir.mkdir(exist_ok=True)
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
            logger.debug(f"Download failed for {url}: {e}")
            # Try alternative download method
            return self._download_via_request(url, doc_type)

    def _download_via_request(self, url: str, doc_type: str) -> dict | None:
        """Fallback download using requests."""
        import requests

        try:
            response = requests.get(
                url, timeout=60, headers={"User-Agent": "KommunDokumentBot/1.0"}
            )
            response.raise_for_status()

            content = response.content
            sha256 = hashlib.sha256(content).hexdigest()

            if dokument_exists(sha256):
                return None

            ext = self._get_extension(url, "")
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{doc_type}_{date_str}_{sha256[:8]}{ext}"

            type_dir = self.pdf_dir / doc_type
            type_dir.mkdir(exist_ok=True)
            filepath = type_dir / filename

            filepath.write_bytes(content)
            logger.info(f"Downloaded (fallback): {filename} ({len(content)} bytes)")

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

    def _get_extension(self, url: str, suggested: str) -> str:
        """Get file extension."""
        for source in [url.lower(), suggested.lower()]:
            for ext in DOCUMENT_EXTENSIONS:
                if ext in source:
                    return ext
        return ".pdf"

    def check_sensitive_content(self, text: str) -> bool:
        """Check for sensitive personal data."""
        pnr_pattern = r"\b(19|20)\d{6}[-]?\d{4}\b"
        return bool(re.search(pnr_pattern, text))

    def extract_date(self, url: str, text: str) -> str | None:
        """Extract date from URL or text."""
        patterns = [r"(\d{4})-(\d{2})-(\d{2})", r"(\d{4})(\d{2})(\d{2})"]
        for pattern in patterns:
            for source in [url, text]:
                match = re.search(pattern, source)
                if match:
                    groups = match.groups()
                    if len(groups) == 3:
                        y, m, d = groups
                        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
                            return f"{y}-{m}-{d}"
        return None

    def run(self, start_urls: list[str] = None) -> ScraperResult:
        """Run the scraper."""
        start_time = time.time()
        doc_type_counts = dict.fromkeys(
            ["protokoll", "beslut", "styrdokument", "rapport", "upphandling", "ekonomi", "ovrigt"],
            0,
        )
        flagged_count = 0
        total_bytes = 0

        logger.info(f"Starting Playwright scrape of {self.namn} ({self.kommun_kod})")

        # Start URLs
        urls_to_visit = start_urls or [self.base_url]
        document_queue = []

        # Phase 1: Discover document links
        for url in urls_to_visit:
            if self.page_count >= self.max_pages:
                break

            if not self.navigate(url):
                continue

            logger.info(f"Scanning: {url}")

            # Wait for dynamic content
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass

            # Find documents
            found = self.find_document_links()
            logger.info(f"Found {len(found)} potential documents on {url}")

            for doc in found:
                if doc["is_direct"]:
                    document_queue.append(doc)
                else:
                    # Add page to visit queue
                    if (
                        doc["url"] not in self.visited_urls
                        and len(urls_to_visit) < self.max_pages * 2
                    ):
                        urls_to_visit.append(doc["url"])

        logger.info(f"Total documents to download: {len(document_queue)}")

        # Phase 2: Download documents
        for doc_info in document_queue[:50]:  # Limit downloads
            result = self._download_via_request(doc_info["url"], doc_info["type"])

            if result:
                title = doc_info["text"][:100] if doc_info["text"] else "Dokument"
                doc_date = self.extract_date(doc_info["url"], title)
                needs_masking = self.check_sensitive_content(doc_info["url"] + title)

                doc = Dokument(
                    kommun_kod=self.kommun_kod,
                    kalla_url=doc_info["url"],
                    titel=title,
                    dokument_datum=doc_date,
                    filtyp=result["extension"],
                    storlek_bytes=result["size"],
                    sha256=result["sha256"],
                    relevans_tagg=result["doc_type"],
                    kraver_maskning=needs_masking,
                    kvalitet_score=3,
                    hamtat=datetime.now().isoformat(),
                    lokal_sokvag=result["filepath"],
                    indexerad=False,
                )

                add_dokument(doc)
                self.documents.append(doc)
                doc_type_counts[result["doc_type"]] += 1
                total_bytes += result["size"]

                if needs_masking:
                    flagged_count += 1

        elapsed = time.time() - start_time

        return ScraperResult(
            kommun_kod=self.kommun_kod,
            namn=self.namn,
            url=self.base_url,
            dokument_hamtade=len(self.documents),
            storlek_bytes=total_bytes,
            dokumenttyper=doc_type_counts,
            flaggade_for_maskning=flagged_count,
            fel=self.errors[:10],
            tid_sekunder=round(elapsed, 1),
        )


def scrape_kommun_playwright(
    kommun_kod: str,
    namn: str,
    url: str,
    start_urls: list[str] = None,
    delay: float = 5.0,
    max_pages: int = 50,
) -> ScraperResult:
    """Convenience function to scrape with Playwright."""
    with PlaywrightKommunScraper(kommun_kod, namn, url, delay, max_pages) as scraper:
        return scraper.run(start_urls)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Playwright-based kommun document scraper")
    parser.add_argument("--kommun", "-k", required=True, help="Kommun code")
    parser.add_argument("--namn", "-n", required=True, help="Kommun name")
    parser.add_argument("--url", "-u", required=True, help="Start URL")
    parser.add_argument("--delay", "-d", type=float, default=5.0, help="Delay between pages")
    parser.add_argument("--max-pages", "-m", type=int, default=50, help="Max pages to visit")

    args = parser.parse_args()

    result = scrape_kommun_playwright(
        args.kommun, args.namn, args.url, delay=args.delay, max_pages=args.max_pages
    )

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

    # Save result
    output_file = BASE_DIR / f"kommun_harvest_{result.kommun_kod}_playwright.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)
    print(f"\nResultat sparat till: {output_file}")
