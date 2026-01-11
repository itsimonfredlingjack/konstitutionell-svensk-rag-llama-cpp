#!/usr/bin/env python3
"""
Chalmers Research OAI-PMH Harvester
URL: https://research.chalmers.se/oai-pmh/general/
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

BASE_URL = "https://research.chalmers.se/oai-pmh/general/"

# Session with proper headers
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; AcademicResearchBot/1.0; research purposes)",
        "Accept": "application/xml, text/xml, */*",
    }
)


def harvest_chalmers(max_records: int = 1000) -> list:
    """
    Harvest records from Chalmers Research using OAI-PMH protocol.

    Args:
        max_records: Maximum number of records to fetch

    Returns:
        List of parsed records
    """
    records = []
    resumption_token = None
    total_fetched = 0
    max_errors = 5
    error_count = 0

    print("[HARVESTER] Starting harvest for Chalmers")
    print(f"[HARVESTER] Target: {max_records} records")

    while total_fetched < max_records:
        # Build request URL
        if resumption_token:
            url = f"{BASE_URL}?verb=ListRecords&resumptionToken={resumption_token}"
        else:
            url = f"{BASE_URL}?verb=ListRecords&metadataPrefix=oai_dc"

        try:
            print(f"[HARVESTER] Fetching batch... (total so far: {total_fetched})")
            response = SESSION.get(url, timeout=60)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Check for errors
            error = root.find(".//oai:error", NAMESPACES)
            if error is not None:
                error_code = error.get("code")
                error_msg = error.text
                print(f"[ERROR] OAI-PMH Error: {error_code} - {error_msg}")
                break

            # Extract records
            record_elements = root.findall(".//oai:record", NAMESPACES)

            if not record_elements:
                print("[HARVESTER] No more records found")
                break

            batch_count = 0
            for record_elem in record_elements:
                if total_fetched >= max_records:
                    break

                record = parse_record(record_elem)
                if record:
                    records.append(record)
                    total_fetched += 1
                    batch_count += 1

            print(f"[HARVESTER] Batch: +{batch_count} records | Total: {total_fetched}")

            # Check for resumption token
            token_elem = root.find(".//oai:resumptionToken", NAMESPACES)
            if token_elem is not None and token_elem.text:
                resumption_token = token_elem.text
                # Get list size if available
                list_size = token_elem.get("completeListSize")
                if list_size:
                    print(f"[HARVESTER] Complete list size: {list_size}")
            else:
                print("[HARVESTER] No more pages (no resumption token)")
                break

            # Rate limit: 1 request per second
            time.sleep(1)
            error_count = 0  # Reset error count on success

        except requests.exceptions.RequestException as e:
            error_count += 1
            print(f"[ERROR] Request failed ({error_count}/{max_errors}): {e}")
            if error_count >= max_errors:
                print("[ERROR] Max errors reached, stopping")
                break
            time.sleep(5)  # Wait before retry
            continue
        except ET.ParseError as e:
            print(f"[ERROR] XML parse error: {e}")
            break

    print(f"[HARVESTER] Complete: {len(records)} records harvested for Chalmers")
    return records


def parse_record(record_elem) -> dict:
    """Parse a single OAI-PMH record into a dictionary."""
    try:
        # Get header info
        header = record_elem.find("oai:header", NAMESPACES)
        if header is None:
            return None

        # Check if deleted
        status = header.get("status")
        if status == "deleted":
            return None

        identifier = header.find("oai:identifier", NAMESPACES)
        datestamp = header.find("oai:datestamp", NAMESPACES)

        record = {
            "oai_identifier": identifier.text if identifier is not None else None,
            "datestamp": datestamp.text if datestamp is not None else None,
            "harvested_at": datetime.now().isoformat(),
        }

        # Get Dublin Core metadata
        metadata = record_elem.find(".//oai_dc:dc", NAMESPACES)
        if metadata is not None:
            # Extract DC fields
            dc_fields = [
                "title",
                "creator",
                "subject",
                "description",
                "publisher",
                "contributor",
                "date",
                "type",
                "format",
                "identifier",
                "source",
                "language",
                "relation",
                "coverage",
                "rights",
            ]

            for field in dc_fields:
                elements = metadata.findall(f"dc:{field}", NAMESPACES)
                if elements:
                    values = [e.text.strip() for e in elements if e.text and e.text.strip()]
                    if len(values) == 1:
                        record[field] = values[0]
                    elif len(values) > 1:
                        record[field] = values

        return record

    except Exception as e:
        print(f"[WARNING] Failed to parse record: {e}")
        return None


def save_records(records: list, output_path: str):
    """Save records to JSON file."""
    output = {
        "source": "research.chalmers.se",
        "institution": "Chalmers tekniska hogskola",
        "harvested_at": datetime.now().isoformat(),
        "record_count": len(records),
        "records": records,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[STORAGE] Saved {len(records)} records to {output_path}")


def main():
    output_dir = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data"
    max_records = 1000  # Test with 1000 records

    print(f"\n{'=' * 60}")
    print("HARVESTING: Chalmers tekniska hogskola")
    print(f"{'=' * 60}")

    records = harvest_chalmers(max_records)

    output_path = f"{output_dir}/diva_batch2_chalmers.json"
    save_records(records, output_path)

    # Print summary
    print(f"\n{'=' * 60}")
    print("HARVEST SUMMARY - CHALMERS")
    print(f"{'=' * 60}")
    print(f"Chalmers tekniska hogskola            | {len(records):6} docs")
    print(f"{'=' * 60}")
    print(f"Output: {output_path}")

    return {"chalmers": {"records": len(records), "file": output_path}}


if __name__ == "__main__":
    main()
