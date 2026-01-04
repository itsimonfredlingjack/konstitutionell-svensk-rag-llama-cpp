#!/usr/bin/env python3
"""
FINAL SWEEP: DiVA OAI-PMH Harvester for last 3 Swedish universities

Targets:
1. Kungliga Konsthogskolan (kkh) - ~5K estimated
2. Sophiahemmet Hogskola (shh) - ~3K estimated
3. Sveriges Lantbruksuniversitet (slu) - ~20K estimated

Total estimated: ~28K documents
"""

import concurrent.futures
import json
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration - FINAL 3 UNIVERSITIES
INSTITUTIONS = [
    {"code": "kkh", "name": "Kungliga Konsthogskolan", "expected": 5000},
    {"code": "shh", "name": "Sophiahemmet Hogskola", "expected": 3000},
    {"code": "slu", "name": "Sveriges Lantbruksuniversitet", "expected": 20000},
]

METADATA_PREFIX = "swepub_mods"
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
CHECKPOINT_DIR = Path("/home/ai-server/.claude/skills/swedish-gov-scraper/scripts/checkpoints")
RATE_LIMIT_SECONDS = 1.0

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "swepub": "http://swepub.kb.se/swepub_mods",
}

# Thread-safe print
print_lock = threading.Lock()


def safe_print(msg):
    with print_lock:
        print(msg, flush=True)


class DiVAHarvester:
    def __init__(self, institution):
        self.code = institution["code"]
        self.name = institution["name"]
        self.expected = institution["expected"]
        self.endpoint = f"https://{self.code}.diva-portal.org/dice/oai"
        self.output_file = OUTPUT_DIR / f"diva_full_{self.code}.json"
        self.checkpoint_file = CHECKPOINT_DIR / f"{self.code}_checkpoint.json"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
                "Accept": "application/xml,text/xml,*/*",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
            }
        )
        self.documents = []
        self.total_fetched = 0
        self.errors = []
        self.start_time = datetime.now()
        self.resumption_token = None

    def load_checkpoint(self):
        """Load checkpoint if exists to resume harvesting."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, encoding="utf-8") as f:
                    checkpoint = json.load(f)
                    self.resumption_token = checkpoint.get("resumption_token")
                    self.total_fetched = checkpoint.get("total_fetched", 0)
                    if self.output_file.exists():
                        with open(self.output_file, encoding="utf-8") as df:
                            self.documents = json.load(df)
                    safe_print(f"[{self.code}] Resuming from checkpoint: {self.total_fetched} docs")
                    return True
            except Exception as e:
                safe_print(f"[{self.code}] Checkpoint load failed: {e}")
        return False

    def save_checkpoint(self):
        """Save checkpoint for resume capability."""
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "resumption_token": self.resumption_token,
            "total_fetched": self.total_fetched,
            "timestamp": datetime.now().isoformat(),
        }
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False)

    def make_request(self, resumption_token=None):
        """Make OAI-PMH request."""
        if resumption_token:
            params = {"verb": "ListRecords", "resumptionToken": resumption_token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX}

        try:
            response = self.session.get(self.endpoint, params=params, timeout=60)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            self.errors.append(
                {"type": "request_error", "error": str(e), "timestamp": datetime.now().isoformat()}
            )
            return None

    def parse_record(self, record_elem):
        """Parse a single OAI-PMH record into a document dict."""
        doc = {
            "source": f"diva_{self.code}",
            "institution": self.name,
            "harvested_at": datetime.now().isoformat(),
        }

        header = record_elem.find("oai:header", NAMESPACES)
        if header is not None:
            identifier = header.find("oai:identifier", NAMESPACES)
            if identifier is not None:
                doc["identifier"] = identifier.text
            datestamp = header.find("oai:datestamp", NAMESPACES)
            if datestamp is not None:
                doc["datestamp"] = datestamp.text
            if header.get("status") == "deleted":
                doc["status"] = "deleted"
                return doc

        metadata = record_elem.find("oai:metadata", NAMESPACES)
        if metadata is not None:
            mods = metadata.find(".//{http://www.loc.gov/mods/v3}mods")

            if mods is not None:
                # Title
                title_info = mods.find(".//{http://www.loc.gov/mods/v3}titleInfo")
                if title_info is not None:
                    title = title_info.find(".//{http://www.loc.gov/mods/v3}title")
                    if title is not None and title.text:
                        doc["title"] = title.text.strip()
                    subtitle = title_info.find(".//{http://www.loc.gov/mods/v3}subTitle")
                    if subtitle is not None and subtitle.text:
                        doc["subtitle"] = subtitle.text.strip()

                # Authors
                authors = []
                for name in mods.findall(".//{http://www.loc.gov/mods/v3}name"):
                    name_parts = {}
                    for part in name.findall(".//{http://www.loc.gov/mods/v3}namePart"):
                        part_type = part.get("type", "unknown")
                        if part.text:
                            name_parts[part_type] = part.text.strip()
                    if name_parts:
                        authors.append(name_parts)
                if authors:
                    doc["authors"] = authors

                # Abstract
                abstract = mods.find(".//{http://www.loc.gov/mods/v3}abstract")
                if abstract is not None and abstract.text:
                    doc["abstract"] = abstract.text.strip()

                # Genre
                genre = mods.find(".//{http://www.loc.gov/mods/v3}genre")
                if genre is not None and genre.text:
                    doc["genre"] = genre.text.strip()

                # Date
                date_issued = mods.find(".//{http://www.loc.gov/mods/v3}dateIssued")
                if date_issued is not None and date_issued.text:
                    doc["date_issued"] = date_issued.text.strip()

                # Language
                language = mods.find(".//{http://www.loc.gov/mods/v3}languageTerm")
                if language is not None and language.text:
                    doc["language"] = language.text.strip()

                # Subjects
                subjects = []
                for subject in mods.findall(".//{http://www.loc.gov/mods/v3}subject"):
                    for topic in subject.findall(".//{http://www.loc.gov/mods/v3}topic"):
                        if topic.text:
                            subjects.append(topic.text.strip())
                if subjects:
                    doc["subjects"] = subjects

                # Identifiers (DOI, etc)
                identifiers = {}
                for ident in mods.findall(".//{http://www.loc.gov/mods/v3}identifier"):
                    ident_type = ident.get("type", "unknown")
                    if ident.text:
                        identifiers[ident_type] = ident.text.strip()
                if identifiers:
                    doc["identifiers"] = identifiers

                # Publisher
                origin = mods.find(".//{http://www.loc.gov/mods/v3}originInfo")
                if origin is not None:
                    publisher = origin.find(".//{http://www.loc.gov/mods/v3}publisher")
                    if publisher is not None and publisher.text:
                        doc["publisher"] = publisher.text.strip()

        return doc

    def parse_response(self, xml_text):
        """Parse OAI-PMH response, extract records and resumption token."""
        try:
            root = ET.fromstring(xml_text)

            error = root.find(".//{http://www.openarchives.org/OAI/2.0/}error")
            if error is not None:
                error_code = error.get("code", "unknown")
                error_msg = error.text or "No message"
                self.errors.append(
                    {
                        "type": "oai_error",
                        "code": error_code,
                        "message": error_msg,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                return [], None

            list_records = root.find(".//{http://www.openarchives.org/OAI/2.0/}ListRecords")
            if list_records is None:
                return [], None

            records = []
            for record in list_records.findall("{http://www.openarchives.org/OAI/2.0/}record"):
                doc = self.parse_record(record)
                if doc and doc.get("identifier"):
                    records.append(doc)

            token_elem = list_records.find("{http://www.openarchives.org/OAI/2.0/}resumptionToken")
            next_token = None
            if token_elem is not None and token_elem.text:
                next_token = token_elem.text.strip()

            return records, next_token

        except ET.ParseError as e:
            self.errors.append(
                {"type": "parse_error", "error": str(e), "timestamp": datetime.now().isoformat()}
            )
            return [], None

    def harvest(self):
        """Run the full harvest for this institution."""
        safe_print(f"\n{'='*60}")
        safe_print(f"[{self.code}] STARTING HARVEST: {self.name}")
        safe_print(f"[{self.code}] Endpoint: {self.endpoint}")
        safe_print(f"[{self.code}] Expected: ~{self.expected} documents")
        safe_print(f"{'='*60}")

        self.load_checkpoint()
        batch_count = 0
        retry_count = 0
        max_retries = 5

        while True:
            batch_count += 1

            xml_response = self.make_request(self.resumption_token)

            if xml_response is None:
                retry_count += 1
                if retry_count > max_retries:
                    safe_print(f"[{self.code}] Max retries exceeded, saving and exiting")
                    break
                safe_print(
                    f"[{self.code}] Request failed, retry {retry_count}/{max_retries} in 10s..."
                )
                time.sleep(10)
                continue

            retry_count = 0
            records, next_token = self.parse_response(xml_response)

            if not records and not next_token:
                if self.resumption_token:
                    safe_print(f"[{self.code}] Empty response, retrying...")
                    time.sleep(5)
                    continue
                else:
                    safe_print(f"[{self.code}] No records found, harvest complete or error.")
                    break

            self.documents.extend(records)
            self.total_fetched += len(records)
            self.resumption_token = next_token

            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = self.total_fetched / elapsed if elapsed > 0 else 0

            if batch_count % 5 == 0:
                safe_print(
                    f"[{self.code}] Batch {batch_count}: {self.total_fetched} docs ({rate:.1f}/s)"
                )

            if batch_count % 10 == 0:
                self.save_checkpoint()

            if not next_token:
                safe_print(f"[{self.code}] Harvest complete!")
                break

            time.sleep(RATE_LIMIT_SECONDS)

        self.save_documents()
        return self.get_report()

    def save_documents(self):
        """Save all documents to output file."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_print(f"[{self.code}] Saving {len(self.documents)} documents...")
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()

        file_size = self.output_file.stat().st_size / 1024 / 1024
        safe_print(f"[{self.code}] Saved to {self.output_file} ({file_size:.2f} MB)")

    def get_report(self):
        """Generate harvest report."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        with_title = sum(1 for d in self.documents if d.get("title"))
        with_abstract = sum(1 for d in self.documents if d.get("abstract"))
        deleted = sum(1 for d in self.documents if d.get("status") == "deleted")

        return {
            "code": self.code,
            "name": self.name,
            "expected": self.expected,
            "harvested": len(self.documents),
            "with_title": with_title,
            "with_abstract": with_abstract,
            "deleted": deleted,
            "errors": len(self.errors),
            "elapsed_minutes": elapsed / 60,
            "rate": len(self.documents) / elapsed if elapsed > 0 else 0,
        }


def harvest_institution(institution):
    """Harvest a single institution (for threading)."""
    harvester = DiVAHarvester(institution)
    try:
        return harvester.harvest()
    except Exception as e:
        safe_print(f"[{institution['code']}] ERROR: {e}")
        return {
            "code": institution["code"],
            "name": institution["name"],
            "expected": institution["expected"],
            "harvested": 0,
            "error": str(e),
        }


def main():
    print("=" * 70)
    print("FINAL SWEEP: DiVA OAI-PMH HARVEST - LAST 3 UNIVERSITIES")
    print("=" * 70)
    print(f"Institutions: {len(INSTITUTIONS)}")
    print("  - kkh: Kungliga Konsthogskolan (~5K)")
    print("  - shh: Sophiahemmet Hogskola (~3K)")
    print("  - slu: Sveriges Lantbruksuniversitet (~20K)")
    print(f"Total expected: ~{sum(i['expected'] for i in INSTITUTIONS):,} documents")
    print("Parallel workers: 3 (all at once)")
    print("=" * 70)

    start_time = datetime.now()
    reports = []

    # Run all 3 harvesters in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(harvest_institution, inst): inst for inst in INSTITUTIONS}

        for future in concurrent.futures.as_completed(futures):
            inst = futures[future]
            try:
                report = future.result()
                reports.append(report)
            except Exception as e:
                safe_print(f"[{inst['code']}] Thread error: {e}")
                reports.append(
                    {"code": inst["code"], "name": inst["name"], "harvested": 0, "error": str(e)}
                )

    # Final summary
    total_elapsed = (datetime.now() - start_time).total_seconds()
    total_docs = sum(r.get("harvested", 0) for r in reports)

    print("\n" + "=" * 70)
    print("FINAL SWEEP COMPLETE - SUMMARY")
    print("=" * 70)

    for r in sorted(reports, key=lambda x: x.get("harvested", 0), reverse=True):
        status = "OK" if r.get("harvested", 0) > 0 else "FAILED"
        print(
            f"[{status}] {r['code']}: {r.get('harvested', 0):,} docs (expected: ~{r.get('expected', '?'):,})"
        )

    print("-" * 70)
    print(f"TOTAL DOCUMENTS: {total_docs:,}")
    print(f"TOTAL TIME: {total_elapsed/60:.1f} minutes")
    if total_elapsed > 0:
        print(f"AVERAGE RATE: {total_docs/total_elapsed:.1f} docs/sec")
    print("=" * 70)

    # Save summary report
    summary_file = OUTPUT_DIR / "final_sweep_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "batch": "final_sweep",
                "timestamp": datetime.now().isoformat(),
                "total_documents": total_docs,
                "elapsed_minutes": total_elapsed / 60,
                "institutions": reports,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nSummary saved to: {summary_file}")

    return total_docs


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted! Checkpoints saved for all active harvesters.")
        sys.exit(1)
