#!/usr/bin/env python3
"""
FULL HARVEST: Karolinska Institutet Publications via PubMed E-utilities (v2)
============================================================================
Uses year-based batching to work around the 10,000 record WebEnv limit.

Endpoint: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
Query: "Karolinska Institutet"[Affiliation]
Target: ~88,000 documents

Strategy: Query by year ranges to stay under 10,000 per query
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BASE_TERM = '"Karolinska Institutet"[Affiliation]'
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_ki.json"
CHECKPOINT_FILE = (
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/ki_pubmed_v2_checkpoint.json"
)
BATCH_SIZE = 500  # Records per fetch request
RATE_LIMIT_SECONDS = 0.4  # ~2.5 requests/second

# Year ranges to process - single years for recent (high volume) years
# PubMed has 10,000 record limit per WebEnv, so we need smaller ranges
YEAR_RANGES = [
    (2025, 2025),  # Current year
    (2024, 2024),  # ~7000 records
    (2023, 2023),  # ~7000 records
    (2022, 2022),  # ~7000 records
    (2021, 2021),  # ~7000 records
    (2020, 2020),  # ~6000 records
    (2019, 2019),  # ~6000 records
    (2018, 2018),  # ~6000 records
    (2017, 2017),  # ~5000 records
    (2016, 2016),  # ~5000 records
    (2015, 2015),  # ~4000 records
    (2014, 2014),
    (2013, 2013),
    (2012, 2012),
    (2011, 2011),
    (2010, 2010),
    (2008, 2009),  # 2 years ~5000 records
    (2006, 2007),
    (2004, 2005),
    (2002, 2003),
    (2000, 2001),
    (1998, 1999),
    (1996, 1997),
    (1994, 1995),
    (1992, 1993),
    (1990, 1991),
    (1985, 1989),  # 5 years
    (1980, 1984),
    (1970, 1979),  # Decade
    (1900, 1969),  # All earlier records
]


def search_pubmed(term, retmax=0):
    """Search PubMed and get total count and IDs."""
    params = {"db": "pubmed", "term": term, "retmax": retmax, "usehistory": "y", "retmode": "json"}

    response = requests.get(ESEARCH_URL, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()
    result = data.get("esearchresult", {})

    return {
        "count": int(result.get("count", 0)),
        "webenv": result.get("webenv"),
        "query_key": result.get("querykey"),
    }


def fetch_records(webenv, query_key, retstart, retmax):
    """Fetch a batch of records using WebEnv and query_key."""
    params = {
        "db": "pubmed",
        "query_key": query_key,
        "WebEnv": webenv,
        "retstart": retstart,
        "retmax": retmax,
        "rettype": "xml",
        "retmode": "xml",
    }

    response = requests.get(EFETCH_URL, params=params, timeout=120)
    response.raise_for_status()

    return response.text


def parse_pubmed_xml(xml_text):
    """Parse PubMed XML and extract structured records."""
    records = []

    try:
        root = ET.fromstring(xml_text)

        for article in root.findall(".//PubmedArticle"):
            record = parse_article(article)
            if record:
                records.append(record)

    except ET.ParseError as e:
        print(f"XML Parse error: {e}")

    return records


def parse_article(article):
    """Parse a single PubMed article element."""
    try:
        record = {
            "source": "pubmed",
            "institution": "Karolinska Institutet",
            "harvested_at": datetime.now().isoformat(),
        }

        # PMID
        medline = article.find(".//MedlineCitation")
        if medline is not None:
            pmid_elem = medline.find("PMID")
            if pmid_elem is not None:
                record["pmid"] = pmid_elem.text

        # Article data
        art = article.find(".//Article")
        if art is None:
            return record

        # Journal
        journal = art.find(".//Journal")
        if journal is not None:
            title_elem = journal.find("Title")
            if title_elem is not None:
                record["journal"] = title_elem.text

            iso_elem = journal.find("ISOAbbreviation")
            if iso_elem is not None:
                record["journal_abbrev"] = iso_elem.text

            # Publication date
            pub_date = journal.find(".//PubDate")
            if pub_date is not None:
                year = pub_date.find("Year")
                month = pub_date.find("Month")
                day = pub_date.find("Day")

                date_parts = []
                if year is not None:
                    date_parts.append(year.text)
                    record["pub_year"] = year.text
                if month is not None:
                    date_parts.append(month.text)
                if day is not None:
                    date_parts.append(day.text)

                if date_parts:
                    record["pub_date"] = "-".join(date_parts)

        # Article title
        title_elem = art.find(".//ArticleTitle")
        if title_elem is not None:
            record["title"] = "".join(title_elem.itertext())

        # Abstract
        abstract = art.find(".//Abstract")
        if abstract is not None:
            abstract_parts = []
            for text_elem in abstract.findall(".//AbstractText"):
                label = text_elem.get("Label", "")
                text = "".join(text_elem.itertext())
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            record["abstract"] = " ".join(abstract_parts)

        # Authors with affiliations
        authors = []
        author_list = art.find(".//AuthorList")
        if author_list is not None:
            for author in author_list.findall("Author"):
                author_data = {}

                last_name = author.find("LastName")
                fore_name = author.find("ForeName")
                initials = author.find("Initials")
                collective = author.find("CollectiveName")

                if last_name is not None:
                    author_data["last_name"] = last_name.text
                if fore_name is not None:
                    author_data["fore_name"] = fore_name.text
                if initials is not None:
                    author_data["initials"] = initials.text
                if collective is not None:
                    author_data["collective_name"] = collective.text

                # Affiliations
                affiliations = []
                for aff in author.findall(".//AffiliationInfo/Affiliation"):
                    if aff.text:
                        affiliations.append(aff.text)
                if affiliations:
                    author_data["affiliations"] = affiliations

                if author_data:
                    authors.append(author_data)

        record["authors"] = authors

        # Keywords
        keywords = []
        for kw in article.findall(".//KeywordList/Keyword"):
            if kw.text:
                keywords.append(kw.text)
        if keywords:
            record["keywords"] = keywords

        # MeSH terms
        mesh_terms = []
        for mesh in article.findall(".//MeshHeadingList/MeshHeading"):
            descriptor = mesh.find("DescriptorName")
            if descriptor is not None and descriptor.text:
                mesh_terms.append(descriptor.text)
        if mesh_terms:
            record["mesh_terms"] = mesh_terms

        # Publication types
        pub_types = []
        for pt in art.findall(".//PublicationTypeList/PublicationType"):
            if pt.text:
                pub_types.append(pt.text)
        if pub_types:
            record["publication_types"] = pub_types

        # Language
        lang = art.find(".//Language")
        if lang is not None:
            record["language"] = lang.text

        # IDs (DOI, PMC, etc)
        identifiers = {}
        for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = article_id.get("IdType", "unknown")
            if article_id.text:
                identifiers[id_type] = article_id.text
        if identifiers:
            record["identifiers"] = identifiers

        # Grant information
        grants = []
        for grant in article.findall(".//GrantList/Grant"):
            grant_data = {}
            grant_id = grant.find("GrantID")
            agency = grant.find("Agency")
            country = grant.find("Country")

            if grant_id is not None:
                grant_data["id"] = grant_id.text
            if agency is not None:
                grant_data["agency"] = agency.text
            if country is not None:
                grant_data["country"] = country.text

            if grant_data:
                grants.append(grant_data)
        if grants:
            record["grants"] = grants

        return record

    except Exception as e:
        print(f"Error parsing article: {e}")
        return None


def save_checkpoint(year_range_idx, retstart, total_records):
    """Save checkpoint for resume capability."""
    checkpoint = {
        "year_range_idx": year_range_idx,
        "retstart": retstart,
        "total_records": total_records,
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


def harvest_year_range(start_year, end_year, existing_pmids, max_records=9500):
    """Harvest all records for a given year range.

    Args:
        max_records: Stop fetching after this many records to avoid WebEnv limit
    """
    term = f"{BASE_TERM} AND {start_year}:{end_year}[dp]"

    print(f"\n  Searching for {start_year}-{end_year}...", end=" ")
    search_result = search_pubmed(term)
    count = search_result["count"]
    webenv = search_result["webenv"]
    query_key = search_result["query_key"]

    print(f"Found {count:,} records")

    if count == 0:
        return []

    if count > max_records:
        print(
            f"    WARNING: {count:,} records exceeds limit of {max_records}. Will fetch first {max_records}."
        )
        count = max_records

    records = []
    retstart = 0
    batch_num = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    while retstart < count and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
        batch_num += 1
        current_batch_size = min(BATCH_SIZE, count - retstart)

        try:
            xml_response = fetch_records(webenv, query_key, retstart, current_batch_size)
            batch_records = parse_pubmed_xml(xml_response)

            # Filter out duplicates
            new_records = []
            for rec in batch_records:
                pmid = rec.get("pmid")
                if pmid and pmid not in existing_pmids:
                    existing_pmids.add(pmid)
                    new_records.append(rec)

            records.extend(new_records)
            retstart += BATCH_SIZE
            consecutive_errors = 0  # Reset on success

            pct = retstart / count * 100
            print(
                f"    [{start_year}-{end_year}] Batch {batch_num}: {len(records):,} new records ({pct:.0f}%)",
                end="\r",
            )

            time.sleep(RATE_LIMIT_SECONDS)

        except requests.exceptions.RequestException as e:
            consecutive_errors += 1
            if "400" in str(e) and retstart >= 9500:
                # Hit the WebEnv limit - this is expected, stop gracefully
                print(f"\n    Reached WebEnv limit at {retstart} records. Moving on.")
                break
            print(f"\n    Network error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
            print("    Waiting 30 seconds before retry...")
            time.sleep(30)
            # Redo search to get fresh webenv
            search_result = search_pubmed(term)
            webenv = search_result["webenv"]
            query_key = search_result["query_key"]
            continue

        except Exception as e:
            consecutive_errors += 1
            print(f"\n    Error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
            time.sleep(10)
            continue

    print(f"    [{start_year}-{end_year}] Complete: {len(records):,} new records         ")
    return records


def main():
    print("=" * 70)
    print("FULL HARVEST: Karolinska Institutet via PubMed (v2)")
    print("=" * 70)
    print(f"Base term: {BASE_TERM}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Year ranges: {len(YEAR_RANGES)}")
    print(f"Rate limit: {RATE_LIMIT_SECONDS}s between requests")
    print("=" * 70)

    all_records = []
    existing_pmids = set()
    start_time = time.time()

    # Load existing data
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

                # Build PMID set for deduplication
                for rec in all_records:
                    pmid = rec.get("pmid")
                    if pmid:
                        existing_pmids.add(pmid)

                print(
                    f"Loaded {len(all_records)} existing records ({len(existing_pmids)} unique PMIDs)"
                )
        except Exception as e:
            print(f"Could not load existing: {e}")

    # Check for checkpoint
    start_idx = 0
    checkpoint = load_checkpoint()
    if checkpoint:
        start_idx = checkpoint.get("year_range_idx", 0)
        print(f"Resuming from year range index {start_idx}")

    # Get initial total count
    print("\nGetting total count...")
    initial_search = search_pubmed(BASE_TERM)
    total_available = initial_search["count"]
    print(f"Total available: {total_available:,}")

    try:
        for idx, (start_year, end_year) in enumerate(YEAR_RANGES[start_idx:], start=start_idx):
            print(f"\n[{idx+1}/{len(YEAR_RANGES)}] Processing years {start_year}-{end_year}")

            year_records = harvest_year_range(start_year, end_year, existing_pmids)
            all_records.extend(year_records)

            # Save progress after each year range
            elapsed = time.time() - start_time
            rate = len(all_records) / elapsed * 60 if elapsed > 0 else 0

            save_checkpoint(idx + 1, 0, len(all_records))

            result = {
                "source": "pubmed",
                "institution": "Karolinska Institutet",
                "search_term": BASE_TERM,
                "total_available": total_available,
                "total_records": len(all_records),
                "harvested_at": datetime.now().isoformat(),
                "elapsed_minutes": round(elapsed / 60, 1),
                "rate_per_minute": round(rate, 1),
                "status": "in_progress",
                "records": all_records,
            }

            with open(OUTPUT_FILE, "w") as f:
                json.dump(result, f, ensure_ascii=False)

            print(
                f"  Saved. Total: {len(all_records):,} | Rate: {rate:.0f}/min | Elapsed: {elapsed/60:.1f}m"
            )

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Saving progress...")

    # Final save
    elapsed = time.time() - start_time
    rate = len(all_records) / elapsed * 60 if elapsed > 0 else 0

    result = {
        "source": "pubmed",
        "institution": "Karolinska Institutet",
        "search_term": BASE_TERM,
        "total_available": total_available,
        "total_records": len(all_records),
        "harvested_at": datetime.now().isoformat(),
        "elapsed_minutes": round(elapsed / 60, 1),
        "rate_per_minute": round(rate, 1),
        "status": "complete",
        "records": all_records,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)

    # Remove checkpoint if complete
    checkpoint_path = Path(CHECKPOINT_FILE)
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    print("\n" + "=" * 70)
    print("OPERATION STATUS")
    print("=" * 70)
    print(f"Documents fetched: {len(all_records):,}")
    print(f"Total available: {total_available:,}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print(f"Rate: {rate:.0f} docs/minute")
    print(f"Output: {OUTPUT_FILE}")
    print("Status: COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
