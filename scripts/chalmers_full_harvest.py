#!/usr/bin/env python3
"""
FULL CHALMERS HARVEST via OAI-PMH
Target: ~80,000 documents
Rate limit: 1 req/sec
"""

import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OAI_ENDPOINT = "https://research.chalmers.se/oai-pmh/general/"
METADATA_PREFIX = "oai_dc"
OUTPUT_FILE = Path(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_chalmers.json"
)
RATE_LIMIT = 1.0  # seconds between requests

# XML namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


def parse_record(record_elem):
    """Extract metadata from a single OAI record."""
    try:
        header = record_elem.find("oai:header", NAMESPACES)
        metadata = record_elem.find("oai:metadata", NAMESPACES)

        if header is None:
            return None

        # Check if deleted
        status = header.get("status", "")
        if status == "deleted":
            return None

        identifier = header.findtext("oai:identifier", "", NAMESPACES)
        datestamp = header.findtext("oai:datestamp", "", NAMESPACES)

        record = {
            "identifier": identifier,
            "datestamp": datestamp,
            "source": "chalmers",
            "titles": [],
            "creators": [],
            "subjects": [],
            "descriptions": [],
            "dates": [],
            "types": [],
            "identifiers": [],
            "languages": [],
            "publishers": [],
            "rights": [],
        }

        if metadata is not None:
            dc = metadata.find("oai_dc:dc", NAMESPACES)
            if dc is not None:
                # Extract all DC fields
                for title in dc.findall("dc:title", NAMESPACES):
                    if title.text:
                        record["titles"].append(title.text.strip())

                for creator in dc.findall("dc:creator", NAMESPACES):
                    if creator.text:
                        record["creators"].append(creator.text.strip())

                for subject in dc.findall("dc:subject", NAMESPACES):
                    if subject.text:
                        record["subjects"].append(subject.text.strip())

                for desc in dc.findall("dc:description", NAMESPACES):
                    if desc.text:
                        record["descriptions"].append(desc.text.strip())

                for date in dc.findall("dc:date", NAMESPACES):
                    if date.text:
                        record["dates"].append(date.text.strip())

                for dtype in dc.findall("dc:type", NAMESPACES):
                    if dtype.text:
                        record["types"].append(dtype.text.strip())

                for ident in dc.findall("dc:identifier", NAMESPACES):
                    if ident.text:
                        record["identifiers"].append(ident.text.strip())

                for lang in dc.findall("dc:language", NAMESPACES):
                    if lang.text:
                        record["languages"].append(lang.text.strip())

                for pub in dc.findall("dc:publisher", NAMESPACES):
                    if pub.text:
                        record["publishers"].append(pub.text.strip())

                for right in dc.findall("dc:rights", NAMESPACES):
                    if right.text:
                        record["rights"].append(right.text.strip())

        return record

    except Exception as e:
        print(f"[ERROR] Failed to parse record: {e}")
        return None


def fetch_batch(resumption_token=None):
    """Fetch a batch of records from OAI-PMH."""
    if resumption_token:
        url = f"{OAI_ENDPOINT}?verb=ListRecords&resumptionToken={resumption_token}"
    else:
        url = f"{OAI_ENDPOINT}?verb=ListRecords&metadataPrefix={METADATA_PREFIX}"

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def parse_response(xml_text):
    """Parse OAI-PMH response, extract records and resumption token."""
    root = ET.fromstring(xml_text)

    # Check for errors
    error = root.find(".//oai:error", NAMESPACES)
    if error is not None:
        error_code = error.get("code", "unknown")
        error_msg = error.text or "No message"
        raise Exception(f"OAI-PMH Error [{error_code}]: {error_msg}")

    records = []
    list_records = root.find(".//oai:ListRecords", NAMESPACES)

    if list_records is not None:
        for record_elem in list_records.findall("oai:record", NAMESPACES):
            record = parse_record(record_elem)
            if record:
                records.append(record)

        # Get resumption token
        token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
        if token_elem is not None and token_elem.text:
            token = token_elem.text.strip()
            # Get complete list size if available
            complete_size = token_elem.get("completeListSize", "unknown")
            cursor = token_elem.get("cursor", "0")
            return records, token, complete_size, cursor
        else:
            return records, None, None, None

    return records, None, None, None


def main():
    print("=" * 60)
    print("CHALMERS FULL HARVEST - OAI-PMH")
    print("=" * 60)
    print(f"Endpoint: {OAI_ENDPOINT}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rate limit: {RATE_LIMIT}s between requests")
    print("=" * 60)

    all_records = []
    resumption_token = None
    batch_num = 0
    total_size = "unknown"
    start_time = datetime.now()
    errors = 0
    max_consecutive_errors = 5
    consecutive_errors = 0

    try:
        while True:
            batch_num += 1

            try:
                print(f"\n[BATCH {batch_num}] Fetching... ", end="", flush=True)
                xml_text = fetch_batch(resumption_token)
                records, new_token, complete_size, cursor = parse_response(xml_text)

                consecutive_errors = 0  # Reset on success

                if complete_size and complete_size != "unknown":
                    total_size = complete_size

                all_records.extend(records)

                elapsed = (datetime.now() - start_time).total_seconds()
                rate = len(all_records) / elapsed if elapsed > 0 else 0

                print(
                    f"Got {len(records)} records. Total: {len(all_records)}/{total_size} ({rate:.1f} docs/sec)"
                )

                if new_token:
                    resumption_token = new_token
                    time.sleep(RATE_LIMIT)
                else:
                    print("\n[COMPLETE] No more resumption token - harvest finished!")
                    break

            except requests.exceptions.RequestException as e:
                errors += 1
                consecutive_errors += 1
                print(f"\n[NETWORK ERROR] {e}")

                if consecutive_errors >= max_consecutive_errors:
                    print(f"[ABORT] {max_consecutive_errors} consecutive errors - stopping")
                    break

                print(
                    f"Waiting 10s before retry... ({consecutive_errors}/{max_consecutive_errors})"
                )
                time.sleep(10)
                continue

            except Exception as e:
                errors += 1
                consecutive_errors += 1
                print(f"\n[ERROR] {e}")

                if consecutive_errors >= max_consecutive_errors:
                    print(f"[ABORT] {max_consecutive_errors} consecutive errors - stopping")
                    break

                print(f"Waiting 5s before retry... ({consecutive_errors}/{max_consecutive_errors})")
                time.sleep(5)
                continue

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Saving collected records...")

    # Calculate stats
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Prepare output
    output = {
        "harvest_info": {
            "source": "Chalmers Research",
            "endpoint": OAI_ENDPOINT,
            "metadata_prefix": METADATA_PREFIX,
            "harvest_start": start_time.isoformat(),
            "harvest_end": end_time.isoformat(),
            "duration_seconds": duration,
            "total_batches": batch_num,
            "total_records": len(all_records),
            "reported_complete_size": total_size,
            "errors_encountered": errors,
        },
        "records": all_records,
    }

    # Save
    print(f"\n[SAVING] Writing {len(all_records)} records to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    file_size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)

    print("\n" + "=" * 60)
    print("HARVEST COMPLETE")
    print("=" * 60)
    print(f"Total records: {len(all_records)}")
    print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print(f"Average rate: {len(all_records)/duration:.2f} records/second")
    print(f"File size: {file_size_mb:.2f} MB")
    print(f"Errors: {errors}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 60)

    return len(all_records)


if __name__ == "__main__":
    count = main()
    sys.exit(0 if count > 0 else 1)
