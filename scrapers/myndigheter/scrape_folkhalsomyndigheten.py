#!/usr/bin/env python3
"""
FOLKHALSOMYNDIGHETEN SCRAPER
Scrapes all publications from folkhalsomyndigheten.se and indexes to ChromaDB
Target: Rapporter, Statistik, Rekommendationer, Kunskapsstöd
"""

import io
import json
import re
import time
from datetime import datetime

import chromadb
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer

# Constants
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "folkhalsomyndigheten"
MIN_DOCS_THRESHOLD = 100

# Base URL
BASE_URL = "https://www.folkhalsomyndigheten.se"

# Publication search - we'll scrape the paginated search results
# The site has 1,257 publications across 51 pages (approximately)
PUBLICATION_SEARCH_URL = f"{BASE_URL}/publikationer-och-material/publikationer/"


class FolkhalsomyndighetenScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

        self.docs_found = 0
        self.docs_indexed = 0
        self.errors = []

        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)

        # Initialize embedding model (same as Boverket - 384 dimensions)
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        # Get or create collection
        try:
            self.collection = self.client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=None,  # We'll generate embeddings manually
            )
            print(f"Connected to existing collection: {COLLECTION_NAME}")
        except:
            from chromadb.utils import embedding_functions

            sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.client.create_collection(
                name=COLLECTION_NAME,
                metadata={"description": "Swedish government documents"},
                embedding_function=sentence_transformer_ef,
            )
            print(f"Created new collection: {COLLECTION_NAME}")

    def fetch_page(self, url: str, max_retries: int = 3) -> BeautifulSoup | None:
        """Fetch and parse a web page with retry logic"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, "lxml")
            except Exception as e:
                if attempt == max_retries - 1:
                    self.errors.append(f"Failed to fetch {url}: {e!s}")
                    return None
                time.sleep(2**attempt)  # Exponential backoff
        return None

    def extract_text_from_pdf(self, pdf_url: str) -> str | None:
        """Download and extract text from PDF (first 50 pages, max 20k chars)"""
        try:
            print(f"  Extracting PDF: {pdf_url}")
            response = self.session.get(pdf_url, timeout=60)
            response.raise_for_status()

            # Read PDF content
            pdf_file = io.BytesIO(response.content)
            reader = PdfReader(pdf_file)

            # Extract text from all pages
            text_parts = []
            for page in reader.pages[:50]:  # Limit to first 50 pages
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            full_text = "\n\n".join(text_parts)

            if full_text.strip():
                return full_text[:20000]  # Limit to 20k chars
            else:
                return f"PDF available at: {pdf_url} (text extraction failed)"

        except Exception as e:
            self.errors.append(f"Failed to extract PDF {pdf_url}: {e!s}")
            return f"PDF available at: {pdf_url} (error: {e!s})"

    def scrape_publication_listing(self, page_num: int = 1) -> list[dict]:
        """Scrape a single page of publication listings"""
        publications = []

        # Construct URL with page parameter
        url = f"{PUBLICATION_SEARCH_URL}?page={page_num}"
        print(f"\nScraping page {page_num}: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return publications

        # Find publication items
        # Looking for article cards or list items containing publications
        pub_items = soup.find_all(
            ["article", "div", "li"],
            class_=re.compile(r"(publication|article|result-item|card|list-item)", re.I),
        )

        # If no structured items found, try finding all links to publication pages
        if not pub_items:
            pub_items = soup.find_all(
                "a", href=re.compile(r"/publikationer-och-material/publikationsarkiv/")
            )

        print(f"  Found {len(pub_items)} publication items on page {page_num}")

        for item in pub_items:
            try:
                pub_data = self.extract_publication_from_listing(item)
                if pub_data:
                    publications.append(pub_data)
                    self.docs_found += 1

                    if self.docs_found % 20 == 0:
                        print(f"  Processed {self.docs_found} publications so far...")

            except Exception as e:
                self.errors.append(f"Error extracting publication from listing: {e!s}")

        return publications

    def extract_publication_from_listing(self, item) -> dict | None:
        """Extract publication metadata from a listing item"""
        try:
            # Find title
            title_elem = item.find(["h1", "h2", "h3", "h4", "h5", "a"])
            if not title_elem:
                return None

            title = title_elem.get_text(strip=True)

            # Find link
            link_elem = item.find("a", href=True) if item.name != "a" else item
            if not link_elem:
                return None

            url = link_elem["href"]
            if not url.startswith("http"):
                url = BASE_URL + url

            # Skip if not a publication page
            if "/publikationsarkiv/" not in url and "/publikationer/" not in url:
                return None

            # Find date (various formats)
            date_elem = item.find(["time", "span"], class_=re.compile(r"date|time|publish", re.I))
            if not date_elem:
                # Try finding date in text
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", item.get_text())
                date_str = date_match.group(1) if date_match else "Unknown"
            else:
                date_str = date_elem.get_text(strip=True)

            # Find publication type/category
            category_elem = item.find(
                ["span", "div"], class_=re.compile(r"category|type|tag", re.I)
            )
            pub_type = category_elem.get_text(strip=True) if category_elem else "publikation"

            # Find summary/description if available
            summary_elem = item.find(
                ["p", "div"], class_=re.compile(r"summary|description|excerpt", re.I)
            )
            summary = summary_elem.get_text(strip=True) if summary_elem else ""

            # Fetch full content from publication page
            full_content = self.fetch_publication_content(url)

            # Combine summary and full content
            content = f"{summary}\n\n{full_content}" if full_content else summary or title

            return {
                "title": title,
                "url": url,
                "pub_type": pub_type,
                "date": date_str,
                "authors": "Folkhälsomyndigheten",
                "content": content,
                "source": SOURCE_NAME,
            }

        except Exception as e:
            self.errors.append(f"Error in extract_publication_from_listing: {e!s}")
            return None

    def fetch_publication_content(self, url: str) -> str | None:
        """Fetch the full text content of a publication"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        # Check if there's a PDF link - if so, extract PDF content
        pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
        if pdf_link:
            pdf_url = pdf_link["href"]
            if not pdf_url.startswith("http"):
                pdf_url = BASE_URL + pdf_url

            # For efficiency, we'll just note the PDF URL rather than extracting full text
            # (extracting 1000+ PDFs would take hours)
            return f"PDF document available at: {pdf_url}"

        # Remove script, style, nav elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
            element.decompose()

        # Try to find main content area
        content = soup.find(
            ["article", "main", "div"], class_=re.compile(r"content|article|body|main", re.I)
        )

        if not content:
            content = soup.find("body")

        if content:
            text = content.get_text(separator="\n", strip=True)
            # Clean up excessive whitespace
            text = re.sub(r"\n\s*\n", "\n\n", text)
            return text[:10000]  # Limit to 10k chars to avoid huge embeddings

        return None

    def scrape_all_publications(self, max_pages: int = 60) -> list[dict]:
        """Scrape all publication pages"""
        all_publications = []

        for page_num in range(1, max_pages + 1):
            pubs = self.scrape_publication_listing(page_num)

            if not pubs:
                print(f"  No publications found on page {page_num}, stopping...")
                break

            all_publications.extend(pubs)

            # Be polite - rate limiting
            time.sleep(2)

            # Break early if we've found a good amount
            if len(all_publications) >= 1000:
                print("  Reached 1000 publications, stopping early...")
                break

        return all_publications

    def scrape_additional_sections(self) -> list[dict]:
        """Scrape additional publication sections"""
        publications = []

        additional_urls = {
            "regulations": f"{BASE_URL}/publikationer-och-material/foreskrifter-och-allmanna-rad/",
            "consultations": f"{BASE_URL}/publikationer-och-material/remisser-och-yttranden/",
            "outlook": f"{BASE_URL}/publikationer-och-material/utblick-folkhalsa/",
        }

        for section_name, url in additional_urls.items():
            print(f"\nScraping section: {section_name}")
            soup = self.fetch_page(url)

            if not soup:
                continue

            # Find all links to publications
            links = soup.find_all("a", href=re.compile(r"/publikationsarkiv/|/publikationer/"))

            for link in links[:50]:  # Limit to 50 per section
                try:
                    pub_url = link["href"]
                    if not pub_url.startswith("http"):
                        pub_url = BASE_URL + pub_url

                    title = link.get_text(strip=True)
                    if not title:
                        continue

                    content = self.fetch_publication_content(pub_url)

                    pub_data = {
                        "title": title,
                        "url": pub_url,
                        "pub_type": section_name,
                        "date": "Unknown",
                        "authors": "Folkhälsomyndigheten",
                        "content": content or title,
                        "source": SOURCE_NAME,
                    }

                    publications.append(pub_data)
                    self.docs_found += 1

                except Exception as e:
                    self.errors.append(f"Error in {section_name}: {e!s}")

            time.sleep(2)

        return publications

    def index_publications(self, publications: list[dict]):
        """Index publications to ChromaDB"""
        if not publications:
            return

        print(f"\nIndexing {len(publications)} publications to ChromaDB...")

        batch_size = 10
        for i in range(0, len(publications), batch_size):
            batch = publications[i : i + batch_size]

            try:
                # Prepare data
                ids = []
                documents = []
                metadatas = []
                embeddings = []

                for pub in batch:
                    # Create unique ID
                    doc_id = f"{SOURCE_NAME}_{hash(pub['url'])}"
                    ids.append(doc_id)

                    # Full text for embedding
                    full_text = f"{pub['title']}\n\n{pub['content']}"
                    documents.append(full_text)

                    # Metadata
                    metadatas.append(
                        {
                            "source": pub["source"],
                            "title": pub["title"],
                            "url": pub["url"],
                            "pub_type": pub["pub_type"],
                            "date": pub["date"],
                            "authors": pub["authors"],
                        }
                    )

                    # Generate embedding
                    embedding = self.embedding_model.encode(full_text).tolist()
                    embeddings.append(embedding)

                # Add to collection
                self.collection.add(
                    ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
                )

                self.docs_indexed += len(batch)
                print(f"  Indexed {self.docs_indexed}/{len(publications)} documents...")

            except Exception as e:
                self.errors.append(f"Error indexing batch: {e!s}")

    def run(self) -> dict:
        """Main scraping workflow"""
        print("=" * 60)
        print("FOLKHALSOMYNDIGHETEN SCRAPER")
        print("=" * 60)

        # Scrape main publication search pages
        all_publications = self.scrape_all_publications(max_pages=60)

        # Scrape additional sections
        additional_pubs = self.scrape_additional_sections()
        all_publications.extend(additional_pubs)

        print(f"\nTotal publications found: {len(all_publications)}")

        # Index all publications
        self.index_publications(all_publications)

        # Check threshold
        status = "OK"
        if self.docs_found < MIN_DOCS_THRESHOLD:
            status = "FLAGGAD"
            self.errors.append(
                f"WARNING: Endast {self.docs_found} publikationer hittade (threshold: {MIN_DOCS_THRESHOLD})"
            )

        result = {
            "myndighet": "Folkhälsomyndigheten",
            "status": status,
            "docs_found": self.docs_found,
            "docs_indexed": self.docs_indexed,
            "errors": self.errors,
            "timestamp": datetime.now().isoformat(),
        }

        return result


def main():
    scraper = FolkhalsomyndighetenScraper()
    result = scraper.run()

    # Print results
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Save results
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/folkhalsomyndigheten_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")

    return result


if __name__ == "__main__":
    main()
