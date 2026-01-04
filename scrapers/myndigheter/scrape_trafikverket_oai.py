#!/usr/bin/env python3
"""
Trafikverket DiVA Portal Scraper - OAI-PMH Version
Harvests publications via OAI-PMH protocol from https://trafikverket.diva-portal.org
Stores results in ChromaDB collection: swedish_gov_docs
"""

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import chromadb
import requests
from chromadb.config import Settings

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# OAI-PMH namespace
OAI_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


@dataclass
class Publication:
    """Represents a Trafikverket publication"""

    title: str
    url: str
    doc_id: str
    authors: list[str]
    year: Optional[str]
    pub_type: Optional[str]
    abstract: Optional[str]
    subjects: list[str]
    language: Optional[str]
    identifier: Optional[str]
    source: str = "trafikverket"
    scraped_at: str = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def generate_hash(self) -> str:
        """Generate unique hash from identifier or URL"""
        base = self.identifier or self.url
        return hashlib.sha256(base.encode()).hexdigest()[:16]


class TrafikverketOAIScraper:
    """Scraper for Trafikverket DiVA Portal using OAI-PMH"""

    BASE_URL = "https://trafikverket.diva-portal.org/dice/oai"
    SET = "all-trafikverket"  # All publications from Trafikverket

    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.chromadb_path = chromadb_path
        self.publications: list[Publication] = []
        self.collection = None
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "TrafikverketScraper/1.0 (Educational Research)"}
        )

    def setup_chromadb(self):
        """Setup ChromaDB connection"""
        logger.info(f"Connecting to ChromaDB at {self.chromadb_path}")
        client = chromadb.PersistentClient(
            path=self.chromadb_path, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = client.get_or_create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
        )
        logger.info(f"ChromaDB collection ready. Current count: {self.collection.count()}")

    def oai_request(self, verb: str, **kwargs) -> ET.Element:
        """Make OAI-PMH request"""
        params = {"verb": verb}
        params.update(kwargs)

        url = f"{self.BASE_URL}?{urlencode(params)}"
        logger.debug(f"OAI request: {url}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)
            return root

        except requests.RequestException as e:
            logger.error(f"OAI request failed: {e}")
            raise
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            raise

    def list_records(self, metadata_prefix: str = "oai_dc", set_spec: Optional[str] = None):
        """
        Harvest all records using ListRecords verb with resumption tokens
        """
        logger.info(f"Harvesting records from set: {set_spec or 'default'}")

        # Initial request
        params = {"metadataPrefix": metadata_prefix}
        if set_spec:
            params["set"] = set_spec

        root = self.oai_request("ListRecords", **params)
        self.process_records(root)

        # Handle resumption tokens for pagination
        while True:
            resumption = root.find(".//oai:resumptionToken", OAI_NS)

            if resumption is None or not resumption.text:
                logger.info("No more resumption tokens - harvest complete")
                break

            token = resumption.text
            cursor = resumption.get("cursor", "?")
            complete_size = resumption.get("completeListSize", "?")

            logger.info(f"Resumption token found. Progress: {cursor}/{complete_size}")

            # Wait before next request (be polite)
            time.sleep(1)

            # Request next batch
            root = self.oai_request("ListRecords", resumptionToken=token)
            self.process_records(root)

    def process_records(self, root: ET.Element):
        """Process records from OAI-PMH response"""
        records = root.findall(".//oai:record", OAI_NS)
        logger.info(f"Processing {len(records)} records...")

        for record in records:
            try:
                pub = self.extract_publication(record)
                if pub:
                    self.publications.append(pub)
            except Exception as e:
                logger.warning(f"Error extracting publication: {e}")
                continue

    def extract_publication(self, record: ET.Element) -> Optional[Publication]:
        """Extract publication data from OAI record"""
        try:
            # Get header info
            header = record.find("oai:header", OAI_NS)
            if header is None:
                return None

            # Check if deleted
            status = header.get("status")
            if status == "deleted":
                return None

            identifier = header.find("oai:identifier", OAI_NS)
            if identifier is None:
                return None

            doc_id = identifier.text

            # Get metadata
            metadata = record.find(".//oai_dc:dc", OAI_NS)
            if metadata is None:
                return None

            # Extract Dublin Core fields
            titles = [t.text for t in metadata.findall("dc:title", OAI_NS) if t.text]
            title = titles[0] if titles else "Untitled"

            creators = [c.text for c in metadata.findall("dc:creator", OAI_NS) if c.text]

            dates = [d.text for d in metadata.findall("dc:date", OAI_NS) if d.text]
            year = dates[0][:4] if dates else None

            descriptions = [d.text for d in metadata.findall("dc:description", OAI_NS) if d.text]
            abstract = descriptions[0] if descriptions else None

            subjects = [s.text for s in metadata.findall("dc:subject", OAI_NS) if s.text]

            types = [t.text for t in metadata.findall("dc:type", OAI_NS) if t.text]
            pub_type = types[0] if types else None

            languages = [l.text for l in metadata.findall("dc:language", OAI_NS) if l.text]
            language = languages[0] if languages else None

            identifiers = [i.text for i in metadata.findall("dc:identifier", OAI_NS) if i.text]
            # Find URL identifier (usually URN or http link)
            url = None
            for ident in identifiers:
                if ident.startswith("http"):
                    url = ident
                    break
                elif "urn:nbn" in ident:
                    url = f"http://urn.kb.se/resolve?urn={ident}"

            if not url:
                url = f"https://trafikverket.diva-portal.org/record/{doc_id}"

            return Publication(
                title=title,
                url=url,
                doc_id=doc_id,
                authors=creators,
                year=year,
                pub_type=pub_type,
                abstract=abstract,
                subjects=subjects,
                language=language,
                identifier=doc_id,
            )

        except Exception as e:
            logger.warning(f"Error parsing publication: {e}")
            return None

    def save_to_chromadb(self):
        """Save publications to ChromaDB"""
        logger.info(f"Saving {len(self.publications)} publications to ChromaDB...")

        if not self.collection:
            self.setup_chromadb()

        saved_count = 0
        duplicate_count = 0

        for pub in self.publications:
            try:
                doc_hash = pub.generate_hash()

                # Check if already exists
                try:
                    existing = self.collection.get(ids=[doc_hash])
                    if existing["ids"]:
                        duplicate_count += 1
                        continue
                except Exception:
                    pass

                # Create searchable text
                text_parts = [pub.title]
                if pub.abstract:
                    text_parts.append(pub.abstract)
                if pub.authors:
                    text_parts.append(" ".join(pub.authors))
                if pub.subjects:
                    text_parts.append(" ".join(pub.subjects))

                document_text = "\n".join(text_parts)

                # Prepare metadata
                metadata = {
                    "source": pub.source,
                    "url": pub.url,
                    "title": pub.title[:500],  # ChromaDB has length limits
                    "year": pub.year or "unknown",
                    "pub_type": pub.pub_type or "unknown",
                    "doc_id": pub.doc_id,
                    "language": pub.language or "unknown",
                    "scraped_at": pub.scraped_at,
                }

                # Add to collection
                self.collection.add(ids=[doc_hash], documents=[document_text], metadatas=[metadata])
                saved_count += 1

            except Exception as e:
                logger.warning(f"Error adding publication to ChromaDB: {e}")
                continue

        logger.info(
            f"ChromaDB indexing complete. Saved: {saved_count}, Duplicates: {duplicate_count}"
        )

    def save_json_report(self) -> str:
        """Save JSON report of scraping results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"trafikverket_scrape_{timestamp}.json"

        # Count unique documents
        unique_pubs = {}
        for pub in self.publications:
            unique_pubs[pub.doc_id] = pub

        total_unique = len(unique_pubs)

        report = {
            "source": "trafikverket",
            "method": "OAI-PMH",
            "set": self.SET,
            "scraped_at": datetime.now().isoformat(),
            "total_records_harvested": len(self.publications),
            "total_unique_publications": total_unique,
            "chromadb_collection": "swedish_gov_docs",
            "chromadb_path": self.chromadb_path,
            "sample_publications": [pub.to_dict() for pub in list(unique_pubs.values())[:10]],
            "status": "WARNING: Less than 100 documents" if total_unique < 100 else "SUCCESS",
            "flagged": total_unique < 100,
        }

        report_path = Path(__file__).parent / report_file
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {report_path}")
        return str(report_path)

    def run(self):
        """Execute full scraping workflow"""
        try:
            logger.info("=== TRAFIKVERKET OAI-PMH SCRAPER START ===")

            self.setup_chromadb()

            # Harvest all records from Trafikverket set
            self.list_records(set_spec=self.SET)

            # Save to ChromaDB
            if self.publications:
                self.save_to_chromadb()

            # Generate report
            report_path = self.save_json_report()

            # Count unique
            unique_count = len(set(pub.doc_id for pub in self.publications))

            # Flag if too few documents
            if unique_count < 100:
                logger.warning(f"⚠️  WARNING: Only found {unique_count} documents (expected 100+)")
            else:
                logger.info(f"✓ SUCCESS: Found {unique_count} publications")

            logger.info("=== TRAFIKVERKET OAI-PMH SCRAPER COMPLETE ===")
            logger.info(f"Total documents scraped: {unique_count}")
            logger.info(f"Report: {report_path}")

            return report_path

        except Exception as e:
            logger.error(f"Scraper failed: {e}")
            raise


def main():
    scraper = TrafikverketOAIScraper()
    scraper.run()


if __name__ == "__main__":
    main()
