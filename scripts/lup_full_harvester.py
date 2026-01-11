#!/usr/bin/env python3
"""
LUP OAI-PMH Full Harvester
Lund University Publications - 242,111 documents
Rate limit: 1 req/sec with resumptionToken pagination
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# OAI-PMH namespace
OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"

BASE_URL = "https://lup.lub.lu.se/oai"
METADATA_PREFIX = "oai_dc"
OUTPUT_FILE = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_lu.json")
RATE_LIMIT = 1.0  # seconds between requests


def extract_dc_text(record_elem, tag):
    """Extract text from Dublin Core element"""
    elem = record_elem.find(f".//{DC_NS}{tag}")
    return elem.text.strip() if elem is not None and elem.text else None


def extract_all_dc(record_elem, tag):
    """Extract all instances of a Dublin Core element"""
    elems = record_elem.findall(f".//{DC_NS}{tag}")
    return [e.text.strip() for e in elems if e.text]


def parse_record(record_elem):
    """Parse OAI-PMH record to dict"""
    header = record_elem.find(f"{OAI_NS}header")
    metadata = record_elem.find(f"{OAI_NS}metadata")

    if header is None:
        return None

    identifier_elem = header.find(f"{OAI_NS}identifier")
    datestamp_elem = header.find(f"{OAI_NS}datestamp")

    doc = {
        "oai_id": identifier_elem.text if identifier_elem is not None else None,
        "datestamp": datestamp_elem.text if datestamp_elem is not None else None,
        "source": "lup.lub.lu.se",
        "university": "Lunds universitet",
    }

    if metadata is not None:
        # Dublin Core fields
        doc["title"] = extract_dc_text(metadata, "title")
        doc["creators"] = extract_all_dc(metadata, "creator")
        doc["subjects"] = extract_all_dc(metadata, "subject")
        doc["description"] = extract_dc_text(metadata, "description")
        doc["publisher"] = extract_dc_text(metadata, "publisher")
        doc["contributors"] = extract_all_dc(metadata, "contributor")
        doc["date"] = extract_dc_text(metadata, "date")
        doc["types"] = extract_all_dc(metadata, "type")
        doc["formats"] = extract_all_dc(metadata, "format")
        doc["identifiers"] = extract_all_dc(metadata, "identifier")
        doc["language"] = extract_dc_text(metadata, "language")
        doc["relations"] = extract_all_dc(metadata, "relation")
        doc["rights"] = extract_all_dc(metadata, "rights")

    return doc


def harvest_all():
    """Full OAI-PMH harvest with resumptionToken"""
    documents = []
    resumption_token = None
    batch_num = 0
    start_time = datetime.now()

    print(f"[{start_time.strftime('%H:%M:%S')}] Starting LUP full harvest...")
    print(f"Endpoint: {BASE_URL}")
    print(f"Metadata prefix: {METADATA_PREFIX}")
    print(f"Rate limit: {RATE_LIMIT}s between requests")
    print("-" * 60)

    while True:
        batch_num += 1

        # Build request URL
        if resumption_token:
            url = f"{BASE_URL}?verb=ListRecords&resumptionToken={resumption_token}"
        else:
            url = f"{BASE_URL}?verb=ListRecords&metadataPrefix={METADATA_PREFIX}"

        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"\n[ERROR] Request failed: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
            continue

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"\n[ERROR] XML parse error: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
            continue

        # Check for OAI-PMH errors
        error_elem = root.find(f".//{OAI_NS}error")
        if error_elem is not None:
            error_code = error_elem.get("code")
            error_msg = error_elem.text
            print(f"\n[OAI-ERROR] {error_code}: {error_msg}")
            break

        # Parse records
        list_records = root.find(f".//{OAI_NS}ListRecords")
        if list_records is None:
            print("\n[ERROR] No ListRecords element found")
            break

        records = list_records.findall(f"{OAI_NS}record")
        batch_count = 0

        for record in records:
            doc = parse_record(record)
            if doc:
                documents.append(doc)
                batch_count += 1

        # Get resumptionToken
        token_elem = list_records.find(f"{OAI_NS}resumptionToken")

        # Progress info
        complete_list_size = None
        cursor = None

        if token_elem is not None:
            complete_list_size = token_elem.get("completeListSize")
            cursor = token_elem.get("cursor")
            resumption_token = token_elem.text
        else:
            resumption_token = None

        # Calculate stats
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = len(documents) / elapsed if elapsed > 0 else 0

        # Progress output
        progress_str = f"Batch {batch_num}: +{batch_count} docs | Total: {len(documents):,}"
        if complete_list_size:
            pct = (len(documents) / int(complete_list_size)) * 100
            progress_str += f" / {int(complete_list_size):,} ({pct:.1f}%)"
        if cursor:
            progress_str += f" | Cursor: {cursor}"
        progress_str += f" | Rate: {rate:.1f}/sec"

        print(f"\r{progress_str}", end="", flush=True)

        # Save checkpoint every 50 batches
        if batch_num % 50 == 0:
            checkpoint_file = OUTPUT_FILE.with_suffix(f".checkpoint_{batch_num}.json")
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "documents": documents,
                        "batch_num": batch_num,
                        "resumption_token": resumption_token,
                        "timestamp": datetime.now().isoformat(),
                    },
                    f,
                    ensure_ascii=False,
                )
            print(f"\n[CHECKPOINT] Saved {len(documents):,} docs to {checkpoint_file.name}")

        # Check if done
        if not resumption_token:
            print("\n\n[DONE] No more resumptionToken - harvest complete!")
            break

        # Rate limit
        time.sleep(RATE_LIMIT)

    # Final save
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    result = {
        "harvest_info": {
            "source": "Lund University Publications (LUP)",
            "endpoint": BASE_URL,
            "metadata_prefix": METADATA_PREFIX,
            "total_documents": len(documents),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "elapsed_seconds": elapsed,
            "batches_processed": batch_num,
        },
        "documents": documents,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print("HARVEST COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total documents: {len(documents):,}")
    print(f"Time elapsed: {elapsed / 60:.1f} minutes")
    print(f"Average rate: {len(documents) / elapsed:.1f} docs/sec")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.1f} MB")

    return len(documents)


if __name__ == "__main__":
    harvest_all()
