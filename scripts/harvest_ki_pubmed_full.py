#!/usr/bin/env python3
"""
FULL HARVEST: Karolinska Institutet Publications via PubMed E-utilities
=======================================================================
Endpoint: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
Query: "Karolinska Institutet"[Affiliation]
Target: ~88,000 documents

Rate limit: NCBI requires max 3 requests/second without API key
           10 requests/second with API key
           We use 1 request/second for safety

Batch size: 500 records per request (max 10,000 with API key)
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
SEARCH_TERM = '"Karolinska Institutet"[Affiliation]'
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/diva_full_ki.json"
CHECKPOINT_FILE = (
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/ki_pubmed_checkpoint.json"
)
BATCH_SIZE = 500  # Records per fetch request
RATE_LIMIT_SECONDS = 0.4  # ~2.5 requests/second (safe without API key)


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


def save_checkpoint(retstart, total_records, batch_num, webenv, query_key):
    """Save checkpoint for resume capability."""
    checkpoint = {
        "retstart": retstart,
        "total_records": total_records,
        "batch_num": batch_num,
        "webenv": webenv,
        "query_key": query_key,
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
    print("FULL HARVEST: Karolinska Institutet via PubMed")
    print("=" * 70)
    print(f"Search term: {SEARCH_TERM}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Rate limit: {RATE_LIMIT_SECONDS}s between requests")
    print("=" * 70)

    all_records = []
    start_time = time.time()

    # Initial search to get total count and history
    print("\nSearching PubMed...")
    search_result = search_pubmed(SEARCH_TERM)
    total_count = search_result["count"]
    webenv = search_result["webenv"]
    query_key = search_result["query_key"]

    print(f"Total documents found: {total_count:,}")
    print(f"WebEnv: {webenv[:30]}...")

    # Check for existing data
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
    retstart = 0
    batch_num = 0
    checkpoint = load_checkpoint()
    if checkpoint and checkpoint.get("retstart", 0) > 0:
        # Need to redo search to get fresh webenv
        print(f"\nFound checkpoint at position {checkpoint['retstart']}")
        retstart = checkpoint["retstart"]
        batch_num = checkpoint["batch_num"]

    try:
        while retstart < total_count:
            batch_num += 1
            current_batch_size = min(BATCH_SIZE, total_count - retstart)

            print(
                f"\n[Batch {batch_num}] Fetching {current_batch_size} records from {retstart}...",
                end=" ",
                flush=True,
            )

            try:
                xml_response = fetch_records(webenv, query_key, retstart, current_batch_size)
                records = parse_pubmed_xml(xml_response)

                all_records.extend(records)
                retstart += BATCH_SIZE

                elapsed = time.time() - start_time
                rate = len(all_records) / elapsed * 60 if elapsed > 0 else 0
                pct = len(all_records) / total_count * 100

                print(
                    f"Got {len(records)}. Total: {len(all_records):,} / {total_count:,} ({pct:.1f}%)"
                )

                # Save checkpoint every 10 batches
                if batch_num % 10 == 0:
                    save_checkpoint(retstart, len(all_records), batch_num, webenv, query_key)

                    # Save intermediate results
                    result = {
                        "source": "pubmed",
                        "institution": "Karolinska Institutet",
                        "search_term": SEARCH_TERM,
                        "total_available": total_count,
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

                # Rate limiting
                time.sleep(RATE_LIMIT_SECONDS)

            except requests.exceptions.RequestException as e:
                print(f"\nNetwork error: {e}")
                print("Waiting 30 seconds before retry...")
                time.sleep(30)
                # Redo search to get fresh webenv
                search_result = search_pubmed(SEARCH_TERM)
                webenv = search_result["webenv"]
                query_key = search_result["query_key"]
                continue

            except Exception as e:
                print(f"\nError in batch {batch_num}: {e}")
                print("Waiting 10 seconds before retry...")
                time.sleep(10)
                continue

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Saving progress...")

    # Final save
    elapsed = time.time() - start_time
    rate = len(all_records) / elapsed * 60 if elapsed > 0 else 0

    result = {
        "source": "pubmed",
        "institution": "Karolinska Institutet",
        "search_term": SEARCH_TERM,
        "total_available": total_count,
        "total_records": len(all_records),
        "harvested_at": datetime.now().isoformat(),
        "elapsed_minutes": round(elapsed / 60, 1),
        "rate_per_minute": round(rate, 1),
        "status": "complete" if len(all_records) >= total_count else "interrupted",
        "records": all_records,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)

    # Remove checkpoint if complete
    if len(all_records) >= total_count:
        checkpoint_path = Path(CHECKPOINT_FILE)
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    print("\n" + "=" * 70)
    print("OPERATION STATUS")
    print("=" * 70)
    print(f"Documents fetched: {len(all_records):,}")
    print(f"Total available: {total_count:,}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print(f"Rate: {rate:.0f} docs/minute")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Status: {'COMPLETE' if len(all_records) >= total_count else 'INTERRUPTED'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
