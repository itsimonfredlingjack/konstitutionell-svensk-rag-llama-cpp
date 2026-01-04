#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - BOVERKET
Scraper for Boverket documents (BBR, EKS, handbooks, reports, guidance)
Target: boverket.se
ChromaDB: swedish_gov_docs collection, source: "boverket"
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

# PDF extraction
try:
    import PyPDF2
except ImportError:
    print("Installing PyPDF2...")
    os.system(f"{sys.executable} -m pip install PyPDF2 -q")
    import PyPDF2

# ChromaDB
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("Installing chromadb...")
    os.system(f"{sys.executable} -m pip install chromadb -q")
    import chromadb
    from chromadb.config import Settings

# BeautifulSoup for HTML parsing
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing beautifulsoup4...")
    os.system(f"{sys.executable} -m pip install beautifulsoup4 -q")


class BoverketScraper:
    """Scraper for Boverket government documents"""

    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.base_url = "https://www.boverket.se"
        self.chromadb_path = chromadb_path
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

        # Stats
        self.stats = {
            "total_documents": 0,
            "successful": 0,
            "failed": 0,
            "skipped_duplicates": 0,
            "categories": {},
            "start_time": datetime.now().isoformat(),
            "errors": [],
        }

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=chromadb_path, settings=Settings(anonymized_telemetry=False)
        )

        # Try to get existing collection, delete if dimension mismatch
        try:
            self.collection = self.chroma_client.get_collection(name="swedish_gov_docs")
            print("✅ Using existing collection: swedish_gov_docs")
        except:
            # Collection doesn't exist, create it
            from chromadb.utils import embedding_functions

            # Use sentence-transformers default (384 dimensions)
            sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.chroma_client.create_collection(
                name="swedish_gov_docs",
                metadata={"description": "Swedish government documents from various agencies"},
                embedding_function=sentence_transformer_ef,
            )
            print("✅ Created new collection: swedish_gov_docs")

        # PDF download directory
        self.pdf_dir = Path(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/pdf_cache/boverket"
        )
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

    def get_document_hash(self, url: str) -> str:
        """Generate unique hash for document URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def download_pdf(self, url: str) -> Optional[Path]:
        """Download PDF and return path"""
        try:
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()

            # Generate filename from URL
            filename = urlparse(url).path.split("/")[-1]
            if not filename.endswith(".pdf"):
                filename += ".pdf"

            filepath = self.pdf_dir / filename

            # Download
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return filepath

        except Exception as e:
            print(f"❌ Download failed for {url}: {e}")
            self.stats["errors"].append({"url": url, "error": str(e), "stage": "download"})
            return None

    def extract_pdf_text(self, filepath: Path) -> str:
        """Extract text from PDF"""
        try:
            text_parts = []
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text_parts.append(page.extract_text())

            return "\n".join(text_parts)

        except Exception as e:
            print(f"⚠️  PDF text extraction failed for {filepath.name}: {e}")
            return ""

    def categorize_document(self, url: str, title: str) -> str:
        """Categorize document by type"""
        url_lower = url.lower()
        title_lower = title.lower()

        if "bbr" in url_lower or "bbr" in title_lower or "byggregler" in title_lower:
            return "BBR - Byggregler"
        elif "bkr" in url_lower or "bkr" in title_lower:
            return "BKR - Konstruktionsregler (äldre)"
        elif "eks" in url_lower or "europeiska konstruktionsstandarder" in title_lower:
            return "EKS - Europeiska konstruktionsstandarder"
        elif "bbk" in url_lower or "betongkonstruktioner" in title_lower:
            return "BBK - Betonghandbok"
        elif "bsk" in url_lower or "stålkonstruktioner" in title_lower:
            return "BSK - Stålhandbok"
        elif "cex" in url_lower or "energiexpert" in title_lower:
            return "CEX - Certifiering energiexperter"
        elif "ben" in url_lower or "energianvändning" in title_lower:
            return "BEN - Energianvändning"
        elif "ovk" in url_lower or "funktionskontroll" in title_lower:
            return "OVK - Funktionskontroll"
        elif "energideklaration" in title_lower or "energi" in title_lower:
            return "Energi & Miljö"
        elif "rapport" in url_lower or "rapport" in title_lower:
            return "Rapporter"
        elif "handbok" in url_lower or "handbok" in title_lower:
            return "Handböcker"
        elif (
            "vägledning" in url_lower or "vagledning" in url_lower or "allmänna råd" in title_lower
        ):
            return "Vägledningar"
        elif "konsekvensutredning" in url_lower:
            return "Konsekvensutredningar"
        else:
            return "Övrigt"

    def add_to_chromadb(self, url: str, title: str, text: str, category: str, metadata: dict):
        """Add document to ChromaDB"""
        try:
            doc_id = self.get_document_hash(url)

            # Check if already exists
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing["ids"]:
                    print(f"⏭️  Skipped (duplicate): {title}")
                    self.stats["skipped_duplicates"] += 1
                    return
            except:
                pass

            # Prepare metadata
            full_metadata = {
                "source": "boverket",
                "url": url,
                "title": title,
                "category": category,
                "scraped_at": datetime.now().isoformat(),
                **metadata,
            }

            # Add to collection
            self.collection.add(
                ids=[doc_id],
                documents=[text[:50000]],  # Limit text size
                metadatas=[full_metadata],
            )

            print(f"✅ Added: {title} ({category})")
            self.stats["successful"] += 1
            self.stats["categories"][category] = self.stats["categories"].get(category, 0) + 1

        except Exception as e:
            print(f"❌ ChromaDB insert failed for {title}: {e}")
            self.stats["failed"] += 1
            self.stats["errors"].append(
                {"url": url, "title": title, "error": str(e), "stage": "chromadb"}
            )

    def scrape_pdf_document(self, url: str, title: str, metadata: dict = {}):
        """Download, extract, and store a PDF document"""
        self.stats["total_documents"] += 1

        print(f"\n[{self.stats['total_documents']}] Processing: {title}")
        print(f"    URL: {url}")

        # Download
        filepath = self.download_pdf(url)
        if not filepath:
            self.stats["failed"] += 1
            return

        # Extract text
        text = self.extract_pdf_text(filepath)
        if not text or len(text) < 100:
            print(f"⚠️  Warning: Extracted text is very short ({len(text)} chars)")

        # Categorize
        category = self.categorize_document(url, title)

        # Add to ChromaDB
        metadata["file_size"] = filepath.stat().st_size
        metadata["local_path"] = str(filepath)
        self.add_to_chromadb(url, title, text, category, metadata)

        # Rate limiting
        time.sleep(1)

    def scrape_bbr_documents(self):
        """Scrape BBR (building regulations) documents"""
        print("\n" + "=" * 80)
        print("SCRAPING BBR DOCUMENTS")
        print("=" * 80)

        bbr_docs = [
            {
                "url": "https://rinfo.boverket.se/BFS2011-6/pdf/BFS2024-14.pdf",
                "title": "BBR 31 - BFS 2024:14 (gäller från 2025-01-01)",
                "metadata": {"year": "2024", "version": "BBR 31", "bfs": "BFS 2024:14"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2011-6/pdf/BFS2024-5.pdf",
                "title": "BBR 30 - BFS 2024:5 (gäller från 2025-01-01)",
                "metadata": {"year": "2024", "version": "BBR 30", "bfs": "BFS 2024:5"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2020/konsoliderad-bbr-2011-6-tom-2020-4.pdf",
                "title": "BBR BFS 2011:6 med ändringar till och med BFS 2020:4 (konsoliderad)",
                "metadata": {"year": "2020", "version": "BBR konsoliderad", "bfs": "BFS 2011:6"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2011-6/pdf/BFS2011-6.pdf",
                "title": "BBR 18 - BFS 2011:6 (originalversion)",
                "metadata": {"year": "2011", "version": "BBR 18", "bfs": "BFS 2011:6"},
            },
        ]

        for doc in bbr_docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_handbooks(self):
        """Scrape technical handbooks"""
        print("\n" + "=" * 80)
        print("SCRAPING HANDBOOKS")
        print("=" * 80)

        handbooks = [
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2004/boverkets_handbok_om_betongkonstruktioner_bbk_04.pdf",
                "title": "BBK 04 - Boverkets handbok om betongkonstruktioner",
                "metadata": {"year": "2004", "type": "Handbok", "code": "BBK 04"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2007/bsk_07.pdf",
                "title": "BSK 07 - Boverkets handbok om stålkonstruktioner",
                "metadata": {"year": "2007", "type": "Handbok", "code": "BSK 07"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2008/bullerskydd_i_bostader_och_lokaler.pdf",
                "title": "Bullerskydd i bostäder och lokaler - Handbok",
                "metadata": {"year": "2008", "type": "Handbok", "topic": "Bullerskydd"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2013/vindkraftshandboken.pdf",
                "title": "Vindkraftshandboken",
                "metadata": {"year": "2013", "type": "Handbok", "topic": "Vindkraft"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2004/boken_om_lov_tillsyn_och_kontroll.pdf",
                "title": "Boken om lov, tillsyn och kontroll",
                "metadata": {"year": "2004", "type": "Handbok", "topic": "Lov och tillsyn"},
            },
        ]

        for doc in handbooks:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_reports(self):
        """Scrape reports and studies"""
        print("\n" + "=" * 80)
        print("SCRAPING REPORTS")
        print("=" * 80)

        reports = [
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/klimatanpassningslaget-i-oversiktsplaner.pdf",
                "title": "Rapport 2025:17 - Klimatanpassningsläget i översiktsplaner",
                "metadata": {
                    "year": "2025",
                    "type": "Rapport",
                    "report_number": "2025:17",
                    "topic": "Klimatanpassning",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/metoder-definitioner-och-krav-inom-solenergi-i-direktivet-om-byggnaders-energiprestanda.pdf",
                "title": "Rapport 2025:3 - Metoder, definitioner och krav inom solenergi i direktivet om byggnaders energiprestanda",
                "metadata": {
                    "year": "2025",
                    "type": "Rapport",
                    "report_number": "2025:3",
                    "topic": "Solenergi",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2019/inspektion-av-uppvarmningssystem-och-luftkonditioneringssystem.pdf",
                "title": "Rapport 2019:16 - Inspektion av uppvärmningssystem och luftkonditioneringssystem",
                "metadata": {
                    "year": "2019",
                    "type": "Rapport",
                    "report_number": "2019:16",
                    "topic": "Inspektion",
                },
            },
            {
                "url": "https://www.boverket.se/contentassets/084acb7f8958448897248ef9a412bebb/byggregler---en-historisk-oversikt-fran-babs-till-bbr-23.pdf",
                "title": "Byggregler - en historisk översikt från BABS till BBR 23",
                "metadata": {"year": "2023", "type": "Rapport", "topic": "Historik byggregler"},
            },
            {
                "url": "https://www.boverket.se/contentassets/ba75fc25915f4a79bad02ff6e9a5eb02/byggregler-en-historisk-oversikt-2022.pdf",
                "title": "Byggregler - en historisk översikt (2022)",
                "metadata": {"year": "2022", "type": "Rapport", "topic": "Historik byggregler"},
            },
        ]

        for doc in reports:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_consequence_analyses(self):
        """Scrape consequence analyses (konsekvensutredningar)"""
        print("\n" + "=" * 80)
        print("SCRAPING CONSEQUENCE ANALYSES")
        print("=" * 80)

        analyses = [
            {
                "url": "https://www.boverket.se/contentassets/11d6b1ba87d243ed9dc60dc8d8c3ba32/2025-03-slutversion-konsoliderad-ku-brandskydd.pdf",
                "title": "Sammanställning av brandskyddsdelarna i Boverkets konsekvensutredningar",
                "metadata": {"year": "2025", "type": "Konsekvensutredning", "topic": "Brandskydd"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2024-8/dok/BFS2024-8_Konsekvensutredning.pdf",
                "title": "Konsekvensutredning BFS 2024:8 - Skydd mot skadliga ämnen",
                "metadata": {"year": "2024", "type": "Konsekvensutredning", "bfs": "BFS 2024:8"},
            },
            {
                "url": "https://www.boverket.se/contentassets/aa5b715ba2af4083b0ec76f4b683956b/utredning-dagsljus-i-andringsregler.pdf",
                "title": "Utredning av lättnader av dagsljuskrav i Boverkets nya byggregler",
                "metadata": {"year": "2024", "type": "Utredning", "topic": "Dagsljus"},
            },
        ]

        for doc in analyses:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_guidance_documents(self):
        """Scrape guidance documents (vägledningar)"""
        print("\n" + "=" * 80)
        print("SCRAPING GUIDANCE DOCUMENTS")
        print("=" * 80)

        guidance = [
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2008/buller_i_planeringen_allmanna_rad_2008_1.pdf",
                "title": "Buller i planeringen - Allmänna råd 2008:1",
                "metadata": {"year": "2008", "type": "Vägledning", "topic": "Buller"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/1994/svangningar_deformationspaverkan_och_olyckslast.pdf",
                "title": "Svängningar, deformationspåverkan och olyckslast",
                "metadata": {"year": "1994", "type": "Vägledning", "topic": "Konstruktion"},
            },
        ]

        for doc in guidance:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_bkr_documents(self):
        """Scrape BKR (older construction regulations) documents"""
        print("\n" + "=" * 80)
        print("SCRAPING BKR DOCUMENTS")
        print("=" * 80)

        bkr_docs = [
            {
                "url": "https://rinfo.boverket.se/BFS1993-58/pdf/BFS2003-6.pdf",
                "title": "BKR 7 - BFS 2003:6 (äldre konstruktionsregler)",
                "metadata": {
                    "year": "2003",
                    "version": "BKR 7",
                    "bfs": "BFS 2003:6",
                    "status": "historisk",
                },
            }
        ]

        for doc in bkr_docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_additional_bbr_versions(self):
        """Scrape additional BBR versions and amendments"""
        print("\n" + "=" * 80)
        print("SCRAPING ADDITIONAL BBR VERSIONS")
        print("=" * 80)

        bbr_additional = [
            {
                "url": "https://rinfo.boverket.se/BFS2011-6/pdf/BFS2020-4.pdf",
                "title": "BBR 29 - BFS 2020:4",
                "metadata": {"year": "2020", "version": "BBR 29", "bfs": "BFS 2020:4"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2011-6/dok/BFS2020-4_Konsolidering.pdf",
                "title": "BBR Konsoliderad BFS 2011:6 t.o.m BFS 2020:4",
                "metadata": {"year": "2020", "version": "BBR konsoliderad", "bfs": "BFS 2011:6"},
            },
            {
                "url": "https://www.boverket.se/contentassets/2b709d86893740bab472714cb1ffb4c0/boverkets-byggregler-bfs-2011-6-tom-2013-3.pdf",
                "title": "BBR BFS 2011:6 t.o.m 2013:3",
                "metadata": {"year": "2013", "version": "BBR", "bfs": "BFS 2011:6"},
            },
        ]

        for doc in bbr_additional:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_eks_documents(self):
        """Scrape EKS (construction rules) documents"""
        print("\n" + "=" * 80)
        print("SCRAPING EKS DOCUMENTS")
        print("=" * 80)

        eks_docs = [
            {
                "url": "https://www.boverket.se/resources/constitutiontextstore/eks/PDF/konsoliderad_eks_bfs_2011-10.pdf",
                "title": "EKS - Boverkets föreskrifter och allmänna råd om tillämpning av europeiska konstruktionsstandarder (konsoliderad BFS 2011:10)",
                "metadata": {"year": "2011", "type": "Föreskrift", "bfs": "BFS 2011:10"},
            }
        ]

        for doc in eks_docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_energy_documents(self):
        """Scrape energy and environmental documents"""
        print("\n" + "=" * 80)
        print("SCRAPING ENERGY & ENVIRONMENTAL DOCUMENTS")
        print("=" * 80)

        energy_docs = [
            {
                "url": "https://rinfo.boverket.se/BFS2007-5/pdf/BFS2013-17.pdf",
                "title": "CEX 4 - BFS 2013:17 Certifiering av energiexperter",
                "metadata": {
                    "year": "2013",
                    "type": "Föreskrift",
                    "bfs": "BFS 2013:17",
                    "topic": "Energideklaration",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/oversyn-av-systemet-med-energideklarationer.pdf",
                "title": "Rapport 2025:6 - Översyn av systemet med energideklarationer",
                "metadata": {
                    "year": "2025",
                    "type": "Rapport",
                    "report_number": "2025:6",
                    "topic": "Energideklaration",
                },
            },
            {
                "url": "https://www.boverket.se/resources/constitutiontextstore/ovk/PDF/konsoliderad_ovk_bfs_2011-16.pdf",
                "title": "OVK - Boverkets föreskrifter om funktionskontroll (konsoliderad BFS 2011:16)",
                "metadata": {
                    "year": "2011",
                    "type": "Föreskrift",
                    "bfs": "BFS 2011:16",
                    "topic": "Funktionskontroll",
                },
            },
            {
                "url": "https://rinfo.boverket.se/BFS2007-5/pdf/BFS2007-5.pdf",
                "title": "CEX - BFS 2007:5 Certifiering av energiexperter (grundföreskrift)",
                "metadata": {
                    "year": "2007",
                    "type": "Föreskrift",
                    "bfs": "BFS 2007:5",
                    "topic": "Energideklaration",
                },
            },
            {
                "url": "https://www.boverket.se/Resources/constitutiontextstore/BEN/xml/Konsoliderad_BEN_BFS_2016_12.pdf",
                "title": "BEN - Boverkets föreskrifter om fastställande av byggnadens energianvändning (konsoliderad BFS 2016:12)",
                "metadata": {
                    "year": "2016",
                    "type": "Föreskrift",
                    "bfs": "BFS 2016:12",
                    "topic": "Energianvändning",
                },
            },
            {
                "url": "https://www.boverket.se/contentassets/9691104cc6b44e83aa3506f4da97ecf4/publikt_api_for_energideklarationer_-_urvalslogik_och_resultat_v1.1.pdf",
                "title": "Publikt API för energideklarationer - Urvalslogik och resultat v1.1",
                "metadata": {
                    "year": "2024",
                    "type": "Dokumentation",
                    "topic": "Energideklaration API",
                },
            },
            {
                "url": "https://www.boverket.se/contentassets/835858adfa9b442e823bd7414c4cf682/ben-3_ex-2-aldre-smahus.pdf",
                "title": "BEN-3 Exempel 2 - Äldre småhus",
                "metadata": {"year": "2018", "type": "Exempel", "topic": "Energianvändning"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2007-5/pdf/BFS2011-9.pdf",
                "title": "CEX 3 - BFS 2011:9 Certifiering av energiexperter",
                "metadata": {
                    "year": "2011",
                    "type": "Föreskrift",
                    "bfs": "BFS 2011:9",
                    "topic": "Energideklaration",
                },
            },
            {
                "url": "https://www.boverket.se/contentassets/8af5c0f9e0ce4f6481323f8a981cea50/validitetskontroll-2021.pdf",
                "title": "Validitetskontroll av 2021 års energideklarationer",
                "metadata": {"year": "2021", "type": "Rapport", "topic": "Energideklaration"},
            },
        ]

        for doc in energy_docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_bfs_regulations(self):
        """Scrape additional BFS regulations from 2020-2024"""
        print("\n" + "=" * 80)
        print("SCRAPING BFS REGULATIONS 2020-2024")
        print("=" * 80)

        bfs_docs = [
            {
                "url": "https://rinfo.boverket.se/BFS2024-7/pdf/BFS2024-7.pdf",
                "title": "BFS 2024:7 - Föreskrifter om trycksystem och brandskydd",
                "metadata": {"year": "2024", "type": "Föreskrift", "bfs": "BFS 2024:7"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2024-9/pdf/BFS2024-9.pdf",
                "title": "BFS 2024:9",
                "metadata": {"year": "2024", "type": "Föreskrift", "bfs": "BFS 2024:9"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2024-12/pdf/BFS2024-12.pdf",
                "title": "BFS 2024:12 - Tillgänglighet för en- och tvåbostadshus",
                "metadata": {
                    "year": "2024",
                    "type": "Föreskrift",
                    "bfs": "BFS 2024:12",
                    "topic": "Tillgänglighet",
                },
            },
            {
                "url": "https://rinfo.boverket.se/BFS2024-6/pdf/BFS2024-6.pdf",
                "title": "BFS 2024:6",
                "metadata": {"year": "2024", "type": "Föreskrift", "bfs": "BFS 2024:6"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2024-2/pdf/BFS2024-2.pdf",
                "title": "BFS 2024:2",
                "metadata": {"year": "2024", "type": "Föreskrift", "bfs": "BFS 2024:2"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2024-10/pdf/BFS2024-10.pdf",
                "title": "BFS 2024:10",
                "metadata": {"year": "2024", "type": "Föreskrift", "bfs": "BFS 2024:10"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2011-16/pdf/BFS2023-4.pdf",
                "title": "BFS 2023:4 OVK 4 - Funktionskontroll ventilation",
                "metadata": {
                    "year": "2023",
                    "type": "Föreskrift",
                    "bfs": "BFS 2023:4",
                    "topic": "Ventilation",
                },
            },
        ]

        for doc in bfs_docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_planning_housing(self):
        """Scrape planning and housing documents"""
        print("\n" + "=" * 80)
        print("SCRAPING PLANNING & HOUSING DOCUMENTS")
        print("=" * 80)

        docs = [
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2019/konsten-att-bygga-en-stad-webb.pdf",
                "title": "Konsten att bygga en stad - svenska stadsplaner genom seklerna",
                "metadata": {"year": "2019", "type": "Rapport", "topic": "Stadsplanering"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2022/ramverk-for-nationell-planering---slutrapport.pdf",
                "title": "Ramverk för nationell planering - Slutrapport",
                "metadata": {"year": "2022", "type": "Rapport", "topic": "Samhällsplanering"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2005/bygga_bra_bostader.pdf",
                "title": "Bygga Bra Bostäder",
                "metadata": {"year": "2005", "type": "Handbok", "topic": "Bostäder"},
            },
            {
                "url": "https://www.boverket.se/contentassets/56b41b3b67c84d27bcd3245894c535fe/vasternorrlands-lan-2024.pdf",
                "title": "Bostadsmarknadsanalys 2024 Västernorrlands län",
                "metadata": {"year": "2024", "type": "Rapport", "topic": "Bostadsmarknad"},
            },
            {
                "url": "https://www.boverket.se/contentassets/d6136e8e4ff143728ce52bdb20b6148f/pbl-kunskapsbanken-dp-fram-till-20141222.pdf",
                "title": "PBL kunskapsbanken Detaljplanering 2014",
                "metadata": {"year": "2014", "type": "Vägledning", "topic": "Detaljplanering"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2007/bostadspolitiken.pdf",
                "title": "Bostadspolitiken - 130 år av svensk politik",
                "metadata": {"year": "2007", "type": "Rapport", "topic": "Bostadspolitik"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2014/samordna-planeringen-for-bebyggelse-och-transporter.pdf",
                "title": "Samordna planeringen för bebyggelse och transporter - Kunskapsöversikt",
                "metadata": {"year": "2014", "type": "Rapport", "topic": "Transportplanering"},
            },
        ]

        for doc in docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_accessibility_elevators(self):
        """Scrape accessibility and elevator documents"""
        print("\n" + "=" * 80)
        print("SCRAPING ACCESSIBILITY & ELEVATOR DOCUMENTS")
        print("=" * 80)

        docs = [
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2012/bfs-2012-11-h-14.pdf",
                "title": "BFS 2012:11 H 14 - Föreskrifter om hissar och motordrivna anordningar",
                "metadata": {
                    "year": "2012",
                    "type": "Föreskrift",
                    "bfs": "BFS 2012:11",
                    "topic": "Hissar",
                },
            },
            {
                "url": "https://www.boverket.se/resources/constitutiontextstore/h/PDF/konsoliderad_h_bfs_2011-12.pdf",
                "title": "Konsoliderad H BFS 2011:12 - Hissar och lyftanordningar",
                "metadata": {
                    "year": "2011",
                    "type": "Föreskrift",
                    "bfs": "BFS 2011:12",
                    "topic": "Hissar",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2005/tillgangliga_platser.pdf",
                "title": "Tillgängliga platser",
                "metadata": {"year": "2005", "type": "Handbok", "topic": "Tillgänglighet"},
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2022/uppdrag-att-utreda-atgarder-for-vissa-sakerhetsrisker-i-aldre-hissar.pdf",
                "title": "Utredning - Säkerhetsrisker i äldre hissar",
                "metadata": {"year": "2022", "type": "Rapport", "topic": "Hissar säkerhet"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS2011-6/pdf/BFS2011-26.pdf",
                "title": "BFS 2011:26 BBR 19 - Rättelseblad",
                "metadata": {"year": "2011", "type": "Föreskrift", "bfs": "BFS 2011:26"},
            },
            {
                "url": "https://rinfo.boverket.se/BFS1993-57/pdf/BFS1998-38.pdf",
                "title": "BFS 1998:38 BBR 7 (historisk)",
                "metadata": {
                    "year": "1998",
                    "type": "Föreskrift",
                    "bfs": "BFS 1998:38",
                    "status": "historisk",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/lattnader-i-kraven-pa-byggnader-vid-andring-och-ombyggnad.pdf",
                "title": "Rapport 2025:12 - Lättnader vid ändring och ombyggnad",
                "metadata": {
                    "year": "2025",
                    "type": "Rapport",
                    "report_number": "2025:12",
                    "topic": "Ändringsbyggnad",
                },
            },
        ]

        for doc in docs:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def scrape_regional_market_analyses(self):
        """Scrape regional housing market analyses"""
        print("\n" + "=" * 80)
        print("SCRAPING REGIONAL MARKET ANALYSES")
        print("=" * 80)

        regions = [
            ("vastmanlands-lan-2024.pdf", "Bostadsmarknadsanalys 2024 Västmanlands län"),
            ("hallands-lan-2024.pdf", "Bostadsmarknadsanalys 2024 Hallands län"),
            ("kronobergs-lan-2024.pdf", "Bostadsmarknadsanalys 2024 Kronobergs län"),
            ("norrbottens-lan-2024.pdf", "Bostadsmarknadsanalys 2024 Norrbottens län"),
            ("kalmar-lan-2023.pdf", "Bostadsmarknadsanalys 2023 Kalmar län"),
            ("hallands-lan-2023.pdf", "Bostadsmarknadsanalys 2023 Hallands län"),
            ("ostergotlands-lan-2023.pdf", "Bostadsmarknadsanalys 2023 Östergötlands län"),
            ("vastra-gotalands-lan-2023.pdf", "Bostadsmarknadsanalys 2023 Västra Götalands län"),
        ]

        for filename, title in regions:
            year = "2024" if "2024" in filename else "2023"
            base_url = "https://www.boverket.se/contentassets/"
            path_2024 = "56b41b3b67c84d27bcd3245894c535fe/"
            path_2023 = "e9809d5193d140a697352fdbe54c86bf/"

            url = base_url + (path_2024 if year == "2024" else path_2023) + filename

            self.scrape_pdf_document(
                url,
                title,
                {"year": year, "type": "Rapport", "report_type": "Bostadsmarknadsanalys"},
            )

        # Add 2025 report
        self.scrape_pdf_document(
            "https://www.boverket.se/contentassets/1a53e212b3214d54ab50aec70135d4ea/bostadsmarknadsanalys-2025-ostergotlands-lan.pdf",
            "Bostadsmarknadsanalys 2025 Östergötlands län",
            {"year": "2025", "type": "Rapport", "report_type": "Bostadsmarknadsanalys"},
        )

    def scrape_additional_reports(self):
        """Scrape additional reports 2022-2024"""
        print("\n" + "=" * 80)
        print("SCRAPING ADDITIONAL REPORTS 2022-2024")
        print("=" * 80)

        reports = [
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2024/uppdrag-att-forbattra-prognoser-och-scenarier-for-bostadsbyggande.pdf",
                "title": "Rapport 2024:4 - Prognoser och scenarier för bostadsbyggande",
                "metadata": {
                    "year": "2024",
                    "type": "Rapport",
                    "report_number": "2024:4",
                    "topic": "Byggprognos",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2024/uppdrag-om-oversyn-av-regelverket-for-andring-av-detaljplan-och-av-olagliga-planbestammelser.pdf",
                "title": "Rapport 2024:21 - Översyn av regelverket för ändring av detaljplan",
                "metadata": {
                    "year": "2024",
                    "type": "Rapport",
                    "report_number": "2024:21",
                    "topic": "Detaljplanering",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2024/trygga-och-jamstallda-stads--och-boendemiljoer.pdf",
                "title": "Rapport 2024:27 - Trygga och jämställda stads- och boendemiljöer",
                "metadata": {
                    "year": "2024",
                    "type": "Rapport",
                    "report_number": "2024:27",
                    "topic": "Trygghet",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2024/inkluderande-bostadsbyggande-med-statligt-stod---en-ideskiss.pdf",
                "title": "Rapport 2024:7 - Inkluderande bostadsbyggande med statligt stöd",
                "metadata": {
                    "year": "2024",
                    "type": "Rapport",
                    "report_number": "2024:7",
                    "topic": "Bostadsbyggande",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2023/boverkets-byggprognos-juni-2023.pdf",
                "title": "Rapport 2023:22 - Boverkets byggprognos Juni 2023",
                "metadata": {
                    "year": "2023",
                    "type": "Rapport",
                    "report_number": "2023:22",
                    "topic": "Byggprognos",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2023/slutrapport-gransvarde-for-byggnaders-klimatpaverkan.pdf",
                "title": "Rapport 2023:20 - Gränsvärde för byggnaders klimatpåverkan",
                "metadata": {
                    "year": "2023",
                    "type": "Rapport",
                    "report_number": "2023:20",
                    "topic": "Klimat",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2023/uppdrag-om-totalforsvarets-intressen-vid-provning-enligt-plan--och-bygglagen.pdf",
                "title": "Rapport 2023:19 - Totalförsvarets intressen vid prövning enligt PBL",
                "metadata": {
                    "year": "2023",
                    "type": "Rapport",
                    "report_number": "2023:19",
                    "topic": "Totalförsvar",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2023/kommunala-erfarenheter-av-finansiering-av-klimatanpassningsatgarder.pdf",
                "title": "Rapport 2023:18 - Kommunala erfarenheter av finansiering av klimatanpassningsåtgärder",
                "metadata": {
                    "year": "2023",
                    "type": "Rapport",
                    "report_number": "2023:18",
                    "topic": "Klimatanpassning",
                },
            },
            {
                "url": "https://www.boverket.se/globalassets/publikationer/dokument/2023/boendesegregationens-utveckling-och-mekanismer.pdf",
                "title": "Rapport 2023:23 - Boendesegregationens utveckling och mekanismer",
                "metadata": {
                    "year": "2023",
                    "type": "Rapport",
                    "report_number": "2023:23",
                    "topic": "Segregation",
                },
            },
        ]

        for doc in reports:
            self.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    def run(self):
        """Run complete scraping operation"""
        print("\n" + "=" * 80)
        print("OPERATION MYNDIGHETS-SWEEP - BOVERKET")
        print("=" * 80)
        print("Target: boverket.se")
        print(f"ChromaDB: {self.chromadb_path}")
        print("Collection: swedish_gov_docs")
        print(f"PDF Cache: {self.pdf_dir}")
        print(f"Started: {self.stats['start_time']}")
        print("=" * 80)

        # Run all scraping operations
        self.scrape_bbr_documents()
        self.scrape_additional_bbr_versions()
        self.scrape_eks_documents()
        self.scrape_bfs_regulations()
        self.scrape_handbooks()
        self.scrape_reports()
        self.scrape_consequence_analyses()
        self.scrape_guidance_documents()
        self.scrape_energy_documents()
        self.scrape_planning_housing()
        self.scrape_accessibility_elevators()
        self.scrape_regional_market_analyses()
        self.scrape_additional_reports()
        self.scrape_bkr_documents()

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate final JSON report"""
        self.stats["end_time"] = datetime.now().isoformat()
        self.stats["duration_seconds"] = (
            datetime.fromisoformat(self.stats["end_time"])
            - datetime.fromisoformat(self.stats["start_time"])
        ).total_seconds()

        # Check flagging rule
        self.stats["flagged"] = self.stats["successful"] < 100
        if self.stats["flagged"]:
            self.stats["flag_reason"] = (
                f"Only {self.stats['successful']} documents collected (minimum: 100)"
            )

        # Save report
        report_path = Path(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/boverket_report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)

        # Print summary
        print("\n" + "=" * 80)
        print("SCRAPING COMPLETE - SUMMARY")
        print("=" * 80)
        print(f"Total documents processed: {self.stats['total_documents']}")
        print(f"Successfully added: {self.stats['successful']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Skipped (duplicates): {self.stats['skipped_duplicates']}")
        print("\nCategories:")
        for category, count in sorted(self.stats["categories"].items()):
            print(f"  - {category}: {count}")
        print(f"\nDuration: {self.stats['duration_seconds']:.1f} seconds")

        if self.stats["flagged"]:
            print(f"\n⚠️  FLAGGED: {self.stats['flag_reason']}")
        else:
            print(f"\n✅ SUCCESS: Threshold met ({self.stats['successful']} >= 100)")

        if self.stats["errors"]:
            print(f"\n❌ Errors encountered: {len(self.stats['errors'])}")
            for err in self.stats["errors"][:5]:  # Show first 5
                print(f"  - {err.get('title', err.get('url'))}: {err['error']}")

        print(f"\nReport saved: {report_path}")
        print("=" * 80)

        return self.stats


def main():
    scraper = BoverketScraper()
    scraper.run()


if __name__ == "__main__":
    main()
