#!/usr/bin/env python3
"""
Jordbruksverket Document Scraper
Scrapes SJVFS föreskrifter, rapporter, statistik och vägledningar
Stores in ChromaDB collection: swedish_gov_docs
"""

import asyncio
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path

import chromadb
import httpx
import PyPDF2
from bs4 import BeautifulSoup
from chromadb.config import Settings

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE = "jordbruksverket"
BASE_URL = "https://jordbruksverket.se"
TIMEOUT = 30.0


class JordbruksverketScraper:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
        )
        self.http_client = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True)
        self.stats = {
            "foreskrifter": 0,
            "rapporter": 0,
            "statistik": 0,
            "vagledningar": 0,
            "errors": 0,
            "total": 0,
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.aclose()

    def generate_doc_id(self, url: str, title: str) -> str:
        """Generate unique document ID"""
        content = f"{url}{title}".encode()
        return f"jordbruksverket_{hashlib.md5(content).hexdigest()}"

    async def extract_pdf_text(self, pdf_url: str) -> str | None:
        """Extract text from PDF"""
        try:
            response = await self.http_client.get(pdf_url)
            response.raise_for_status()

            pdf_file = io.BytesIO(response.content)
            reader = PyPDF2.PdfReader(pdf_file)

            text = ""
            max_pages = min(10, len(reader.pages))  # First 10 pages for preview
            for page_num in range(max_pages):
                page = reader.pages[page_num]
                text += page.extract_text() + "\n\n"

            return text.strip()
        except Exception as e:
            print(f"  ⚠️  PDF extraction failed for {pdf_url}: {e}")
            return None

    async def scrape_forfattningar(self) -> list[dict]:
        """Scrape SJVFS författningar (regulations)"""
        print("\n📜 Scraping författningar...")
        documents = []

        # The search interface shows 353 documents across 8 pages
        # We'll parse the search results page
        search_url = f"{BASE_URL}/om-jordbruksverket/forfattningar"

        try:
            response = await self.http_client.get(search_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Find all document links in search results
            # Looking for patterns like SJVFS YYYY:XX
            sjvfs_pattern = re.compile(r"SJVFS\s+(\d{4}):(\d+)", re.IGNORECASE)

            # Find all links that might be documents
            links = soup.find_all("a", href=True)

            for link in links:
                href = link["href"]
                text = link.get_text(strip=True)

                # Check if this is a SJVFS document
                if sjvfs_pattern.search(text) or "download" in href.lower():
                    if not href.startswith("http"):
                        href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"

                    # Extract SJVFS number if present
                    sjvfs_match = sjvfs_pattern.search(text)
                    sjvfs_nr = (
                        f"{sjvfs_match.group(1)}:{sjvfs_match.group(2)}"
                        if sjvfs_match
                        else "unknown"
                    )

                    doc = {
                        "url": href,
                        "title": text or f"SJVFS {sjvfs_nr}",
                        "sjvfs_nr": sjvfs_nr,
                        "type": "foreskrift",
                        "year": sjvfs_match.group(1) if sjvfs_match else "unknown",
                    }

                    # Extract PDF text if it's a PDF link
                    if href.endswith(".pdf"):
                        doc["content"] = await self.extract_pdf_text(href)

                    documents.append(doc)
                    self.stats["foreskrifter"] += 1

            print(f"  ✓ Found {len(documents)} författningar from search page")

            # Also check the directory PDF
            directory_url = "https://jordbruksverket.se/download/18.3bdd6579197600d23bc697a0/1752040687713/Forteckning-jan-juni-2025-tga.pdf"

            print("  📄 Parsing författningsförteckning PDF...")
            directory_text = await self.extract_pdf_text(directory_url)

            if directory_text:
                # Extract all SJVFS references from the directory
                sjvfs_refs = sjvfs_pattern.findall(directory_text)
                print(f"  ✓ Found {len(sjvfs_refs)} SJVFS references in directory")

                # Add document for the directory itself
                documents.append(
                    {
                        "url": directory_url,
                        "title": "Förteckning över Statens jordbruksverks författningar 2025",
                        "sjvfs_nr": "directory",
                        "type": "directory",
                        "year": "2025",
                        "content": directory_text,
                    }
                )
                self.stats["foreskrifter"] += 1

        except Exception as e:
            print(f"  ❌ Error scraping författningar: {e}")
            self.stats["errors"] += 1

        return documents

    async def scrape_statistik(self) -> list[dict]:
        """Scrape statistics reports"""
        print("\n📊 Scraping statistik...")
        documents = []

        # Multiple entry points for statistics
        stats_urls = [
            f"{BASE_URL}/om-jordbruksverket/jordbruksverkets-officiella-statistik",
            f"{BASE_URL}/om-jordbruksverket/jordbruksverkets-officiella-statistik/jordbruksverkets-statistikrapporter",
            f"{BASE_URL}/om-jordbruksverket/jordbruksverkets-officiella-statistik/jordbruksverkets-statistikrapporter/statistik",
        ]

        # Also use direct download URL patterns from search results
        known_statistics = [
            "https://jordbruksverket.se/download/18.46ae4116195bf598eee44f2d/1743760216455/Utrikeshandel-arssammanstallning-2024-tga.pdf",
            "https://jordbruksverket.se/download/18.3bdd6579197600d23bcdb418/1755672862096/Statistikens%20framstallning%20av%20Markpriser%202024%20(JO%201002)-tga.pdf",
            "https://jordbruksverket.se/download/18.23e68dd418d7c649d171739/1707220231639/Priser-pa-jordbruksprodukter-2024-02-06-tga.pdf",
            "https://jordbruksverket.se/download/18.ee7a45f193b2a3ce672b7fe/1734617258963/Priser-pa-jordbruksprodukter-2024-12-05-tga.pdf",
        ]

        # Scrape from known statistics URLs
        for stat_url in known_statistics:
            try:
                # Get filename and create title
                filename = stat_url.split("/")[-1].replace("-tga.pdf", "").replace("-", " ")
                title = filename.replace(".pdf", "").strip().title()

                # Extract year
                year_match = re.search(r"20\d{2}", filename)
                year = year_match.group(0) if year_match else "unknown"

                doc = {"url": stat_url, "title": title, "type": "statistik", "year": year}

                # Extract PDF content
                doc["content"] = await self.extract_pdf_text(stat_url)

                documents.append(doc)
                self.stats["statistik"] += 1

            except Exception as e:
                print(f"  ⚠️  Error fetching {stat_url}: {e}")
                continue

        # Scrape statistics pages
        for stats_url in stats_urls:
            try:
                response = await self.http_client.get(stats_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                # Find all PDF links
                pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE))

                for link in pdf_links:
                    href = link["href"]
                    if not href.startswith("http"):
                        href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"

                    # Avoid duplicates
                    if any(d["url"] == href for d in documents):
                        continue

                    title = link.get_text(strip=True) or "Statistikrapport"

                    # Extract year if present
                    year_match = re.search(r"20\d{2}", title + href)
                    year = year_match.group(0) if year_match else "unknown"

                    doc = {"url": href, "title": title, "type": "statistik", "year": year}

                    # Extract PDF content
                    doc["content"] = await self.extract_pdf_text(href)

                    documents.append(doc)
                    self.stats["statistik"] += 1

            except Exception as e:
                print(f"  ⚠️  Error scraping {stats_url}: {e}")
                continue

        print(f"  ✓ Found {len(documents)} statistikrapporter")
        return documents

    async def scrape_rapporter(self) -> list[dict]:
        """Scrape general reports and publications"""
        print("\n📑 Scraping rapporter...")
        documents = []

        # Known reports from search results
        known_reports = [
            "https://jordbruksverket.se/download/18.224634c81900509cce84f98/1718192143943/Pa-tal-om-jordbruk-och-fiske-juni-2024-tga.pdf",
            "https://www2.jordbruksverket.se/download/18.41aa6e2218e54b01de91a5f9/1711375515932/ra24_3.pdf",
            "https://jordbruksverket.se/download/18.4483ef91188de34c0fd6ef1/1687376137781/Prioriteringar-for-anslagen-2024-tga.pdf",
            "https://jordbruksverket.se/download/18.d2af131196a047ce99c135/1746626286067/Sammanfattning-for-allmanheten-prestationsrapport-2024-tga.pdf",
            "https://jordbruksverket.se/download/18.511baa8d18fbcf6d63ec408/1717140589107/Lagesrapport-om-marknadslaget-i-jordbrukssektorn-31-maj-2024-tga.pdf",
            "https://www2.jordbruksverket.se/webdav/files/SJV/trycksaker/Pdf_rapporter/ra03_14.pdf",
            "https://www2.jordbruksverket.se/webdav/files/SJV/trycksaker/Pdf_rapporter/ra05_2.pdf",
            "https://www2.jordbruksverket.se/webdav/files/SJV/trycksaker/Pdf_rapporter/ra03_1.pdf",
            "https://www2.jordbruksverket.se/webdav/files/SJV/trycksaker/Pdf_rapporter/ra02_7.pdf",
        ]

        # Add known reports
        for report_url in known_reports:
            try:
                filename = report_url.split("/")[-1].replace("-tga.pdf", "").replace("-", " ")
                title = filename.replace(".pdf", "").strip().title()

                # Extract year
                year_match = re.search(r"20\d{2}", filename)
                year = year_match.group(0) if year_match else "unknown"

                # Extract report number if present (e.g., ra24_3)
                rapport_nr_match = re.search(r"ra(\d{2})_(\d+)", filename)
                rapport_nr = (
                    f"20{rapport_nr_match.group(1)}:{rapport_nr_match.group(2)}"
                    if rapport_nr_match
                    else None
                )

                doc = {"url": report_url, "title": title, "type": "rapport", "year": year}

                if rapport_nr:
                    doc["rapport_nr"] = rapport_nr

                doc["content"] = await self.extract_pdf_text(report_url)

                documents.append(doc)
                self.stats["rapporter"] += 1

            except Exception as e:
                print(f"  ⚠️  Error fetching {report_url}: {e}")
                continue

        # Try to find more reports from webdav directory
        print("  🔍 Searching for more reports in PDF archives...")

        # Pattern matching for report numbers
        # Try common report years and numbers
        for year in range(2020, 2026):  # 2020-2025
            for num in range(1, 20):  # Up to 20 reports per year
                report_url = f"https://www2.jordbruksverket.se/webdav/files/SJV/trycksaker/Pdf_rapporter/ra{str(year)[2:]}_{num}.pdf"

                try:
                    response = await self.http_client.head(report_url)
                    if response.status_code == 200:
                        # Report exists, fetch it
                        title = f"Rapport {year}:{num}"

                        doc = {
                            "url": report_url,
                            "title": title,
                            "type": "rapport",
                            "year": str(year),
                            "rapport_nr": f"{year}:{num}",
                        }

                        doc["content"] = await self.extract_pdf_text(report_url)

                        # Avoid duplicates
                        if not any(d["url"] == report_url for d in documents):
                            documents.append(doc)
                            self.stats["rapporter"] += 1

                except Exception:
                    # Report doesn't exist, continue
                    continue

        # Search for common report patterns on main site
        search_terms = ["handlingsplan", "instruktion", "konsekvensutredning", "lägesrapport"]

        for term in search_terms:
            try:
                # Use site search
                search_url = f"{BASE_URL}/search?q={term}+filetype:pdf"
                response = await self.http_client.get(search_url)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE))

                    for link in pdf_links[:15]:  # Limit to 15 per search term
                        href = link["href"]
                        if not href.startswith("http"):
                            href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"

                        title = link.get_text(strip=True) or f"{term.title()}"

                        # Avoid duplicates
                        if any(d["url"] == href for d in documents):
                            continue

                        doc = {"url": href, "title": title, "type": "rapport", "category": term}

                        doc["content"] = await self.extract_pdf_text(href)

                        documents.append(doc)
                        self.stats["rapporter"] += 1

            except Exception as e:
                print(f"  ⚠️  Error searching for '{term}': {e}")
                continue

        print(f"  ✓ Found {len(documents)} rapporter")
        return documents

    async def scrape_vagledningar(self) -> list[dict]:
        """Scrape vägledningar (guidelines)"""
        print("\n📖 Scraping vägledningar...")
        documents = []

        # Known vägledningar, handböcker, and instruktioner from search results
        known_urls = [
            "https://jordbruksverket.se/download/18.5af35a1a180ad2c3ce3a2691/1705506075210/Vagledning-till-jordbruksverkets-foreskrifter-tga.pdf",
            "https://jordbruksverket.se/download/18.1b29a1dd194b2e0589698552/1740471204810/Instruktion-stodberattigad-jordbruksmark-2025-tga.pdf",
            "https://djur.jordbruksverket.se/download/18.6beab0f111fb74e78a780001198/1370041067445/Handbok+CDB-Internet+f%C3%B6r+slakterier.pdf",
        ]

        for url in known_urls:
            try:
                # Get filename from URL
                filename = url.split("/")[-1]
                title = (
                    filename.replace("-", " ")
                    .replace(".pdf", "")
                    .replace("tga", "")
                    .replace("+", " ")
                    .strip()
                    .title()
                )

                doc = {"url": url, "title": title, "type": "vagledning"}

                doc["content"] = await self.extract_pdf_text(url)

                documents.append(doc)
                self.stats["vagledningar"] += 1

            except Exception as e:
                print(f"  ⚠️  Error fetching vägledning {url}: {e}")
                continue

        # Search for vägledningar, handböcker, and instruktioner
        search_terms = ["vägledning", "handbok", "instruktion", "guide"]

        for term in search_terms:
            try:
                search_url = f"{BASE_URL}/search?q={term}+filetype:pdf"
                response = await self.http_client.get(search_url)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE))

                    for link in pdf_links[:20]:  # 20 per search term
                        href = link["href"]
                        if not href.startswith("http"):
                            href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"

                        title = link.get_text(strip=True)

                        # Filter for relevant documents
                        if any(
                            keyword in title.lower()
                            for keyword in [
                                "vägledning",
                                "vagledning",
                                "handbok",
                                "instruktion",
                                "guide",
                            ]
                        ):
                            # Avoid duplicates
                            if any(d["url"] == href for d in documents):
                                continue

                            doc = {"url": href, "title": title, "type": "vagledning"}

                            doc["content"] = await self.extract_pdf_text(href)

                            documents.append(doc)
                            self.stats["vagledningar"] += 1

            except Exception as e:
                print(f"  ⚠️  Error searching for '{term}': {e}")
                continue

        print(f"  ✓ Found {len(documents)} vägledningar")
        return documents

    async def store_documents(self, documents: list[dict]):
        """Store documents in ChromaDB"""
        print(f"\n💾 Storing {len(documents)} documents in ChromaDB...")

        for doc in documents:
            try:
                doc_id = self.generate_doc_id(doc["url"], doc["title"])

                # Prepare metadata
                metadata = {
                    "source": SOURCE,
                    "type": doc.get("type", "unknown"),
                    "url": doc["url"],
                    "title": doc["title"],
                    "scraped_at": datetime.now().isoformat(),
                }

                # Add optional fields
                if "sjvfs_nr" in doc:
                    metadata["sjvfs_nr"] = doc["sjvfs_nr"]
                if "year" in doc:
                    metadata["year"] = doc["year"]
                if "category" in doc:
                    metadata["category"] = doc["category"]

                # Content for embedding
                content = doc.get("content", "")
                if not content:
                    content = f"{doc['title']}\nURL: {doc['url']}"

                # Store in ChromaDB
                self.collection.upsert(
                    ids=[doc_id],
                    documents=[content[:10000]],  # Limit content length
                    metadatas=[metadata],
                )

                self.stats["total"] += 1

            except Exception as e:
                print(f"  ❌ Error storing document {doc.get('title', 'unknown')}: {e}")
                self.stats["errors"] += 1

    async def run(self):
        """Main scraping workflow"""
        print("=" * 80)
        print("🚀 JORDBRUKSVERKET SCRAPER")
        print("=" * 80)

        start_time = datetime.now()

        # Scrape all document types
        all_documents = []

        # 1. Författningar (SJVFS)
        forfattningar = await self.scrape_forfattningar()
        all_documents.extend(forfattningar)

        # 2. Statistik
        statistik = await self.scrape_statistik()
        all_documents.extend(statistik)

        # 3. Rapporter
        rapporter = await self.scrape_rapporter()
        all_documents.extend(rapporter)

        # 4. Vägledningar
        vagledningar = await self.scrape_vagledningar()
        all_documents.extend(vagledningar)

        # Store all documents
        await self.store_documents(all_documents)

        # Generate report
        duration = (datetime.now() - start_time).total_seconds()

        report = {
            "source": SOURCE,
            "scraped_at": datetime.now().isoformat(),
            "duration_seconds": round(duration, 2),
            "stats": self.stats,
            "flagged": self.stats["total"] < 100,
            "flag_reason": "Less than 100 documents found" if self.stats["total"] < 100 else None,
        }

        # Save report
        report_path = (
            Path(__file__).parent
            / f"report_jordbruksverket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Print summary
        print("\n" + "=" * 80)
        print("📊 SCRAPING COMPLETE")
        print("=" * 80)
        print(f"Source:            {SOURCE}")
        print(f"Duration:          {duration:.2f}s")
        print(f"Total documents:   {self.stats['total']}")
        print(f"  - Föreskrifter:  {self.stats['foreskrifter']}")
        print(f"  - Statistik:     {self.stats['statistik']}")
        print(f"  - Rapporter:     {self.stats['rapporter']}")
        print(f"  - Vägledningar:  {self.stats['vagledningar']}")
        print(f"Errors:            {self.stats['errors']}")
        print(f"Flagged:           {'⚠️  YES' if report['flagged'] else '✅ NO'}")
        if report["flag_reason"]:
            print(f"Flag reason:       {report['flag_reason']}")
        print(f"\nReport saved:      {report_path}")
        print("=" * 80)

        return report


async def main():
    async with JordbruksverketScraper() as scraper:
        report = await scraper.run()
        return report


if __name__ == "__main__":
    asyncio.run(main())
