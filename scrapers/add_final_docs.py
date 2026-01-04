#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# New reports from 2025 and 2024
final_docs = [
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/allmannyttan-2024-underhall-och-modernisering-av-bestandet.pdf",
        "title": "Rapport 2025:17 - Allmännyttan 2024: Underhåll och modernisering",
        "metadata": {
            "year": "2025",
            "type": "Rapport",
            "report_number": "2025:17",
            "topic": "Allmännyttan",
        },
    },
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/underlag-till-nationell-byggnadsrenoveringsplan---till-utkastet-2025.pdf",
        "title": "Rapport 2025:19 - Underlag till nationell byggnadsrenoveringsplan",
        "metadata": {
            "year": "2025",
            "type": "Rapport",
            "report_number": "2025:19",
            "topic": "Renovering",
        },
    },
    {
        "url": "https://www.boverket.se/contentassets/7b709f90e49f4db3a0dc02a3f2c41faf/livsvillkor-i-utanforskapsomraden.pdf",
        "title": "Rapport 2025:13 - Livsvillkor i utanförskapsområden",
        "metadata": {
            "year": "2025",
            "type": "Rapport",
            "report_number": "2025:13",
            "topic": "Segregation",
        },
    },
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2025/oversyn-av-systemet-med-energideklarationer-delrapport-2.pdf",
        "title": "Rapport 2025:18 - Översyn av energideklarationer Delrapport 2",
        "metadata": {
            "year": "2025",
            "type": "Rapport",
            "report_number": "2025:18",
            "topic": "Energideklaration",
        },
    },
    {
        "url": "https://www.boverket.se/globalassets/publikationer/dokument/2024/fordjupad_analys_om_utanforskap_slutrapport-2024.pdf",
        "title": "Rapport 2024:2 - Fördjupad analys om utanförskap",
        "metadata": {
            "year": "2024",
            "type": "Rapport",
            "report_number": "2024:2",
            "topic": "Segregation",
        },
    },
]

for doc in final_docs:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

scraper.generate_report()
print("\n📊 Total Boverket documents in ChromaDB:")

# Count Boverket docs
import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_collection("swedish_gov_docs")
boverket_docs = collection.get(where={"source": "boverket"}, limit=200)
print(f"{len(boverket_docs['ids'])} documents")
