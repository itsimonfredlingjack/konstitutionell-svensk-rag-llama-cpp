#!/usr/bin/env python3
"""
Pilot: Sekventiell dokumentinsamling från 10 mindre kommuner (15-50k invånare)
Mål: >70% success rate
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

# 10 mindre kommuner (population 15-50k)
PILOT_KOMMUNER = [
    {"kod": "1440", "namn": "Ale", "url": "https://ale.se", "pop": 32000},
    {"kod": "1489", "namn": "Alingsås", "url": "https://alingsas.se", "pop": 42000},
    {"kod": "1984", "namn": "Arboga", "url": "https://arboga.se", "pop": 14000},
    {"kod": "2084", "namn": "Avesta", "url": "https://avesta.se", "pop": 23000},
    {"kod": "2582", "namn": "Boden", "url": "https://boden.se", "pop": 28000},
    {"kod": "1382", "namn": "Falkenberg", "url": "https://falkenberg.se", "pop": 46000},
    {"kod": "1499", "namn": "Falköping", "url": "https://falkoping.se", "pop": 34000},
    {"kod": "1782", "namn": "Filipstad", "url": "https://filipstad.se", "pop": 10000},
    {"kod": "0562", "namn": "Finspång", "url": "https://finspang.se", "pop": 22000},
    {"kod": "0482", "namn": "Flen", "url": "https://flen.se", "pop": 16000},
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
    population: int
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
        self.population = kommun.get("pop", 0)

        self.pdf_dir = PDF_CACHE_DIR / f"{self.kod}_{self._safe_name()}"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.result = PilotResult(
            kommun_kod=self.kod,
            namn=self.namn,
            url=self.base_url,
            population=self.population,
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

        if any(kw in combined for kw in ["protokoll", "sammanträde", "möte", "kallelse"]):
            return "protokoll"
        elif any(kw in combined for kw in ["beslut", "delegation"]):
            return "beslut"
        elif any(kw in combined for kw in ["policy", "riktlinje", "styrdokument", "reglemente"]):
            return "styrdokument"
        elif any(kw in combined for kw in ["rapport", "utredning", "granskning"]):
            return "rapport"
        elif any(kw in combined for kw in ["budget", "årsredovisning", "ekonomi"]):
            return "ekonomi"
        elif any(kw in combined for kw in ["taxa", "avgift"]):
            return "taxa"
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

            # Skip tiny files (likely error pages)
            if len(content) < 1000:
                return None

            sha256 = hashlib.sha256(content).hexdigest()

            if dokument_exists(sha256):
                return None

            filename = f"{doc_type}_{datetime.now().strftime('%Y-%m-%d')}_{sha256[:8]}.pdf"
            type_dir = self.pdf_dir / doc_type
            type_dir.mkdir(exist_ok=True)
            filepath = type_dir / filename
            filepath.write_bytes(content)

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
            self.result.errors.append(f"Download error: {str(e)[:50]}")
            log_fel(self.kod, url, "download_error", str(e))
            return None

    def run(self) -> PilotResult:
        """Run pilot scrape for this kommun."""
        start_time = time.time()
        print(f"\n{'='*60}")
        print(f"PILOT: {self.namn} ({self.kod}) - pop: {self.population:,}")
        print(f"URL: {self.base_url}")
        print(f"{'='*60}")

        # Common document page patterns for smaller kommuner
        doc_paths = [
            "/",
            "/kommun-och-politik/",
            "/kommun/",
            "/politik/",
            "/kommun-politik/",
            "/styrdokument/",
            "/dokument/",
            "/protokoll/",
            "/moten-och-protokoll/",
            "/sammantraden/",
        ]

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent="KommunDokumentBot/1.0", locale="sv-SE")
                page = context.new_page()
                page.set_default_timeout(30000)

                # Visit base URL first
                print(f"Loading {self.base_url}...")
                try:
                    page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)

                    html = page.content()
                    self.result.cms_detected, self.result.cms_indicators = self.detect_cms(
                        html, self.base_url
                    )
                    print(f"CMS: {self.result.cms_detected}")

                    # Find PDFs on homepage
                    pdfs = self.find_pdfs_on_page(page, self.base_url)
                    self.found_pdfs.extend(pdfs)

                except Exception as e:
                    self.result.errors.append(f"Initial load: {str(e)[:50]}")
                    print(f"  Error: {e}")

                # Try document paths
                for doc_path in doc_paths:
                    if len(self.found_pdfs) >= MAX_DOCS_PER_KOMMUN * 5:
                        break

                    full_url = urljoin(self.base_url, doc_path)
                    if full_url in self.visited_urls:
                        continue
                    self.visited_urls.add(full_url)

                    try:
                        page.goto(full_url, wait_until="networkidle", timeout=15000)
                        time.sleep(1)

                        # Check if page exists (not 404)
                        if "404" in page.title().lower() or "finns inte" in page.content().lower():
                            continue

                        pdfs = self.find_pdfs_on_page(page, full_url)
                        if pdfs:
                            print(f"  {doc_path}: {len(pdfs)} PDFs")
                            self.found_pdfs.extend(pdfs)

                        # Check one level deeper for document-related links
                        links = page.query_selector_all("a[href]")
                        for link in links[:10]:
                            href = link.get_attribute("href") or ""
                            text = ""
                            try:
                                text = link.inner_text()[:50].lower()
                            except:
                                pass

                            if any(
                                kw in (href + text)
                                for kw in [
                                    "protokoll",
                                    "beslut",
                                    "handlingar",
                                    "dokument",
                                    "sammanträde",
                                    "kallelse",
                                ]
                            ):
                                sub_url = urljoin(full_url, href)
                                if (
                                    sub_url not in self.visited_urls
                                    and urlparse(sub_url).netloc == urlparse(self.base_url).netloc
                                ):
                                    self.visited_urls.add(sub_url)
                                    try:
                                        page.goto(sub_url, wait_until="networkidle", timeout=15000)
                                        time.sleep(1)
                                        sub_pdfs = self.find_pdfs_on_page(page, sub_url)
                                        if sub_pdfs:
                                            print(f"    -> {len(sub_pdfs)} PDFs")
                                            self.found_pdfs.extend(sub_pdfs)
                                    except:
                                        pass

                    except Exception:
                        pass  # Skip paths that don't exist

                browser.close()

            # Deduplicate
            seen_urls = set()
            unique_pdfs = []
            for pdf in self.found_pdfs:
                if pdf["url"] not in seen_urls:
                    seen_urls.add(pdf["url"])
                    unique_pdfs.append(pdf)

            self.result.docs_found = len(unique_pdfs)
            print(f"\nTotal PDFs found: {len(unique_pdfs)}")

            # Download
            print(f"Downloading up to {MAX_DOCS_PER_KOMMUN}...")

            for pdf in unique_pdfs[:MAX_DOCS_PER_KOMMUN]:
                print(f"  {pdf['title'][:40]}...", end=" ")
                result = self.download_pdf(pdf["url"], pdf["title"], pdf["type"])

                if result:
                    self.result.docs_downloaded += 1
                    self.result.total_bytes += result["size"]
                    self.result.doc_types[result["type"]] = (
                        self.result.doc_types.get(result["type"], 0) + 1
                    )
                    print(f"OK ({result['size']/1024:.0f}KB)")
                else:
                    print("skip")

            # Status
            if self.result.docs_downloaded >= 3:
                self.result.status = "success"
            elif self.result.docs_downloaded > 0:
                self.result.status = "partial"
            else:
                self.result.status = "failed"

        except Exception as e:
            self.result.status = "failed"
            self.result.errors.append(f"Fatal: {str(e)[:50]}")
            print(f"FATAL: {e}")

        self.result.elapsed_seconds = round(time.time() - start_time, 1)

        print(
            f"\n→ {self.result.status.upper()}: {self.result.docs_downloaded} docs, {self.result.total_bytes/1024:.0f}KB, {self.result.elapsed_seconds}s"
        )

        return self.result


def run_pilot():
    """Run pilot on 10 smaller kommuner."""
    print("\n" + "=" * 70)
    print("PILOT: 10 mindre kommuner (15-50k population)")
    print("Mål: >70% success rate")
    print("=" * 70)

    results = []

    for kommun in PILOT_KOMMUNER:
        scraper = KommunPilotScraper(kommun)
        result = scraper.run()
        results.append(result)
        time.sleep(2)

    # Summary
    print("\n" + "=" * 70)
    print("PILOT SUMMARY - Mindre kommuner")
    print("=" * 70)

    total_docs = sum(r.docs_downloaded for r in results)
    total_bytes = sum(r.total_bytes for r in results)
    success_count = sum(1 for r in results if r.status == "success")
    partial_count = sum(1 for r in results if r.status == "partial")
    failed_count = sum(1 for r in results if r.status == "failed")

    success_rate = (success_count + partial_count * 0.5) / len(results) * 100

    print(f"\n✓ Success: {success_count}/10")
    print(f"⚠ Partial: {partial_count}/10")
    print(f"✗ Failed:  {failed_count}/10")
    print(f"\nSuccess rate: {success_rate:.0f}% (mål: >70%)")
    print(f"Total docs: {total_docs}")
    print(f"Total size: {total_bytes/1024/1024:.2f} MB")

    # CMS distribution
    cms_dist = {}
    for r in results:
        cms_dist[r.cms_detected] = cms_dist.get(r.cms_detected, 0) + 1

    print("\nCMS Distribution:")
    for cms, count in sorted(cms_dist.items(), key=lambda x: -x[1]):
        print(f"  {cms}: {count}")

    # Per-kommun
    print(f"\n{'Kommun':<12} {'Pop':<8} {'Status':<10} {'CMS':<12} {'Docs':<6} {'Size':<8}")
    print("-" * 60)
    for r in results:
        size_str = f"{r.total_bytes/1024:.0f}KB" if r.total_bytes > 0 else "0"
        status_icon = "✓" if r.status == "success" else ("⚠" if r.status == "partial" else "✗")
        print(
            f"{r.namn:<12} {r.population:<8} {status_icon} {r.status:<8} {r.cms_detected:<12} {r.docs_downloaded:<6} {size_str:<8}"
        )

    # Failure patterns
    failures = [r for r in results if r.status == "failed"]
    if failures:
        print("\nFailure patterns:")
        for r in failures:
            err = r.errors[0][:60] if r.errors else "No PDFs found"
            print(f"  {r.namn}: {err}")

    # Save results
    output = {
        "pilot_date": datetime.now().isoformat(),
        "pilot_type": "small_kommuner",
        "target_success_rate": 70,
        "actual_success_rate": success_rate,
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

    output_path = BASE_DIR / "pilot_small_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_path}")

    # Success check
    if success_rate >= 70:
        print(f"\n🎉 MÅL UPPNÅTT! Success rate {success_rate:.0f}% >= 70%")
        print("→ Redo för batch-körning på ~200 kommuner")
    else:
        print(f"\n⚠ Mål ej uppnått. Success rate {success_rate:.0f}% < 70%")

    return results, success_rate


if __name__ == "__main__":
    results, rate = run_pilot()
