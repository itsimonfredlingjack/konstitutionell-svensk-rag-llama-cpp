#!/usr/bin/env python3
"""
SFS Scraper - Hämtar lagtexter från Riksdagens öppna data
==========================================================

Hämtar SFS-texter (Svensk författningssamling) och chunkar per kapitel/paragraf
för indexering i ChromaDB.

Officiella källor (prioritetsordning):
1. Riksdagens öppna data (data.riksdagen.se) - strukturerat API
2. Regeringskansliets rättsdatabaser (rkrattsbaser.gov.se) - autentisk version
3. Lagrummet (lagrummet.se) - metadata och kopplingar

Användning:
    python sfs_scraper.py --grundlagar          # Hämta bara grundlagarna
    python sfs_scraper.py --viktiga             # Hämta viktiga lagar
    python sfs_scraper.py --sfs 1974:152        # Hämta specifik SFS
    python sfs_scraper.py --all                 # Hämta alla (varning: tar tid)
"""

import argparse
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# Konfigurera logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Grundlagar och viktiga lagar att prioritera
GRUNDLAGAR = [
    ("1974:152", "Regeringsformen (RF)"),
    ("1810:0926", "Successionsordningen (SO)"),
    ("1949:105", "Tryckfrihetsförordningen (TF)"),
    ("1991:1469", "Yttrandefrihetsgrundlagen (YGL)"),
]

VIKTIGA_LAGAR = [
    ("2009:400", "Offentlighets- och sekretesslagen (OSL)"),
    ("2017:900", "Förvaltningslagen (FL)"),
    ("1971:291", "Förvaltningsprocesslagen (FPL)"),  # TIER 1: Kritisk för överklagande
    ("2017:725", "Kommunallagen (KL)"),
    ("1962:700", "Brottsbalken (BrB)"),
    ("1942:740", "Rättegångsbalken (RB)"),
    ("2018:218", "Dataskyddslagen"),
    ("1960:729", "Upphovsrättslagen (URL)"),
    ("1915:218", "Avtalslagen (AvtL)"),
    ("1972:207", "Skadeståndslagen (SkL)"),
    ("1990:52", "Lagen om särskilda bestämmelser om vård av unga (LVU)"),
]


@dataclass
class SFSChunk:
    """En chunk av lagtext (kapitel eller paragraf)"""

    sfs_nummer: str  # T.ex. "1974:152"
    titel: str  # T.ex. "Regeringsformen"
    kortnamn: str  # T.ex. "RF"
    kapitel: Optional[str]  # T.ex. "2 kap."
    kapitel_rubrik: Optional[str]  # T.ex. "Grundläggande fri- och rättigheter"
    paragraf: Optional[str]  # T.ex. "1 §"
    text: str  # Själva lagtexten
    senast_andrad: Optional[str]  # T.ex. "SFS 2022:1600"
    chunk_id: str  # Unik identifierare
    source_url: str  # Källa
    scraped_at: str  # Tidpunkt för scraping


@dataclass
class SFSDocument:
    """Ett helt SFS-dokument"""

    sfs_nummer: str
    titel: str
    kortnamn: str
    departement: str
    utfardad: str
    senast_andrad: Optional[str]
    full_text: str
    chunks: list[SFSChunk]
    source_url: str
    scraped_at: str


class SFSScraper:
    """Scraper för SFS-texter från Riksdagens öppna data"""

    BASE_URL = "https://data.riksdagen.se"
    RATE_LIMIT_SECONDS = 2  # Var snäll mot API:et

    def __init__(self, output_dir: str = "scraped_data/sfs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Constitutional-AI-SFS-Scraper/1.0 (research project)"}
        )

    def fetch_sfs_text(self, sfs_nummer: str) -> Optional[str]:
        """Hämta fullständig text för ett SFS-nummer"""
        # Konvertera "1974:152" till "sfs-1974-152"
        doc_id = f"sfs-{sfs_nummer.replace(':', '-')}"
        url = f"{self.BASE_URL}/dokument/{doc_id}.text"

        logger.info(f"Hämtar {sfs_nummer} från {url}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as e:
            logger.error(f"Kunde inte hämta {sfs_nummer}: {e}")
            return None

    def parse_sfs_metadata(self, text: str) -> dict:
        """Extrahera metadata från SFS-text"""
        metadata = {
            "titel": "",
            "sfs_nummer": "",
            "departement": "",
            "utfardad": "",
            "senast_andrad": None,
        }

        lines = text.split("\n")

        # Första raden är oftast titeln
        if lines:
            metadata["titel"] = lines[0].strip()

        for line in lines[:20]:  # Metadata är i början
            line = line.strip()
            if line.startswith("SFS nr:"):
                metadata["sfs_nummer"] = line.replace("SFS nr:", "").strip()
            elif line.startswith("Departement/myndighet:"):
                metadata["departement"] = line.replace("Departement/myndighet:", "").strip()
            elif line.startswith("Utfärdad:"):
                metadata["utfardad"] = line.replace("Utfärdad:", "").strip()
            elif line.startswith("Ändrad:"):
                metadata["senast_andrad"] = line.replace("Ändrad:", "").strip()
            elif line.startswith("Omtryck:"):
                if not metadata["senast_andrad"]:
                    metadata["senast_andrad"] = line.replace("Omtryck:", "").strip()

        return metadata

    def _chunk_so_format(
        self, text: str, sfs_nummer: str, titel: str, kortnamn: str
    ) -> list[SFSChunk]:
        """
        Specialhantering för Successionsordningen (1810:0926).
        SO har artikelformat: "Art. 1", "Art. 2", etc. istället för kapitel/paragrafer.
        """
        chunks = []

        # Hitta var artikeltexten börjar
        content_start = re.search(r"\n\s*(Art\.\s*1)", text, re.IGNORECASE)
        if content_start:
            text = text[content_start.start() :]

        # Regex för att hitta artiklar: "Art. 1", "Art. 2", etc.
        artikel_pattern = re.compile(r"^(Art\.\s*\d+)", re.MULTILINE | re.IGNORECASE)

        artikel_matches = list(artikel_pattern.finditer(text))

        if not artikel_matches:
            logger.warning(f"Inga artiklar hittades i SO ({sfs_nummer})")
            return chunks

        for i, match in enumerate(artikel_matches):
            artikel_num = match.group(1).strip()

            # Hitta slutet av artikeln
            if i + 1 < len(artikel_matches):
                artikel_end = artikel_matches[i + 1].start()
            else:
                artikel_end = len(text)

            artikel_text = text[match.start() : artikel_end].strip()

            # Skapa chunk
            chunk_id = f"{sfs_nummer}_{artikel_num}".replace(" ", "_").replace(".", "")

            chunks.append(
                SFSChunk(
                    sfs_nummer=sfs_nummer,
                    titel=titel,
                    kortnamn=kortnamn,
                    kapitel=None,  # SO har inga kapitel
                    kapitel_rubrik=None,
                    paragraf=artikel_num,  # Använd artikel som "paragraf"
                    text=artikel_text,
                    senast_andrad=None,
                    chunk_id=chunk_id,
                    source_url=f"{self.BASE_URL}/dokument/sfs-{sfs_nummer.replace(':', '-')}.text",
                    scraped_at=datetime.now().isoformat(),
                )
            )

        logger.info(f"SO chunkat: {len(chunks)} artiklar")
        return chunks

    def chunk_by_paragraph(
        self, text: str, sfs_nummer: str, titel: str, kortnamn: str
    ) -> list[SFSChunk]:
        """Chunka lagtext per kapitel och paragraf"""
        chunks = []

        # SPECIAL CASE: Successionsordningen (1810:0926) har artikelformat
        if sfs_nummer == "1810:0926":
            return self._chunk_so_format(text, sfs_nummer, titel, kortnamn)

        # Hitta var själva lagtexten börjar (efter metadata)
        # Letar efter "1 kap." eller "1 §"
        content_start = re.search(r"\n\s*(1 kap\.|1 §)", text)
        if content_start:
            text = text[content_start.start() :]

        # Regex för att hitta kapitel
        kapitel_pattern = re.compile(r"^(\d+[a-z]?\s*kap\.)\s*(.*)$", re.MULTILINE)

        # Regex för att hitta paragrafer
        paragraf_pattern = re.compile(r"^(\d+[a-z]?\s*§)\s*", re.MULTILINE)

        # Dela upp i kapitel först
        kapitel_matches = list(kapitel_pattern.finditer(text))

        if kapitel_matches:
            # Lagen har kapitelindelning
            for i, match in enumerate(kapitel_matches):
                kapitel_num = match.group(1).strip()
                kapitel_rubrik = match.group(2).strip()

                # Hitta slutet av kapitlet
                if i + 1 < len(kapitel_matches):
                    kapitel_end = kapitel_matches[i + 1].start()
                else:
                    kapitel_end = len(text)

                kapitel_text = text[match.end() : kapitel_end]

                # Dela upp kapitlet i paragrafer
                paragraf_matches = list(paragraf_pattern.finditer(kapitel_text))

                for j, p_match in enumerate(paragraf_matches):
                    paragraf_num = p_match.group(0).strip()

                    # Hitta slutet av paragrafen
                    if j + 1 < len(paragraf_matches):
                        paragraf_end = paragraf_matches[j + 1].start()
                    else:
                        paragraf_end = len(kapitel_text)

                    paragraf_text = kapitel_text[p_match.start() : paragraf_end].strip()

                    # Skapa chunk
                    chunk_id = f"{sfs_nummer}_{kapitel_num}_{paragraf_num}".replace(
                        " ", "_"
                    ).replace(".", "")

                    chunks.append(
                        SFSChunk(
                            sfs_nummer=sfs_nummer,
                            titel=titel,
                            kortnamn=kortnamn,
                            kapitel=kapitel_num,
                            kapitel_rubrik=kapitel_rubrik,
                            paragraf=paragraf_num,
                            text=paragraf_text,
                            senast_andrad=None,  # Fylls i senare
                            chunk_id=chunk_id,
                            source_url=f"{self.BASE_URL}/dokument/sfs-{sfs_nummer.replace(':', '-')}.text",
                            scraped_at=datetime.now().isoformat(),
                        )
                    )
        else:
            # Lagen saknar kapitelindelning, chunka bara per paragraf
            paragraf_matches = list(paragraf_pattern.finditer(text))

            for j, p_match in enumerate(paragraf_matches):
                paragraf_num = p_match.group(0).strip()

                if j + 1 < len(paragraf_matches):
                    paragraf_end = paragraf_matches[j + 1].start()
                else:
                    paragraf_end = len(text)

                paragraf_text = text[p_match.start() : paragraf_end].strip()

                chunk_id = f"{sfs_nummer}_{paragraf_num}".replace(" ", "_").replace(".", "")

                chunks.append(
                    SFSChunk(
                        sfs_nummer=sfs_nummer,
                        titel=titel,
                        kortnamn=kortnamn,
                        kapitel=None,
                        kapitel_rubrik=None,
                        paragraf=paragraf_num,
                        text=paragraf_text,
                        senast_andrad=None,
                        chunk_id=chunk_id,
                        source_url=f"{self.BASE_URL}/dokument/sfs-{sfs_nummer.replace(':', '-')}.text",
                        scraped_at=datetime.now().isoformat(),
                    )
                )

        return chunks

    def scrape_sfs(self, sfs_nummer: str, kortnamn: str = "") -> Optional[SFSDocument]:
        """Scrapa ett SFS-dokument och chunka det"""
        text = self.fetch_sfs_text(sfs_nummer)
        if not text:
            return None

        metadata = self.parse_sfs_metadata(text)

        # Extrahera kortnamn från titel om inte angivet
        if not kortnamn:
            # Försök hitta kortnamn i parentes, t.ex. "(RF)"
            match = re.search(r"\(([A-ZÅÄÖ]{2,5})\)", metadata["titel"])
            if match:
                kortnamn = match.group(1)
            else:
                kortnamn = sfs_nummer

        chunks = self.chunk_by_paragraph(text, sfs_nummer, metadata["titel"], kortnamn)

        # Uppdatera senast_andrad i alla chunks
        for chunk in chunks:
            chunk.senast_andrad = metadata["senast_andrad"]

        doc = SFSDocument(
            sfs_nummer=sfs_nummer,
            titel=metadata["titel"],
            kortnamn=kortnamn,
            departement=metadata["departement"],
            utfardad=metadata["utfardad"],
            senast_andrad=metadata["senast_andrad"],
            full_text=text,
            chunks=chunks,
            source_url=f"{self.BASE_URL}/dokument/sfs-{sfs_nummer.replace(':', '-')}.text",
            scraped_at=datetime.now().isoformat(),
        )

        logger.info(f"Scrapade {sfs_nummer}: {len(chunks)} chunks")
        return doc

    def save_document(self, doc: SFSDocument):
        """Spara dokument till fil"""
        filename = f"sfs_{doc.sfs_nummer.replace(':', '_')}.json"
        filepath = self.output_dir / filename

        # Konvertera till dict för JSON-serialisering
        doc_dict = {
            "sfs_nummer": doc.sfs_nummer,
            "titel": doc.titel,
            "kortnamn": doc.kortnamn,
            "departement": doc.departement,
            "utfardad": doc.utfardad,
            "senast_andrad": doc.senast_andrad,
            "source_url": doc.source_url,
            "scraped_at": doc.scraped_at,
            "chunk_count": len(doc.chunks),
            "chunks": [asdict(c) for c in doc.chunks],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(doc_dict, f, ensure_ascii=False, indent=2)

        logger.info(f"Sparade {filepath}")

        # Spara också full text separat
        text_filepath = self.output_dir / f"sfs_{doc.sfs_nummer.replace(':', '_')}_fulltext.txt"
        with open(text_filepath, "w", encoding="utf-8") as f:
            f.write(doc.full_text)

    def scrape_grundlagar(self) -> list[SFSDocument]:
        """Scrapa alla grundlagar"""
        docs = []
        for sfs_nummer, namn in GRUNDLAGAR:
            # Extrahera kortnamn från parentes
            kortnamn_match = re.search(r"\(([A-ZÅÄÖ]+)\)", namn)
            kortnamn = kortnamn_match.group(1) if kortnamn_match else ""

            doc = self.scrape_sfs(sfs_nummer, kortnamn)
            if doc:
                self.save_document(doc)
                docs.append(doc)

            time.sleep(self.RATE_LIMIT_SECONDS)

        return docs

    def scrape_viktiga_lagar(self) -> list[SFSDocument]:
        """Scrapa viktiga lagar"""
        docs = []
        for sfs_nummer, namn in VIKTIGA_LAGAR:
            kortnamn_match = re.search(r"\(([A-ZÅÄÖ]+)\)", namn)
            kortnamn = kortnamn_match.group(1) if kortnamn_match else ""

            doc = self.scrape_sfs(sfs_nummer, kortnamn)
            if doc:
                self.save_document(doc)
                docs.append(doc)

            time.sleep(self.RATE_LIMIT_SECONDS)

        return docs


def main():
    parser = argparse.ArgumentParser(description="SFS Scraper - Hämtar lagtexter")
    parser.add_argument("--grundlagar", action="store_true", help="Hämta grundlagarna")
    parser.add_argument("--viktiga", action="store_true", help="Hämta viktiga lagar")
    parser.add_argument("--sfs", type=str, help="Hämta specifik SFS (t.ex. 1974:152)")
    parser.add_argument("--output", type=str, default="scraped_data/sfs", help="Output-katalog")

    args = parser.parse_args()

    scraper = SFSScraper(output_dir=args.output)

    if args.grundlagar:
        logger.info("Hämtar grundlagar...")
        docs = scraper.scrape_grundlagar()
        logger.info(f"Klart! Hämtade {len(docs)} grundlagar")

    elif args.viktiga:
        logger.info("Hämtar viktiga lagar...")
        docs = scraper.scrape_viktiga_lagar()
        logger.info(f"Klart! Hämtade {len(docs)} lagar")

    elif args.sfs:
        logger.info(f"Hämtar SFS {args.sfs}...")
        doc = scraper.scrape_sfs(args.sfs)
        if doc:
            scraper.save_document(doc)
            logger.info(f"Klart! {len(doc.chunks)} chunks")
        else:
            logger.error(f"Kunde inte hämta {args.sfs}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
