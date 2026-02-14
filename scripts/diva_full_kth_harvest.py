#!/usr/bin/env python3
"""
KTH DiVA Full Harvest - OAI-PMH
================================
Endpoint: https://kth.diva-portal.org/dice/oai
MetadataPrefix: swepub_mods
Target: ~58,678 documents

Uses resumptionToken for pagination.
Rate limit: 1 request/second
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration
BASE_URL = "https://kth.diva-portal.org/dice/oai"
METADATA_PREFIX = "swepub_mods"
OUTPUT_FILE = Path(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_kth.json"
)
STATE_FILE = Path(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_kth_state.json"
)
RATE_LIMIT = 1.0  # seconds between requests

# Headers to avoid 403 Forbidden
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DiVA-Harvester/1.0; Academic Research)"}

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "swepub": "http://swepub.kb.se/mods/swepub",
}


def parse_record(record_elem):
    """Extract metadata from a single OAI-PMH record."""
    try:
        header = record_elem.find("oai:header", NAMESPACES)
        if header is None:
            return None

        # Check if deleted
        status = header.get("status", "")
        if status == "deleted":
            return None

        identifier = header.findtext("oai:identifier", "", NAMESPACES)
        datestamp = header.findtext("oai:datestamp", "", NAMESPACES)

        # Get metadata
        metadata = record_elem.find("oai:metadata", NAMESPACES)
        if metadata is None:
            return {
                "id": identifier,
                "datestamp": datestamp,
                "deleted": False,
                "title": "",
                "authors": [],
                "year": "",
                "type": "",
                "abstract": "",
            }

        # Find MODS record
        mods = metadata.find(".//mods:mods", NAMESPACES)
        if mods is None:
            # Try without namespace
            mods = metadata.find(".//{http://www.loc.gov/mods/v3}mods")

        title = ""
        authors = []
        year = ""
        doc_type = ""
        abstract = ""
        subjects = []
        language = ""

        if mods is not None:
            # Title
            title_elem = mods.find(".//mods:titleInfo/mods:title", NAMESPACES)
            if title_elem is None:
                title_elem = mods.find(
                    ".//{http://www.loc.gov/mods/v3}titleInfo/{http://www.loc.gov/mods/v3}title"
                )
            if title_elem is not None:
                title = title_elem.text or ""

            # Authors
            for name in mods.findall(".//{http://www.loc.gov/mods/v3}name"):
                name_parts = []
                for part in name.findall(".//{http://www.loc.gov/mods/v3}namePart"):
                    if part.text:
                        name_parts.append(part.text)
                if name_parts:
                    authors.append(" ".join(name_parts))

            # Year
            date_elem = mods.find(".//{http://www.loc.gov/mods/v3}dateIssued")
            if date_elem is not None and date_elem.text:
                year = date_elem.text[:4] if len(date_elem.text) >= 4 else date_elem.text

            # Type
            genre = mods.find(".//{http://www.loc.gov/mods/v3}genre")
            if genre is not None:
                doc_type = genre.text or ""

            # Abstract
            abstract_elem = mods.find(".//{http://www.loc.gov/mods/v3}abstract")
            if abstract_elem is not None:
                abstract = abstract_elem.text or ""

            # Subjects
            for subject in mods.findall(".//{http://www.loc.gov/mods/v3}subject"):
                for topic in subject.findall(".//{http://www.loc.gov/mods/v3}topic"):
                    if topic.text:
                        subjects.append(topic.text)

            # Language
            lang_elem = mods.find(".//{http://www.loc.gov/mods/v3}languageTerm")
            if lang_elem is not None:
                language = lang_elem.text or ""

        return {
            "id": identifier,
            "datestamp": datestamp,
            "title": title,
            "authors": authors[:10],  # Limit authors
            "year": year,
            "type": doc_type,
            "abstract": abstract[:2000] if abstract else "",  # Limit abstract
            "subjects": subjects[:20],  # Limit subjects
            "language": language,
        }
    except Exception as e:
        return {"id": "error", "error": str(e)}


def fetch_records(resumption_token=None):
    """Fetch a batch of records from OAI-PMH."""
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX}

    response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def parse_response(xml_text):
    """Parse OAI-PMH response, extract records and resumptionToken."""
    root = ET.fromstring(xml_text)

    # Check for errors
    error = root.find(".//oai:error", NAMESPACES)
    if error is not None:
        error_code = error.get("code", "unknown")
        error_msg = error.text or ""
        raise Exception(f"OAI-PMH Error: {error_code} - {error_msg}")

    # Get records
    records = []
    list_records = root.find(".//oai:ListRecords", NAMESPACES)
    if list_records is not None:
        for record in list_records.findall("oai:record", NAMESPACES):
            parsed = parse_record(record)
            if parsed:
                records.append(parsed)

    # Get resumptionToken
    token_elem = root.find(".//oai:resumptionToken", NAMESPACES)
    resumption_token = None
    complete_size = None
    cursor = None

    if token_elem is not None:
        resumption_token = token_elem.text
        if token_elem.get("completeListSize"):
            complete_size = int(token_elem.get("completeListSize"))
        if token_elem.get("cursor"):
            cursor = int(token_elem.get("cursor"))

    return records, resumption_token, complete_size, cursor


def load_state():
    """Load harvesting state if exists."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def save_state(token, total_harvested, complete_size):
    """Save current harvesting state."""
    state = {
        "resumption_token": token,
        "total_harvested": total_harvested,
        "complete_size": complete_size,
        "timestamp": datetime.now().isoformat(),
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    print("=" * 60)
    print("KTH DiVA FULL HARVEST")
    print("=" * 60)
    print(f"Endpoint: {BASE_URL}")
    print(f"MetadataPrefix: {METADATA_PREFIX}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rate limit: {RATE_LIMIT}s between requests")
    print("=" * 60)

    # Check for resume state
    state = load_state()
    all_records = []
    resumption_token = None

    if state and state.get("resumption_token"):
        print("\nRESUMING from previous harvest!")
        print(f"Previously harvested: {state['total_harvested']} records")
        resumption_token = state["resumption_token"]

        # Load existing records
        if OUTPUT_FILE.exists():
            with open(OUTPUT_FILE) as f:
                data = json.load(f)
                all_records = data.get("records", [])
            print(f"Loaded {len(all_records)} existing records")

    batch_num = len(all_records) // 100 + 1
    start_time = datetime.now()
    complete_size = state.get("complete_size") if state else None
    errors = 0
    max_errors = 10

    try:
        while True:
            batch_start = time.time()

            try:
                xml_text = fetch_records(resumption_token)
                records, resumption_token, size, _cursor = parse_response(xml_text)

                if size and not complete_size:
                    complete_size = size

                all_records.extend(records)
                errors = 0  # Reset error counter on success

                # Progress report
                progress = (len(all_records) / complete_size * 100) if complete_size else 0
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = len(all_records) / elapsed if elapsed > 0 else 0

                print(
                    f"Batch {batch_num}: +{len(records)} records | "
                    f"Total: {len(all_records):,}/{complete_size or '?':,} ({progress:.1f}%) | "
                    f"Rate: {rate:.1f} docs/s"
                )

                # Save progress every 10 batches
                if batch_num % 10 == 0:
                    save_state(resumption_token, len(all_records), complete_size)
                    # Write partial results
                    output_data = {
                        "source": "KTH DiVA",
                        "endpoint": BASE_URL,
                        "metadata_prefix": METADATA_PREFIX,
                        "harvest_started": start_time.isoformat(),
                        "last_updated": datetime.now().isoformat(),
                        "complete_size": complete_size,
                        "total_harvested": len(all_records),
                        "status": "in_progress",
                        "records": all_records,
                    }
                    with open(OUTPUT_FILE, "w") as f:
                        json.dump(output_data, f, ensure_ascii=False)
                    print(f"  [Checkpoint saved: {len(all_records):,} records]")

                batch_num += 1

                # Check if done
                if not resumption_token:
                    print("\n[No more resumptionToken - harvest complete]")
                    break

                # Rate limiting
                elapsed_batch = time.time() - batch_start
                if elapsed_batch < RATE_LIMIT:
                    time.sleep(RATE_LIMIT - elapsed_batch)

            except requests.exceptions.RequestException as e:
                errors += 1
                print(f"  [Network error ({errors}/{max_errors}): {e}]")
                if errors >= max_errors:
                    print("[Too many errors, stopping]")
                    break
                time.sleep(5 * errors)  # Exponential backoff
                continue
            except Exception as e:
                errors += 1
                print(f"  [Parse error ({errors}/{max_errors}): {e}]")
                if errors >= max_errors:
                    print("[Too many errors, stopping]")
                    break
                time.sleep(2)
                continue

    except KeyboardInterrupt:
        print("\n[Interrupted by user]")

    # Final save
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    output_data = {
        "source": "KTH DiVA",
        "endpoint": BASE_URL,
        "metadata_prefix": METADATA_PREFIX,
        "harvest_started": start_time.isoformat(),
        "harvest_completed": end_time.isoformat(),
        "duration_seconds": duration,
        "complete_size": complete_size,
        "total_harvested": len(all_records),
        "status": "completed" if not resumption_token else "interrupted",
        "records": all_records,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_data, f, ensure_ascii=False)

    # Clean up state file if completed
    if not resumption_token and STATE_FILE.exists():
        STATE_FILE.unlink()

    print("\n" + "=" * 60)
    print("HARVEST COMPLETE")
    print("=" * 60)
    print(f"Total records: {len(all_records):,}")
    print(f"Duration: {duration / 60:.1f} minutes")
    print(f"Rate: {len(all_records) / duration:.1f} docs/second")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
