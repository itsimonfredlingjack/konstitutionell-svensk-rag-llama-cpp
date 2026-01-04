#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# The 100th document
doc_100 = {
    "url": "https://www.boverket.se/contentassets/4da481ce87014f43917b64fa9a48c566/publikt_api_for_energideklarationer_-_enkel_anvandning_v1.1.pdf",
    "title": "Publikt API för energideklarationer - Enkel användning v1.1",
    "metadata": {"year": "2024", "type": "Dokumentation", "topic": "API"},
}

scraper.scrape_pdf_document(doc_100["url"], doc_100["title"], doc_100["metadata"])

# FINAL
import json
from collections import Counter
from datetime import datetime

import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_collection("swedish_gov_docs")
boverket_docs = collection.get(where={"source": "boverket"}, limit=200)
total = len(boverket_docs["ids"])

categories = Counter([m.get("category", "Uncategorized") for m in boverket_docs["metadatas"]])
years = Counter([m.get("year", "Unknown") for m in boverket_docs["metadatas"]])

print(f"\n{'='*80}")
print("OPERATION MYNDIGHETS-SWEEP - BOVERKET")
print("✅ MISSION COMPLETE")
print(f"{'='*80}")
print(f"Total documents: {total}")
print("Target: 100")
print(
    f"Status: {'✅ SUCCESS - THRESHOLD MET' if total >= 100 else '⚠️  SHORT BY ' + str(100-total)}"
)
print("\nTop 5 Categories:")
for cat, count in categories.most_common(5):
    print(f"  {cat}: {count}")
print("\nDocument distribution by year:")
for year in sorted(years.keys(), reverse=True)[:10]:
    print(f"  {year}: {years[year]}")
print(f"{'='*80}")

# Final JSON
final_report = {
    "operation": "MYNDIGHETS-SWEEP - BOVERKET",
    "completed_at": datetime.now().isoformat(),
    "source": "boverket.se",
    "chromadb_collection": "swedish_gov_docs",
    "chromadb_path": "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    "total_documents": total,
    "target": 100,
    "success": total >= 100,
    "flagged": total < 100,
    "flag_reason": None if total >= 100 else f"Only {total} documents (minimum: 100)",
    "categories": dict(categories),
    "years": dict(years),
}

with open(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/BOVERKET_FINAL.json",
    "w",
) as f:
    json.dump(final_report, f, indent=2, ensure_ascii=False)

print(
    "Report: /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/BOVERKET_FINAL.json"
)
