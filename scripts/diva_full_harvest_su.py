#!/usr/bin/env python3
"""
FULL DiVA OAI-PMH Harvester - Stockholm University
===================================================
Target: ~31,890 documents
Endpoint: https://su.diva-portal.org/dice/oai
Metadata: oai_dc (Dublin Core - swepub_mods blocked)

Rate limit: 1 request/second
Uses resumptionToken for pagination
"""

import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OAI_ENDPOINT = "https://su.diva-portal.org/dice/oai"
METADATA_PREFIX = "oai_dc"  # swepub_mods is blocked, using Dublin Core
OUTPUT_FILE = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_su.json")
CHECKPOINT_FILE = Path(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_su_checkpoint.json"
)
RATE_LIMIT_SECONDS = 1.0

# HTTP headers - proper user agent to avoid blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Academic Research Bot; +https://github.com/ai-server)",
    "Accept": "application/xml, text/xml, */*",
}

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


def extract_text(element, xpath, namespaces=NAMESPACES):
    """Extract text from element using xpath"""
    if element is None:
        return None
    found = element.find(xpath, namespaces)
    if found is not None and found.text:
        return found.text.strip()
    return None


def extract_all_texts(element, xpath, namespaces=NAMESPACES):
    """Extract all texts from elements matching xpath"""
    if element is None:
        return []
    found = element.findall(xpath, namespaces)
    return [e.text.strip() for e in found if e is not None and e.text]


def parse_dc_record(record_element):
    """Parse a Dublin Core record into structured data"""
    header = record_element.find("oai:header", NAMESPACES)
    metadata = record_element.find("oai:metadata", NAMESPACES)

    if header is None:
        return None

    # Check if deleted
    status = header.get("status")
    if status == "deleted":
        return None

    doc = {
        "identifier": extract_text(header, "oai:identifier"),
        "datestamp": extract_text(header, "oai:datestamp"),
        "setSpec": extract_all_texts(header, "oai:setSpec"),
    }

    if metadata is not None:
        # Find Dublin Core element
        dc = metadata.find(".//oai_dc:dc", NAMESPACES)
        if dc is not None:
            # Title(s)
            titles = extract_all_texts(dc, "dc:title")
            doc["title"] = titles[0] if titles else None
            doc["alternativeTitles"] = titles[1:] if len(titles) > 1 else []

            # Creators/Authors
            doc["creators"] = extract_all_texts(dc, "dc:creator")

            # Subjects
            doc["subjects"] = extract_all_texts(dc, "dc:subject")

            # Description/Abstract
            descriptions = extract_all_texts(dc, "dc:description")
            doc["description"] = descriptions[0] if descriptions else None
            doc["additionalDescriptions"] = descriptions[1:] if len(descriptions) > 1 else []

            # Publisher
            doc["publisher"] = extract_text(dc, "dc:publisher")

            # Date
            doc["date"] = extract_text(dc, "dc:date")

            # Type
            doc["types"] = extract_all_texts(dc, "dc:type")

            # Format
            doc["format"] = extract_text(dc, "dc:format")

            # Identifier (URL, URN, DOI, etc)
            doc["identifiers"] = extract_all_texts(dc, "dc:identifier")

            # Language
            doc["language"] = extract_text(dc, "dc:language")

            # Rights
            doc["rights"] = extract_text(dc, "dc:rights")

            # Contributor
            doc["contributors"] = extract_all_texts(dc, "dc:contributor")

            # Source
            doc["source"] = extract_text(dc, "dc:source")

            # Relation
            doc["relations"] = extract_all_texts(dc, "dc:relation")

            # Coverage
            doc["coverage"] = extract_text(dc, "dc:coverage")

    return doc


def fetch_records(resumption_token=None):
    """Fetch a batch of records from OAI-PMH endpoint"""
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX}

    try:
        response = requests.get(OAI_ENDPOINT, params=params, headers=HEADERS, timeout=120)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"[ERROR] Request failed: {e}")
        return None


def parse_response(xml_text):
    """Parse OAI-PMH response and extract records"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[ERROR] XML parse error: {e}")
        return [], None, None

    records = []
    list_records = root.find(".//oai:ListRecords", NAMESPACES)

    if list_records is None:
        # Check for error
        error = root.find(".//oai:error", NAMESPACES)
        if error is not None:
            error_code = error.get("code", "unknown")
            error_msg = error.text or ""
            print(f"[ERROR] OAI-PMH error: {error_code} - {error_msg}")
        return [], None, None

    # Parse records
    for record in list_records.findall("oai:record", NAMESPACES):
        parsed = parse_dc_record(record)
        if parsed:
            records.append(parsed)

    # Get resumption token
    token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
    resumption_token = None
    complete_list_size = None

    if token_elem is not None:
        resumption_token = token_elem.text.strip() if token_elem.text else None
        complete_list_size = token_elem.get("completeListSize")

    return records, resumption_token, complete_list_size


def save_checkpoint(documents, resumption_token, batch_num):
    """Save checkpoint for resume capability"""
    checkpoint = {
        "documents_count": len(documents),
        "resumption_token": resumption_token,
        "batch_num": batch_num,
        "timestamp": datetime.now().isoformat(),
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def load_checkpoint():
    """Load checkpoint if exists"""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    print("=" * 60)
    print("DiVA FULL HARVEST - Stockholm University")
    print("=" * 60)
    print(f"Endpoint: {OAI_ENDPOINT}")
    print(f"Metadata: {METADATA_PREFIX}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rate limit: {RATE_LIMIT_SECONDS}s between requests")
    print("=" * 60)

    all_documents = []
    resumption_token = None
    batch_num = 0
    total_expected = None
    errors = 0
    max_errors = 10
    deleted_count = 0

    # Check for checkpoint
    checkpoint = load_checkpoint()
    if checkpoint and checkpoint.get("resumption_token"):
        print(f"\n[RESUME] Found checkpoint from {checkpoint['timestamp']}")
        print(f"[RESUME] Resuming from batch {checkpoint['batch_num']}")
        resumption_token = checkpoint["resumption_token"]
        batch_num = checkpoint["batch_num"]

        # Load existing documents if checkpoint file exists
        if OUTPUT_FILE.exists():
            print("[RESUME] Loading existing documents...")
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, dict) and "documents" in existing:
                    all_documents = existing["documents"]
                elif isinstance(existing, list):
                    all_documents = existing
            print(f"[RESUME] Loaded {len(all_documents)} existing documents")

    start_time = datetime.now()

    while True:
        batch_num += 1

        # Progress indicator
        progress = f"[Batch {batch_num}]"
        if total_expected:
            pct = (len(all_documents) / int(total_expected)) * 100
            progress += f" {len(all_documents):,}/{total_expected} ({pct:.1f}%)"
        else:
            progress += f" {len(all_documents):,} documents"

        print(f"\n{progress}")
        print("  Fetching records...")

        # Fetch batch
        xml_response = fetch_records(resumption_token)

        if xml_response is None:
            errors += 1
            if errors >= max_errors:
                print(f"[FATAL] Too many errors ({errors}), stopping")
                break
            print(f"[WARN] Error {errors}/{max_errors}, retrying in 5s...")
            time.sleep(5)
            continue

        # Parse response
        records, new_token, complete_size = parse_response(xml_response)

        if complete_size and total_expected is None:
            total_expected = complete_size
            print(f"  Total expected: {total_expected} documents")

        if records:
            all_documents.extend(records)
            print(f"  Parsed {len(records)} records (total: {len(all_documents):,})")
            errors = 0  # Reset error counter on success
        else:
            print("  No records in this batch")

        # Save checkpoint every 10 batches
        if batch_num % 10 == 0:
            save_checkpoint(all_documents, new_token, batch_num)
            # Also save documents periodically
            interim_data = {
                "source": "DiVA OAI-PMH",
                "institution": "Stockholm University",
                "harvest_date": datetime.now().isoformat(),
                "status": "in_progress",
                "documents_count": len(all_documents),
                "documents": all_documents,
            }
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(interim_data, f, ensure_ascii=False)
            print(f"  [CHECKPOINT] Saved {len(all_documents):,} documents")

        # Check if done
        if not new_token:
            print("\n[COMPLETE] No more resumption token - harvest finished!")
            break

        resumption_token = new_token

        # Rate limiting
        time.sleep(RATE_LIMIT_SECONDS)

    # Final save
    end_time = datetime.now()
    duration = end_time - start_time

    final_data = {
        "source": "DiVA OAI-PMH",
        "institution": "Stockholm University",
        "endpoint": OAI_ENDPOINT,
        "metadata_prefix": METADATA_PREFIX,
        "harvest_start": start_time.isoformat(),
        "harvest_end": end_time.isoformat(),
        "duration_seconds": duration.total_seconds(),
        "total_batches": batch_num,
        "documents_count": len(all_documents),
        "documents": all_documents,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False)

    # Clean up checkpoint
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    print("\n" + "=" * 60)
    print("HARVEST COMPLETE")
    print("=" * 60)
    print(f"Total documents: {len(all_documents):,}")
    print(f"Duration: {duration}")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size / (1024*1024):.2f} MB")
    print("=" * 60)

    return len(all_documents)


if __name__ == "__main__":
    try:
        count = main()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Saving current progress...")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
