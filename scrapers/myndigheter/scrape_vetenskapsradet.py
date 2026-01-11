#!/usr/bin/env python3
"""
VETENSKAPSRÅDET SCRAPER
Hämtar rapporter, publikationer och forskningspolicy från vr.se
Lagrar i ChromaDB collection: swedish_gov_docs | source: vetenskapsradet
"""

import hashlib
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup


class VetenskapsradetScraper:
    def __init__(self, chromadb_path: str):
        self.base_url = "https://www.vr.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        # ChromaDB
        self.client = chromadb.PersistentClient(path=chromadb_path)
        try:
            self.collection = self.client.get_collection("swedish_gov_docs")
        except:
            self.collection = self.client.create_collection(
                name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
            )

        self.scraped_urls: set[str] = set()
        self.documents: list[dict] = []

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
                    raise
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

    def scrape_publication_page(self, url: str) -> dict:
        """Scrapa enskild publikation"""
        try:
            soup = self.fetch_page(url)

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
        print("📚 Scraping Publikationer...")

        sections = [
            "/publikationer",
            "/analys/rapporter",
            "/publikationer/alla-publikationer",
            "/om-oss/publikationer-och-press/publikationer",
        ]

        for section in sections:
            url = urljoin(self.base_url, section)
            try:
                print(f"  🔍 Checking {url}")
                soup = self.fetch_page(url)

                # Leta efter publikationslänkar
                links = soup.find_all("a", href=True)
                pub_links = []

                for link in links:
                    href = link["href"]
                    full_url = urljoin(url, href)

                    # Filtrera relevanta länkar
                    if any(
                        keyword in full_url.lower()
                        for keyword in ["rapport", "publikation", "analys", "policy", "redovisning"]
                    ):
                        if full_url not in self.scraped_urls:
                            pub_links.append(full_url)

                print(f"    ✓ Found {len(pub_links)} potential publications")

                # Scrapa varje publikation
                for pub_url in pub_links[:50]:  # Begränsa för testning
                    if pub_url not in self.scraped_urls:
                        print(f"    📄 Scraping: {pub_url}")
                        doc = self.scrape_publication_page(pub_url)
                        if doc:
                            self.documents.append(doc)
                            self.scraped_urls.add(pub_url)
                        time.sleep(1)  # Rate limiting

            except Exception as e:
                print(f"  ⚠️  Error in section {section}: {e}")

    def scrape_news_and_press(self):
        """Scrapa nyheter och pressmeddelanden"""
        print("📰 Scraping Nyheter och Press...")

        sections = [
            "/aktuellt-och-press",
            "/aktuellt-och-press/nyheter",
            "/aktuellt-och-press/pressmeddelanden",
        ]

        for section in sections:
            url = urljoin(self.base_url, section)
            try:
                print(f"  🔍 Checking {url}")
                soup = self.fetch_page(url)

                # Leta efter artikellänkar
                articles = soup.find_all(
                    ["article", "div"], class_=re.compile(r"news|article|post")
                )

                for article in articles[:30]:  # Begränsa
                    link = article.find("a", href=True)
                    if link:
                        article_url = urljoin(url, link["href"])
                        if article_url not in self.scraped_urls:
                            print(f"    📰 Scraping: {article_url}")
                            doc = self.scrape_publication_page(article_url)
                            if doc:
                                self.documents.append(doc)
                                self.scraped_urls.add(article_url)
                            time.sleep(1)

            except Exception as e:
                print(f"  ⚠️  Error in section {section}: {e}")

    def scrape_research_areas(self):
        """Scrapa forskningsområden och strategi"""
        print("🔬 Scraping Forskningsområden...")

        sections = ["/finansiering", "/om-oss/strategi", "/om-oss/sa-arbetar-vi"]

        for section in sections:
            url = urljoin(self.base_url, section)
            try:
                print(f"  🔍 Scraping: {url}")
                doc = self.scrape_publication_page(url)
                if doc:
                    self.documents.append(doc)
                    self.scraped_urls.add(url)
                time.sleep(1)
            except Exception as e:
                print(f"  ⚠️  Error: {e}")

    def save_to_chromadb(self):
        """Spara alla dokument till ChromaDB"""
        print(f"\n💾 Saving {len(self.documents)} documents to ChromaDB...")

        if not self.documents:
            print("  ⚠️  No documents to save")
            return

        ids = []
        documents = []
        metadatas = []

        for doc in self.documents:
            doc_id = self.generate_doc_id(doc["url"])

            # Metadata
            metadata = {
                "source": "vetenskapsradet",
                "url": doc["url"],
                "title": doc["title"][:500] if doc["title"] else "",
                "scraped_at": doc["scraped_at"],
            }

            if doc.get("date"):
                metadata["published_date"] = doc["date"]

            if doc.get("pdf_links"):
                metadata["pdf_links"] = json.dumps(doc["pdf_links"])

            # Begränsa content till vad ChromaDB klarar
            content = doc["content"][:10000] if doc["content"] else ""

            ids.append(doc_id)
            documents.append(content)
            metadatas.append(metadata)

        # Spara i batches
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]

            try:
                self.collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
                print(f"  ✓ Saved batch {i // batch_size + 1} ({len(batch_ids)} docs)")
            except Exception as e:
                print(f"  ⚠️  Error saving batch: {e}")

    def export_results(self, output_file: str):
        """Exportera resultat till JSON"""
        print(f"\n📊 Exporting results to {output_file}...")

        results = {
            "source": "vetenskapsradet",
            "scraped_at": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "total_urls": len(self.scraped_urls),
            "documents": self.documents,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"  ✓ Exported {len(self.documents)} documents")

    def run(self):
        """Kör full scraping"""
        print("=" * 60)
        print("VETENSKAPSRÅDET SCRAPER")
        print("=" * 60)

        start_time = time.time()

        # Scrapa olika sektioner
        self.scrape_publications_section()
        self.scrape_news_and_press()
        self.scrape_research_areas()

        # Spara
        self.save_to_chromadb()

        # Exportera
        output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/vetenskapsradet_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.export_results(output_file)

        elapsed = time.time() - start_time

        print("\n" + "=" * 60)
        print("✅ DONE!")
        print(f"   Documents scraped: {len(self.documents)}")
        print(f"   Time elapsed: {elapsed:.1f}s")
        print(f"   Results: {output_file}")
        print("=" * 60)


if __name__ == "__main__":
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

    scraper = VetenskapsradetScraper(chromadb_path)
    scraper.run()
