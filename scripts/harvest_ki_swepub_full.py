#!/usr/bin/env python3
"""
FULL HARVEST: Karolinska Institutet via SwePub OAI-PMH
======================================================
Endpoint: http://api.libris.kb.se/swepub/oaipmh/SWEPUB
Set: KI_SWEPUB
Metadataprefix: mods (or oai_dc)
Target: ~50,000 documents

Rate limit: 1 request/second
Uses resumptionToken for complete pagination.
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OAI_ENDPOINT = "http://api.libris.kb.se/swepub/oaipmh/SWEPUB"
METADATA_PREFIX = "mods"  # or oai_dc
SET_SPEC = "KI_SWEPUB"
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_ki.json"
CHECKPOINT_FILE = (
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/ki_swepub_checkpoint.json"
)
RATE_LIMIT_SECONDS = 1.0

# OAI-PMH namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


def get_text(element, xpath, namespaces=None):
    """Safely extract text from XML element."""
    if element is None:
        return None
    found = element.find(xpath, namespaces or NAMESPACES)
    return found.text if found is not None else None


def get_all_text(element, xpath, namespaces=None):
    """Get all matching text values."""
    if element is None:
        return []
    found = element.findall(xpath, namespaces or NAMESPACES)
    return [f.text for f in found if f is not None and f.text]


def parse_mods_record(record_elem):
    """Parse a single MODS record from OAI-PMH response."""
    try:
        header = record_elem.find("oai:header", NAMESPACES)
        metadata = record_elem.find("oai:metadata", NAMESPACES)

        if header is None:
            return None

        # Check if deleted
        status = header.get("status", "")
        if status == "deleted":
            return None

        identifier = get_text(header, "oai:identifier")
        datestamp = get_text(header, "oai:datestamp")

        record = {
            "oai_identifier": identifier,
            "datestamp": datestamp,
            "source": "swepub.kb.se",
            "institution": "Karolinska Institutet",
            "harvested_at": datetime.now().isoformat(),
        }

        if metadata is None:
            return record

        # Find MODS element
        mods = metadata.find(".//mods:mods", NAMESPACES)
        if mods is None:
            mods = metadata.find(".//{http://www.loc.gov/mods/v3}mods")

        if mods is not None:
            # Title
            title_info = mods.find("mods:titleInfo", NAMESPACES)
            if title_info is not None:
                record["title"] = get_text(title_info, "mods:title")
                record["subtitle"] = get_text(title_info, "mods:subTitle")

            # Authors
            authors = []
            for name in mods.findall("mods:name", NAMESPACES):
                name_parts = {}
                for part in name.findall("mods:namePart", NAMESPACES):
                    part_type = part.get("type", "full")
                    if part.text:
                        name_parts[part_type] = part.text

                # Get affiliation
                affiliation = name.find("mods:affiliation", NAMESPACES)
                if affiliation is not None and affiliation.text:
                    name_parts["affiliation"] = affiliation.text

                if name_parts:
                    authors.append(name_parts)
            record["authors"] = authors

            # Abstract
            abstract = mods.find("mods:abstract", NAMESPACES)
            if abstract is not None and abstract.text:
                record["abstract"] = abstract.text

            # Keywords/subjects
            subjects = []
            for subject in mods.findall("mods:subject", NAMESPACES):
                topic = get_text(subject, "mods:topic")
                if topic:
                    subjects.append(topic)
            record["subjects"] = subjects

            # Language
            language = mods.find("mods:language/mods:languageTerm", NAMESPACES)
            if language is not None:
                record["language"] = language.text

            # Origin info (publication date, publisher)
            origin = mods.find("mods:originInfo", NAMESPACES)
            if origin is not None:
                record["publisher"] = get_text(origin, "mods:publisher")
                date_issued = origin.find("mods:dateIssued", NAMESPACES)
                if date_issued is not None:
                    record["date_issued"] = date_issued.text

            # Record type/genre
            genres = get_all_text(mods, "mods:genre")
            record["genres"] = genres

            # Identifiers (DOI, ISBN, PMID, etc)
            identifiers = {}
            for ident in mods.findall("mods:identifier", NAMESPACES):
                id_type = ident.get("type", "unknown")
                if ident.text:
                    identifiers[id_type] = ident.text
            record["identifiers"] = identifiers

            # Physical description (extent/pages)
            phys = mods.find("mods:physicalDescription/mods:extent", NAMESPACES)
            if phys is not None:
                record["extent"] = phys.text

            # Related items (journal, series, etc)
            related = mods.find("mods:relatedItem", NAMESPACES)
            if related is not None:
                rel_type = related.get("type", "")
                rel_title = related.find("mods:titleInfo/mods:title", NAMESPACES)
                if rel_title is not None:
                    record["published_in"] = rel_title.text
                    record["published_in_type"] = rel_type

            # Notes
            notes = get_all_text(mods, "mods:note")
            if notes:
                record["notes"] = notes

            # Classification
            classifications = []
            for classif in mods.findall("mods:classification", NAMESPACES):
                if classif.text:
                    classifications.append(
                        {"authority": classif.get("authority", ""), "value": classif.text}
                    )
            if classifications:
                record["classifications"] = classifications

        return record

    except Exception as e:
        print(f"Error parsing record: {e}")
        return None


def fetch_records(resumption_token=None):
    """Fetch a batch of records from OAI-PMH endpoint."""
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX, "set": SET_SPEC}

    response = requests.get(OAI_ENDPOINT, params=params, timeout=120)
    response.raise_for_status()

    return response.text


def parse_response(xml_text):
    """Parse OAI-PMH response and extract records + resumption token."""
    root = ET.fromstring(xml_text)

    # Check for errors
    error = root.find("oai:error", NAMESPACES)
    if error is not None:
        error_code = error.get("code", "unknown")
        error_msg = error.text or ""
        raise Exception(f"OAI-PMH error [{error_code}]: {error_msg}")

    records = []
    list_records = root.find("oai:ListRecords", NAMESPACES)

    if list_records is None:
        return records, None

    for record_elem in list_records.findall("oai:record", NAMESPACES):
        parsed = parse_mods_record(record_elem)
        if parsed:
            records.append(parsed)

    # Get resumption token
    resumption_elem = list_records.find("oai:resumptionToken", NAMESPACES)
    resumption_token = None
    complete_list_size = None
    cursor = None

    if resumption_elem is not None:
        resumption_token = resumption_elem.text
        complete_list_size = resumption_elem.get("completeListSize")
        cursor = resumption_elem.get("cursor")

        # Empty token means we're done
        if resumption_token == "" or resumption_token is None:
            resumption_token = None

    return records, {
        "token": resumption_token,
        "complete_list_size": complete_list_size,
        "cursor": cursor,
    }


def save_checkpoint(token_info, total_records, batch_num):
    """Save checkpoint for resume capability."""
    checkpoint = {
        "resumption_token": token_info.get("token") if token_info else None,
        "total_records": total_records,
        "batch_num": batch_num,
        "timestamp": datetime.now().isoformat(),
    }
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f)


def load_checkpoint():
    """Load checkpoint if exists."""
    try:
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def main():
    print("=" * 70)
    print("FULL HARVEST: Karolinska Institutet via SwePub")
    print("=" * 70)
    print(f"Endpoint: {OAI_ENDPOINT}")
    print(f"Set: {SET_SPEC}")
    print(f"Metadata prefix: {METADATA_PREFIX}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rate limit: {RATE_LIMIT_SECONDS}s between requests")
    print("=" * 70)

    all_records = []
    resumption_token = None
    batch_num = 0
    start_time = time.time()

    # Check for existing data to append to
    output_path = Path(OUTPUT_FILE)
    if output_path.exists():
        print(f"\nLoading existing records from {OUTPUT_FILE}...")
        try:
            with open(OUTPUT_FILE) as f:
                existing = json.load(f)
                if isinstance(existing, dict) and "records" in existing:
                    all_records = existing["records"]
                elif isinstance(existing, list):
                    all_records = existing
                print(f"Loaded {len(all_records)} existing records")
        except Exception as e:
            print(f"Could not load existing: {e}")

    # Check for checkpoint
    checkpoint = load_checkpoint()
    if checkpoint and checkpoint.get("resumption_token"):
        print(f"\nFound checkpoint at batch {checkpoint['batch_num']}")
        print(f"Resuming from token: {checkpoint['resumption_token'][:50]}...")
        resumption_token = checkpoint["resumption_token"]
        batch_num = checkpoint["batch_num"]

    try:
        while True:
            batch_num += 1

            print(f"\n[Batch {batch_num}] Fetching records...", end=" ", flush=True)

            try:
                xml_response = fetch_records(resumption_token)
                records, token_info = parse_response(xml_response)

                all_records.extend(records)

                if token_info:
                    complete_size = token_info.get("complete_list_size", "?")
                    cursor = token_info.get("cursor", "?")
                    print(
                        f"Got {len(records)} records. Total: {len(all_records)} / {complete_size} (cursor: {cursor})"
                    )

                    resumption_token = token_info.get("token")
                else:
                    print(f"Got {len(records)} records. Total: {len(all_records)}")
                    resumption_token = None

                # Save checkpoint every 5 batches
                if batch_num % 5 == 0:
                    save_checkpoint(token_info, len(all_records), batch_num)

                    # Also save intermediate results
                    elapsed = time.time() - start_time
                    rate = len(all_records) / elapsed * 60 if elapsed > 0 else 0

                    result = {
                        "source": "swepub.kb.se",
                        "set": SET_SPEC,
                        "institution": "Karolinska Institutet",
                        "metadata_prefix": METADATA_PREFIX,
                        "total_records": len(all_records),
                        "harvested_at": datetime.now().isoformat(),
                        "elapsed_minutes": round(elapsed / 60, 1),
                        "rate_per_minute": round(rate, 1),
                        "status": "in_progress",
                        "records": all_records,
                    }

                    with open(OUTPUT_FILE, "w") as f:
                        json.dump(result, f, ensure_ascii=False)

                    print(f"    Checkpoint saved. Rate: {rate:.0f} docs/min")

                # Check if we're done
                if not resumption_token:
                    print("\n" + "=" * 70)
                    print("HARVEST COMPLETE - No more resumption tokens")
                    break

                # Rate limiting
                time.sleep(RATE_LIMIT_SECONDS)

            except requests.exceptions.RequestException as e:
                print(f"\nNetwork error: {e}")
                print("Waiting 30 seconds before retry...")
                time.sleep(30)
                continue

            except Exception as e:
                print(f"\nError in batch {batch_num}: {e}")
                if "noRecordsMatch" in str(e):
                    print("No records match - harvest complete")
                    break
                print("Waiting 10 seconds before retry...")
                time.sleep(10)
                continue

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Saving progress...")

    # Final save
    elapsed = time.time() - start_time
    rate = len(all_records) / elapsed * 60 if elapsed > 0 else 0

    result = {
        "source": "swepub.kb.se",
        "set": SET_SPEC,
        "institution": "Karolinska Institutet",
        "metadata_prefix": METADATA_PREFIX,
        "total_records": len(all_records),
        "harvested_at": datetime.now().isoformat(),
        "elapsed_minutes": round(elapsed / 60, 1),
        "rate_per_minute": round(rate, 1),
        "status": "complete" if not resumption_token else "interrupted",
        "records": all_records,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)

    # Remove checkpoint if complete
    if not resumption_token:
        checkpoint_path = Path(CHECKPOINT_FILE)
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    print("\n" + "=" * 70)
    print("OPERATION STATUS")
    print("=" * 70)
    print(f"Documents fetched: {len(all_records)}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print(f"Rate: {rate:.0f} docs/minute")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Status: {'COMPLETE' if not resumption_token else 'INTERRUPTED'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
