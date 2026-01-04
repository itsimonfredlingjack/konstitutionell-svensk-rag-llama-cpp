#!/usr/bin/env python3
"""
VETENSKAPSRÅDET SCRAPER - SQLite Version
Hämtar rapporter, publikationer och forskningspolicy från vr.se
Sparar till SQLite först, sedan till ChromaDB
"""

import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class VetenskapsradetScraperSQLite:
    def __init__(self, db_path: str):
        self.base_url = "https://www.vr.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        # SQLite
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.setup_database()

        self.scraped_urls: set[str] = set()
        self.doc_count = 0

    def setup_database(self):
        """Skapa databas schema"""
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
        """Generera unikt ID baserat på URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def fetch_page(self, url: str, retries: int = 3) -> BeautifulSoup:
        """Hämta och parsa sida med retry-logik"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, "html.parser")
            except Exception as e:
                if attempt == retries - 1:
                    print(f"  ❌ Failed after {retries} attempts: {url} - {e}")
                    return None
                time.sleep(2**attempt)
        return None

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extrahera ren text från sida"""
        # Ta bort script, style
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Extrahera text
        text = soup.get_text(separator="\n", strip=True)

        # Rensa
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def save_document(self, doc: dict):
        """Spara dokument till SQLite"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO documents
                (id, source, url, title, content, published_date, pdf_links, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.generate_doc_id(doc["url"]),
                    "vetenskapsradet",
                    doc["url"],
                    doc.get("title", ""),
                    doc.get("content", ""),
                    doc.get("date", ""),
                    json.dumps(doc.get("pdf_links", [])),
                    doc["scraped_at"],
                ),
            )
            self.conn.commit()
            self.doc_count += 1
            print(f"      ✓ Saved [{self.doc_count}] {doc['title'][:60]}...")
        except Exception as e:
            print(f"      ⚠️  Error saving: {e}")

    def scrape_publication_page(self, url: str) -> dict:
        """Scrapa enskild publikation"""
        try:
            soup = self.fetch_page(url)
            if not soup:
                return None

            # Titel
            title = None
            if soup.find("h1"):
                title = soup.find("h1").get_text(strip=True)

            # Datum
            date = None
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

            return {
                "url": url,
                "title": title or url,
                "content": content,
                "date": date,
                "pdf_links": pdf_links,
                "scraped_at": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"  ⚠️  Error scraping {url}: {e}")
            return None

    def scrape_publications_section(self):
        """Scrapa publikationssektionen"""
        print("\n📚 Scraping Publikationer...")

        sections = [
            "/publikationer",
            "/analys/rapporter",
            "/publikationer/alla-publikationer",
            "/om-oss/publikationer-och-press/publikationer",
            "/analys",
            "/download",
        ]

        for section in sections:
            url = urljoin(self.base_url, section)
            try:
                print(f"\n  🔍 Checking {url}")
                soup = self.fetch_page(url)
                if not soup:
                    continue

                # Leta efter publikationslänkar
                links = soup.find_all("a", href=True)
                pub_links = set()

                for link in links:
                    href = link["href"]
                    full_url = urljoin(url, href)

                    # Filtrera relevanta länkar
                    if self.base_url in full_url and any(
                        keyword in full_url.lower()
                        for keyword in [
                            "rapport",
                            "publikation",
                            "analys",
                            "policy",
                            "redovisning",
                            "download",
                        ]
                    ):
                        if full_url not in self.scraped_urls:
                            pub_links.add(full_url)

                print(f"    ✓ Found {len(pub_links)} potential publications")

                # Scrapa varje publikation
                for i, pub_url in enumerate(list(pub_links)[:100], 1):  # Max 100 per sektion
                    if pub_url not in self.scraped_urls:
                        print(f"    [{i}/{min(len(pub_links), 100)}] Scraping: {pub_url[:80]}...")
                        doc = self.scrape_publication_page(pub_url)
                        if doc and doc["content"]:
                            self.save_document(doc)
                            self.scraped_urls.add(pub_url)
                        time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"  ⚠️  Error in section {section}: {e}")

    def scrape_news_and_press(self):
        """Scrapa nyheter och pressmeddelanden"""
        print("\n📰 Scraping Nyheter och Press...")

        sections = [
            "/aktuellt-och-press",
            "/aktuellt-och-press/nyheter",
            "/aktuellt-och-press/pressmeddelanden",
        ]

        for section in sections:
            url = urljoin(self.base_url, section)
            try:
                print(f"\n  🔍 Checking {url}")
                soup = self.fetch_page(url)
                if not soup:
                    continue

                # Leta efter artikellänkar
                articles = soup.find_all(
                    ["article", "div", "li"], class_=re.compile(r"news|article|post|item")
                )

                print(f"    ✓ Found {len(articles)} potential articles")

                for i, article in enumerate(articles[:50], 1):  # Max 50
                    link = article.find("a", href=True)
                    if link:
                        article_url = urljoin(url, link["href"])
                        if article_url not in self.scraped_urls and self.base_url in article_url:
                            print(
                                f"    [{i}/{min(len(articles), 50)}] Scraping: {article_url[:80]}..."
                            )
                            doc = self.scrape_publication_page(article_url)
                            if doc and doc["content"]:
                                self.save_document(doc)
                                self.scraped_urls.add(article_url)
                            time.sleep(0.5)

            except Exception as e:
                print(f"  ⚠️  Error in section {section}: {e}")

    def scrape_research_areas(self):
        """Scrapa forskningsområden och strategi"""
        print("\n🔬 Scraping Forskningsområden...")

        sections = [
            "/finansiering",
            "/om-oss/strategi",
            "/om-oss/sa-arbetar-vi",
            "/om-oss",
            "/vara-omraden",
        ]

        for section in sections:
            url = urljoin(self.base_url, section)
            try:
                print(f"  🔍 Scraping: {url}")
                doc = self.scrape_publication_page(url)
                if doc and doc["content"]:
                    self.save_document(doc)
                    self.scraped_urls.add(url)
                time.sleep(0.5)
            except Exception as e:
                print(f"  ⚠️  Error: {e}")

    def export_to_json(self) -> str:
        """Exportera alla dokument till JSON"""
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

        output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/vetenskapsradet_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

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
        """Visa statistik"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(LENGTH(content)) FROM documents")
        avg_length = cursor.fetchone()[0]

        print("\n📊 Statistics:")
        print(f"   Total documents: {total}")
        print(f"   Average content length: {avg_length:.0f} chars")

        return total

    def run(self):
        """Kör full scraping"""
        print("=" * 60)
        print("VETENSKAPSRÅDET SCRAPER (SQLite)")
        print("=" * 60)

        start_time = time.time()

        try:
            # Scrapa olika sektioner
            self.scrape_publications_section()
            self.scrape_news_and_press()
            self.scrape_research_areas()

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

    scraper = VetenskapsradetScraperSQLite(db_path)
    scraper.run()
