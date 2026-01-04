#!/usr/bin/env python3
"""
RIKSBANKEN SCRAPER
Scrapes all publications from riksbank.se and indexes to ChromaDB
"""

import io
import json
import re
import time
from datetime import datetime
from typing import Optional

import chromadb
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer

# Constants
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "riksbanken"
MIN_DOCS_THRESHOLD = 100

# Riksbanken publication types and their URLs
PUBLICATION_URLS = {
    "penningpolitisk_rapport": "https://www.riksbank.se/sv/penningpolitik/penningpolitisk-rapport/penningpolitiska-rapporter-och-uppdateringar/",
    "publikationer": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/",
    "ekonomiska_kommentarer": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/ekonomiska-kommentarer/",
    "finansiell_stabilitet": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/finansiell-stabilitetsrapport/",
}


class RiksbankenScraper:
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

        # Initialize embedding model
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer("KBLab/sentence-bert-swedish-cased")

        # Get or create collection
        try:
            self.collection = self.client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=None,  # We'll generate embeddings manually
            )
            print(f"Connected to existing collection: {COLLECTION_NAME}")
        except:
            self.collection = self.client.create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )
            print(f"Created new collection: {COLLECTION_NAME}")

    def fetch_page(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
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

    def extract_text_from_pdf(self, pdf_url: str) -> Optional[str]:
        """Download and extract text from PDF"""
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

    def extract_pdf_publication(self, pdf_link, pub_type: str) -> Optional[dict]:
        """Extract data from a direct PDF link"""
        try:
            pdf_url = pdf_link.get("href", "")
            if not pdf_url:
                return None

            if not pdf_url.startswith("http"):
                pdf_url = "https://www.riksbank.se" + pdf_url

            # Get title from link text or nearby text
            title = pdf_link.get_text(strip=True)
            if not title or len(title) < 5:
                # Try to find title in parent
                parent = pdf_link.parent
                if parent:
                    title = parent.get_text(strip=True)[:200]

            # Try to extract date from URL or title
            date_match = re.search(r"(202\d)-?(\d{2})", pdf_url + title)
            if date_match:
                date_str = f"{date_match.group(1)}-{date_match.group(2)}"
            else:
                date_match = re.search(r"(20\d{2})", pdf_url + title)
                date_str = date_match.group(1) if date_match else "Unknown"

            # For PDF documents, use title + metadata as content
            # (extracting full PDF text is too slow for this batch operation)
            content = f"{title}\n\nDokumenttyp: {pub_type}\nFormat: PDF\nTillgänglig: {pdf_url}"

            return {
                "title": title or "Unnamed PDF",
                "url": pdf_url,
                "pub_type": pub_type,
                "date": date_str,
                "authors": "Riksbanken",
                "content": content,
                "source": SOURCE_NAME,
            }
        except Exception as e:
            self.errors.append(f"Error in extract_pdf_publication: {e!s}")
            return None

    def scrape_publication_list(self, pub_type: str, base_url: str) -> list[dict]:
        """Scrape a publication listing page"""
        publications = []

        print(f"\nScraping {pub_type} from {base_url}")
        soup = self.fetch_page(base_url)

        if not soup:
            return publications

        # Find direct PDF links
        pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
        print(f"  Found {len(pdf_links)} PDF links")
        for i, pdf_link in enumerate(pdf_links):
            try:
                pub_data = self.extract_pdf_publication(pdf_link, pub_type)
                if pub_data:
                    publications.append(pub_data)
                    self.docs_found += 1
                    if (i + 1) % 10 == 0:
                        print(f"  Processed {i + 1}/{len(pdf_links)} PDFs...")
            except Exception as e:
                self.errors.append(f"Error extracting PDF publication: {e!s}")

        # Find all publication links (HTML pages)
        # Try finding article/publication containers
        containers = soup.find_all(
            ["article", "div", "li"], class_=re.compile(r"(publication|article|item|list)", re.I)
        )

        if not containers:
            # Fallback: find all links that look like publications
            containers = soup.find_all(
                "a", href=re.compile(r"/(publikationer|rapporter|tal|forskning)/")
            )

        for container in containers:
            try:
                pub_data = self.extract_publication_data(container, pub_type)
                if pub_data:
                    publications.append(pub_data)
                    self.docs_found += 1
            except Exception as e:
                self.errors.append(f"Error extracting publication: {e!s}")

        # Try pagination
        next_page = soup.find("a", class_=re.compile(r"next|pagination", re.I))
        if next_page and "href" in next_page.attrs:
            next_url = next_page["href"]
            if not next_url.startswith("http"):
                next_url = "https://www.riksbank.se" + next_url
            time.sleep(1)  # Be polite
            publications.extend(self.scrape_publication_list(pub_type, next_url))

        return publications

    def extract_publication_data(self, element, pub_type: str) -> Optional[dict]:
        """Extract metadata and content from a publication element"""
        try:
            # Find title
            title_elem = element.find(["h1", "h2", "h3", "h4", "a"])
            if not title_elem:
                return None

            title = title_elem.get_text(strip=True)

            # Find link
            link_elem = element.find("a", href=True) if element.name != "a" else element
            if not link_elem:
                return None

            url = link_elem["href"]
            if not url.startswith("http"):
                url = "https://www.riksbank.se" + url

            # Find date
            date_elem = element.find(["time", "span"], class_=re.compile(r"date|time", re.I))
            date_str = date_elem.get_text(strip=True) if date_elem else "Unknown"

            # Find authors (if available)
            author_elem = element.find(["span", "div"], class_=re.compile(r"author|writer", re.I))
            authors = author_elem.get_text(strip=True) if author_elem else "Riksbanken"

            # Get full text
            full_text = self.fetch_publication_content(url)

            return {
                "title": title,
                "url": url,
                "pub_type": pub_type,
                "date": date_str,
                "authors": authors,
                "content": full_text or title,  # Fallback to title if content unavailable
                "source": SOURCE_NAME,
            }
        except Exception as e:
            self.errors.append(f"Error in extract_publication_data: {e!s}")
            return None

    def fetch_publication_content(self, url: str) -> Optional[str]:
        """Fetch the full text content of a publication"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        # Remove script, style, nav elements
        for element in soup(["script", "style", "nav", "header", "footer"]):
            element.decompose()

        # Try to find main content area
        content = soup.find(
            ["article", "main", "div"], class_=re.compile(r"content|article|body", re.I)
        )

        if not content:
            content = soup.find("body")

        if content:
            text = content.get_text(separator="\n", strip=True)
            # Clean up excessive whitespace
            text = re.sub(r"\n\s*\n", "\n\n", text)
            return text[:10000]  # Limit to 10k chars to avoid huge embeddings

        return None

    def index_publications(self, publications: list[dict]):
        """Index publications to ChromaDB"""
        if not publications:
            return

        print(f"\nIndexing {len(publications)} publications...")

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
                    doc_id = f"{SOURCE_NAME}_{pub['pub_type']}_{hash(pub['url'])}"
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
                print(f"Indexed {self.docs_indexed}/{len(publications)} documents...")

            except Exception as e:
                self.errors.append(f"Error indexing batch: {e!s}")

    def run(self) -> dict:
        """Main scraping workflow"""
        print("=" * 60)
        print("RIKSBANKEN SCRAPER")
        print("=" * 60)

        all_publications = []

        # Scrape each publication type
        for pub_type, url in PUBLICATION_URLS.items():
            pubs = self.scrape_publication_list(pub_type, url)
            all_publications.extend(pubs)
            print(f"Found {len(pubs)} documents in {pub_type}")
            time.sleep(2)  # Be polite between sections

        # Index all publications
        self.index_publications(all_publications)

        # Check threshold
        status = "OK"
        if self.docs_found < MIN_DOCS_THRESHOLD:
            status = "FLAGGAD"
            self.errors.append(
                f"SIMON: Riksbanken verkar ha problem - endast {self.docs_found} publikationer hittade"
            )

        result = {
            "myndighet": "Riksbanken",
            "status": status,
            "docs_found": self.docs_found,
            "docs_indexed": self.docs_indexed,
            "errors": self.errors,
            "timestamp": datetime.now().isoformat(),
        }

        return result


def main():
    scraper = RiksbankenScraper()
    result = scraper.run()

    # Print results
    print("\n" + "=" * 60)
    print("RESULTAT")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Save results
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/riksbanken_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")

    return result


if __name__ == "__main__":
    main()
