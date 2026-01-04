#!/usr/bin/env python3
"""
GU Full Harvest - Göteborgs universitet via GUP OAI-PMH
Target: 241,769 documents
Format: MODS (only supported format)
Rate limit: 1 req/sec
"""

import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

# Configuration
OAI_ENDPOINT = "https://gup.ub.gu.se/oai"
METADATA_PREFIX = "mods"  # GUP only supports MODS
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_gu.json"
CHECKPOINT_FILE = (
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/gu_harvest_checkpoint.json"
)
RATE_LIMIT = 1.0  # seconds between requests

# OAI-PMH and MODS namespaces
NAMESPACES = {"oai": "http://www.openarchives.org/OAI/2.0/", "mods": "http://www.loc.gov/mods/v3"}


def parse_mods_record(record_elem):
    """Parse a single OAI-PMH record with MODS metadata into a dict."""
    try:
        header = record_elem.find("oai:header", NAMESPACES)
        metadata = record_elem.find("oai:metadata", NAMESPACES)

        if header is None:
            return None

        # Check if deleted
        if header.get("status") == "deleted":
            return None

        identifier = header.find("oai:identifier", NAMESPACES)
        datestamp = header.find("oai:datestamp", NAMESPACES)

        record = {
            "identifier": identifier.text if identifier is not None else None,
            "datestamp": datestamp.text if datestamp is not None else None,
            "source": "GU",
        }

        # Parse MODS metadata
        if metadata is not None:
            mods = metadata.find("mods:mods", NAMESPACES)
            if mods is not None:
                # Title
                title_info = mods.find("mods:titleInfo", NAMESPACES)
                if title_info is not None:
                    title = title_info.find("mods:title", NAMESPACES)
                    if title is not None and title.text:
                        record["title"] = title.text
                    subtitle = title_info.find("mods:subTitle", NAMESPACES)
                    if subtitle is not None and subtitle.text:
                        record["subtitle"] = subtitle.text

                # Authors/Names
                names = []
                for name_elem in mods.findall("mods:name", NAMESPACES):
                    name_parts = name_elem.findall("mods:namePart", NAMESPACES)
                    name_str = " ".join([np.text for np in name_parts if np.text])
                    if name_str:
                        role_term = name_elem.find(".//mods:roleTerm", NAMESPACES)
                        role = role_term.text if role_term is not None else "author"
                        names.append({"name": name_str, "role": role})
                if names:
                    record["names"] = names

                # Abstract
                abstract = mods.find("mods:abstract", NAMESPACES)
                if abstract is not None and abstract.text:
                    record["abstract"] = abstract.text

                # Subjects/Keywords
                subjects = []
                for subject in mods.findall("mods:subject", NAMESPACES):
                    for topic in subject.findall("mods:topic", NAMESPACES):
                        if topic.text:
                            subjects.append(topic.text)
                if subjects:
                    record["subjects"] = subjects

                # Type of resource
                type_of_resource = mods.find("mods:typeOfResource", NAMESPACES)
                if type_of_resource is not None and type_of_resource.text:
                    record["type_of_resource"] = type_of_resource.text

                # Genre
                genre = mods.find("mods:genre", NAMESPACES)
                if genre is not None and genre.text:
                    record["genre"] = genre.text

                # Origin info (publisher, date, etc)
                origin_info = mods.find("mods:originInfo", NAMESPACES)
                if origin_info is not None:
                    publisher = origin_info.find("mods:publisher", NAMESPACES)
                    if publisher is not None and publisher.text:
                        record["publisher"] = publisher.text
                    date_issued = origin_info.find("mods:dateIssued", NAMESPACES)
                    if date_issued is not None and date_issued.text:
                        record["date_issued"] = date_issued.text
                    place = origin_info.find(".//mods:placeTerm", NAMESPACES)
                    if place is not None and place.text:
                        record["place"] = place.text

                # Language
                language = mods.find(".//mods:languageTerm", NAMESPACES)
                if language is not None and language.text:
                    record["language"] = language.text

                # Identifiers (DOI, ISBN, etc)
                identifiers = {}
                for id_elem in mods.findall("mods:identifier", NAMESPACES):
                    id_type = id_elem.get("type", "unknown")
                    if id_elem.text:
                        identifiers[id_type] = id_elem.text
                if identifiers:
                    record["identifiers"] = identifiers

                # Related items (journal info)
                related = mods.find("mods:relatedItem", NAMESPACES)
                if related is not None:
                    rel_title = related.find(".//mods:title", NAMESPACES)
                    if rel_title is not None and rel_title.text:
                        record["journal"] = rel_title.text
                    part = related.find("mods:part", NAMESPACES)
                    if part is not None:
                        volume = part.find('.//mods:detail[@type="volume"]/mods:number', NAMESPACES)
                        issue = part.find('.//mods:detail[@type="issue"]/mods:number', NAMESPACES)
                        if volume is not None and volume.text:
                            record["volume"] = volume.text
                        if issue is not None and issue.text:
                            record["issue"] = issue.text

                # Physical description
                physical = mods.find("mods:physicalDescription", NAMESPACES)
                if physical is not None:
                    extent = physical.find("mods:extent", NAMESPACES)
                    if extent is not None and extent.text:
                        record["extent"] = extent.text

                # Record info
                record_info = mods.find("mods:recordInfo", NAMESPACES)
                if record_info is not None:
                    record_id = record_info.find("mods:recordIdentifier", NAMESPACES)
                    if record_id is not None and record_id.text:
                        record["record_id"] = record_id.text

        return record
    except Exception as e:
        print(f"Error parsing record: {e}")
        return None


def fetch_records(resumption_token=None):
    """Fetch a batch of records from OAI-PMH endpoint."""
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX}

    response = requests.get(OAI_ENDPOINT, params=params, timeout=120)
    response.raise_for_status()

    return response.text


def parse_response(xml_text):
    """Parse OAI-PMH response, extract records and resumption token."""
    root = ET.fromstring(xml_text)

    # Check for errors
    error = root.find(".//oai:error", NAMESPACES)
    if error is not None:
        error_code = error.get("code")
        error_msg = error.text
        raise Exception(f"OAI-PMH Error: {error_code} - {error_msg}")

    list_records = root.find(".//oai:ListRecords", NAMESPACES)
    if list_records is None:
        return [], None, 0

    # Parse all records
    records = []
    for record_elem in list_records.findall("oai:record", NAMESPACES):
        record = parse_mods_record(record_elem)
        if record:
            records.append(record)

    # Get resumption token
    token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
    resumption_token = None
    complete_list_size = 0

    if token_elem is not None:
        resumption_token = token_elem.text if token_elem.text else None
        if token_elem.get("completeListSize"):
            complete_list_size = int(token_elem.get("completeListSize"))

    return records, resumption_token, complete_list_size


def save_checkpoint(token, total_fetched, all_records):
    """Save current state to checkpoint file."""
    checkpoint = {
        "resumption_token": token,
        "total_fetched": total_fetched,
        "timestamp": datetime.now().isoformat(),
        "records_count": len(all_records),
    }
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f)

    # Also save records incrementally
    with open(OUTPUT_FILE, "w") as f:
        json.dump(
            {
                "source": "Göteborgs universitet (GUP)",
                "endpoint": OAI_ENDPOINT,
                "metadata_format": METADATA_PREFIX,
                "harvest_date": datetime.now().isoformat(),
                "total_records": len(all_records),
                "records": all_records,
            },
            f,
            ensure_ascii=False,
        )


def load_checkpoint():
    """Load checkpoint if exists."""
    if os.path.exists(CHECKPOINT_FILE) and os.path.exists(OUTPUT_FILE):
        with open(CHECKPOINT_FILE) as f:
            checkpoint = json.load(f)
        with open(OUTPUT_FILE) as f:
            data = json.load(f)
        return checkpoint.get("resumption_token"), data.get("records", [])
    return None, []


def harvest():
    """Main harvest loop."""
    print("=" * 60)
    print("GU FULL HARVEST - Göteborgs universitet")
    print("=" * 60)
    print(f"Endpoint: {OAI_ENDPOINT}")
    print(f"Format: {METADATA_PREFIX}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rate limit: {RATE_LIMIT}s between requests")
    print("=" * 60)

    # Check for existing checkpoint
    resumption_token, all_records = load_checkpoint()
    if resumption_token and all_records:
        print(f"\nResuming from checkpoint: {len(all_records)} records already fetched")
        print(
            f"Token: {resumption_token[:50]}..."
            if len(resumption_token) > 50
            else f"Token: {resumption_token}"
        )
    else:
        resumption_token = None
        all_records = []
        print("\nStarting fresh harvest...")

    batch_num = len(all_records) // 100 + 1 if all_records else 1
    complete_list_size = 0
    errors_in_row = 0
    max_errors = 10

    start_time = datetime.now()

    try:
        while True:
            try:
                print(f"\n[Batch {batch_num}] Fetching records...", end=" ", flush=True)

                xml_response = fetch_records(resumption_token)
                records, resumption_token, list_size = parse_response(xml_response)

                if list_size > 0:
                    complete_list_size = list_size

                all_records.extend(records)
                errors_in_row = 0

                elapsed = (datetime.now() - start_time).total_seconds()
                rate = len(all_records) / elapsed if elapsed > 0 else 0

                progress = ""
                if complete_list_size > 0:
                    pct = (len(all_records) / complete_list_size) * 100
                    progress = f" ({pct:.1f}% of {complete_list_size:,})"

                print(
                    f"+{len(records)} = {len(all_records):,} total{progress} [{rate:.1f} docs/sec]"
                )

                # Save checkpoint every 10 batches
                if batch_num % 10 == 0:
                    print("    Saving checkpoint...", end=" ", flush=True)
                    save_checkpoint(resumption_token, len(all_records), all_records)
                    print("done")

                if not resumption_token:
                    print("\n" + "=" * 60)
                    print("HARVEST COMPLETE!")
                    print("=" * 60)
                    break

                batch_num += 1
                time.sleep(RATE_LIMIT)

            except requests.exceptions.RequestException as e:
                errors_in_row += 1
                print(f"\nNetwork error ({errors_in_row}/{max_errors}): {e}")
                if errors_in_row >= max_errors:
                    print("Too many consecutive errors, saving and exiting...")
                    break
                wait_time = min(30 * errors_in_row, 300)
                print(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

            except Exception as e:
                errors_in_row += 1
                print(f"\nError ({errors_in_row}/{max_errors}): {e}")
                if errors_in_row >= max_errors:
                    print("Too many consecutive errors, saving and exiting...")
                    break
                time.sleep(5)

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving progress...")

    # Final save
    print(f"\nSaving {len(all_records):,} records to {OUTPUT_FILE}...")
    save_checkpoint(resumption_token, len(all_records), all_records)

    elapsed = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 60)
    print("OPERATION STATUS")
    print("=" * 60)
    print(f"Documents fetched: {len(all_records):,}")
    print(
        f"Expected total: {complete_list_size:,}"
        if complete_list_size
        else "Expected total: Unknown"
    )
    print(f"Time elapsed: {int(elapsed // 60)}m {int(elapsed % 60)}s")
    print(f"Rate: {len(all_records) / elapsed:.2f} docs/sec" if elapsed > 0 else "")
    print(f"Output file: {OUTPUT_FILE}")
    if resumption_token:
        print("\nHarvest INCOMPLETE - can resume with checkpoint")
    else:
        print("\nHarvest COMPLETE!")
    print("=" * 60)

    return len(all_records)


if __name__ == "__main__":
    harvest()
