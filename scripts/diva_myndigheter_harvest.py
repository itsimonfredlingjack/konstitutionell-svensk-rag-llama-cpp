#!/usr/bin/env python3
"""
DiVA OAI-PMH Harvester for Swedish Government Agencies
Targets: Naturvårdsverket, Trafikverket, RISE, SMHI
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

# Configuration - MYNDIGHETER DiVA PORTALS
INSTITUTIONS = [
    {"code": "naturvardsverket", "name": "Naturvårdsverket", "expected": 9971},
    {"code": "trafikverket", "name": "Trafikverket", "expected": 5984},
    {"code": "ri", "name": "RISE Research Institutes of Sweden", "expected": 5000},
    {"code": "smhi", "name": "SMHI", "expected": 2000},
]

METADATA_PREFIX = "swepub_mods"
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
RATE_LIMIT_SECONDS = 1.0

NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
}

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
        self.output_file = OUTPUT_DIR / f"diva_myndighet_{self.code}.json"
        self.checkpoint_file = CHECKPOINT_DIR / f"myndighet_{self.code}_checkpoint.json"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
                "Accept": "application/xml,text/xml,*/*",
            }
        )
        self.documents = []
        self.total_fetched = 0
        self.errors = []
        self.start_time = datetime.now()
        self.resumption_token = None

    def load_checkpoint(self):
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
        if resumption_token:
            params = {"verb": "ListRecords", "resumptionToken": resumption_token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX}

        try:
            response = self.session.get(self.endpoint, params=params, timeout=60)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            self.errors.append({"type": "request_error", "error": str(e)})
            return None

    def parse_record(self, record_elem):
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
                title_info = mods.find(".//{http://www.loc.gov/mods/v3}titleInfo")
                if title_info is not None:
                    title = title_info.find(".//{http://www.loc.gov/mods/v3}title")
                    if title is not None and title.text:
                        doc["title"] = title.text.strip()

                abstract = mods.find(".//{http://www.loc.gov/mods/v3}abstract")
                if abstract is not None and abstract.text:
                    doc["abstract"] = abstract.text.strip()

                genre = mods.find(".//{http://www.loc.gov/mods/v3}genre")
                if genre is not None and genre.text:
                    doc["genre"] = genre.text.strip()

                date_issued = mods.find(".//{http://www.loc.gov/mods/v3}dateIssued")
                if date_issued is not None and date_issued.text:
                    doc["date_issued"] = date_issued.text.strip()

                language = mods.find(".//{http://www.loc.gov/mods/v3}languageTerm")
                if language is not None and language.text:
                    doc["language"] = language.text.strip()

        return doc

    def parse_response(self, xml_text):
        try:
            root = ET.fromstring(xml_text)

            error = root.find(".//{http://www.openarchives.org/OAI/2.0/}error")
            if error is not None:
                self.errors.append(
                    {"type": "oai_error", "code": error.get("code"), "message": error.text}
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
            self.errors.append({"type": "parse_error", "error": str(e)})
            return [], None

    def harvest(self):
        safe_print(f"\n{'='*60}")
        safe_print(f"[{self.code}] STARTING: {self.name}")
        safe_print(f"[{self.code}] Endpoint: {self.endpoint}")
        safe_print(f"[{self.code}] Expected: ~{self.expected:,} documents")
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
                    safe_print(f"[{self.code}] No records found")
                    break

            self.documents.extend(records)
            self.total_fetched += len(records)
            self.resumption_token = next_token

            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = self.total_fetched / elapsed if elapsed > 0 else 0
            pct = (self.total_fetched / self.expected * 100) if self.expected > 0 else 0

            if batch_count % 5 == 0:
                safe_print(
                    f"[{self.code}] Batch {batch_count}: {self.total_fetched:,} docs ({pct:.1f}%) @ {rate:.1f}/s"
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
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_print(f"[{self.code}] Saving {len(self.documents):,} documents...")
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()

        file_size = self.output_file.stat().st_size / 1024 / 1024
        safe_print(f"[{self.code}] Saved to {self.output_file} ({file_size:.2f} MB)")

    def get_report(self):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "code": self.code,
            "name": self.name,
            "expected": self.expected,
            "harvested": len(self.documents),
            "errors": len(self.errors),
            "elapsed_minutes": elapsed / 60,
        }


def harvest_institution(institution):
    harvester = DiVAHarvester(institution)
    try:
        return harvester.harvest()
    except Exception as e:
        safe_print(f"[{institution['code']}] ERROR: {e}")
        return {
            "code": institution["code"],
            "name": institution["name"],
            "harvested": 0,
            "error": str(e),
        }


def main():
    print("=" * 70)
    print("DiVA MYNDIGHETER HARVEST - 4 GOVERNMENT AGENCIES")
    print("=" * 70)
    print("  - naturvardsverket: Naturvårdsverket (~9,971)")
    print("  - trafikverket: Trafikverket (~5,984)")
    print("  - ri: RISE (~5,000)")
    print("  - smhi: SMHI (~2,000)")
    print(f"Total expected: ~{sum(i['expected'] for i in INSTITUTIONS):,} documents")
    print("=" * 70)

    start_time = datetime.now()
    reports = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
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

    total_elapsed = (datetime.now() - start_time).total_seconds()
    total_docs = sum(r.get("harvested", 0) for r in reports)

    print("\n" + "=" * 70)
    print("MYNDIGHETER HARVEST COMPLETE - SUMMARY")
    print("=" * 70)

    for r in sorted(reports, key=lambda x: x.get("harvested", 0), reverse=True):
        status = "OK" if r.get("harvested", 0) > 0 else "FAILED"
        print(
            f"[{status}] {r['code']}: {r.get('harvested', 0):,} docs (expected: ~{r.get('expected', '?'):,})"
        )

    print("-" * 70)
    print(f"TOTAL DOCUMENTS: {total_docs:,}")
    print(f"TOTAL TIME: {total_elapsed/60:.1f} minutes")
    print("=" * 70)

    summary_file = OUTPUT_DIR / "myndigheter_diva_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "batch": "myndigheter_diva",
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
        print("\n\nInterrupted! Checkpoints saved.")
        sys.exit(1)
