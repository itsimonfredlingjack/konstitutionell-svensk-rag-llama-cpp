#!/usr/bin/env python3
"""
VETENSKAPSRÅDET DEEP SCRAPER
Använder faktisk site-struktur från vr.se
"""

import hashlib
import json
import sqlite3
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class VRDeepScraper:
    def __init__(self, db_path: str):
        self.base_url = "https://www.vr.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.setup_database()

        self.scraped_urls: set[str] = set()
        self.doc_count = 0

    def setup_database(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                source TEXT,
                url TEXT UNIQUE,
                title TEXT,
                content TEXT,
                published_date TEXT,
                pdf_links TEXT,
                scraped_at TEXT
            )
        """)
        self.conn.commit()

    def generate_doc_id(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def fetch_page(self, url: str) -> BeautifulSoup:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"      ⚠️  Failed: {e}")
            return None

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def save_document(
        self, url: str, title: str, content: str, date: str = "", pdf_links: list = None
    ):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO documents
                (id, source, url, title, content, published_date, pdf_links, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.generate_doc_id(url),
                    "vetenskapsradet",
                    url,
                    title,
                    content,
                    date,
                    json.dumps(pdf_links or []),
                    datetime.now().isoformat(),
                ),
            )
            self.conn.commit()
            self.doc_count += 1
            print(f"      ✓ [{self.doc_count}] {title[:60]}...")
        except Exception as e:
            print(f"      ⚠️  Error saving: {e}")

    def scrape_page(self, url: str):
        """Scrapa en sida och extrahera innehåll"""
        if url in self.scraped_urls:
            return

        soup = self.fetch_page(url)
        if not soup:
            return

        # Titel
        title = soup.find("h1")
        title_text = title.get_text(strip=True) if title else url

        # Datum
        date = ""
        date_elem = soup.find("time")
        if date_elem:
            date = date_elem.get("datetime", date_elem.get_text(strip=True))

        # Innehåll
        content = self.extract_text_content(soup)

        # PDF länkar
        pdf_links = []
        for link in soup.find_all("a", href=True):
            if ".pdf" in link["href"].lower():
                pdf_url = urljoin(url, link["href"])
                pdf_links.append(pdf_url)

        # Spara
        if content and len(content) > 100:  # Minst 100 tecken
            self.save_document(url, title_text, content, date, pdf_links)
            self.scraped_urls.add(url)

    def discover_all_pages(self):
        """Hitta alla sidor från startsidan"""
        print("🔍 Discovering all pages from vr.se...")

        discovered = set()
        to_visit = {self.base_url}

        while to_visit:
            url = to_visit.pop()
            if url in discovered:
                continue

            print(f"  Discovering: {url}")
            soup = self.fetch_page(url)
            if not soup:
                continue

            discovered.add(url)

            # Hitta alla länkar
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.startswith("/"):
                    full_url = urljoin(self.base_url, href)

                    # Filtrera
                    if (
                        self.base_url in full_url
                        and full_url not in discovered
                        and not any(
                            skip in full_url
                            for skip in ["#", "javascript:", ".jpg", ".png", ".gif"]
                        )
                    ):
                        # Prioritera innehållsrika sidor
                        if any(
                            kw in full_url.lower()
                            for kw in [
                                "rapport",
                                "analys",
                                "nyhet",
                                "publikation",
                                "uppdrag",
                                "etik",
                                "infrastruktur",
                                "evenemang",
                            ]
                        ):
                            to_visit.add(full_url)

            time.sleep(0.3)

            # Begränsa discovery (max 200 sidor)
            if len(discovered) >= 200:
                break

        print(f"  ✓ Discovered {len(discovered)} pages")
        return discovered

    def scrape_priority_sections(self):
        """Scrapa prioriterade sektioner"""
        print("\n📚 Scraping priority sections...")

        priority_urls = [
            # Analys och rapporter
            "/analys.html",
            "/analys/rapporter.html",
            "/analys/sa-arbetar-vi-med-analys.html",
            "/analys/sa-kan-svensk-forskning-starkas.html",
            "/analys/svensk-forskning-i-siffror.html",
            # Aktuellt
            "/aktuellt.html",
            "/aktuellt/nyheter.html",
            "/aktuellt/evenemang.html",
            "/aktuellt/generaldirektoren-kommenterar.html",
            # Uppdrag
            "/uppdrag.html",
            "/uppdrag/etik.html",
            "/uppdrag/forskningsinfrastruktur.html",
            "/uppdrag/forskningskommunikation.html",
            # Om
            "/om-vetenskapsradet.html",
            "/om-vetenskapsradet/styrande-dokument.html",
            # Söka finansiering
            "/soka-finansiering.html",
            "/soka-finansiering/krav-och-villkor.html",
        ]

        for path in priority_urls:
            url = urljoin(self.base_url, path)
            print(f"  📄 Scraping: {url}")
            self.scrape_page(url)
            time.sleep(0.5)

    def scrape_all_reports(self):
        """Hitta och scrapa alla rapporter"""
        print("\n📊 Scraping all reports...")

        # Hämta rapportindex
        reports_url = urljoin(self.base_url, "/analys/rapporter.html")
        soup = self.fetch_page(reports_url)

        if soup:
            # Hitta alla rapportlänkar
            report_links = set()
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "vara-rapporter" in href or "rapport" in href.lower():
                    full_url = urljoin(reports_url, href)
                    report_links.add(full_url)

            print(f"  ✓ Found {len(report_links)} reports")

            for i, report_url in enumerate(report_links, 1):
                print(f"  [{i}/{len(report_links)}] {report_url[:80]}")
                self.scrape_page(report_url)
                time.sleep(0.5)

    def scrape_all_news(self):
        """Hitta och scrapa alla nyheter"""
        print("\n📰 Scraping all news...")

        news_url = urljoin(self.base_url, "/aktuellt/nyheter.html")
        soup = self.fetch_page(news_url)

        if soup:
            # Hitta alla nyhetslänkar
            news_links = set()
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "nyhetsarkiv" in href or "nyhet" in href.lower():
                    full_url = urljoin(news_url, href)
                    news_links.add(full_url)

            print(f"  ✓ Found {len(news_links)} news articles")

            for i, news_url in enumerate(list(news_links)[:100], 1):  # Max 100
                print(f"  [{i}/{min(len(news_links), 100)}] {news_url[:80]}")
                self.scrape_page(news_url)
                time.sleep(0.5)

    def export_to_json(self) -> str:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents")

        documents = []
        for row in cursor.fetchall():
            documents.append(
                {
                    "id": row[0],
                    "source": row[1],
                    "url": row[2],
                    "title": row[3],
                    "content": row[4],
                    "published_date": row[5],
                    "pdf_links": json.loads(row[6]) if row[6] else [],
                    "scraped_at": row[7],
                }
            )

        output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/vetenskapsradet_deep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source": "vetenskapsradet",
                    "scraped_at": datetime.now().isoformat(),
                    "total_documents": len(documents),
                    "documents": documents,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        return output_file

    def get_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(LENGTH(content)) FROM documents WHERE LENGTH(content) > 0")
        avg_length = cursor.fetchone()[0] or 0

        print("\n📊 Statistics:")
        print(f"   Total documents: {total}")
        print(f"   Average content length: {avg_length:.0f} chars")

        return total

    def run(self):
        print("=" * 60)
        print("VETENSKAPSRÅDET DEEP SCRAPER")
        print("=" * 60)

        start_time = time.time()

        try:
            # Scrapa i prioritetsordning
            self.scrape_priority_sections()
            self.scrape_all_reports()
            self.scrape_all_news()

            # Stats
            total_docs = self.get_stats()

            # Exportera
            output_file = self.export_to_json()

            elapsed = time.time() - start_time

            print("\n" + "=" * 60)
            print("✅ DONE!")
            print(f"   Documents scraped: {total_docs}")
            print(f"   Time elapsed: {elapsed:.1f}s")
            print(f"   Database: {self.db_path}")
            print(f"   JSON export: {output_file}")
            print("=" * 60)

            return output_file

        finally:
            self.conn.close()


if __name__ == "__main__":
    db_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/vetenskapsradet.db"
    scraper = VRDeepScraper(db_path)
    scraper.run()
