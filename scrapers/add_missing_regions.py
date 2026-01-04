#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# All Swedish counties - bostadsmarknadsanalyser 2024
regions_2024 = [
    "uppsala-lan-2024.pdf",
    "sodermanlands-lan-2024.pdf",
    "ostergotlands-lan-2024.pdf",
    "jonkopings-lan-2024.pdf",
    "kalmar-lan-2024.pdf",
    "gotlands-lan-2024.pdf",
    "blekinge-lan-2024.pdf",
    "skane-lan-2024.pdf",
    "varmlands-lan-2024.pdf",
    "orebro-lan-2024.pdf",
    "dalarna-lan-2024.pdf",
    "gavleborgs-lan-2024.pdf",
    "vasternorrlands-lan-2024.pdf",
    "jamtlands-lan-2024.pdf",
    "vasterbottens-lan-2024.pdf",
    "stockholm-lan-2024.pdf",
    "vastra-gotalands-lan-2024.pdf",
]

base_url = "https://www.boverket.se/contentassets/56b41b3b67c84d27bcd3245894c535fe/"

for filename in regions_2024:
    title = f"Bostadsmarknadsanalys 2024 {filename.replace('-lan-2024.pdf', ' län').replace('-', ' ').title()}"
    url = base_url + filename

    scraper.scrape_pdf_document(
        url, title, {"year": "2024", "type": "Rapport", "report_type": "Bostadsmarknadsanalys"}
    )

# Add Stockholm 2025
scraper.scrape_pdf_document(
    "https://www.boverket.se/contentassets/1a53e212b3214d54ab50aec70135d4ea/bostadsmarknadsanalys-2025-stockholms-lan.pdf",
    "Bostadsmarknadsanalys 2025 Stockholms län",
    {"year": "2025", "type": "Rapport", "report_type": "Bostadsmarknadsanalys"},
)

scraper.generate_report()
print(f"\n📊 Total documents in ChromaDB: {scraper.collection.count()}")
