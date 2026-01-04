#!/usr/bin/env python3
import requests
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# Try more BFS numbers
bfs_2025 = [3, 4, 5, 6, 7, 8, 9, 10]
bfs_2024 = [15, 16, 17, 18, 19, 20]

for num in bfs_2025:
    url = f"https://rinfo.boverket.se/BFS2025-{num}/pdf/BFS2025-{num}.pdf"
    try:
        resp = requests.head(url, timeout=5)
        if resp.status_code == 200:
            scraper.scrape_pdf_document(
                url,
                f"BFS 2025:{num}",
                {"year": "2025", "type": "Föreskrift", "bfs": f"BFS 2025:{num}"},
            )
    except:
        pass

for num in bfs_2024:
    url = f"https://rinfo.boverket.se/BFS2024-{num}/pdf/BFS2024-{num}.pdf"
    try:
        resp = requests.head(url, timeout=5)
        if resp.status_code == 200:
            scraper.scrape_pdf_document(
                url,
                f"BFS 2024:{num}",
                {"year": "2024", "type": "Föreskrift", "bfs": f"BFS 2024:{num}"},
            )
    except:
        pass

# Add more 2025 reports we might have missed
extra_2025 = [
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/metoder-definitioner-och-krav-inom-solenergi-i-direktivet-om-byggnaders-energiprestanda.pdf",
        "title": "Rapport 2025:3 - Solenergi i energiprestanda-direktivet",
        "metadata": {"year": "2025", "type": "Rapport", "report_number": "2025:3"},
    }
]

for doc in extra_2025:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

scraper.generate_report()

# Final count
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
print(f"FINAL COUNT: {total} Boverket documents")
print("TARGET: 100 documents")
print(f"STATUS: {'✅ SUCCESS' if total >= 100 else f'❌ NEED {100-total} MORE'}")
print(f"{'='*80}")
