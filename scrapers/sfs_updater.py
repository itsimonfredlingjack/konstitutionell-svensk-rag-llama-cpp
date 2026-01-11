#!/usr/bin/env python3
"""
SFS Updater - Selektiv reindexering av SFS-lagtexter
====================================================

Jämför content_hash/last_modified och upsertar bara diff.
Sparar manifest för rollback/debug.

Användning:
    python sfs_updater.py --check              # Kolla vilka som ändrats
    python sfs_updater.py --update             # Uppdatera ändrade
    python sfs_updater.py --sfs 1974:152       # Uppdatera specifik SFS
    python sfs_updater.py --manifest           # Visa manifest
"""

import argparse
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings

# Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
SFS_DATA_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data/sfs"
MANIFEST_PATH = (
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data/sfs/manifest.json"
)
COLLECTION_NAME = "sfs_lagtext"


class SFSManifest:
    """
    Manifest för SFS-dokument.

    Spårar:
    - content_hash per SFS-dokument
    - indexed_at timestamp
    - parser_version
    - chunk_count
    """

    def __init__(self, manifest_path: Path = Path(MANIFEST_PATH)):
        self.manifest_path = manifest_path
        self.data = self._load()

    def _load(self) -> dict:
        """Ladda manifest från fil"""
        if self.manifest_path.exists():
            with open(self.manifest_path, encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.0", "documents": {}}

    def save(self):
        """Spara manifest till fil"""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        logger.info(f"Manifest saved to {self.manifest_path}")

    def get_doc(self, sfs_nummer: str) -> dict | None:
        """Hämta dokument från manifest"""
        return self.data["documents"].get(sfs_nummer)

    def set_doc(
        self, sfs_nummer: str, content_hash: str, chunk_count: int, parser_version: str = "2.0"
    ):
        """Uppdatera dokument i manifest"""
        self.data["documents"][sfs_nummer] = {
            "content_hash": content_hash,
            "chunk_count": chunk_count,
            "parser_version": parser_version,
            "indexed_at": datetime.now().isoformat(),
        }

    def list_docs(self) -> list[str]:
        """Lista alla SFS-nummer i manifest"""
        return list(self.data["documents"].keys())


class SFSUpdater:
    """Selektiv uppdatering av SFS-dokument"""

    def __init__(self, chromadb_path: str = CHROMADB_PATH, sfs_path: str = SFS_DATA_PATH):
        self.sfs_path = Path(sfs_path)
        self.manifest = SFSManifest()

        # Anslut till ChromaDB
        logger.info(f"Connecting to ChromaDB: {chromadb_path}")
        self.client = chromadb.PersistentClient(
            path=chromadb_path, settings=Settings(anonymized_telemetry=False)
        )

        # Hämta collection
        try:
            self.collection = self.client.get_collection(name=COLLECTION_NAME)
            logger.info(f"Collection '{COLLECTION_NAME}' loaded, {self.collection.count()} chunks")
        except Exception as e:
            logger.error(f"Collection '{COLLECTION_NAME}' not found: {e}")
            logger.error("Run sfs_indexer.py first to create collection")
            raise

    def calculate_content_hash(self, sfs_data: dict) -> str:
        """
        Beräkna content hash för hela SFS-dokumentet.

        Baserat på alla chunks' text (normaliserad).
        """
        chunks = sfs_data.get("chunks", [])

        # Kombinera all text
        all_text = ""
        for chunk in chunks:
            text = chunk.get("text", "")
            # Normalisera
            normalized = " ".join(text.split()).strip().lower()
            all_text += normalized

        # SHA256 hash
        return hashlib.sha256(all_text.encode("utf-8")).hexdigest()

    def check_changes(self) -> dict[str, str]:
        """
        Kolla vilka SFS-dokument som ändrats.

        Returns:
            Dict med {sfs_nummer: status} där status är:
            - "new": Finns inte i manifest
            - "changed": Content hash ändrad
            - "unchanged": Ingen ändring
            - "missing": I manifest men inte på disk
        """
        changes = {}

        # Kolla alla filer på disk
        sfs_files = list(self.sfs_path.glob("sfs_*.json"))
        sfs_files = [f for f in sfs_files if "fulltext" not in f.name]

        for filepath in sfs_files:
            # Ladda SFS-data
            with open(filepath, encoding="utf-8") as f:
                sfs_data = json.load(f)

            sfs_nummer = sfs_data.get("sfs_nummer")
            if not sfs_nummer:
                continue

            # Beräkna content hash
            current_hash = self.calculate_content_hash(sfs_data)

            # Jämför med manifest
            manifest_doc = self.manifest.get_doc(sfs_nummer)

            if not manifest_doc:
                changes[sfs_nummer] = "new"
            elif manifest_doc["content_hash"] != current_hash:
                changes[sfs_nummer] = "changed"
            else:
                changes[sfs_nummer] = "unchanged"

        # Kolla om något saknas
        for sfs_nummer in self.manifest.list_docs():
            if sfs_nummer not in changes:
                changes[sfs_nummer] = "missing"

        return changes

    def update_sfs(self, sfs_nummer: str):
        """
        Uppdatera ett specifikt SFS-dokument.

        1. Radera gamla chunks (via where filter)
        2. Scrapa ny version (eller ladda från fil)
        3. Indexera med samma ID-struktur
        4. Uppdatera manifest
        """
        logger.info(f"Updating {sfs_nummer}...")

        # Hitta fil
        filepath = self.sfs_path / f"sfs_{sfs_nummer.replace(':', '_')}.json"
        if not filepath.exists():
            logger.error(f"File not found: {filepath}")
            return False

        # Ladda SFS-data
        with open(filepath, encoding="utf-8") as f:
            sfs_data = json.load(f)

        # Radera gamla chunks
        logger.info(f"Deleting old chunks for {sfs_nummer}...")
        try:
            # ChromaDB delete via where filter
            self.collection.delete(where={"sfs_nummer": sfs_nummer})
            logger.info("Old chunks deleted")
        except Exception as e:
            logger.warning(f"Could not delete old chunks: {e}")

        # Indexera nya chunks
        logger.info("Indexing new chunks...")
        from sfs_indexer import SFSIndexer

        indexer = SFSIndexer(chromadb_path=CHROMADB_PATH, sfs_path=SFS_DATA_PATH)
        chunks_indexed = indexer.index_sfs_document(sfs_data)

        # Uppdatera manifest
        content_hash = self.calculate_content_hash(sfs_data)
        self.manifest.set_doc(sfs_nummer, content_hash, chunks_indexed)
        self.manifest.save()

        logger.info(f"✅ {sfs_nummer} updated: {chunks_indexed} chunks")
        return True

    def update_all_changed(self):
        """Uppdatera alla ändrade SFS-dokument"""
        changes = self.check_changes()

        to_update = [sfs for sfs, status in changes.items() if status in ["new", "changed"]]

        if not to_update:
            logger.info("No changes detected")
            return

        logger.info(f"Updating {len(to_update)} documents...")

        for sfs_nummer in to_update:
            self.update_sfs(sfs_nummer)

        logger.info(f"✅ Update complete: {len(to_update)} documents")


def main():
    parser = argparse.ArgumentParser(description="SFS Updater - Selektiv reindexering")
    parser.add_argument("--check", action="store_true", help="Kolla vilka som ändrats")
    parser.add_argument("--update", action="store_true", help="Uppdatera ändrade")
    parser.add_argument("--sfs", type=str, help="Uppdatera specifik SFS (t.ex. 1974:152)")
    parser.add_argument("--manifest", action="store_true", help="Visa manifest")

    args = parser.parse_args()

    updater = SFSUpdater()

    if args.manifest:
        # Visa manifest
        print("\n=== SFS Manifest ===")
        print(f"Version: {updater.manifest.data['version']}")
        print(f"Documents: {len(updater.manifest.list_docs())}")
        print()

        for sfs_nummer in sorted(updater.manifest.list_docs()):
            doc = updater.manifest.get_doc(sfs_nummer)
            print(f"{sfs_nummer}:")
            print(f"  Content hash: {doc['content_hash'][:12]}...")
            print(f"  Chunks: {doc['chunk_count']}")
            print(f"  Indexed: {doc['indexed_at']}")
            print(f"  Parser: v{doc['parser_version']}")
            print()

        return

    if args.check:
        # Kolla ändringar
        changes = updater.check_changes()

        print("\n=== Change Detection ===")

        new = [sfs for sfs, status in changes.items() if status == "new"]
        changed = [sfs for sfs, status in changes.items() if status == "changed"]
        unchanged = [sfs for sfs, status in changes.items() if status == "unchanged"]
        missing = [sfs for sfs, status in changes.items() if status == "missing"]

        if new:
            print(f"\n🆕 New ({len(new)}):")
            for sfs in new:
                print(f"  - {sfs}")

        if changed:
            print(f"\n🔄 Changed ({len(changed)}):")
            for sfs in changed:
                print(f"  - {sfs}")

        if missing:
            print(f"\n⚠️  Missing ({len(missing)}):")
            for sfs in missing:
                print(f"  - {sfs}")

        if unchanged:
            print(f"\n✅ Unchanged ({len(unchanged)}):")
            for sfs in unchanged:
                print(f"  - {sfs}")

        print()
        return

    if args.update:
        # Uppdatera alla ändrade
        updater.update_all_changed()
        return

    if args.sfs:
        # Uppdatera specifik SFS
        updater.update_sfs(args.sfs)
        return

    # Default: visa hjälp
    parser.print_help()


if __name__ == "__main__":
    main()
