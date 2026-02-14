#!/usr/bin/env python3
"""
DiVA OAI-PMH Harvester for Swedish Universities
Batch 2: Technical Universities

Correct URL: http://www.diva-portal.org/dice/oai
Set format: SwePub-{code} for SwePub sets or all-{code} for all records
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

BASE_URL = "http://www.diva-portal.org/dice/oai"

# Session with proper headers to avoid 403
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; AcademicResearchBot/1.0; research purposes)",
        "Accept": "application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
    }
)


def harvest_diva(set_code: str, max_records: int = 1000) -> list:
    """
    Harvest records from DiVA using OAI-PMH protocol.

    Args:
        set_code: The set code (e.g., 'SwePub-liu', 'SwePub-ltu')
        max_records: Maximum number of records to fetch

    Returns:
        List of parsed records
    """
    records = []
    resumption_token = None
    total_fetched = 0
    max_errors = 5
    error_count = 0

    print(f"[HARVESTER] Starting harvest for {set_code}")
    print(f"[HARVESTER] Target: {max_records} records")

    while total_fetched < max_records:
        # Build request URL
        if resumption_token:
            url = f"{BASE_URL}?verb=ListRecords&resumptionToken={resumption_token}"
        else:
            url = f"{BASE_URL}?verb=ListRecords&metadataPrefix=oai_dc&set={set_code}"

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

    print(f"[HARVESTER] Complete: {len(records)} records harvested for {set_code}")
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


def save_records(records: list, output_path: str, set_code: str, institution_name: str):
    """Save records to JSON file."""
    output = {
        "source": "diva-portal.org",
        "set_code": set_code,
        "institution": institution_name,
        "harvested_at": datetime.now().isoformat(),
        "record_count": len(records),
        "records": records,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[STORAGE] Saved {len(records)} records to {output_path}")


def main():
    # Batch 2: Technical Universities
    # Note: Chalmers is NOT in DiVA - they have their own system
    # Using SwePub sets for peer-reviewed publications
    institutions = [
        ("SwePub-liu", "liu", "Linkopings universitet"),
        ("SwePub-ltu", "ltu", "Lulea tekniska universitet"),
        ("SwePub-miun", "miun", "Mittuniversitetet"),
        ("SwePub-bth", "bth", "Blekinge tekniska hogskola"),
    ]

    output_dir = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data"
    max_records = 1000  # Test with 1000 per institution

    results = {}

    for set_code, short_code, name in institutions:
        print(f"\n{'=' * 60}")
        print(f"HARVESTING: {name} ({set_code})")
        print(f"{'=' * 60}")

        records = harvest_diva(set_code, max_records)

        output_path = f"{output_dir}/diva_batch2_{short_code}.json"
        save_records(records, output_path, set_code, name)

        results[short_code] = {
            "name": name,
            "set_code": set_code,
            "records": len(records),
            "file": output_path,
        }

        # Pause between institutions
        print("[HARVESTER] Pausing 3 seconds before next institution...")
        time.sleep(3)

    # Print summary
    print(f"\n{'=' * 60}")
    print("HARVEST SUMMARY - DiVA BATCH 2")
    print(f"{'=' * 60}")

    total = 0
    for _code, data in results.items():
        print(f"{data['name']:40} | {data['records']:6} docs")
        total += data["records"]

    print(f"{'=' * 60}")
    print(f"{'TOTAL':40} | {total:6} docs")
    print("\nNote: Chalmers not included - uses separate repository system")

    # Save summary
    summary_path = f"{output_dir}/diva_batch2_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "batch": 2,
                "harvested_at": datetime.now().isoformat(),
                "institutions": results,
                "total_records": total,
                "notes": "Chalmers excluded - not in DiVA system",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nSummary saved to: {summary_path}")

    return results


if __name__ == "__main__":
    main()
