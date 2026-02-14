#!/usr/bin/env python3
"""
Full OAI-PMH Harvest of Uppsala University DiVA Portal
========================================================
Target: ~128,767 documents
Endpoint: http://uu.diva-portal.org/dice/oai
MetadataPrefix: swepub_mods
Rate limit: 1 request/second
"""

import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# Configuration
OAI_ENDPOINT = "https://uu.diva-portal.org/dice/oai"
METADATA_PREFIX = "swepub_mods"
OUTPUT_FILE = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_uu.json")
CHECKPOINT_FILE = Path(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_uu_checkpoint.json"
)
RATE_LIMIT_SECONDS = 1.0

# Headers to mimic browser/curl
HEADERS = {
    "User-Agent": "DiVA-Harvester/1.0 (Academic Research; OAI-PMH)",
    "Accept": "application/xml, text/xml, */*",
}

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "swepub": "http://swepub.kb.se/swepub_mods",
}


def parse_mods_record(record_elem):
    """Extract key fields from a MODS record."""
    try:
        header = record_elem.find("oai:header", NAMESPACES)
        metadata = record_elem.find("oai:metadata", NAMESPACES)

        if header is None:
            return None

        # Check if deleted
        status = header.get("status", "")
        if status == "deleted":
            return None

        identifier = header.find("oai:identifier", NAMESPACES)
        datestamp = header.find("oai:datestamp", NAMESPACES)

        record_data = {
            "oai_id": identifier.text if identifier is not None else None,
            "datestamp": datestamp.text if datestamp is not None else None,
            "source": "Uppsala University DiVA",
            "harvested_at": datetime.now().isoformat(),
        }

        if metadata is not None:
            # Find MODS element
            mods = metadata.find(".//mods:mods", NAMESPACES)
            if mods is not None:
                # Title
                title_info = mods.find(".//mods:titleInfo/mods:title", NAMESPACES)
                if title_info is not None and title_info.text:
                    record_data["title"] = title_info.text.strip()

                # Authors
                authors = []
                for name in mods.findall('.//mods:name[@type="personal"]', NAMESPACES):
                    name_parts = name.findall("mods:namePart", NAMESPACES)
                    full_name = " ".join([p.text for p in name_parts if p.text])
                    if full_name:
                        authors.append(full_name)
                if authors:
                    record_data["authors"] = authors

                # Abstract
                abstract = mods.find(".//mods:abstract", NAMESPACES)
                if abstract is not None and abstract.text:
                    record_data["abstract"] = abstract.text.strip()[:2000]  # Limit size

                # Publication year
                date_issued = mods.find(".//mods:originInfo/mods:dateIssued", NAMESPACES)
                if date_issued is not None and date_issued.text:
                    record_data["year"] = date_issued.text[:4]

                # Subject keywords
                subjects = []
                for subject in mods.findall(".//mods:subject/mods:topic", NAMESPACES):
                    if subject.text:
                        subjects.append(subject.text.strip())
                if subjects:
                    record_data["subjects"] = subjects

                # Genre/type
                genre = mods.find(".//mods:genre", NAMESPACES)
                if genre is not None and genre.text:
                    record_data["type"] = genre.text.strip()

                # Language
                lang = mods.find(".//mods:language/mods:languageTerm", NAMESPACES)
                if lang is not None and lang.text:
                    record_data["language"] = lang.text.strip()

                # Identifier (DOI, URN, etc.)
                for ident in mods.findall(".//mods:identifier", NAMESPACES):
                    id_type = ident.get("type", "")
                    if id_type and ident.text:
                        record_data[f"id_{id_type}"] = ident.text.strip()

        return record_data

    except Exception as e:
        return {"error": str(e), "raw": "parse_error"}


def load_checkpoint():
    """Load checkpoint if exists."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"records": [], "resumption_token": None, "total_fetched": 0}


def save_checkpoint(records, token, total):
    """Save checkpoint for resume capability."""
    checkpoint = {
        "records_count": len(records),
        "resumption_token": token,
        "total_fetched": total,
        "last_save": datetime.now().isoformat(),
    }
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f)


def harvest_oai():
    """Main harvest function with resumption token support."""

    print("=" * 60)
    print("FULL HARVEST: Uppsala University DiVA Portal")
    print("=" * 60)
    print(f"Endpoint: {OAI_ENDPOINT}")
    print(f"Metadata: {METADATA_PREFIX}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 60)

    # Check for existing partial harvest
    all_records = []
    resumption_token = None

    if OUTPUT_FILE.exists():
        print("\nFound existing output file, loading...")
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)
            if "records" in existing:
                all_records = existing["records"]
                resumption_token = existing.get("last_resumption_token")
                print(f"Loaded {len(all_records)} existing records")
                if resumption_token:
                    print(f"Resuming from token: {resumption_token[:50]}...")

    batch_num = len(all_records) // 100 + 1
    total_fetched = len(all_records)
    consecutive_errors = 0
    start_time = time.time()

    while True:
        try:
            # Build request
            if resumption_token:
                params = {"verb": "ListRecords", "resumptionToken": resumption_token}
            else:
                params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX}

            # Make request
            response = requests.get(OAI_ENDPOINT, params=params, headers=HEADERS, timeout=60)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Check for errors
            error = root.find(".//oai:error", NAMESPACES)
            if error is not None:
                error_code = error.get("code", "unknown")
                error_msg = error.text or "No message"
                print(f"\nOAI Error: {error_code} - {error_msg}")
                if error_code == "noRecordsMatch":
                    break
                consecutive_errors += 1
                if consecutive_errors > 5:
                    print("Too many consecutive errors, stopping.")
                    break
                time.sleep(5)
                continue

            # Find ListRecords element
            list_records = root.find(".//oai:ListRecords", NAMESPACES)
            if list_records is None:
                print("No ListRecords found in response")
                break

            # Parse records
            records = list_records.findall("oai:record", NAMESPACES)
            batch_count = 0

            for record in records:
                parsed = parse_mods_record(record)
                if parsed and "oai_id" in parsed:
                    all_records.append(parsed)
                    batch_count += 1
                    total_fetched += 1

            # Get resumption token
            token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
            if token_elem is not None and token_elem.text:
                resumption_token = token_elem.text.strip()
                complete_size = token_elem.get("completeListSize", "unknown")
                # Cursor is informational only.

                # Progress report
                elapsed = time.time() - start_time
                rate = total_fetched / elapsed if elapsed > 0 else 0

                print(
                    f"Batch {batch_num}: +{batch_count} records | "
                    f"Total: {total_fetched:,} / {complete_size} | "
                    f"Rate: {rate:.1f} docs/sec"
                )
            else:
                # No more records
                print(f"\nFinal batch: +{batch_count} records")
                resumption_token = None

            # Reset error counter on success
            consecutive_errors = 0
            batch_num += 1

            # Save checkpoint every 50 batches (~5000 records)
            if batch_num % 50 == 0:
                print(f"  [Checkpoint saved: {total_fetched:,} records]")
                output_data = {
                    "source": "Uppsala University DiVA",
                    "endpoint": OAI_ENDPOINT,
                    "metadata_prefix": METADATA_PREFIX,
                    "harvest_started": start_time,
                    "last_update": datetime.now().isoformat(),
                    "total_records": len(all_records),
                    "last_resumption_token": resumption_token,
                    "records": all_records,
                }
                with open(OUTPUT_FILE, "w") as f:
                    json.dump(output_data, f, ensure_ascii=False)

            # Check if done
            if not resumption_token:
                break

            # Rate limit
            time.sleep(RATE_LIMIT_SECONDS)

        except requests.exceptions.Timeout:
            print("  Timeout, retrying in 10 seconds...")
            time.sleep(10)
            consecutive_errors += 1

        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}")
            time.sleep(10)
            consecutive_errors += 1

        except ET.ParseError as e:
            print(f"  XML parse error: {e}")
            time.sleep(5)
            consecutive_errors += 1

        if consecutive_errors > 10:
            print("\nToo many errors, saving and exiting.")
            break

    # Final save
    elapsed = time.time() - start_time

    output_data = {
        "source": "Uppsala University DiVA",
        "endpoint": OAI_ENDPOINT,
        "metadata_prefix": METADATA_PREFIX,
        "harvest_started": datetime.fromtimestamp(start_time).isoformat(),
        "harvest_completed": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
        "total_records": len(all_records),
        "records": all_records,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=None)

    # Report
    print("\n" + "=" * 60)
    print("HARVEST COMPLETE")
    print("=" * 60)
    print(f"Total documents: {len(all_records):,}")
    print(f"Elapsed time: {elapsed / 60:.1f} minutes")
    print(f"Rate: {len(all_records) / elapsed:.1f} docs/sec")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.1f} MB")
    print("=" * 60)

    return len(all_records)


if __name__ == "__main__":
    try:
        count = harvest_oai()
        print(f"\nSUCCESS: Harvested {count:,} documents from Uppsala University DiVA")
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        sys.exit(1)
