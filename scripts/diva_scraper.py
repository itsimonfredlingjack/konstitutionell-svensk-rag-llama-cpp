#!/usr/bin/env python3
"""
DiVA MEGA-SCRAPE - OAI-PMH Harvester for Swedish Universities
==============================================================
Harvests academic publications from 5 major Swedish universities.

Rate limit: 1 request/second
Target: 1000 docs per university for initial test
"""

import json
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# OAI-PMH Namespaces
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "mods": "http://www.loc.gov/mods/v3",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


@dataclass
class UniversityConfig:
    """Configuration for each university OAI-PMH endpoint"""

    code: str
    name: str
    base_url: str
    metadata_prefix: str
    total_docs: int


UNIVERSITIES = {
    "uu": UniversityConfig(
        code="uu",
        name="Uppsala universitet",
        base_url="https://uu.diva-portal.org/dice/oai",
        metadata_prefix="swepub_mods",
        total_docs=128767,
    ),
    "su": UniversityConfig(
        code="su",
        name="Stockholms universitet",
        base_url="https://su.diva-portal.org/dice/oai",
        metadata_prefix="swepub_mods",
        total_docs=31890,
    ),
    "kth": UniversityConfig(
        code="kth",
        name="KTH",
        base_url="https://kth.diva-portal.org/dice/oai",
        metadata_prefix="swepub_mods",
        total_docs=58678,
    ),
    "gu": UniversityConfig(
        code="gu",
        name="Goteborgs universitet",
        base_url="https://gup.ub.gu.se/oai",
        metadata_prefix="mods",
        total_docs=241769,
    ),
    "lu": UniversityConfig(
        code="lu",
        name="Lunds universitet",
        base_url="https://lup.lub.lu.se/oai",
        metadata_prefix="swepub_mods",
        total_docs=242111,
    ),
}


@dataclass
class HarvestStats:
    """Statistics for harvest operation"""

    university: str
    docs_fetched: int = 0
    batches_processed: int = 0
    errors: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    rate_limit_hits: int = 0
    last_resumption_token: str | None = None


def parse_mods_record(record_elem) -> dict[str, Any]:
    """Parse a MODS record into a structured dictionary"""
    doc = {"source": "diva", "harvested_at": datetime.now().isoformat()}

    # Get identifier from header
    header = record_elem.find("oai:header", NAMESPACES)
    if header is not None:
        identifier = header.find("oai:identifier", NAMESPACES)
        if identifier is not None and identifier.text:
            doc["oai_identifier"] = identifier.text
            # Extract DiVA ID: oai:DiVA.org:uu-331564 -> uu-331564
            parts = identifier.text.split(":")
            if len(parts) >= 3:
                doc["diva_id"] = parts[-1]

        datestamp = header.find("oai:datestamp", NAMESPACES)
        if datestamp is not None and datestamp.text:
            doc["datestamp"] = datestamp.text

        # Get all setSpecs (classifications)
        setspecs = header.findall("oai:setSpec", NAMESPACES)
        doc["sets"] = [s.text for s in setspecs if s.text]

    # Get metadata
    metadata = record_elem.find("oai:metadata", NAMESPACES)
    if metadata is None:
        return doc

    mods = metadata.find("mods:mods", NAMESPACES)
    if mods is None:
        # Try without namespace prefix (some responses differ)
        mods = metadata.find(".//{http://www.loc.gov/mods/v3}mods")
    if mods is None:
        return doc

    # Title
    title_info = mods.find(".//{http://www.loc.gov/mods/v3}titleInfo")
    if title_info is not None:
        title = title_info.find("{http://www.loc.gov/mods/v3}title")
        subtitle = title_info.find("{http://www.loc.gov/mods/v3}subTitle")
        doc["title"] = title.text if title is not None and title.text else ""
        if subtitle is not None and subtitle.text:
            doc["subtitle"] = subtitle.text
            doc["title"] = f"{doc['title']}: {subtitle.text}"

    # Authors
    authors = []
    for name in mods.findall('.//{http://www.loc.gov/mods/v3}name[@type="personal"]'):
        family = name.find('{http://www.loc.gov/mods/v3}namePart[@type="family"]')
        given = name.find('{http://www.loc.gov/mods/v3}namePart[@type="given"]')
        affiliation = name.find("{http://www.loc.gov/mods/v3}affiliation")

        author = {}
        if family is not None and family.text:
            author["family"] = family.text
        if given is not None and given.text:
            author["given"] = given.text
        if affiliation is not None and affiliation.text:
            author["affiliation"] = affiliation.text

        if author:
            authors.append(author)

    if authors:
        doc["authors"] = authors

    # Date
    date_issued = mods.find(".//{http://www.loc.gov/mods/v3}dateIssued")
    if date_issued is not None and date_issued.text:
        doc["date_issued"] = date_issued.text

    # Language
    lang_term = mods.find(".//{http://www.loc.gov/mods/v3}languageTerm")
    if lang_term is not None and lang_term.text:
        doc["language"] = lang_term.text

    # Subjects
    subjects = []
    for subject in mods.findall(".//{http://www.loc.gov/mods/v3}subject"):
        lang = subject.get("{http://www.w3.org/XML/1998/namespace}lang", "unknown")
        topics = []
        for topic in subject.findall("{http://www.loc.gov/mods/v3}topic"):
            if topic.text:
                topics.append(topic.text)
        if topics:
            subjects.append({"lang": lang, "topics": topics})

    if subjects:
        doc["subjects"] = subjects

    # Genre/Publication type
    genres = []
    for genre in mods.findall(".//{http://www.loc.gov/mods/v3}genre"):
        if genre.text:
            genres.append(
                {
                    "value": genre.text,
                    "authority": genre.get("authority", ""),
                    "type": genre.get("type", ""),
                }
            )
    if genres:
        doc["genres"] = genres

    # Abstract
    abstracts = []
    for abstract in mods.findall(".//{http://www.loc.gov/mods/v3}abstract"):
        if abstract.text:
            lang = abstract.get("{http://www.w3.org/XML/1998/namespace}lang", "unknown")
            abstracts.append({"lang": lang, "text": abstract.text})
    if abstracts:
        doc["abstracts"] = abstracts

    # Identifiers (URI, ISBN, ISSN, DOI)
    identifiers = {}
    for identifier in mods.findall(".//{http://www.loc.gov/mods/v3}identifier"):
        id_type = identifier.get("type", "unknown")
        if identifier.text:
            identifiers[id_type] = identifier.text
    if identifiers:
        doc["identifiers"] = identifiers

    # Full text URL
    for location in mods.findall(".//{http://www.loc.gov/mods/v3}location"):
        for url in location.findall("{http://www.loc.gov/mods/v3}url"):
            display_label = url.get("displayLabel", "")
            if "fulltext" in display_label.lower() and url.text:
                doc["fulltext_url"] = url.text
                break

    # Record info
    record_info = mods.find(".//{http://www.loc.gov/mods/v3}recordInfo")
    if record_info is not None:
        record_id = record_info.find("{http://www.loc.gov/mods/v3}recordIdentifier")
        if record_id is not None and record_id.text:
            doc["record_identifier"] = record_id.text

        content_source = record_info.find("{http://www.loc.gov/mods/v3}recordContentSource")
        if content_source is not None and content_source.text:
            doc["content_source"] = content_source.text

    return doc


def parse_dc_record(record_elem) -> dict[str, Any]:
    """Parse a Dublin Core record into a structured dictionary"""
    doc = {"source": "diva", "harvested_at": datetime.now().isoformat()}

    # Get identifier from header
    header = record_elem.find("oai:header", NAMESPACES)
    if header is not None:
        identifier = header.find("oai:identifier", NAMESPACES)
        if identifier is not None and identifier.text:
            doc["oai_identifier"] = identifier.text

        datestamp = header.find("oai:datestamp", NAMESPACES)
        if datestamp is not None and datestamp.text:
            doc["datestamp"] = datestamp.text

    # Get metadata
    metadata = record_elem.find("oai:metadata", NAMESPACES)
    if metadata is None:
        return doc

    dc = metadata.find("oai_dc:dc", NAMESPACES)
    if dc is None:
        dc = metadata.find(".//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
    if dc is None:
        return doc

    # Map DC elements
    dc_mappings = {
        "title": "dc:title",
        "creator": "dc:creator",
        "subject": "dc:subject",
        "description": "dc:description",
        "publisher": "dc:publisher",
        "contributor": "dc:contributor",
        "date": "dc:date",
        "type": "dc:type",
        "format": "dc:format",
        "identifier": "dc:identifier",
        "source": "dc:source",
        "language": "dc:language",
        "relation": "dc:relation",
        "coverage": "dc:coverage",
        "rights": "dc:rights",
    }

    for field_name, xpath in dc_mappings.items():
        elements = dc.findall(xpath, NAMESPACES)
        if not elements:
            elements = dc.findall(f".//{{{NAMESPACES['dc']}}}{field_name.split(':')[-1]}")

        values = [e.text for e in elements if e.text]
        if len(values) == 1:
            doc[field_name] = values[0]
        elif len(values) > 1:
            doc[field_name] = values

    return doc


def harvest_university(
    config: UniversityConfig, output_dir: Path, max_docs: int = 1000, rate_limit: float = 1.0
) -> HarvestStats:
    """
    Harvest documents from a university OAI-PMH endpoint.

    Args:
        config: University configuration
        output_dir: Directory to save JSON output
        max_docs: Maximum documents to harvest (for testing)
        rate_limit: Seconds between requests

    Returns:
        HarvestStats with operation statistics
    """
    stats = HarvestStats(university=config.name)
    documents = []
    resumption_token = None

    print(f"\n{'=' * 60}")
    print(f"HARVESTING: {config.name} ({config.code})")
    print(f"Endpoint: {config.base_url}")
    print(f"Format: {config.metadata_prefix}")
    print(f"Total available: {config.total_docs:,} docs")
    print(f"Target: {max_docs:,} docs")
    print(f"{'=' * 60}\n")

    # Determine parser based on metadata format
    if "mods" in config.metadata_prefix.lower():
        parse_record = parse_mods_record
    else:
        parse_record = parse_dc_record

    session = requests.Session()
    session.headers.update(
        {"User-Agent": "DiVA-Harvester/1.0 (Swedish Gov Scraper; contact: ai-server@local)"}
    )

    while stats.docs_fetched < max_docs:
        try:
            # Build request URL
            if resumption_token:
                url = f"{config.base_url}?verb=ListRecords&resumptionToken={resumption_token}"
            else:
                url = f"{config.base_url}?verb=ListRecords&metadataPrefix={config.metadata_prefix}"

            # Make request
            response = session.get(url, timeout=60)

            if response.status_code == 429:
                print("  [RATE LIMIT] Waiting 30s...")
                stats.rate_limit_hits += 1
                time.sleep(30)
                continue

            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Check for errors
            error = root.find(".//oai:error", NAMESPACES)
            if error is not None:
                error_code = error.get("code", "unknown")
                error_msg = error.text or "No message"
                print(f"  [ERROR] {error_code}: {error_msg}")
                stats.errors += 1

                if error_code == "noRecordsMatch":
                    print("  No records found. Stopping.")
                    break
                elif error_code == "badResumptionToken":
                    print("  Bad token. Restarting from beginning.")
                    resumption_token = None
                    continue
                else:
                    break

            # Extract records
            list_records = root.find(".//oai:ListRecords", NAMESPACES)
            if list_records is None:
                print("  [WARNING] No ListRecords element found")
                stats.errors += 1
                break

            records = list_records.findall("oai:record", NAMESPACES)
            batch_count = len(records)

            for record in records:
                if stats.docs_fetched >= max_docs:
                    break

                # Check if record is deleted
                header = record.find("oai:header", NAMESPACES)
                if header is not None and header.get("status") == "deleted":
                    continue

                doc = parse_record(record)
                doc["university"] = config.code
                documents.append(doc)
                stats.docs_fetched += 1

            stats.batches_processed += 1

            # Progress update
            progress = (stats.docs_fetched / max_docs) * 100
            print(
                f"  Batch {stats.batches_processed}: +{batch_count} records | "
                f"Total: {stats.docs_fetched:,}/{max_docs:,} ({progress:.1f}%)"
            )

            # Get resumption token
            token_elem = list_records.find("oai:resumptionToken", NAMESPACES)
            if token_elem is not None and token_elem.text:
                resumption_token = token_elem.text
                stats.last_resumption_token = resumption_token
            else:
                print("  [INFO] No more records (no resumption token)")
                break

            # Rate limiting
            time.sleep(rate_limit)

        except requests.exceptions.Timeout:
            print("  [TIMEOUT] Retrying in 10s...")
            stats.errors += 1
            time.sleep(10)
            continue

        except requests.exceptions.RequestException as e:
            print(f"  [REQUEST ERROR] {e}")
            stats.errors += 1
            if stats.errors > 5:
                print("  Too many errors. Stopping.")
                break
            time.sleep(5)
            continue

        except ET.ParseError as e:
            print(f"  [XML ERROR] {e}")
            stats.errors += 1
            break

    stats.end_time = datetime.now()

    # Save to JSON
    output_file = output_dir / f"diva_batch1_{config.code}.json"
    output_data = {
        "metadata": {
            "university": config.name,
            "code": config.code,
            "harvested_at": stats.start_time.isoformat(),
            "completed_at": stats.end_time.isoformat(),
            "total_docs": len(documents),
            "source_url": config.base_url,
            "metadata_format": config.metadata_prefix,
            "last_resumption_token": stats.last_resumption_token,
        },
        "documents": documents,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n  Saved: {output_file}")
    print(f"  Documents: {len(documents):,}")

    return stats


def main():
    """Main entry point for DiVA harvester"""
    output_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse arguments
    max_docs = 1000
    selected_unis = list(UNIVERSITIES.keys())

    if len(sys.argv) > 1:
        try:
            max_docs = int(sys.argv[1])
        except ValueError:
            # Assume it's a university code
            selected_unis = sys.argv[1:]

    if len(sys.argv) > 2:
        selected_unis = sys.argv[2:]

    print(f"""
    =============================================
    DiVA MEGA-SCRAPE - Batch 1
    =============================================
    Target docs per university: {max_docs:,}
    Universities: {", ".join(selected_unis)}
    Output directory: {output_dir}
    Rate limit: 1 req/sec
    =============================================
    """)

    all_stats = []

    for uni_code in selected_unis:
        if uni_code not in UNIVERSITIES:
            print(f"Unknown university: {uni_code}")
            continue

        config = UNIVERSITIES[uni_code]
        stats = harvest_university(config, output_dir, max_docs=max_docs)
        all_stats.append(stats)

    # Final report
    print(f"\n{'=' * 60}")
    print("OPERATION COMPLETE - FINAL REPORT")
    print(f"{'=' * 60}\n")

    total_docs = 0
    total_errors = 0

    for stats in all_stats:
        duration = (stats.end_time - stats.start_time).total_seconds() if stats.end_time else 0
        rate = stats.docs_fetched / duration if duration > 0 else 0

        print(f"{stats.university}:")
        print(f"  Documents fetched: {stats.docs_fetched:,}")
        print(f"  Batches processed: {stats.batches_processed}")
        print(f"  Errors: {stats.errors}")
        print(f"  Rate limit hits: {stats.rate_limit_hits}")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Rate: {rate:.2f} docs/sec")
        print()

        total_docs += stats.docs_fetched
        total_errors += stats.errors

    print(f"TOTAL: {total_docs:,} documents, {total_errors} errors")
    print("\nOutput files:")
    for uni_code in selected_unis:
        if uni_code in UNIVERSITIES:
            print(f"  {output_dir}/diva_batch1_{uni_code}.json")


if __name__ == "__main__":
    main()
