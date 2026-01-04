#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# Documents we KNOW exist from earlier searches
victory_docs = [
    {
        "url": "https://rinfo.boverket.se/BFS2011-6/dok/BFS2020-4_Konsolidering.pdf",
        "title": "BBR Konsoliderad BFS 2011:6 t.o.m BFS 2020:4 (Konsolideringsdokument)",
        "metadata": {"year": "2020", "type": "Föreskrift", "document_type": "Konsolidering"},
    },
    {
        "url": "https://www.boverket.se/contentassets/472f6722abc046b1973f2401be1a7bfc/remiss---boverkets-forslag-till-andring-av-boverkets-foreskrifter-och-allmanna-rad-om-energideklaration-for-byggnader.pdf",
        "title": "Remiss - Förslag till ändring av föreskrifter om energideklaration",
        "metadata": {"year": "2024", "type": "Remiss", "topic": "Energideklaration"},
    },
]

for doc in victory_docs:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

# ULTIMATE FINAL COUNT
import json
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

success = total >= 100

print(f"\n{'='*80}")
print("OPERATION MYNDIGHETS-SWEEP - BOVERKET")
print("FINAL REPORT")
print(f"{'='*80}")
print(f"Documents collected: {total}")
print("Target threshold: 100")
if success:
    print("✅ SUCCESS! THRESHOLD MET")
else:
    print(f"⚠️  FLAGGED: {100-total} documents short")
print(f"{'='*80}")

# Update final JSON
final_report = {
    "operation": "MYNDIGHETS-SWEEP - BOVERKET",
    "completed_at": datetime.now().isoformat(),
    "source": "boverket.se",
    "chromadb_collection": "swedish_gov_docs",
    "total_documents": total,
    "target": 100,
    "success": success,
    "flagged": not success,
    "flag_reason": None if success else f"Only {total} documents collected (minimum: 100)",
}

with open(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/reports/BOVERKET_FINAL.json",
    "w",
) as f:
    json.dump(final_report, f, indent=2, ensure_ascii=False)

print("Final report saved: scrapers/reports/BOVERKET_FINAL.json")
