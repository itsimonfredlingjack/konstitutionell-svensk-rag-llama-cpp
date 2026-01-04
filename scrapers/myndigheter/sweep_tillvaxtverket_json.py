#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET JSON
Extract data from embedded JSON in HTML
"""

import hashlib
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests


def extract_json_data(url, headers):
    """Extract publication data from embedded JSON"""
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()

        # Find the specific JSON with publication data
        pattern = r"AppRegistry\.registerInitialState\('12\.[a-f0-9]+',(.+?)\);</script>"
        matches = re.findall(pattern, r.text, re.DOTALL)

        all_pubs = []

        for match in matches:
            try:
                data = json.loads(match)
                if "items" in data and isinstance(data["items"], list):
                    all_pubs.extend(data["items"])
            except json.JSONDecodeError:
                continue

        return all_pubs

    except Exception as e:
        print(f"  Error: {e}")
        return []


def scrape_with_json_pagination(base_url, headers, param_name, max_pages=20):
    """Scrape using JSON-embedded data with custom pagination param"""
    all_publications = []
    seen_ids = set()

    for page_num in range(1, max_pages + 1):
        try:
            if page_num == 1:
                url = base_url
            else:
                separator = "&" if "?" in base_url else "?"
                url = f"{base_url}{separator}{param_name}={page_num}"

            print(f"  Page {page_num}...", end=" ")

            pubs = extract_json_data(url, headers)

            new_pubs = 0
            for pub in pubs:
                if "identifier" in pub and pub["identifier"] not in seen_ids:
                    seen_ids.add(pub["identifier"])
                    all_publications.append(pub)
                    new_pubs += 1

            print(f"{new_pubs} new publications")

            if new_pubs == 0:
                break

            time.sleep(0.5)

        except Exception as e:
            print(f"  Error: {e}")
            break

    return all_publications


def main():
    print("=== TILLVÄXTVERKET JSON SWEEP ===\n")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # First, detect pagination parameter
    print("Detecting pagination parameter...")
    r = requests.get(
        "https://tillvaxtverket.se/tillvaxtverket/publikationer.publikation.html", headers=headers
    )
    param_match = re.search(r"page12_([a-f0-9]+)", r.text)
    current_param = (
        f"page12_{param_match.group(1)}" if param_match else "page12_732e53db184a85fc7bc27d7"
    )
    print(f"Using parameter: {current_param}\n")

    sections = [
        {
            "name": "Current Publications",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer.publikation.html",
            "param": current_param,
        },
        {
            "name": "Archived Publications",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer/arkiveradepublikationer.1576.html",
            "param": current_param,  # Usually same parameter
        },
    ]

    all_raw_pubs = []

    for section in sections:
        print(f"{section['name']}:")
        pubs = scrape_with_json_pagination(section["url"], headers, section["param"], max_pages=30)
        all_raw_pubs.extend(pubs)
        print(f"  Section total: {len(pubs)}\n")

    print(f"Total publications extracted: {len(all_raw_pubs)}")

    # Convert to document format
    documents = []

    for pub in all_raw_pubs:
        # Publication page
        pub_url = urljoin("https://tillvaxtverket.se", pub.get("link", ""))
        doc_id = hashlib.md5(pub_url.encode()).hexdigest()

        doc_type = "publication"
        categories = [cat["name"] for cat in pub.get("categories", [])]

        documents.append(
            {
                "id": doc_id,
                "url": pub_url,
                "title": pub.get("name", "Untitled"),
                "description": pub.get("description"),
                "date": pub.get("date", {}).get("readable"),
                "categories": categories,
                "source": "tillvaxtverket",
                "type": doc_type,
                "scraped_at": datetime.now().isoformat(),
            }
        )

    # Deduplicate
    unique_docs = {d["id"]: d for d in documents}
    documents = list(unique_docs.values())

    print(f"Unique documents after deduplication: {len(documents)}")

    # Summary
    summary = {
        "agency": "Tillväxtverket",
        "url": "tillvaxtverket.se",
        "scraped_at": datetime.now().isoformat(),
        "documents_scraped": len(documents),
        "types": {},
        "sample_docs": documents[:50],
    }

    for doc in documents:
        doc_type = doc["type"]
        summary["types"][doc_type] = summary["types"].get(doc_type, 0) + 1

    # Save
    output_path = (
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_sweep.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    docs_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_docs.json"
    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    print("\nFiles saved:")
    print(f"  {output_path}")
    print(f"  {docs_path}")

    print("\nType breakdown:")
    for doc_type, count in sorted(summary["types"].items(), key=lambda x: -x[1]):
        print(f"  {doc_type}: {count}")

    if len(documents) < 100:
        print(f"\n⚠️  FLAG: Only {len(documents)} documents (expected >100)")
    else:
        print(f"\n✓ SUCCESS: Collected {len(documents)} documents")


if __name__ == "__main__":
    main()
