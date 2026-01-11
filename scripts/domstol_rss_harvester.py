#!/usr/bin/env python3
"""
Swedish Courts RSS Harvester
Hämtar avgöranden från Högsta domstolen och Högsta förvaltningsdomstolen via RSS.

Bekräftade RSS-feeds:
- HFD: /feed/1092?searchPageId=1092&scope=decision (50 beslut)
- HD: /feed/1122?searchPageId=1122&scope=decision (60 beslut)
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")

# Bekräftade domstolar med RSS
COURTS = [
    {
        "id": "hfd",
        "name": "Högsta förvaltningsdomstolen",
        "rss_url": "https://www.domstol.se/feed/1092?searchPageId=1092&scope=decision",
        "base_url": "https://www.domstol.se/hogsta-forvaltningsdomstolen",
    },
    {
        "id": "hd",
        "name": "Högsta domstolen",
        "rss_url": "https://www.domstol.se/feed/1122?searchPageId=1122&scope=decision",
        "base_url": "https://www.domstol.se/hogsta-domstolen",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
}


def fetch_rss(url):
    """Fetch and parse RSS feed."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def parse_rss_items(xml_text):
    """Parse RSS items from XML."""
    root = ET.fromstring(xml_text)
    items = []

    for item in root.findall(".//item"):
        doc = {}

        title = item.find("title")
        if title is not None and title.text:
            doc["title"] = title.text.strip()

        link = item.find("link")
        if link is not None and link.text:
            doc["url"] = link.text.strip()

        description = item.find("description")
        if description is not None and description.text:
            doc["description"] = description.text.strip()

        pub_date = item.find("pubDate")
        if pub_date is not None and pub_date.text:
            doc["pub_date"] = pub_date.text.strip()

        guid = item.find("guid")
        if guid is not None and guid.text:
            doc["guid"] = guid.text.strip()

        if doc.get("title") or doc.get("url"):
            items.append(doc)

    return items


def fetch_decision_page(url):
    """Fetch full decision page and extract content."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        content = {}

        # Sök efter huvudinnehållet
        main = soup.find("main") or soup.find("article") or soup.find("div", class_="content")
        if main:
            content["full_text"] = main.get_text(separator="\n", strip=True)

        # Sök efter metadata
        meta_section = soup.find("div", class_="metadata") or soup.find("dl")
        if meta_section:
            content["metadata_text"] = meta_section.get_text(separator="\n", strip=True)

        # Extrahera målnummer från titel eller innehåll
        text = soup.get_text()
        mal_match = re.search(r"[BTPÖÄ]\s*\d+-\d+", text)
        if mal_match:
            content["case_number"] = mal_match.group(0)

        return content

    except Exception as e:
        return {"error": str(e)}


def harvest_court(court):
    """Harvest all decisions from a court's RSS feed."""
    print(f"\n{'=' * 60}")
    print(f"HARVESTING: {court['name']}")
    print(f"RSS: {court['rss_url']}")
    print(f"{'=' * 60}")

    try:
        xml_text = fetch_rss(court["rss_url"])
        items = parse_rss_items(xml_text)
        print(f"Found {len(items)} items in RSS")

    except Exception as e:
        print(f"ERROR fetching RSS: {e}")
        return []

    documents = []

    for i, item in enumerate(items, 1):
        doc = {
            "source": f"domstol_{court['id']}",
            "court": court["name"],
            "court_id": court["id"],
            **item,
            "harvested_at": datetime.now().isoformat(),
        }

        # Hämta fullständigt innehåll
        if item.get("url"):
            print(f"  [{i}/{len(items)}] {item.get('title', 'Unknown')[:50]}...")
            page_content = fetch_decision_page(item["url"])
            doc.update(page_content)
            time.sleep(0.5)  # Rate limit

        documents.append(doc)

    return documents


def main():
    print("=" * 70)
    print("SWEDISH COURTS RSS HARVESTER")
    print("=" * 70)
    print(f"Courts: {len(COURTS)}")
    for court in COURTS:
        print(f"  - {court['name']} ({court['id']})")
    print("=" * 70)

    start_time = datetime.now()
    all_documents = []
    reports = []

    for court in COURTS:
        docs = harvest_court(court)
        all_documents.extend(docs)

        reports.append({"court": court["name"], "id": court["id"], "count": len(docs)})

    # Spara alla dokument
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / "domstol_avgoranden.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "domstol.se",
                "harvested_at": datetime.now().isoformat(),
                "total_documents": len(all_documents),
                "courts": reports,
                "documents": all_documents,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    elapsed = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("HARVEST COMPLETE")
    print("=" * 70)
    for r in reports:
        print(f"  {r['court']}: {r['count']} avgöranden")
    print("-" * 70)
    print(f"TOTAL: {len(all_documents)} avgöranden")
    print(f"TIME: {elapsed:.1f} seconds")
    print(f"OUTPUT: {output_file}")
    print("=" * 70)

    return len(all_documents)


if __name__ == "__main__":
    main()
