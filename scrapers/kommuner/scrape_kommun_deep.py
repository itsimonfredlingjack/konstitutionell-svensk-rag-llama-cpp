#!/usr/bin/env python3
"""
Deep-crawl Kommun Document Scraper
Follows nämnd structure to find documents nested 2-3 levels deep.
Uses Playwright for JavaScript rendering.
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
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from sqlite_state import Dokument, add_dokument, dokument_exists, log_fel

# Configuration
BASE_DIR = Path(__file__).parent
PDF_CACHE_DIR = BASE_DIR / "pdf_cache" / "kommun"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Document patterns
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt", ".xlsx", ".xls"}

# Swedish keywords for document sections (politik/beslut related)
POLITIK_KEYWORDS = [
    "politik",
    "demokrati",
    "beslut",
    "protokoll",
    "sammanträde",
    "kallelse",
    "handlingar",
    "nämnd",
    "styrelse",
    "fullmäktige",
    "kommun-och-politik",
    "moten-och-protokoll",
    "styrdokument",
]

# Nämnd-specific keywords to follow
NAMND_KEYWORDS = [
    "kommunfullmäktige",
    "kommunstyrelse",
    "fullmäktige",
    "barn-och-utbildning",
    "utbildningsnämnd",
    "socialnämnd",
    "vård-och-omsorg",
    "omsorgsnämnd",
    "miljö-och-bygg",
    "byggnadsnämnd",
    "samhällsbyggnad",
    "tekniska",
    "teknik-och-fritid",
    "kultur",
    "kulturnämnd",
    "arbetsmarknad",
    "näringsliv",
    "revision",
    "valnämnd",
    "överförmyndare",
]

# Sitevision-specific paths to try
SITEVISION_PATHS = [
    "/sammantraden",
    "/politik/protokoll",
    "/kommun-och-politik",
    "/kommun-och-politik/moten-och-protokoll",
    "/kommun-och-politik/politik-och-beslut",
    "/kommun-och-politik/styrdokument",
    "/om-kommunen/politik-och-demokrati",
    "/om-kommunen/politik-och-demokrati/moten-och-protokoll",
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
    pages_visited: int
    pdfs_found: int


class DeepKommunScraper:
    """Deep-crawl scraper that follows nämnd structure."""

    def __init__(
        self,
        kommun_kod: str,
        namn: str,
        url: str,
        delay: float = 5.0,
        max_pages: int = 100,
        max_downloads: int = 50,
        headless: bool = True,
    ):
        self.kommun_kod = kommun_kod
        self.namn = namn
        self.base_url = url.rstrip("/") if url.startswith("http") else f"https://{url}".rstrip("/")
        self.domain = urlparse(self.base_url).netloc
        self.delay = delay
        self.max_pages = max_pages
        self.max_downloads = max_downloads
        self.headless = headless

        self.page_count = 0
        self.documents: list[Dokument] = []
        self.errors: list[str] = []
        self.visited_urls: set[str] = set()
        self.doc_urls_found: set[str] = set()
        self.pdf_queue: list[dict] = []

        # PDF storage
        safe_name = self._safe_name(namn)
        self.pdf_dir = PDF_CACHE_DIR / f"{kommun_kod}_{safe_name}"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def _safe_name(self, name: str) -> str:
        """Create filesystem-safe name."""
        return name.lower().replace(" ", "_").replace("å", "a").replace("ä", "a").replace("ö", "o")

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            user_agent="KommunDokumentBot/1.0 (Constitutional AI Research, respekterar robots.txt)",
            locale="sv-SE",
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        url = url.split("#")[0].split("?")[0]  # Remove fragments and query
        url = url.rstrip("/")
        return url

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL is on same domain or relevant subdomain."""
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        base_domain = self.domain.lower()

        # Same domain
        if host == base_domain:
            return True

        # Relevant subdomain (e.g., municipio.alingsas.se)
        kommun_name = self._safe_name(self.namn)
        if kommun_name in host or base_domain.split(".")[0] in host:
            return True

        return False

    def navigate(self, url: str) -> bool:
        """Navigate to URL with rate limiting."""
        if self.page_count >= self.max_pages:
            logger.debug(f"Max pages ({self.max_pages}) reached")
            return False

        norm_url = self._normalize_url(url)
        if norm_url in self.visited_urls:
            return False

        # Check domain
        if not self._is_same_domain(url):
            logger.debug(f"Skipping external URL: {url}")
            return False

        time.sleep(self.delay)
        self.page_count += 1
        self.visited_urls.add(norm_url)

        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)
            # Extra wait for dynamic content
            try:
                self.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass
            return True
        except PlaywrightTimeout:
            self.errors.append(f"Timeout: {url}")
            log_fel(self.kommun_kod, url, "timeout", "Page load timeout")
            return False
        except Exception as e:
            self.errors.append(f"Error: {url} - {str(e)[:50]}")
            log_fel(self.kommun_kod, url, "navigation_error", str(e))
            return False

    def find_politik_links(self) -> list[str]:
        """Find links to politik/beslut sections."""
        links = []

        try:
            elements = self.page.query_selector_all("a[href]")

            for elem in elements:
                href = elem.get_attribute("href")
                text = (elem.inner_text() or "").lower().strip()

                if not href:
                    continue

                full_url = urljoin(self.page.url, href)
                combined = href.lower() + " " + text

                # Check if link is politik-related
                if any(kw in combined for kw in POLITIK_KEYWORDS):
                    if self._normalize_url(full_url) not in self.visited_urls:
                        links.append(full_url)

        except Exception as e:
            logger.debug(f"Error finding politik links: {e}")

        return list(set(links))[:20]  # Limit to prevent explosion

    def find_namnd_links(self) -> list[str]:
        """Find links to specific nämnd pages."""
        links = []

        try:
            elements = self.page.query_selector_all("a[href]")

            for elem in elements:
                href = elem.get_attribute("href")
                text = (elem.inner_text() or "").lower().strip()

                if not href:
                    continue

                full_url = urljoin(self.page.url, href)
                combined = href.lower() + " " + text

                # Check if link is nämnd-related
                if any(kw in combined for kw in NAMND_KEYWORDS):
                    if self._normalize_url(full_url) not in self.visited_urls:
                        links.append(full_url)

        except Exception as e:
            logger.debug(f"Error finding nämnd links: {e}")

        return list(set(links))[:30]

    def find_document_links(self) -> list[dict]:
        """Find all document links on current page."""
        docs = []

        try:
            links = self.page.query_selector_all("a[href]")

            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue

                full_url = urljoin(self.page.url, href)
                text = (link.inner_text() or "").strip()

                # Check if it's a document
                is_doc = any(full_url.lower().endswith(ext) for ext in DOCUMENT_EXTENSIONS)
                is_download = "/download/" in full_url or "/polopoly_fs/" in full_url

                if (is_doc or is_download) and full_url not in self.doc_urls_found:
                    self.doc_urls_found.add(full_url)
                    doc_type = self._classify_document(full_url, text)
                    docs.append(
                        {
                            "url": full_url,
                            "text": text[:100],
                            "type": doc_type,
                        }
                    )

        except Exception as e:
            logger.debug(f"Error finding document links: {e}")

        return docs

    def _classify_document(self, url: str, text: str) -> str:
        """Classify document type based on URL and text."""
        combined = (url + " " + text).lower()

        if any(kw in combined for kw in ["protokoll", "sammanträde", "möte", "kallelse"]):
            return "protokoll"
        elif any(kw in combined for kw in ["beslut", "delegation"]):
            return "beslut"
        elif any(kw in combined for kw in ["policy", "riktlinje", "styrdokument", "reglemente"]):
            return "styrdokument"
        elif any(kw in combined for kw in ["rapport", "utredning", "granskning"]):
            return "rapport"
        elif any(kw in combined for kw in ["upphandling", "anbud", "förfrågning"]):
            return "upphandling"
        elif any(kw in combined for kw in ["budget", "årsredovisning", "ekonomi", "bokslut"]):
            return "ekonomi"
        elif any(kw in combined for kw in ["taxa", "avgift"]):
            return "taxa"
        else:
            return "ovrigt"

    def download_document(self, url: str, doc_type: str, text: str) -> Optional[dict]:
        """Download a document using requests."""
        import requests

        try:
            response = requests.get(
                url,
                timeout=60,
                headers={"User-Agent": "KommunDokumentBot/1.0 (Constitutional AI Research)"},
            )
            response.raise_for_status()

            content = response.content
            sha256 = hashlib.sha256(content).hexdigest()

            # Check for duplicates
            if dokument_exists(sha256):
                logger.debug(f"Skipping duplicate: {url}")
                return None

            # Get extension
            ext = ".pdf"
            for e in DOCUMENT_EXTENSIONS:
                if e in url.lower():
                    ext = e
                    break

            # Save file
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{doc_type}_{date_str}_{sha256[:8]}{ext}"

            type_dir = self.pdf_dir / doc_type
            type_dir.mkdir(exist_ok=True)
            filepath = type_dir / filename

            filepath.write_bytes(content)
            logger.info(f"Downloaded: {filename} ({len(content):,} bytes)")

            return {
                "url": url,
                "filepath": str(filepath),
                "sha256": sha256,
                "size": len(content),
                "extension": ext,
                "doc_type": doc_type,
                "title": text,
            }

        except Exception as e:
            self.errors.append(f"Download error: {url[:50]} - {str(e)[:30]}")
            log_fel(self.kommun_kod, url, "download_error", str(e))
            return None

    def check_sensitive_content(self, text: str) -> bool:
        """Check for sensitive personal data (personnummer)."""
        pnr_pattern = r"\b(19|20)\d{6}[-]?\d{4}\b"
        return bool(re.search(pnr_pattern, text))

    def extract_date(self, url: str, text: str) -> Optional[str]:
        """Extract date from URL or text."""
        patterns = [r"(\d{4})-(\d{2})-(\d{2})", r"(\d{4})(\d{2})(\d{2})"]
        for pattern in patterns:
            for source in [url, text]:
                match = re.search(pattern, source)
                if match:
                    y, m, d = match.groups()
                    if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
                        return f"{y}-{m}-{d}"
        return None

    def run(self) -> ScraperResult:
        """Run the deep-crawl scraper."""
        start_time = time.time()
        doc_type_counts = {
            t: 0
            for t in [
                "protokoll",
                "beslut",
                "styrdokument",
                "rapport",
                "upphandling",
                "ekonomi",
                "taxa",
                "ovrigt",
            ]
        }
        flagged_count = 0
        total_bytes = 0

        logger.info(f"Starting deep crawl of {self.namn} ({self.kommun_kod})")

        # Phase 1: Build URL queue with known Sitevision paths
        urls_to_visit = [self.base_url]

        # Add known Sitevision paths
        for path in SITEVISION_PATHS:
            urls_to_visit.append(f"{self.base_url}{path}")

        # Phase 2: Discover politik sections from homepage
        if self.navigate(self.base_url):
            politik_links = self.find_politik_links()
            logger.info(f"Found {len(politik_links)} politik sections on homepage")
            urls_to_visit.extend(politik_links)

        # Phase 3: Deep crawl politik sections → nämnd pages → documents
        visited_politik = set()

        for url in urls_to_visit:
            if self.page_count >= self.max_pages:
                break

            if url in visited_politik:
                continue
            visited_politik.add(url)

            if not self.navigate(url):
                continue

            logger.info(f"Scanning: {url}")

            # Find documents on this page
            docs = self.find_document_links()
            self.pdf_queue.extend(docs)

            # Find nämnd sub-pages and add to queue
            namnd_links = self.find_namnd_links()
            logger.info(f"  Found {len(docs)} docs, {len(namnd_links)} nämnd links")

            for namnd_url in namnd_links:
                if namnd_url not in visited_politik:
                    visited_politik.add(namnd_url)

                    if not self.navigate(namnd_url):
                        continue

                    # Find documents on nämnd page
                    namnd_docs = self.find_document_links()
                    self.pdf_queue.extend(namnd_docs)
                    logger.info(f"    Nämnd page: {len(namnd_docs)} docs")

        logger.info(f"Total PDFs found: {len(self.pdf_queue)}")

        # Phase 4: Download documents
        downloaded = 0
        for doc_info in self.pdf_queue[: self.max_downloads]:
            result = self.download_document(doc_info["url"], doc_info["type"], doc_info["text"])

            if result:
                downloaded += 1
                doc_date = self.extract_date(doc_info["url"], doc_info["text"])
                needs_masking = self.check_sensitive_content(doc_info["url"] + doc_info["text"])

                doc = Dokument(
                    kommun_kod=self.kommun_kod,
                    kalla_url=doc_info["url"],
                    titel=doc_info["text"][:200] if doc_info["text"] else "Dokument",
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
            pages_visited=self.page_count,
            pdfs_found=len(self.pdf_queue),
        )


def scrape_kommun_deep(
    kommun_kod: str,
    namn: str,
    url: str,
    delay: float = 5.0,
    max_pages: int = 100,
    max_downloads: int = 50,
) -> ScraperResult:
    """Convenience function for deep-crawl scraping."""
    with DeepKommunScraper(kommun_kod, namn, url, delay, max_pages, max_downloads) as scraper:
        return scraper.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deep-crawl kommun document scraper")
    parser.add_argument("--kommun", "-k", required=True, help="Kommun code")
    parser.add_argument("--namn", "-n", required=True, help="Kommun name")
    parser.add_argument("--url", "-u", required=True, help="Start URL")
    parser.add_argument("--delay", "-d", type=float, default=5.0, help="Delay between pages")
    parser.add_argument("--max-pages", "-m", type=int, default=100, help="Max pages to visit")
    parser.add_argument("--max-downloads", type=int, default=50, help="Max docs to download")

    args = parser.parse_args()

    result = scrape_kommun_deep(
        args.kommun,
        args.namn,
        args.url,
        delay=args.delay,
        max_pages=args.max_pages,
        max_downloads=args.max_downloads,
    )

    print("\n" + "=" * 60)
    print(f"RESULTAT: {result.namn} ({result.kommun_kod})")
    print("=" * 60)
    print(f"Sidor besökta: {result.pages_visited}")
    print(f"PDFs hittade: {result.pdfs_found}")
    print(f"Dokument nedladdade: {result.dokument_hamtade}")
    print(f"Total storlek: {result.storlek_bytes / 1024 / 1024:.1f} MB")
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
    output_file = BASE_DIR / f"kommun_harvest_{result.kommun_kod}_deep.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)
    print(f"\nResultat sparat till: {output_file}")
