#!/usr/bin/env python3
"""
Pilot: Sekventiell dokumentinsamling från 10 storstäder
Max 5 dokument per kommun, CMS-detection, resultatrapportering
"""

import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from sqlite_state import Dokument, add_dokument, dokument_exists, log_fel

# Configuration
BASE_DIR = Path(__file__).parent
PDF_CACHE_DIR = BASE_DIR / "pdf_cache" / "kommun"
MAX_DOCS_PER_KOMMUN = 5
REQUEST_DELAY = 3.0

# Pilot kommuner (Borås redan klar)
PILOT_KOMMUNER = [
    {
        "kod": "0180",
        "namn": "Stockholm",
        "url": "https://start.stockholm",
        "doc_pages": ["/kommun-politik/", "/om-stockholms-stad/"],
    },
    {
        "kod": "1480",
        "namn": "Göteborg",
        "url": "https://goteborg.se",
        "doc_pages": ["/wps/portal/start/kommun-o-politik/", "/wps/portal/start/"],
    },
    {
        "kod": "1280",
        "namn": "Malmö",
        "url": "https://malmo.se",
        "doc_pages": ["/kommun-och-politik/", "/sa-arbetar-vi-med/"],
    },
    {
        "kod": "0380",
        "namn": "Uppsala",
        "url": "https://uppsala.se",
        "doc_pages": ["/kommun-och-politik/", "/publikationer/"],
    },
    {
        "kod": "0580",
        "namn": "Linköping",
        "url": "https://linkoping.se",
        "doc_pages": ["/kommun-och-politik/", "/"],
    },
    {
        "kod": "1880",
        "namn": "Örebro",
        "url": "https://orebro.se",
        "doc_pages": ["/kommun-och-politik/", "/"],
    },
    {
        "kod": "1980",
        "namn": "Västerås",
        "url": "https://vasteras.se",
        "doc_pages": ["/kommun-och-politik/", "/"],
    },
    {
        "kod": "1283",
        "namn": "Helsingborg",
        "url": "https://helsingborg.se",
        "doc_pages": ["/kommun-och-politik/", "/"],
    },
    {
        "kod": "0680",
        "namn": "Jönköping",
        "url": "https://jonkoping.se",
        "doc_pages": ["/kommun-och-politik/", "/"],
    },
    # Borås redan klar - skippa
]

# CMS detection patterns
CMS_PATTERNS = {
    "sitevision": ["/download/18.", "sv-portal", "sv-layout", "sv-use-margins", "SiteVision"],
    "episerver": ["EPiServer", "episerver", "epi-"],
    "wordpress": ["wp-content", "wp-includes", "WordPress"],
    "drupal": ["drupal", "sites/default"],
    "sharepoint": ["sharepoint", "_layouts"],
    "custom": [],
}


@dataclass
class PilotResult:
    kommun_kod: str
    namn: str
    url: str
    status: str  # success, partial, failed
    cms_detected: str
    cms_indicators: list[str] = field(default_factory=list)
    docs_found: int = 0
    docs_downloaded: int = 0
    total_bytes: int = 0
    doc_types: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class KommunPilotScraper:
    def __init__(self, kommun: dict):
        self.kommun = kommun
        self.kod = kommun["kod"]
        self.namn = kommun["namn"]
        self.base_url = kommun["url"]
        self.doc_pages = kommun.get("doc_pages", ["/"])

        self.pdf_dir = PDF_CACHE_DIR / f"{self.kod}_{self._safe_name()}"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.result = PilotResult(
            kommun_kod=self.kod,
            namn=self.namn,
            url=self.base_url,
            status="pending",
            cms_detected="unknown",
        )

        self.visited_urls = set()
        self.found_pdfs = []

    def _safe_name(self) -> str:
        return (
            self.namn.lower()
            .replace(" ", "_")
            .replace("å", "a")
            .replace("ä", "a")
            .replace("ö", "o")
        )

    def detect_cms(self, html: str, page_url: str) -> tuple:
        """Detect CMS from HTML content."""
        indicators = []

        for cms, patterns in CMS_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in html.lower():
                    indicators.append(pattern)
                    if cms != "custom":
                        return cms, indicators

        # Check for specific URL patterns
        if "/download/18." in page_url or "/download/18." in html:
            return "sitevision", ["/download/18."]

        return "custom", indicators

    def find_pdfs_on_page(self, page: Page, base_url: str) -> list[dict]:
        """Find PDF links on current page."""
        pdfs = []

        try:
            links = page.query_selector_all("a[href]")

            for link in links:
                href = link.get_attribute("href") or ""
                text = ""
                try:
                    text = link.inner_text()[:100] if link.inner_text() else ""
                except:
                    pass

                full_url = urljoin(base_url, href)

                # Check for PDF
                is_pdf = (
                    ".pdf" in href.lower()
                    or "/download/" in href.lower()
                    or "filetype=pdf" in href.lower()
                )

                if is_pdf and full_url not in [p["url"] for p in pdfs]:
                    doc_type = self._classify_doc(href, text)
                    pdfs.append(
                        {
                            "url": full_url,
                            "title": text.strip()[:100] if text else "Dokument",
                            "type": doc_type,
                        }
                    )

        except Exception as e:
            self.result.errors.append(f"PDF scan error: {e}")

        return pdfs

    def _classify_doc(self, url: str, text: str) -> str:
        """Classify document type."""
        combined = (url + " " + text).lower()

        if any(kw in combined for kw in ["protokoll", "sammanträde", "möte"]):
            return "protokoll"
        elif any(kw in combined for kw in ["beslut", "delegation"]):
            return "beslut"
        elif any(kw in combined for kw in ["policy", "riktlinje", "styrdokument"]):
            return "styrdokument"
        elif any(kw in combined for kw in ["rapport", "utredning"]):
            return "rapport"
        elif any(kw in combined for kw in ["budget", "årsredovisning"]):
            return "ekonomi"
        else:
            return "ovrigt"

    def download_pdf(self, url: str, title: str, doc_type: str) -> Optional[dict]:
        """Download a PDF file."""
        try:
            time.sleep(REQUEST_DELAY)

            resp = requests.get(
                url,
                timeout=60,
                headers={"User-Agent": "KommunDokumentBot/1.0 (Constitutional AI Research)"},
            )
            resp.raise_for_status()

            content = resp.content
            sha256 = hashlib.sha256(content).hexdigest()

            # Check duplicate
            if dokument_exists(sha256):
                return None

            # Save file
            filename = f"{doc_type}_{datetime.now().strftime('%Y-%m-%d')}_{sha256[:8]}.pdf"
            type_dir = self.pdf_dir / doc_type
            type_dir.mkdir(exist_ok=True)
            filepath = type_dir / filename
            filepath.write_bytes(content)

            # Add to database
            doc = Dokument(
                kommun_kod=self.kod,
                kalla_url=url,
                titel=title,
                dokument_datum=None,
                filtyp=".pdf",
                storlek_bytes=len(content),
                sha256=sha256,
                relevans_tagg=doc_type,
                kraver_maskning=False,
                kvalitet_score=3,
                hamtat=datetime.now().isoformat(),
                lokal_sokvag=str(filepath),
                indexerad=False,
            )
            add_dokument(doc)

            return {"path": str(filepath), "size": len(content), "type": doc_type}

        except Exception as e:
            self.result.errors.append(f"Download error {url[:50]}: {str(e)[:50]}")
            log_fel(self.kod, url, "download_error", str(e))
            return None

    def run(self) -> PilotResult:
        """Run pilot scrape for this kommun."""
        start_time = time.time()
        print(f"\n{'='*60}")
        print(f"PILOT: {self.namn} ({self.kod})")
        print(f"URL: {self.base_url}")
        print(f"{'='*60}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent="KommunDokumentBot/1.0", locale="sv-SE")
                page = context.new_page()
                page.set_default_timeout(30000)

                # Visit base URL first for CMS detection
                print(f"Loading {self.base_url}...")
                try:
                    page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)

                    html = page.content()
                    self.result.cms_detected, self.result.cms_indicators = self.detect_cms(
                        html, self.base_url
                    )
                    print(f"CMS detected: {self.result.cms_detected}")

                except Exception as e:
                    self.result.errors.append(f"Initial load failed: {e}")
                    print(f"  Error loading base URL: {e}")

                # Scan document pages
                for doc_path in self.doc_pages:
                    if len(self.found_pdfs) >= MAX_DOCS_PER_KOMMUN * 3:
                        break

                    full_url = urljoin(self.base_url, doc_path)
                    if full_url in self.visited_urls:
                        continue
                    self.visited_urls.add(full_url)

                    print(f"Scanning: {doc_path}")

                    try:
                        page.goto(full_url, wait_until="networkidle", timeout=30000)
                        time.sleep(2)

                        # Find PDFs
                        pdfs = self.find_pdfs_on_page(page, full_url)
                        print(f"  Found {len(pdfs)} potential PDFs")

                        # Also check sub-links for document pages
                        links = page.query_selector_all("a[href]")
                        subpages = []

                        for link in links:
                            href = link.get_attribute("href") or ""
                            text = link.inner_text()[:50] if link.inner_text() else ""

                            # Look for document-related subpages
                            if any(
                                kw in (href + text).lower()
                                for kw in [
                                    "protokoll",
                                    "beslut",
                                    "handlingar",
                                    "sammanträde",
                                    "dokument",
                                ]
                            ):
                                sub_url = urljoin(full_url, href)
                                if (
                                    sub_url not in self.visited_urls
                                    and urlparse(sub_url).netloc == urlparse(self.base_url).netloc
                                ):
                                    subpages.append(sub_url)

                        # Check first 2 subpages
                        for sub_url in subpages[:2]:
                            if len(self.found_pdfs) >= MAX_DOCS_PER_KOMMUN * 3:
                                break

                            self.visited_urls.add(sub_url)
                            print(f"  Checking subpage: {sub_url[:60]}...")

                            try:
                                page.goto(sub_url, wait_until="networkidle", timeout=30000)
                                time.sleep(2)
                                sub_pdfs = self.find_pdfs_on_page(page, sub_url)
                                pdfs.extend(sub_pdfs)
                            except:
                                pass

                        self.found_pdfs.extend(pdfs)

                    except Exception as e:
                        self.result.errors.append(f"Scan error {doc_path}: {str(e)[:50]}")
                        print(f"  Error: {e}")

                browser.close()

            # Deduplicate PDFs
            seen_urls = set()
            unique_pdfs = []
            for pdf in self.found_pdfs:
                if pdf["url"] not in seen_urls:
                    seen_urls.add(pdf["url"])
                    unique_pdfs.append(pdf)

            self.result.docs_found = len(unique_pdfs)
            print(f"\nTotal unique PDFs found: {len(unique_pdfs)}")

            # Download up to MAX_DOCS
            print(f"Downloading up to {MAX_DOCS_PER_KOMMUN} documents...")

            for pdf in unique_pdfs[:MAX_DOCS_PER_KOMMUN]:
                print(f"  Downloading: {pdf['title'][:50]}...")
                result = self.download_pdf(pdf["url"], pdf["title"], pdf["type"])

                if result:
                    self.result.docs_downloaded += 1
                    self.result.total_bytes += result["size"]
                    self.result.doc_types[result["type"]] = (
                        self.result.doc_types.get(result["type"], 0) + 1
                    )
                    print(f"    OK: {result['size']/1024:.1f} KB")
                else:
                    print("    Skipped (duplicate or error)")

            # Set status
            if self.result.docs_downloaded > 0:
                self.result.status = (
                    "success" if self.result.docs_downloaded >= MAX_DOCS_PER_KOMMUN else "partial"
                )
            else:
                self.result.status = "failed"

        except Exception as e:
            self.result.status = "failed"
            self.result.errors.append(f"Fatal error: {e!s}")
            print(f"FATAL ERROR: {e}")

        self.result.elapsed_seconds = round(time.time() - start_time, 1)

        # Summary
        print(f"\n--- Result for {self.namn} ---")
        print(f"Status: {self.result.status}")
        print(f"CMS: {self.result.cms_detected}")
        print(f"Docs: {self.result.docs_downloaded}/{self.result.docs_found} found")
        print(f"Size: {self.result.total_bytes/1024:.1f} KB")
        print(f"Time: {self.result.elapsed_seconds}s")
        if self.result.errors:
            print(f"Errors: {len(self.result.errors)}")

        return self.result


def run_pilot():
    """Run pilot on all 10 kommuner sequentially."""
    print("\n" + "=" * 70)
    print("KOMMUN PILOT: 10 storstäder (max 5 docs each)")
    print("=" * 70)

    results = []

    # Add Borås as already complete
    boras_result = PilotResult(
        kommun_kod="1490",
        namn="Borås",
        url="https://boras.se",
        status="success",
        cms_detected="sitevision",
        cms_indicators=["/download/18.", "SiteVision"],
        docs_found=9,
        docs_downloaded=2,
        total_bytes=9766419,
        doc_types={"protokoll": 2},
        elapsed_seconds=0,
    )
    results.append(boras_result)
    print("\nBorås: Already complete (2 docs, 9.3 MB)")

    # Run pilot for remaining kommuner
    for kommun in PILOT_KOMMUNER:
        scraper = KommunPilotScraper(kommun)
        result = scraper.run()
        results.append(result)
        time.sleep(2)  # Pause between kommuner

    # Generate summary
    print("\n" + "=" * 70)
    print("PILOT SUMMARY")
    print("=" * 70)

    total_docs = sum(r.docs_downloaded for r in results)
    total_bytes = sum(r.total_bytes for r in results)
    success_count = sum(1 for r in results if r.status == "success")
    partial_count = sum(1 for r in results if r.status == "partial")
    failed_count = sum(1 for r in results if r.status == "failed")

    print(f"\nOverall: {success_count} success, {partial_count} partial, {failed_count} failed")
    print(f"Total docs: {total_docs}")
    print(f"Total size: {total_bytes/1024/1024:.2f} MB")

    # CMS distribution
    cms_dist = {}
    for r in results:
        cms_dist[r.cms_detected] = cms_dist.get(r.cms_detected, 0) + 1

    print("\nCMS Distribution:")
    for cms, count in sorted(cms_dist.items(), key=lambda x: -x[1]):
        print(f"  {cms}: {count} kommuner")

    # Per-kommun summary
    print("\nPer kommun:")
    print(f"{'Kommun':<15} {'Status':<10} {'CMS':<12} {'Docs':<8} {'Size':<10} {'Errors'}")
    print("-" * 70)
    for r in results:
        size_str = f"{r.total_bytes/1024:.0f}KB" if r.total_bytes > 0 else "0"
        error_str = str(len(r.errors)) if r.errors else "-"
        print(
            f"{r.namn:<15} {r.status:<10} {r.cms_detected:<12} {r.docs_downloaded:<8} {size_str:<10} {error_str}"
        )

    # Failure patterns
    if failed_count > 0:
        print("\nFailure patterns:")
        for r in results:
            if r.status == "failed" and r.errors:
                print(f"  {r.namn}: {r.errors[0][:60]}")

    # Save results
    output = {
        "pilot_date": datetime.now().isoformat(),
        "summary": {
            "total_kommuner": len(results),
            "success": success_count,
            "partial": partial_count,
            "failed": failed_count,
            "total_docs": total_docs,
            "total_bytes": total_bytes,
            "cms_distribution": cms_dist,
        },
        "results": [asdict(r) for r in results],
    }

    output_path = BASE_DIR / "pilot_10_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_path}")

    return results


if __name__ == "__main__":
    run_pilot()
