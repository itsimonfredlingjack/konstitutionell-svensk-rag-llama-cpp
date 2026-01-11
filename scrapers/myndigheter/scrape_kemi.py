#!/usr/bin/env python3
"""
KEMIKALIEINSPEKTIONEN SCRAPER
Target: KIFS, rapporter, vägledningar, publikationer
ChromaDB collection: swedish_gov_docs | source: kemi
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

# Configuration
BASE_URL = "https://kemi.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI")
RATE_DELAY = 1.5  # Polite crawling
MAX_TEXT_LENGTH = 50000

HEADERS = {
    "User-Agent": "ConstitutionalNerdyAI/2.0 (swedish-gov-docs-harvest)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


@dataclass
class Document:
    doc_id: str
    title: str
    url: str
    doc_type: str
    text_content: str
    date: str
    source: str = "kemi"
    metadata: dict = None


class KemiScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.visited_urls: set[str] = set()
        self.documents: list[Document] = []
        self.stats = {"crawled": 0, "extracted": 0, "errors": 0, "duplicates": 0}

    def fetch_page(self, url: str) -> str:
        """Fetch page with error handling"""
        try:
            if url in self.visited_urls:
                self.stats["duplicates"] += 1
                return None

            print(f"  Fetching: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.visited_urls.add(url)
            self.stats["crawled"] += 1
            time.sleep(RATE_DELAY)
            return response.text

        except Exception as e:
            print(f"  ERROR: {e}")
            self.stats["errors"] += 1
            return None

    def extract_text_from_html(self, html: str, url: str) -> str:
        """Extract clean text from HTML"""
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Remove script, style, nav, footer
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            # Get main content
            main_content = (
                soup.find("main") or soup.find("article") or soup.find("div", class_="content")
            )
            if main_content:
                text = main_content.get_text(separator=" ", strip=True)
            else:
                text = soup.get_text(separator=" ", strip=True)

            # Clean whitespace
            text = re.sub(r"\s+", " ", text).strip()
            return text[:MAX_TEXT_LENGTH]

        except Exception as e:
            print(f"  Text extraction error: {e}")
            return ""

    def scrape_kifs_regulations(self) -> list[Document]:
        """Scrape KIFS föreskrifter"""
        print("\n SCRAPING: KIFS Föreskrifter")
        docs = []

        # Main KIFS page
        main_url = f"{BASE_URL}/lagar-och-regler/lagstiftningar-inom-kemikalieomradet/kemikalieinspektionens-foreskrifter-kifs"
        html = self.fetch_page(main_url)
        if not html:
            return docs

        soup = BeautifulSoup(html, "html.parser")

        # Find all KIFS links (active and discontinued)
        kifs_links = soup.find_all("a", href=re.compile(r"/kifs-\d{4}"))

        for link in kifs_links:
            kifs_url = urljoin(BASE_URL, link["href"])
            kifs_html = self.fetch_page(kifs_url)

            if not kifs_html:
                continue

            kifs_soup = BeautifulSoup(kifs_html, "html.parser")
            title = kifs_soup.find("h1")
            title_text = title.get_text(strip=True) if title else link.get_text(strip=True)

            # Extract date
            date_match = re.search(r"\d{4}[-:]\d+", kifs_url)
            date = date_match.group(0).replace("-", ":") if date_match else ""

            text_content = self.extract_text_from_html(kifs_html, kifs_url)

            if text_content and len(text_content) > 200:
                doc_id = hashlib.md5(kifs_url.encode()).hexdigest()
                docs.append(
                    Document(
                        doc_id=doc_id,
                        title=title_text,
                        url=kifs_url,
                        doc_type="föreskrift",
                        text_content=text_content,
                        date=date,
                        metadata={"kifs_id": date},
                    )
                )
                self.stats["extracted"] += 1
                print(f"    ✓ {title_text}")

        print(f"  KIFS: {len(docs)} documents")
        return docs

    def scrape_publication_category(self, category_url: str, category_name: str) -> list[Document]:
        """Scrape a publication category"""
        print(f"\n SCRAPING: {category_name}")
        docs = []

        html = self.fetch_page(category_url)
        if not html:
            return docs

        soup = BeautifulSoup(html, "html.parser")

        # Find all publication links
        pub_links = soup.find_all("a", href=True)

        for link in pub_links:
            href = link["href"]

            # Skip navigation links
            if any(
                skip in href for skip in ["/om-kemi", "/kontakt", "/sok", "/publication", "mailto:"]
            ):
                continue

            # Only follow internal links
            if not href.startswith("/") and not href.startswith(BASE_URL):
                continue

            full_url = urljoin(BASE_URL, href)

            # Check if it's a document page
            if "/publikationer/" in full_url and full_url not in self.visited_urls:
                pub_html = self.fetch_page(full_url)

                if not pub_html:
                    continue

                pub_soup = BeautifulSoup(pub_html, "html.parser")
                title = pub_soup.find("h1")
                title_text = title.get_text(strip=True) if title else link.get_text(strip=True)

                # Extract publication date
                date_elem = pub_soup.find("time") or pub_soup.find(class_="date")
                date = date_elem.get_text(strip=True) if date_elem else ""

                text_content = self.extract_text_from_html(pub_html, full_url)

                if text_content and len(text_content) > 200:
                    doc_id = hashlib.md5(full_url.encode()).hexdigest()
                    docs.append(
                        Document(
                            doc_id=doc_id,
                            title=title_text,
                            url=full_url,
                            doc_type=category_name.lower(),
                            text_content=text_content,
                            date=date,
                            metadata={"category": category_name},
                        )
                    )
                    self.stats["extracted"] += 1
                    print(f"    ✓ {title_text[:60]}...")

                if len(docs) >= 50:  # Limit per category
                    break

        print(f"  {category_name}: {len(docs)} documents")
        return docs

    def scrape_all_publications(self) -> list[Document]:
        """Scrape all publication categories"""
        categories = [
            ("/publikationer/rapporter", "Rapporter"),
            ("/publikationer/faktablad", "Faktablad"),
            ("/publikationer/broschyrer-och-foldrar", "Broschyrer"),
            ("/publikationer/pm", "PM"),
            ("/publikationer/tillsynsrapporter", "Tillsynsrapporter"),
            ("/publikationer/arsredovisningar-och-budgetunderlag", "Årsredovisningar"),
        ]

        all_docs = []
        for path, name in categories:
            url = f"{BASE_URL}{path}"
            docs = self.scrape_publication_category(url, name)
            all_docs.extend(docs)

        return all_docs

    def index_to_chromadb(self, documents: list[Document]):
        """Index documents to ChromaDB"""
        if not documents:
            print("\n  No documents to index!")
            return

        print(f"\n INDEXING: {len(documents)} documents to ChromaDB...")

        try:
            # Load embedding model (paraphrase-multilingual-MiniLM-L12-v2 = 384 dimensions)
            print("  Loading embedding model...")
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

            # Connect to ChromaDB
            client = chromadb.PersistentClient(path=CHROMADB_PATH)
            collection = client.get_or_create_collection(name=COLLECTION_NAME)

            batch_size = 50
            indexed = 0

            for i in range(0, len(documents), batch_size):
                batch = documents[i : i + batch_size]

                ids = []
                texts = []
                embeddings = []
                metadatas = []

                for doc in batch:
                    # Create embedding text
                    embed_text = f"{doc.title}. {doc.text_content[:2000]}"
                    embedding = model.encode(embed_text).tolist()

                    ids.append(doc.doc_id)
                    texts.append(doc.text_content[:5000])
                    embeddings.append(embedding)
                    metadatas.append(
                        {
                            "title": doc.title[:200],
                            "url": doc.url,
                            "doc_type": doc.doc_type,
                            "source": doc.source,
                            "date": doc.date,
                            "indexed_at": datetime.now().isoformat(),
                        }
                    )

                collection.upsert(
                    ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas
                )

                indexed += len(batch)
                print(f"  Batch {i // batch_size + 1}: {indexed}/{len(documents)}")

            final_count = collection.count()
            print(f"\n CHROMADB: {final_count:,} total documents in collection")

        except Exception as e:
            print(f"\n  ChromaDB Error: {e}")
            import traceback

            traceback.print_exc()

    def run(self):
        """Main execution"""
        start_time = time.time()

        print("""
╔═══════════════════════════════════════════════════════════════════╗
║                  KEMIKALIEINSPEKTIONEN SCRAPER                    ║
║                        kemi.se → ChromaDB                         ║
╚═══════════════════════════════════════════════════════════════════╝
        """)

        # Scrape KIFS
        kifs_docs = self.scrape_kifs_regulations()
        self.documents.extend(kifs_docs)

        # Scrape Publications
        pub_docs = self.scrape_all_publications()
        self.documents.extend(pub_docs)

        # Index to ChromaDB
        self.index_to_chromadb(self.documents)

        # Generate report
        elapsed = time.time() - start_time

        report = {
            "operation": "KEMI_SCRAPE",
            "timestamp": datetime.now().isoformat(),
            "source": "kemi.se",
            "documents_collected": len(self.documents),
            "stats": self.stats,
            "time_seconds": elapsed,
            "documents_by_type": {},
        }

        # Count by type
        for doc in self.documents:
            report["documents_by_type"][doc.doc_type] = (
                report["documents_by_type"].get(doc.doc_type, 0) + 1
            )

        # Save report
        report_path = OUTPUT_DIR / f"kemi_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║                      SCRAPE COMPLETE                              ║
╠═══════════════════════════════════════════════════════════════════╣
║  Total documents:  {len(self.documents):>4}                                       ║
║  Pages crawled:    {self.stats["crawled"]:>4}                                       ║
║  Extracted:        {self.stats["extracted"]:>4}                                       ║
║  Errors:           {self.stats["errors"]:>4}                                       ║
║  Time:             {elapsed / 60:>4.1f} min                                      ║
║                                                                   ║
║  BY TYPE:                                                         ║
""")
        for doc_type, count in sorted(report["documents_by_type"].items()):
            print(f"║    {doc_type:<20} {count:>4}                              ║")

        print(f"""╠═══════════════════════════════════════════════════════════════════╣
║  Report saved: {report_path.name:<40}║
╚═══════════════════════════════════════════════════════════════════╝
        """)

        return report


if __name__ == "__main__":
    scraper = KemiScraper()
    scraper.run()
