#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# Last batch of documents
final_batch = [
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2022/undersokning-av-fragor-med-anledning-av-takraset-i-tarfalahallen.pdf",
        "title": "Rapport 2022:1 - Undersökning av frågor med anledning av takraset i Tarfalahallen",
        "metadata": {
            "year": "2022",
            "type": "Rapport",
            "report_number": "2022:1",
            "topic": "Byggnadssäkerhet",
        },
    },
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2022/bilaga-1.-bakgrund-till-kap-2.pdf",
        "title": "Bilaga 1 - Bakgrund till kapitel 2 (2022)",
        "metadata": {"year": "2022", "type": "Dokumentation"},
    },
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2024/regionala-bostadsmarknadsanalyser-2023.pdf",
        "title": "Sammanställning: Regionala bostadsmarknadsanalyser 2023",
        "metadata": {"year": "2024", "type": "Rapport", "report_type": "Sammanställning"},
    },
    # Try BFS from earlier years
    {
        "url": "https://rinfo.boverket.se/BFS2022-4/pdf/BFS2022-4.pdf",
        "title": "BFS 2022:4",
        "metadata": {"year": "2022", "type": "Föreskrift", "bfs": "BFS 2022:4"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2023-1/pdf/BFS2023-1.pdf",
        "title": "BFS 2023:1",
        "metadata": {"year": "2023", "type": "Föreskrift", "bfs": "BFS 2023:1"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2023-2/pdf/BFS2023-2.pdf",
        "title": "BFS 2023:2",
        "metadata": {"year": "2023", "type": "Föreskrift", "bfs": "BFS 2023:2"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2023-3/pdf/BFS2023-3.pdf",
        "title": "BFS 2023:3",
        "metadata": {"year": "2023", "type": "Föreskrift", "bfs": "BFS 2023:3"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2021-4/pdf/BFS2021-4.pdf",
        "title": "BFS 2021:4",
        "metadata": {"year": "2021", "type": "Föreskrift", "bfs": "BFS 2021:4"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2021-3/pdf/BFS2021-3.pdf",
        "title": "BFS 2021:3",
        "metadata": {"year": "2021", "type": "Föreskrift", "bfs": "BFS 2021:3"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2020-6/pdf/BFS2020-6.pdf",
        "title": "BFS 2020:6",
        "metadata": {"year": "2020", "type": "Föreskrift", "bfs": "BFS 2020:6"},
    },
]

for doc in final_batch:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

scraper.generate_report()

# FINAL COUNT
import json
from collections import Counter

import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_collection("swedish_gov_docs")
boverket_docs = collection.get(where={"source": "boverket"}, limit=200)
total = len(boverket_docs["ids"])

# Generate final statistics
categories = Counter([m.get("category", "Uncategorized") for m in boverket_docs["metadatas"]])
years = Counter([m.get("year", "Unknown") for m in boverket_docs["metadatas"]])

final_report = {
    "operation": "MYNDIGHETS-SWEEP - BOVERKET",
    "status": "COMPLETED",
    "total_documents": total,
    "target": 100,
    "success": total >= 100,
    "categories": dict(categories),
    "years": dict(years),
    "top_documents": [
        {"title": m.get("title"), "year": m.get("year"), "url": m.get("url")}
        for m in boverket_docs["metadatas"][:20]
    ],
}

# Save final report
with open(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/BOVERKET_FINAL.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(final_report, f, indent=2, ensure_ascii=False)

print(f"\n{'='*80}")
print("OPERATION MYNDIGHETS-SWEEP - BOVERKET")
print(f"{'='*80}")
print(f"FINAL COUNT: {total} documents")
print("TARGET: 100 documents")
print(
    f"STATUS: {'✅ SUCCESS - THRESHOLD MET' if total >= 100 else f'⚠️  FLAGGED - NEED {100-total} MORE'}"
)
print("\nTop Categories:")
for cat, count in categories.most_common(5):
    print(f"  - {cat}: {count}")
print("\nFinal report: scrapers/reports/BOVERKET_FINAL.json")
print(f"{'='*80}")
