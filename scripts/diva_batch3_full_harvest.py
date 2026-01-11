#!/usr/bin/env python3
"""
DiVA OAI-PMH FULL HARVEST - Batch 3: 10 Medium-Sized Swedish Universities
==========================================================================
TOTAL TARGET: ~220,602 documents

Institutions:
1. Orebro universitet (oru) - 18,165
2. Karlstads universitet (kau) - 25,629
3. Linneuniversitetet (lnu) - 42,759
4. Malmo universitet (mau) - 36,477
5. Sodertorns hogskola (sh) - 14,934
6. Malardalens universitet (mdh) - 16,790
7. Hogskolan i Halmstad (hh) - 17,154
8. Hogskolan Dalarna (du) - 14,131
9. Hogskolan i Gavle (hig) - 18,368
10. Hogskolan i Boras (hb) - 16,195

Endpoint format: https://{code}.diva-portal.org/dice/oai
Metadata prefix: swepub_mods
Rate limit: 1 request/second per institution
"""

import argparse
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
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
METADATA_PREFIX = "swepub_mods"
RATE_LIMIT_SECONDS = 1.0
MAX_CONSECUTIVE_ERRORS = 10

# Institutions to harvest
INSTITUTIONS = [
    ("oru", "Orebro universitet", 18165),
    ("kau", "Karlstads universitet", 25629),
    ("lnu", "Linneuniversitetet", 42759),
    ("mau", "Malmo universitet", 36477),
    ("sh", "Sodertorns hogskola", 14934),
    ("mdh", "Malardalens universitet", 16790),
    ("hh", "Hogskolan i Halmstad", 17154),
    ("du", "Hogskolan Dalarna", 14131),
    ("hig", "Hogskolan i Gavle", 18368),
    ("hb", "Hogskolan i Boras", 16195),
]

# Headers to avoid 403
HEADERS = {
    "User-Agent": "DiVA-Harvester/1.0 (Academic Research; OAI-PMH; Swedish Universities)",
    "Accept": "application/xml, text/xml, */*",
}

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "swepub": "http://swepub.kb.se/swepub_mods",
}


def get_endpoint(code: str) -> str:
    """Get OAI-PMH endpoint URL for institution code."""
    return f"https://{code}.diva-portal.org/dice/oai"


def parse_mods_record(record_elem) -> dict | None:
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
                    record_data["abstract"] = abstract.text.strip()[:2000]

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

                # Identifiers (DOI, URN, etc.)
                for ident in mods.findall(".//mods:identifier", NAMESPACES):
                    id_type = ident.get("type", "")
                    if id_type and ident.text:
                        record_data[f"id_{id_type}"] = ident.text.strip()

        return record_data

    except Exception as e:
        return {"error": str(e), "raw": "parse_error"}


def harvest_institution(code: str, name: str, expected_count: int) -> tuple[int, str]:
    """
    Harvest all records from a single institution.
    Returns (record_count, output_file_path).
    """
    endpoint = get_endpoint(code)
    output_file = OUTPUT_DIR / f"diva_full_{code}.json"
    checkpoint_file = OUTPUT_DIR / f"diva_{code}_checkpoint.json"

    print(f"\n{'=' * 70}")
    print(f"HARVESTING: {name} ({code})")
    print(f"{'=' * 70}")
    print(f"Endpoint: {endpoint}")
    print(f"Expected: ~{expected_count:,} records")
    print(f"Output: {output_file}")
    print(f"{'=' * 70}")

    # Check for existing partial harvest
    all_records = []
    resumption_token = None

    if output_file.exists():
        try:
            with open(output_file) as f:
                existing = json.load(f)
                if "records" in existing:
                    all_records = existing["records"]
                    resumption_token = existing.get("last_resumption_token")
                    print(f"Resuming: {len(all_records):,} existing records loaded")
                    if resumption_token:
                        print(f"Token: {resumption_token[:50]}...")
        except json.JSONDecodeError:
            print("Warning: Corrupt checkpoint file, starting fresh")

    session = requests.Session()
    session.headers.update(HEADERS)

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
            response = session.get(endpoint, params=params, timeout=60)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Check for errors
            error = root.find(".//oai:error", NAMESPACES)
            if error is not None:
                error_code = error.get("code", "unknown")
                error_msg = error.text or "No message"
                print(f"OAI Error: {error_code} - {error_msg}")
                if error_code == "noRecordsMatch":
                    break
                consecutive_errors += 1
                if consecutive_errors > MAX_CONSECUTIVE_ERRORS:
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
                    parsed["source_institution"] = name
                    parsed["source_code"] = code
                    all_records.append(parsed)
                    batch_count += 1
                    total_fetched += 1

            # Get resumption token
            token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
            if token_elem is not None and token_elem.text:
                resumption_token = token_elem.text.strip()
                complete_size = token_elem.get("completeListSize", "unknown")
                cursor = token_elem.get("cursor", "?")

                # Progress report
                elapsed = time.time() - start_time
                rate = total_fetched / elapsed if elapsed > 0 else 0
                pct = (total_fetched / expected_count * 100) if expected_count > 0 else 0

                print(
                    f"[{code.upper()}] Batch {batch_num}: +{batch_count} | "
                    f"Total: {total_fetched:,} / {complete_size} ({pct:.1f}%) | "
                    f"Rate: {rate:.1f}/sec"
                )
            else:
                # No more records
                print(f"[{code.upper()}] Final batch: +{batch_count} records")
                resumption_token = None

            # Reset error counter on success
            consecutive_errors = 0
            batch_num += 1

            # Save checkpoint every 50 batches (~5000 records)
            if batch_num % 50 == 0:
                save_output(
                    all_records,
                    output_file,
                    code,
                    name,
                    start_time,
                    resumption_token,
                    in_progress=True,
                )
                print(f"  [Checkpoint saved: {total_fetched:,} records]")

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

        if consecutive_errors > MAX_CONSECUTIVE_ERRORS:
            print(f"\n[{code.upper()}] Too many errors, saving and moving to next institution.")
            break

    # Final save
    save_output(all_records, output_file, code, name, start_time, None, in_progress=False)

    # Clean up checkpoint
    if checkpoint_file.exists():
        checkpoint_file.unlink()

    elapsed = time.time() - start_time
    print(f"\n[{code.upper()}] COMPLETE: {len(all_records):,} records in {elapsed / 60:.1f} min")

    return len(all_records), str(output_file)


def save_output(
    records: list,
    output_file: Path,
    code: str,
    name: str,
    start_time: float,
    resumption_token: str | None,
    in_progress: bool,
):
    """Save records to JSON file."""
    output_data = {
        "source": name,
        "source_code": code,
        "endpoint": get_endpoint(code),
        "metadata_prefix": METADATA_PREFIX,
        "harvest_started": datetime.fromtimestamp(start_time).isoformat(),
        "last_update": datetime.now().isoformat(),
        "status": "in_progress" if in_progress else "complete",
        "total_records": len(records),
        "records": records,
    }

    if resumption_token:
        output_data["last_resumption_token"] = resumption_token

    with open(output_file, "w") as f:
        json.dump(output_data, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="DiVA OAI-PMH Full Harvest - Batch 3")
    parser.add_argument(
        "--start", type=str, default=None, help='Start from specific institution code (e.g., "lnu")'
    )
    parser.add_argument(
        "--only", type=str, default=None, help='Only harvest specific institution (e.g., "mau")'
    )
    parser.add_argument("--list", action="store_true", help="List all institutions and exit")
    args = parser.parse_args()

    if args.list:
        print("\nBATCH 3 INSTITUTIONS:")
        print("-" * 60)
        total = 0
        for code, name, count in INSTITUTIONS:
            print(f"  {code:5} | {name:30} | {count:,} docs")
            total += count
        print("-" * 60)
        print(f"  TOTAL: {total:,} documents")
        return

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("DiVA OAI-PMH FULL HARVEST - BATCH 3")
    print("10 Medium-Sized Swedish Universities")
    print("=" * 70)

    start_time = time.time()
    results = {}
    total_harvested = 0

    # Filter institutions if needed
    institutions_to_harvest = INSTITUTIONS

    if args.only:
        institutions_to_harvest = [(c, n, e) for c, n, e in INSTITUTIONS if c == args.only]
        if not institutions_to_harvest:
            print(f"Error: Unknown institution code '{args.only}'")
            return

    if args.start:
        found = False
        filtered = []
        for inst in INSTITUTIONS:
            if inst[0] == args.start:
                found = True
            if found:
                filtered.append(inst)
        if not filtered:
            print(f"Error: Unknown institution code '{args.start}'")
            return
        institutions_to_harvest = filtered

    # Harvest each institution
    for code, name, expected in institutions_to_harvest:
        try:
            count, output_path = harvest_institution(code, name, expected)
            results[code] = {
                "name": name,
                "expected": expected,
                "harvested": count,
                "output": output_path,
                "status": "complete",
            }
            total_harvested += count

            # Brief pause between institutions
            time.sleep(2)

        except KeyboardInterrupt:
            print(f"\n\nInterrupted during {name}. Progress saved.")
            results[code] = {
                "name": name,
                "expected": expected,
                "harvested": 0,
                "status": "interrupted",
            }
            break

        except Exception as e:
            print(f"\n[ERROR] Failed to harvest {name}: {e}")
            results[code] = {
                "name": name,
                "expected": expected,
                "harvested": 0,
                "status": f"error: {e}",
            }

    # Final summary
    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("HARVEST SUMMARY - BATCH 3")
    print("=" * 70)

    expected_total = 0
    for code, data in results.items():
        status = "OK" if data.get("status") == "complete" else data.get("status", "unknown")
        print(
            f"  {code:5} | {data['name']:30} | {data.get('harvested', 0):,} / {data['expected']:,} | {status}"
        )
        expected_total += data["expected"]

    print("=" * 70)
    print(f"  TOTAL: {total_harvested:,} / {expected_total:,} documents")
    print(f"  Time elapsed: {elapsed / 60:.1f} minutes ({elapsed / 3600:.2f} hours)")
    print(f"  Average rate: {total_harvested / elapsed:.1f} docs/sec")
    print("=" * 70)

    # Save summary
    summary_file = OUTPUT_DIR / "diva_batch3_summary.json"
    with open(summary_file, "w") as f:
        json.dump(
            {
                "batch": 3,
                "description": "10 Medium-Sized Swedish Universities",
                "harvested_at": datetime.now().isoformat(),
                "elapsed_seconds": elapsed,
                "total_harvested": total_harvested,
                "institutions": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nSummary saved to: {summary_file}")

    return total_harvested


if __name__ == "__main__":
    try:
        count = main()
        if count:
            print(f"\nSUCCESS: Harvested {count:,} documents from Batch 3")
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
