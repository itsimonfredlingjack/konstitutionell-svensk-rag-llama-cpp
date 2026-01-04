#!/usr/bin/env python3
"""
DiVA OAI-PMH Full Harvester - Linkopings universitet
=====================================================
Harvests ALL 125,102 documents from LiU DiVA portal.

Endpoint: http://liu.diva-portal.org/dice/oai
Metadata prefix: swepub_mods
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
OAI_ENDPOINT = "https://liu.diva-portal.org/dice/oai"
METADATA_PREFIX = "swepub_mods"
OUTPUT_FILE = Path(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_liu.json"
)
RATE_LIMIT = 1.0  # seconds between requests
CHECKPOINT_INTERVAL = 1000  # Save checkpoint every N records

# HTTP Headers to avoid bot blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/xml,text/xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
}

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "swepub": "http://www.kb.se/swepub/mods",
}


def parse_mods_record(record_elem):
    """Extract metadata from a MODS record."""
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

        record_data = {
            "oai_identifier": identifier,
            "datestamp": datestamp,
            "source": "liu.diva-portal.org",
        }

        if metadata is not None:
            mods = metadata.find(".//mods:mods", NAMESPACES)
            if mods is not None:
                # Title
                title_info = mods.find("mods:titleInfo", NAMESPACES)
                if title_info is not None:
                    title = title_info.findtext("mods:title", "", NAMESPACES)
                    subtitle = title_info.findtext("mods:subTitle", "", NAMESPACES)
                    record_data["title"] = f"{title}: {subtitle}" if subtitle else title

                # Authors
                authors = []
                for name in mods.findall("mods:name", NAMESPACES):
                    name_type = name.get("type", "")
                    if name_type == "personal":
                        given = name.findtext('.//mods:namePart[@type="given"]', "", NAMESPACES)
                        family = name.findtext('.//mods:namePart[@type="family"]', "", NAMESPACES)
                        if given or family:
                            authors.append(f"{given} {family}".strip())
                record_data["authors"] = authors

                # Abstract
                abstract = mods.findtext("mods:abstract", "", NAMESPACES)
                if abstract:
                    record_data["abstract"] = abstract[:2000]  # Truncate long abstracts

                # Publication year
                origin_info = mods.find("mods:originInfo", NAMESPACES)
                if origin_info is not None:
                    date_issued = origin_info.findtext("mods:dateIssued", "", NAMESPACES)
                    if date_issued:
                        record_data["year"] = date_issued[:4]

                # Genre/Type
                genre = mods.findtext("mods:genre", "", NAMESPACES)
                if genre:
                    record_data["genre"] = genre

                # Subjects
                subjects = []
                for subject in mods.findall("mods:subject/mods:topic", NAMESPACES):
                    if subject.text:
                        subjects.append(subject.text)
                if subjects:
                    record_data["subjects"] = subjects

                # Language
                lang = mods.findtext(".//mods:languageTerm", "", NAMESPACES)
                if lang:
                    record_data["language"] = lang

                # Record identifier (DiVA ID)
                for identifier_elem in mods.findall("mods:identifier", NAMESPACES):
                    id_type = identifier_elem.get("type", "")
                    if id_type == "uri" and "diva" in (identifier_elem.text or "").lower():
                        record_data["diva_url"] = identifier_elem.text
                    elif id_type == "doi":
                        record_data["doi"] = identifier_elem.text

        return record_data

    except Exception as e:
        print(f"Error parsing record: {e}", file=sys.stderr)
        return None


def harvest_oai(endpoint, metadata_prefix):
    """Harvest all records via OAI-PMH with resumptionToken pagination."""

    all_records = []
    resumption_token = None
    batch_count = 0
    total_processed = 0
    deleted_count = 0
    error_count = 0
    start_time = datetime.now()

    print("=" * 60)
    print("DiVA Full Harvest - Linkopings universitet")
    print("=" * 60)
    print(f"Endpoint: {endpoint}")
    print(f"Metadata prefix: {metadata_prefix}")
    print(f"Started: {start_time.isoformat()}")
    print("=" * 60)

    while True:
        batch_count += 1

        # Build request
        if resumption_token:
            params = {"verb": "ListRecords", "resumptionToken": resumption_token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": metadata_prefix}

        try:
            response = requests.get(endpoint, params=params, headers=HEADERS, timeout=60)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"\nRequest error on batch {batch_count}: {e}")
            error_count += 1
            if error_count > 5:
                print("Too many errors, stopping.")
                break
            time.sleep(5)
            continue

        # Parse XML
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"\nXML parse error on batch {batch_count}: {e}")
            error_count += 1
            if error_count > 5:
                print("Too many errors, stopping.")
                break
            time.sleep(5)
            continue

        # Check for OAI-PMH errors
        error_elem = root.find(".//oai:error", NAMESPACES)
        if error_elem is not None:
            error_code = error_elem.get("code", "unknown")
            error_msg = error_elem.text or ""
            print(f"\nOAI-PMH error: {error_code} - {error_msg}")
            if error_code == "noRecordsMatch":
                print("No records found.")
                break
            break

        # Extract records
        list_records = root.find(".//oai:ListRecords", NAMESPACES)
        if list_records is None:
            print(f"\nNo ListRecords element found in batch {batch_count}")
            break

        records = list_records.findall("oai:record", NAMESPACES)
        batch_size = len(records)

        for record in records:
            parsed = parse_mods_record(record)
            if parsed:
                all_records.append(parsed)
            else:
                deleted_count += 1

        total_processed += batch_size

        # Progress report
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = len(all_records) / elapsed if elapsed > 0 else 0
        eta_seconds = (125102 - len(all_records)) / rate if rate > 0 else 0
        eta_minutes = eta_seconds / 60

        print(
            f"\rBatch {batch_count}: {len(all_records):,} records | "
            f"Rate: {rate:.1f}/sec | "
            f"ETA: {eta_minutes:.0f}min | "
            f"Deleted: {deleted_count}",
            end="",
            flush=True,
        )

        # Save checkpoint
        if len(all_records) % CHECKPOINT_INTERVAL < batch_size:
            checkpoint_file = OUTPUT_FILE.with_suffix(".checkpoint.json")
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "records": all_records,
                        "count": len(all_records),
                        "batch": batch_count,
                        "last_token": resumption_token,
                        "timestamp": datetime.now().isoformat(),
                    },
                    f,
                )

        # Get resumption token
        token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
        if token_elem is not None and token_elem.text:
            resumption_token = token_elem.text.strip()

            # Get list size if available
            complete_size = token_elem.get("completeListSize")
            if complete_size:
                print(f" | Total: {complete_size}", end="")
        else:
            # No more pages
            print("\n\nHarvest complete - no more resumption tokens.")
            break

        # Rate limiting
        time.sleep(RATE_LIMIT)

    return all_records, deleted_count


def main():
    """Main entry point."""

    records, deleted = harvest_oai(OAI_ENDPOINT, METADATA_PREFIX)

    end_time = datetime.now()

    # Save final output
    output_data = {
        "metadata": {
            "source": "liu.diva-portal.org",
            "harvested_at": end_time.isoformat(),
            "total_records": len(records),
            "deleted_skipped": deleted,
            "metadata_prefix": METADATA_PREFIX,
        },
        "records": records,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Remove checkpoint if exists
    checkpoint_file = OUTPUT_FILE.with_suffix(".checkpoint.json")
    if checkpoint_file.exists():
        checkpoint_file.unlink()

    print("\n" + "=" * 60)
    print("HARVEST COMPLETE")
    print("=" * 60)
    print(f"Total records harvested: {len(records):,}")
    print(f"Deleted/skipped: {deleted:,}")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size / (1024*1024):.1f} MB")
    print("=" * 60)

    return len(records)


if __name__ == "__main__":
    count = main()
    print(f"\nFINAL COUNT: {count}")
