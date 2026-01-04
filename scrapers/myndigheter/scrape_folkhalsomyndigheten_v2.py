#!/usr/bin/env python3
"""
FOLKHALSOMYNDIGHETEN SCRAPER V2
Scrapes all publications from folkhalsomyndigheten.se and indexes to ChromaDB
Strategy: Use direct alphabetical archive browsing + search pagination
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

import chromadb
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

# Constants
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "folkhalsomyndigheten"
MIN_DOCS_THRESHOLD = 100

BASE_URL = "https://www.folkhalsomyndigheten.se"

# All letters in Swedish alphabet for archive browsing
LETTERS = [
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "å",
    "ä",
    "ö",
    "0-9",
]


class FolkhalsomyndighetenScraperV2:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        self.docs_found = 0
        self.docs_indexed = 0
        self.errors = []
        self.seen_urls: set[str] = set()

        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)

        # Initialize embedding model (384 dimensions - same as Boverket)
        print("Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=COLLECTION_NAME)
            print(f"Connected to existing collection: {COLLECTION_NAME}")
        except:
            from chromadb.utils import embedding_functions

            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.client.create_collection(
                name=COLLECTION_NAME,
                metadata={"description": "Swedish government documents"},
                embedding_function=ef,
            )
            print(f"Created new collection: {COLLECTION_NAME}")

    def fetch_page(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, "html.parser")
            except Exception as e:
                if attempt == max_retries - 1:
                    self.errors.append(f"Failed to fetch {url}: {e!s}")
                    return None
                time.sleep(2**attempt)
        return None

    def scrape_alphabetical_archive(self, letter: str) -> list[dict]:
        """Scrape publications starting with a specific letter"""
        publications = []

        # Don't use alphabetical archives - they have limited pagination
        # Instead, use the main search page with pagination
        return publications

    def fetch_publication_details(self, url: str, fallback_title: str) -> Optional[dict]:
        """Fetch full details from a publication page"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        try:
            # Extract title (prefer h1, fallback to provided title)
            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else fallback_title

            # Extract publication date
            date_str = "Unknown"
            date_elem = soup.find(["time", "span"], class_=re.compile(r"date|publish", re.I))
            if date_elem:
                date_str = date_elem.get_text(strip=True)
            else:
                # Try to find "Publicerad: YYYY-MM-DD" pattern
                text = soup.get_text()
                match = re.search(r"Publicerad:?\s*(\d{4}-\d{2}-\d{2})", text)
                if match:
                    date_str = match.group(1)

            # Extract publication type/category
            pub_type = "publikation"
            category_elem = soup.find(["span", "div"], class_=re.compile(r"category|type", re.I))
            if category_elem:
                pub_type = category_elem.get_text(strip=True)

            # Extract main content
            content = self.extract_content(soup, url)

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
            self.errors.append(f"Error extracting details from {url}: {e!s}")
            return None

    def extract_content(self, soup: BeautifulSoup, url: str) -> str:
        """Extract text content from publication page"""
        # Check for PDF download link
        pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
        if pdf_link:
            pdf_url = pdf_link["href"]
            if not pdf_url.startswith("http"):
                pdf_url = BASE_URL + pdf_url
            return f"PDF document: {pdf_url}"

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Find main content area
        content_area = soup.find(
            ["article", "main", "div"], class_=re.compile(r"content|article|main|body", re.I)
        )

        if not content_area:
            content_area = soup.find("body")

        if content_area:
            text = content_area.get_text(separator="\n", strip=True)
            # Clean up whitespace
            text = re.sub(r"\n\s*\n", "\n\n", text)
            return text[:10000]  # Limit to 10k chars

        return f"Publication at: {url}"

    def scrape_main_search_paginated(self, max_pages: int = 60) -> list[dict]:
        """Scrape main publication search with pagination"""
        all_publications = []

        base_url = f"{BASE_URL}/publikationer-och-material/publikationer/"

        for page_num in range(1, max_pages + 1):
            url = f"{base_url}?pn={page_num}"
            print(f"\nScraping page {page_num}/{max_pages}: {url}")

            soup = self.fetch_page(url)
            if not soup:
                print(f"  Failed to fetch page {page_num}, stopping...")
                break

            # Find all publication links on this page
            # They follow pattern /publikationsarkiv/[letter]/[title]/
            links = soup.find_all("a", href=re.compile(r"/publikationsarkiv/[a-z0-9-]+/"))

            print(f"  Found {len(links)} publication links")

            if not links:
                print(f"  No publications found on page {page_num}, stopping...")
                break

            page_pubs = 0
            for link in links:
                try:
                    pub_url = link.get("href", "")
                    if not pub_url:
                        continue

                    if not pub_url.startswith("http"):
                        pub_url = BASE_URL + pub_url

                    # Skip if already seen
                    if pub_url in self.seen_urls:
                        continue

                    self.seen_urls.add(pub_url)

                    # Get title from link
                    title = link.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    # Fetch publication page
                    pub_data = self.fetch_publication_details(pub_url, title)
                    if pub_data:
                        all_publications.append(pub_data)
                        self.docs_found += 1
                        page_pubs += 1

                except Exception as e:
                    self.errors.append(f"Error processing link: {e!s}")

            print(f"  Extracted {page_pubs} unique publications from page {page_num}")
            print(f"  Total so far: {self.docs_found}")

            # Rate limiting
            time.sleep(2)

        return all_publications

    def index_publications(self, publications: list[dict]):
        """Index publications to ChromaDB"""
        if not publications:
            print("No publications to index")
            return

        print(f"\nIndexing {len(publications)} publications...")

        batch_size = 10
        for i in range(0, len(publications), batch_size):
            batch = publications[i : i + batch_size]

            try:
                ids = []
                documents = []
                metadatas = []
                embeddings = []

                for pub in batch:
                    # Create unique ID
                    doc_id = f"{SOURCE_NAME}_{hash(pub['url'])}"
                    ids.append(doc_id)

                    # Full text
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
                print(f"  Indexed {self.docs_indexed}/{len(publications)}...")

            except Exception as e:
                error_msg = str(e)
                if "Expected IDs to be unique" in error_msg:
                    print("  Skipping duplicate batch")
                else:
                    self.errors.append(f"Error indexing batch: {error_msg}")

    def run(self) -> dict:
        """Main scraping workflow"""
        print("=" * 60)
        print("FOLKHALSOMYNDIGHETEN SCRAPER V2")
        print("=" * 60)

        # Scrape main search with pagination (up to 60 pages)
        publications = self.scrape_main_search_paginated(max_pages=60)

        print(f"\nTotal unique publications found: {len(publications)}")

        # Index to ChromaDB
        self.index_publications(publications)

        # Check threshold
        status = "OK"
        if self.docs_found < MIN_DOCS_THRESHOLD:
            status = "FLAGGAD"
            self.errors.append(
                f"WARNING: Endast {self.docs_found} publikationer hittade "
                f"(threshold: {MIN_DOCS_THRESHOLD})"
            )

        result = {
            "myndighet": "Folkhälsomyndigheten",
            "status": status,
            "docs_found": self.docs_found,
            "docs_indexed": self.docs_indexed,
            "errors": self.errors[:10],  # Limit error list
            "timestamp": datetime.now().isoformat(),
        }

        return result


def main():
    scraper = FolkhalsomyndighetenScraperV2()
    result = scraper.run()

    # Print results
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/folkhalsomyndigheten_final_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")

    return result


if __name__ == "__main__":
    main()
