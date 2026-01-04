#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# Last two documents
last_two = [
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2020/konsoliderad-bbr-2011-6-tom-2020-4.pdf",
        "title": "BBR Konsoliderad BFS 2011:6 t.o.m. BFS 2020:4",
        "metadata": {"year": "2020", "type": "Föreskrift", "version": "BBR konsoliderad"},
    },
    {
        "url": "https://www.boverket.se/contentassets/2b709d86893740bab472714cb1ffb4c0/boverkets-byggregler-bfs-2011-6-tom-2013-3.pdf",
        "title": "BBR BFS 2011:6 t.o.m. 2013:3",
        "metadata": {"year": "2013", "type": "Föreskrift", "version": "BBR konsoliderad"},
    },
]

for doc in last_two:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

# ULTIMATE FINAL COUNT
import json

import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_collection("swedish_gov_docs")
boverket_docs = collection.get(where={"source": "boverket"}, limit=200)
total = len(boverket_docs["ids"])

print(f"\n{'='*80}")
print("OPERATION MYNDIGHETS-SWEEP - BOVERKET")
print("ULTIMATE FINAL COUNT")
print(f"{'='*80}")
print(f"Total Boverket documents: {total}")
print("Target: 100 documents")
if total >= 100:
    print(f"✅ SUCCESS! Threshold MET ({total} >= 100)")
else:
    print(f"⚠️  FLAGGED: Only {total} documents ({100-total} short of target)")
print(f"{'='*80}")

# Save to file
with open(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/BOVERKET_FINAL.json"
) as f:
    report = json.load(f)

report["total_documents"] = total
report["success"] = total >= 100
report["flagged"] = total < 100

with open(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/BOVERKET_FINAL.json",
    "w",
) as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
