#!/usr/bin/env python3
"""
Migrationsverket Document Scraper
Scrapes documents from migrationsverket.se and lifos.migrationsverket.se

Target content:
- Lifos landinformation
- Rättsliga ställningstaganden (Legal positions)
- Statistik (Statistics)
- Vägledningar (Guidelines)
- Publikationer (Publications)
"""

import asyncio
import gzip
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import aiohttp
import chromadb
from bs4 import BeautifulSoup
from chromadb.config import Settings
from tenacity import retry, stop_after_attempt, wait_exponential


class MigrationsverketScraper:
    def __init__(self, chromadb_path: str):
        self.base_urls = {
            "main": "https://www.migrationsverket.se",
            "lifos": "https://lifos.migrationsverket.se",
        }
        self.session: aiohttp.ClientSession | None = None
        self.documents: list[dict] = []

        # ChromaDB setup
        self.chroma_client = chromadb.PersistentClient(
            path=chromadb_path, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
        )

        # User agent for polite scraping
        self.headers = {
            "User-Agent": "MigrationsverketResearchBot/1.0 (Constitutional AI Research; +simon@example.com)"
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch(self, url: str) -> str:
        """Fetch URL with retry logic"""
        async with self.session.get(url, timeout=30) as response:
            response.raise_for_status()
            return await response.text()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_binary(self, url: str) -> bytes:
        """Fetch binary content (for PDFs, compressed files)"""
        async with self.session.get(url, timeout=30) as response:
            response.raise_for_status()
            return await response.read()

    async def get_sitemap_urls(self) -> list[str]:
        """Extract all URLs from sitemap"""
        urls = []

        try:
            # Fetch main sitemap index
            sitemap_index = await self.fetch(f"{self.base_urls['main']}/sitemap.xml")
            root = ET.fromstring(sitemap_index)

            # Find all sitemap URLs
            namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            sitemap_locs = root.findall(".//sm:loc", namespace)

            for loc in sitemap_locs:
                sitemap_url = loc.text
                print(f"Processing sitemap: {sitemap_url}")

                # Handle gzipped sitemaps
                if sitemap_url.endswith(".gz"):
                    content = await self.fetch_binary(sitemap_url)
                    xml_content = gzip.decompress(content).decode("utf-8")
                else:
                    xml_content = await self.fetch(sitemap_url)

                # Parse sitemap
                sitemap_root = ET.fromstring(xml_content)
                for url_elem in sitemap_root.findall(".//sm:loc", namespace):
                    url = url_elem.text
                    # Filter for relevant sections
                    if any(
                        keyword in url.lower()
                        for keyword in [
                            "publikation",
                            "statistik",
                            "rattslig",
                            "vagledning",
                            "rapport",
                            "lifos",
                            "stallningstagande",
                        ]
                    ):
                        urls.append(url)

        except Exception as e:
            print(f"Error fetching sitemap: {e}")

        return urls

    async def scrape_lifos_by_country(self, countries: list[str]) -> list[dict]:
        """Scrape Lifos documents by iterating through countries"""
        documents = []

        for country in countries:
            print(f"Scraping Lifos for country: {country}")
            try:
                # Try different URL patterns for country pages
                country_urls = [
                    f"{self.base_urls['lifos']}/land/{country.lower()}",
                    f"{self.base_urls['lifos']}/dokument?land={country}",
                ]

                for url in country_urls:
                    try:
                        html = await self.fetch(url)
                        soup = BeautifulSoup(html, "html.parser")

                        # Find all document links
                        doc_links = soup.find_all(
                            "a", href=re.compile(r"/dokument\?documentSummaryId=")
                        )

                        for link in doc_links:
                            doc_url = urljoin(self.base_urls["lifos"], link["href"])
                            if doc_url not in [d["url"] for d in documents]:
                                doc = await self.scrape_lifos_document(doc_url)
                                if doc:
                                    documents.append(doc)
                                await asyncio.sleep(0.3)

                        break  # If successful, don't try other patterns
                    except:
                        continue

            except Exception as e:
                print(f"Error scraping country {country}: {e}")

        return documents

    async def scrape_lifos_recent(self, max_pages: int = 10) -> list[dict]:
        """Scrape recent Lifos documents"""
        documents = []

        try:
            # Try to get recent documents page
            recent_url = f"{self.base_urls['lifos']}/nyheter"
            html = await self.fetch(recent_url)
            soup = BeautifulSoup(html, "html.parser")

            # Find document links
            doc_links = soup.find_all("a", href=re.compile(r"/dokument\?documentSummaryId="))
            print(f"Found {len(doc_links)} recent Lifos documents")

            for link in doc_links:
                doc_url = urljoin(self.base_urls["lifos"], link["href"])
                doc = await self.scrape_lifos_document(doc_url)
                if doc:
                    documents.append(doc)
                await asyncio.sleep(0.3)

        except Exception as e:
            print(f"Error scraping recent Lifos documents: {e}")

        return documents

    async def scrape_lifos_by_id_range(
        self, start_id: int, end_id: int, sample_rate: int = 10
    ) -> list[dict]:
        """Scrape Lifos documents by trying ID ranges"""
        documents = []
        print(
            f"Sampling Lifos document IDs from {start_id} to {end_id} (every {sample_rate}th ID)..."
        )

        for doc_id in range(start_id, end_id, sample_rate):
            try:
                doc_url = f"{self.base_urls['lifos']}/dokument?documentSummaryId={doc_id}"
                doc = await self.scrape_lifos_document(doc_url)
                if doc and doc["content"]:  # Only keep if has content
                    documents.append(doc)
                    if len(documents) % 10 == 0:
                        print(f"Found {len(documents)} valid documents so far...")
                await asyncio.sleep(0.2)
            except:
                continue

        return documents

    async def scrape_lifos_search(self, search_params: dict = None) -> list[dict]:
        """Scrape Lifos via search interface"""
        documents = []

        try:
            # Method 1: Recent documents
            print("Method 1: Recent documents...")
            recent_docs = await self.scrape_lifos_recent()
            documents.extend(recent_docs)

            # Method 2: Focus countries
            print("Method 2: Focus countries...")
            focus_countries = [
                "Afghanistan",
                "Irak",
                "Iran",
                "Somalia",
                "Syrien",
                "Eritrea",
                "Etiopien",
                "Ryssland",
                "Ukraina",
                "Venezuela",
            ]
            country_docs = await self.scrape_lifos_by_country(focus_countries)
            documents.extend(country_docs)

            # Method 3: Try main Lifos page
            print("Method 3: Main Lifos page...")
            try:
                html = await self.fetch(self.base_urls["lifos"])
                soup = BeautifulSoup(html, "html.parser")
                doc_links = soup.find_all("a", href=re.compile(r"/dokument\?documentSummaryId="))

                for link in doc_links:
                    doc_url = urljoin(self.base_urls["lifos"], link["href"])
                    if doc_url not in [d["url"] for d in documents]:
                        doc = await self.scrape_lifos_document(doc_url)
                        if doc:
                            documents.append(doc)
                        await asyncio.sleep(0.3)
            except Exception as e:
                print(f"Error scraping main Lifos page: {e}")

            # Method 4: Sample document IDs
            # Based on the IDs we saw (49099-49637), let's sample a wider range
            print("Method 4: Sampling document ID range...")
            id_docs = await self.scrape_lifos_by_id_range(
                start_id=45000,
                end_id=50000,
                sample_rate=20,  # Every 20th document
            )
            documents.extend(id_docs)

        except Exception as e:
            print(f"Error in Lifos scraping: {e}")

        # Remove duplicates
        unique_docs = []
        seen_urls = set()
        for doc in documents:
            if doc["url"] not in seen_urls:
                unique_docs.append(doc)
                seen_urls.add(doc["url"])

        print(f"Total unique Lifos documents: {len(unique_docs)}")
        return unique_docs

    async def scrape_lifos_document(self, url: str) -> dict | None:
        """Scrape individual Lifos document"""
        try:
            html = await self.fetch(url)
            soup = BeautifulSoup(html, "html.parser")

            # Extract title - it's in the main content area (not always in h1)
            title_text = "Untitled"

            # Try multiple methods to find title
            title_elem = soup.find("h1")
            if title_elem:
                title_text = title_elem.get_text(strip=True)
            else:
                # Title might be in metadata display
                meta_display = soup.find("div", id="metadataDisplayMain")
                if meta_display:
                    first_text = meta_display.get_text(strip=True, separator=" ")
                    # First substantial text is often the title
                    if len(first_text) > 10:
                        title_text = first_text.split("\n")[0][:200]

            # Extract content - using correct class names
            content = ""

            # Try documentViewerSummary
            summary_div = soup.find("div", id="documentViewerSummary")
            if summary_div:
                content += summary_div.get_text(strip=True, separator="\n") + "\n"

            # Try documentViewerGetDocument
            doc_viewer = soup.find("div", class_="documentViewerGetDocument")
            if doc_viewer:
                content += doc_viewer.get_text(strip=True, separator="\n") + "\n"

            # Fallback to main or article
            if not content:
                content_div = soup.find("article") or soup.find("main")
                if content_div:
                    content = content_div.get_text(strip=True, separator="\n")

            # Extract metadata from metadataDisplayMain
            metadata = {}
            meta_main = soup.find("div", id="metadataDisplayMain")
            if meta_main:
                # Find all left/right column pairs
                left_cols = meta_main.find_all("div", class_="metadataDisplayLeftColumn")
                right_cols = meta_main.find_all("div", class_="metadataDisplayRightColumn")

                for left, right in zip(left_cols, right_cols):
                    label = left.get_text(strip=True).rstrip(":")
                    value = right.get_text(strip=True)
                    if label and value:
                        metadata[label] = value

            # Extract specific fields
            country = metadata.get("Land")
            doc_number = metadata.get("Dokumentnr")
            source = metadata.get("Källa")
            date = metadata.get("Upphovsdat")
            subject_terms = metadata.get("Ämnesord")

            # Extract attachments
            attachments = []
            attach_container = soup.find("div", id="documentViewerGetContainer")
            if attach_container:
                for link in attach_container.find_all(
                    "a", href=re.compile(r"documentAttachmentId=")
                ):
                    attach_url = urljoin(self.base_urls["lifos"], link["href"])
                    attachments.append({"url": attach_url, "filename": link.get_text(strip=True)})

            # Determine document type
            doc_type = "lifos_document"
            if title_text:
                title_lower = title_text.lower()
                if "rättsfallssamling" in title_lower or "rättsfall" in title_lower:
                    doc_type = "case_law"
                elif (
                    "rättsligt ställningstagande" in title_lower
                    or "ställningstagande" in title_lower
                ):
                    doc_type = "legal_position"
                elif "landinformation" in title_lower:
                    doc_type = "country_info"

            # Also check subject terms
            if subject_terms:
                if "rättsfall" in subject_terms.lower():
                    doc_type = "case_law"

            return {
                "url": url,
                "title": title_text,
                "content": content,
                "source": "migrationsverket",
                "subsource": "lifos",
                "document_type": doc_type,
                "country": country,
                "document_number": doc_number,
                "publication_date": date,
                "source_organization": source,
                "subject_terms": subject_terms,
                "attachments": attachments,
                "metadata": metadata,
                "scraped_at": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"Error scraping Lifos document {url}: {e}")
            return None

    async def scrape_statistics_page(self, url: str) -> dict | None:
        """Scrape statistics pages and Excel files"""
        try:
            html = await self.fetch(url)
            soup = BeautifulSoup(html, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            # Extract main content
            content_div = soup.find("article") or soup.find("main")
            content = content_div.get_text(strip=True, separator="\n") if content_div else ""

            # Find Excel/CSV downloads
            downloads = []
            for link in soup.find_all("a", href=re.compile(r"\.(xlsx?|csv|pdf)$")):
                download_url = urljoin(url, link["href"])
                downloads.append({"url": download_url, "title": link.get_text(strip=True)})

            return {
                "url": url,
                "title": title_text,
                "content": content,
                "source": "migrationsverket",
                "subsource": "statistics",
                "document_type": "statistics",
                "downloads": downloads,
                "scraped_at": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"Error scraping statistics page {url}: {e}")
            return None

    async def scrape_legal_position(self, url: str) -> dict | None:
        """Scrape rättsliga ställningstaganden"""
        try:
            html = await self.fetch(url)
            soup = BeautifulSoup(html, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            # Extract content
            content_div = soup.find("article") or soup.find("main")
            content = content_div.get_text(strip=True, separator="\n") if content_div else ""

            # Extract date if available
            date_elem = soup.find(string=re.compile(r"Datum:|Publicerad:"))
            date = None
            if date_elem:
                date_text = date_elem.find_next().get_text(strip=True)
                date = date_text

            return {
                "url": url,
                "title": title_text,
                "content": content,
                "source": "migrationsverket",
                "subsource": "legal_positions",
                "document_type": "legal_position",
                "publication_date": date,
                "scraped_at": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"Error scraping legal position {url}: {e}")
            return None

    async def scrape_publication(self, url: str) -> dict | None:
        """Scrape general publications and guidelines"""
        try:
            html = await self.fetch(url)
            soup = BeautifulSoup(html, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            # Extract content
            content_div = soup.find("article") or soup.find("main")
            content = content_div.get_text(strip=True, separator="\n") if content_div else ""

            # Determine document type
            doc_type = "publication"
            if "vägledning" in title_text.lower() or "vägledning" in url.lower():
                doc_type = "guideline"
            elif "rapport" in title_text.lower():
                doc_type = "report"

            return {
                "url": url,
                "title": title_text,
                "content": content,
                "source": "migrationsverket",
                "subsource": "publications",
                "document_type": doc_type,
                "scraped_at": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"Error scraping publication {url}: {e}")
            return None

    async def categorize_and_scrape(self, url: str) -> dict | None:
        """Categorize URL and scrape accordingly"""
        # Skip binary files - just register them as downloadable resources
        if any(
            url.lower().endswith(ext)
            for ext in [".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".doc", ".xls"]
        ):
            return {
                "url": url,
                "title": url.split("/")[-1],
                "content": f"[Binary file: {url.split('/')[-1]}]",
                "source": "migrationsverket",
                "subsource": "downloads",
                "document_type": "file_download",
                "file_type": url.split(".")[-1],
                "scraped_at": datetime.now().isoformat(),
            }

        if "lifos.migrationsverket.se" in url:
            if "/dokument" in url:
                return await self.scrape_lifos_document(url)
        elif "statistik" in url.lower():
            return await self.scrape_statistics_page(url)
        elif "rattslig" in url.lower() or "stallningstagande" in url.lower():
            return await self.scrape_legal_position(url)
        elif "publikation" in url.lower() or "vagledning" in url.lower():
            return await self.scrape_publication(url)
        else:
            # Generic scraper
            return await self.scrape_publication(url)

    async def run(self) -> dict:
        """Main scraping orchestration"""
        print("Starting Migrationsverket scraper...")
        print("=" * 60)

        # 1. Get URLs from sitemap
        print("\n[1/4] Fetching sitemap URLs...")
        sitemap_urls = await self.get_sitemap_urls()
        print(f"Found {len(sitemap_urls)} relevant URLs from sitemap")

        # 2. Scrape Lifos documents
        print("\n[2/4] Scraping Lifos documents...")
        lifos_docs = await self.scrape_lifos_search()
        self.documents.extend(lifos_docs)
        print(f"Scraped {len(lifos_docs)} Lifos documents")

        # 3. Scrape sitemap URLs
        print("\n[3/4] Scraping sitemap URLs...")
        max_sitemap_urls = min(200, len(sitemap_urls))  # Scrape up to 200 URLs
        for i, url in enumerate(sitemap_urls[:max_sitemap_urls], 1):
            print(f"Scraping {i}/{max_sitemap_urls}: {url}")
            doc = await self.categorize_and_scrape(url)
            if doc:
                self.documents.append(doc)
            await asyncio.sleep(0.3)  # Polite crawling

        # 4. Store in ChromaDB
        print("\n[4/4] Storing in ChromaDB...")
        await self.store_in_chromadb()

        # Generate report
        report = self.generate_report()

        return report

    async def store_in_chromadb(self):
        """Store documents in ChromaDB"""
        if not self.documents:
            print("No documents to store")
            return

        for doc in self.documents:
            # Create unique ID
            doc_id = f"migrationsverket_{abs(hash(doc['url']))}"

            # Prepare metadata
            metadata = {
                "source": doc["source"],
                "subsource": doc.get("subsource", ""),
                "document_type": doc.get("document_type", ""),
                "url": doc["url"],
                "title": doc["title"][:500],  # ChromaDB metadata limit
                "scraped_at": doc["scraped_at"],
            }

            # Add optional fields
            if doc.get("country"):
                metadata["country"] = doc["country"]
            if doc.get("publication_date"):
                metadata["publication_date"] = doc["publication_date"]

            # Store in ChromaDB
            try:
                self.collection.upsert(
                    ids=[doc_id],
                    documents=[doc["content"][:10000]],  # Limit content size
                    metadatas=[metadata],
                )
            except Exception as e:
                print(f"Error storing document {doc_id}: {e}")

        print(f"Stored {len(self.documents)} documents in ChromaDB")

    def generate_report(self) -> dict:
        """Generate JSON report"""
        doc_types = {}
        for doc in self.documents:
            doc_type = doc.get("document_type", "unknown")
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1

        subsources = {}
        for doc in self.documents:
            subsource = doc.get("subsource", "unknown")
            subsources[subsource] = subsources.get(subsource, 0) + 1

        report = {
            "agency": "migrationsverket",
            "scraped_at": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "document_types": doc_types,
            "subsources": subsources,
            "flag": len(self.documents) < 100,
            "flag_reason": "Less than 100 documents found" if len(self.documents) < 100 else None,
            "sample_documents": self.documents[:5] if self.documents else [],
        }

        return report


async def main():
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
    output_file = Path(__file__).parent / "migrationsverket_report.json"

    async with MigrationsverketScraper(chromadb_path) as scraper:
        report = await scraper.run()

        # Save report
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Total documents: {report['total_documents']}")
        print(f"Document types: {report['document_types']}")
        print(f"Subsources: {report['subsources']}")
        if report["flag"]:
            print(f"\n⚠️  FLAG: {report['flag_reason']}")
        print(f"\nReport saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
