#!/usr/bin/env python3
"""
DiVA OAI-PMH Full Harvester - Umea University
=============================================
Full harvest of all documents from Umea University via DiVA OAI-PMH.

Endpoint: https://umu.diva-portal.org/dice/oai
Metadataprefix: swepub_mods
Expected: ~60,000 documents

Rate limit: 1 request/second
Uses resumptionToken for pagination.
"""

import json
import time
import xml.etree.ElementTree as ET
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import requests

# Configuration
BASE_URL = "https://umu.diva-portal.org/dice/oai"
METADATA_PREFIX = "swepub_mods"
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_umu.json"
CHECKPOINT_FILE = (
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_umu_checkpoint.json"
)
RATE_LIMIT = 1.0  # seconds between requests

# HTTP Headers - required for DiVA servers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OAI-Harvester/1.0; +mailto:research@example.org)",
    "Accept": "application/xml, text/xml",
}

# OAI-PMH namespaces
NAMESPACES = {"oai": "http://www.openarchives.org/OAI/2.0/", "mods": "http://www.loc.gov/mods/v3"}


def parse_record(record_elem):
    """Extract metadata from a single OAI-PMH record."""
    try:
        header = record_elem.find("oai:header", NAMESPACES)
        metadata = record_elem.find("oai:metadata", NAMESPACES)

        if header is None:
            return None

        # Check if deleted
        status = header.get("status")
        if status == "deleted":
            return {
                "identifier": header.findtext("oai:identifier", "", NAMESPACES),
                "datestamp": header.findtext("oai:datestamp", "", NAMESPACES),
                "status": "deleted",
            }

        identifier = header.findtext("oai:identifier", "", NAMESPACES)
        datestamp = header.findtext("oai:datestamp", "", NAMESPACES)

        # Extract setSpecs
        setspecs = [s.text for s in header.findall("oai:setSpec", NAMESPACES) if s.text]

        # Parse MODS metadata if present
        doc = {
            "identifier": identifier,
            "datestamp": datestamp,
            "setSpecs": setspecs,
            "status": "active",
        }

        if metadata is not None:
            mods = metadata.find("mods:mods", NAMESPACES)
            if mods is not None:
                # Title
                title_info = mods.find("mods:titleInfo", NAMESPACES)
                if title_info is not None:
                    title = title_info.findtext("mods:title", "", NAMESPACES)
                    subtitle = title_info.findtext("mods:subTitle", "", NAMESPACES)
                    doc["title"] = f"{title}: {subtitle}" if subtitle else title
                    doc["title_lang"] = title_info.get("lang", "unknown")

                # Authors
                authors = []
                for name in mods.findall('mods:name[@type="personal"]', NAMESPACES):
                    family = name.findtext('mods:namePart[@type="family"]', "", NAMESPACES)
                    given = name.findtext('mods:namePart[@type="given"]', "", NAMESPACES)
                    if family or given:
                        authors.append({"family": family, "given": given})
                doc["authors"] = authors

                # Publication type
                genres = []
                for genre in mods.findall("mods:genre", NAMESPACES):
                    if genre.text:
                        genres.append(
                            {
                                "authority": genre.get("authority", ""),
                                "type": genre.get("type", ""),
                                "value": genre.text,
                            }
                        )
                doc["genres"] = genres

                # Origin info (publisher, date)
                origin = mods.find("mods:originInfo", NAMESPACES)
                if origin is not None:
                    doc["publisher"] = origin.findtext("mods:publisher", "", NAMESPACES)
                    doc["dateIssued"] = origin.findtext("mods:dateIssued", "", NAMESPACES)
                    place = origin.find("mods:place/mods:placeTerm", NAMESPACES)
                    doc["place"] = place.text if place is not None else ""

                # Language
                lang_elem = mods.find("mods:language/mods:languageTerm", NAMESPACES)
                doc["language"] = lang_elem.text if lang_elem is not None else ""

                # URI identifier
                for ident in mods.findall("mods:identifier", NAMESPACES):
                    if ident.get("type") == "uri":
                        doc["uri"] = ident.text
                        break

                # Abstract
                abstract = mods.findtext("mods:abstract", "", NAMESPACES)
                if abstract:
                    doc["abstract"] = abstract[:2000]  # Truncate long abstracts

                # Subjects
                subjects = []
                for subject in mods.findall("mods:subject", NAMESPACES):
                    topic = subject.findtext("mods:topic", "", NAMESPACES)
                    if topic:
                        subjects.append(
                            {
                                "topic": topic,
                                "authority": subject.get("authority", ""),
                                "lang": subject.get("lang", ""),
                            }
                        )
                doc["subjects"] = subjects

                # Record info
                record_info = mods.find("mods:recordInfo", NAMESPACES)
                if record_info is not None:
                    doc["recordIdentifier"] = record_info.findtext(
                        "mods:recordIdentifier", "", NAMESPACES
                    )
                    doc["recordSource"] = record_info.findtext(
                        "mods:recordContentSource", "", NAMESPACES
                    )

                # Fulltext URL
                location = mods.find("mods:location", NAMESPACES)
                if location is not None:
                    url_elem = location.find("mods:url", NAMESPACES)
                    if url_elem is not None:
                        doc["fulltextUrl"] = url_elem.text

        return doc

    except Exception as e:
        print(f"Error parsing record: {e}")
        return None


def harvest_batch(resumption_token=None):
    """Fetch one batch of records from OAI-PMH endpoint."""
    if resumption_token:
        url = f"{BASE_URL}?verb=ListRecords&resumptionToken={resumption_token}"
    else:
        url = f"{BASE_URL}?verb=ListRecords&metadataPrefix={METADATA_PREFIX}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=60)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        # Check for errors
        error = root.find("oai:error", NAMESPACES)
        if error is not None:
            error_code = error.get("code", "unknown")
            error_msg = error.text or "No message"
            return None, None, f"OAI-PMH Error: {error_code} - {error_msg}"

        list_records = root.find("oai:ListRecords", NAMESPACES)
        if list_records is None:
            return None, None, "No ListRecords element found"

        # Parse all records
        records = []
        for record in list_records.findall("oai:record", NAMESPACES):
            parsed = parse_record(record)
            if parsed:
                records.append(parsed)

        # Get resumption token
        token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
        new_token = None
        complete_list_size = None

        if token_elem is not None:
            new_token = token_elem.text if token_elem.text else None
            complete_list_size = token_elem.get("completeListSize")

        return records, new_token, complete_list_size

    except requests.exceptions.RequestException as e:
        return None, None, f"Request error: {e}"
    except ET.ParseError as e:
        return None, None, f"XML parse error: {e}"


def save_checkpoint(documents, token, batch_num, total_expected):
    """Save progress checkpoint."""
    checkpoint = {
        "timestamp": datetime.now().isoformat(),
        "documents_collected": len(documents),
        "resumption_token": token,
        "batch_number": batch_num,
        "total_expected": total_expected,
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f)


def load_checkpoint():
    """Load checkpoint if exists."""
    try:
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    print("=" * 60)
    print("DiVA OAI-PMH FULL HARVEST - UMEA UNIVERSITY")
    print("=" * 60)
    print(f"Endpoint: {BASE_URL}")
    print(f"Metadata prefix: {METADATA_PREFIX}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rate limit: {RATE_LIMIT}s between requests")
    print("=" * 60)

    start_time = datetime.now()

    # Check for existing checkpoint
    checkpoint = load_checkpoint()
    all_documents = []
    resumption_token = None
    batch_num = 0
    total_expected = None

    if checkpoint and Path(OUTPUT_FILE).exists():
        print(f"\nFound checkpoint from {checkpoint['timestamp']}")
        print(f"Documents collected: {checkpoint['documents_collected']}")
        print(f"Batch number: {checkpoint['batch_number']}")

        # Load existing documents
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                data = json.load(f)
                all_documents = data.get("documents", [])
            resumption_token = checkpoint.get("resumption_token")
            batch_num = checkpoint.get("batch_number", 0)
            total_expected = checkpoint.get("total_expected")
            print(f"Resuming from batch {batch_num} with {len(all_documents)} existing documents")
        except Exception as e:
            print(f"Could not load checkpoint data: {e}")
            print("Starting fresh harvest...")
            all_documents = []
            resumption_token = None
            batch_num = 0

    print("\nStarting harvest...")

    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        batch_num += 1

        print(f"\n[Batch {batch_num}] Fetching records...", end=" ", flush=True)

        records, new_token, result = harvest_batch(resumption_token)

        if records is None:
            consecutive_errors += 1
            print(f"ERROR: {result}")

            if consecutive_errors >= max_consecutive_errors:
                print(f"\n{max_consecutive_errors} consecutive errors. Stopping.")
                break

            print(
                f"Waiting 10 seconds before retry ({consecutive_errors}/{max_consecutive_errors})..."
            )
            time.sleep(10)
            continue

        consecutive_errors = 0

        # First batch - get total size
        if batch_num == 1 and result:
            try:
                total_expected = int(result)
                print(f"Total expected documents: {total_expected}")
            except Exception:
                pass

        all_documents.extend(records)

        active_count = len([r for r in records if r.get("status") != "deleted"])
        deleted_count = len(records) - active_count

        print(f"Got {len(records)} records ({active_count} active, {deleted_count} deleted)")
        print(f"Total collected: {len(all_documents)}", end="")

        if total_expected:
            pct = (len(all_documents) / int(total_expected)) * 100
            print(f" ({pct:.1f}% of {total_expected})")
        else:
            print()

        # Save checkpoint every 10 batches
        if batch_num % 10 == 0:
            save_checkpoint(all_documents, new_token, batch_num, total_expected)

            # Also save documents periodically
            output_data = {
                "source": "DiVA OAI-PMH",
                "institution": "Umea University (umu)",
                "endpoint": BASE_URL,
                "metadataPrefix": METADATA_PREFIX,
                "harvest_started": start_time.isoformat(),
                "harvest_timestamp": datetime.now().isoformat(),
                "status": "in_progress",
                "total_expected": total_expected,
                "documents_collected": len(all_documents),
                "documents": all_documents,
            }

            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            print(f"[Checkpoint saved: {len(all_documents)} documents]")

        # Check if done
        if not new_token:
            print("\n" + "=" * 60)
            print("HARVEST COMPLETE - No more resumptionToken")
            break

        resumption_token = new_token

        # Rate limit
        time.sleep(RATE_LIMIT)

    # Final save
    end_time = datetime.now()
    duration = end_time - start_time

    active_docs = [d for d in all_documents if d.get("status") != "deleted"]
    deleted_docs = [d for d in all_documents if d.get("status") == "deleted"]

    # Count by publication type
    pub_types = {}
    for doc in active_docs:
        for genre in doc.get("genres", []):
            if genre.get("authority") == "diva" and genre.get("type") == "publicationTypeCode":
                pt = genre.get("value", "unknown")
                pub_types[pt] = pub_types.get(pt, 0) + 1

    output_data = {
        "source": "DiVA OAI-PMH",
        "institution": "Umea University (umu)",
        "endpoint": BASE_URL,
        "metadataPrefix": METADATA_PREFIX,
        "harvest_started": start_time.isoformat(),
        "harvest_completed": end_time.isoformat(),
        "duration_seconds": duration.total_seconds(),
        "status": "completed",
        "statistics": {
            "total_records": len(all_documents),
            "active_records": len(active_docs),
            "deleted_records": len(deleted_docs),
            "batches_processed": batch_num,
            "publication_types": pub_types,
        },
        "documents": all_documents,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Remove checkpoint file
    with suppress(Exception):
        Path(CHECKPOINT_FILE).unlink()

    print("\n" + "=" * 60)
    print("HARVEST SUMMARY")
    print("=" * 60)
    print(f"Total records:   {len(all_documents):,}")
    print(f"Active records:  {len(active_docs):,}")
    print(f"Deleted records: {len(deleted_docs):,}")
    print(f"Batches:         {batch_num}")
    print(f"Duration:        {duration}")
    print("\nPublication types:")
    for pt, count in sorted(pub_types.items(), key=lambda x: -x[1])[:10]:
        print(f"  {pt}: {count:,}")
    print(f"\nOutput saved to: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
