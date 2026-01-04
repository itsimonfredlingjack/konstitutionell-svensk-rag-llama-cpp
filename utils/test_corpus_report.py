#!/usr/bin/env python3
"""
Test script for Weekly Corpus Report
Simulates the n8n workflow execution for testing and validation
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path


def get_chromadb_stats():
    """Get ChromaDB statistics"""
    try:
        import chromadb

        chroma_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
        client = chromadb.PersistentClient(path=chroma_path)

        collections = client.list_collections()
        collection_stats = {}
        total_documents = 0

        for collection in collections:
            try:
                coll = client.get_collection(collection.name)
                count = coll.count()
                collection_stats[collection.name] = count
                total_documents += count
            except Exception as e:
                collection_stats[collection.name] = f"Error: {e!s}"

        # Count PDFs
        pdf_cache_path = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/pdf_cache")
        pdf_count = 0
        if pdf_cache_path.exists():
            pdf_count = sum(1 for _ in pdf_cache_path.rglob("*.pdf"))

        # Get disk usage
        result = subprocess.run(["du", "-sh", chroma_path], capture_output=True, text=True)
        disk_usage = result.stdout.split()[0] if result.stdout else "N/A"

        # Database size
        db_path = Path(chroma_path) / "chroma.sqlite3"
        db_size_bytes = db_path.stat().st_size if db_path.exists() else 0
        db_size_gb = round(db_size_bytes / (1024**3), 2)

        return {
            "total_documents": total_documents,
            "collection_stats": collection_stats,
            "pdf_count": pdf_count,
            "disk_usage": disk_usage,
            "database_size_gb": db_size_gb,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


def get_pdf_cache_size():
    """Get PDF cache directory size"""
    try:
        result = subprocess.run(
            ["du", "-sh", "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/pdf_cache"],
            capture_output=True,
            text=True,
        )
        return result.stdout.split()[0] if result.stdout else "0B"
    except:
        return "Unknown"


def format_report(stats, pdf_cache_size):
    """Format the weekly corpus report"""
    if "error" in stats:
        return f"""📋 *VECKORAPPORT - CORPUS STATUS*

🚨 ERROR: Kunde inte hämta statistik
{stats['error']}"""

    # Format collection breakdown
    collection_text = ""
    if stats.get("collection_stats"):
        lines = []
        for name, count in stats["collection_stats"].items():
            if isinstance(count, int):
                lines.append(f"  • {name}: {count:,} dokument")
            else:
                lines.append(f"  • {name}: {count}")
        collection_text = "\n".join(lines)

    # Format timestamp
    now = datetime.now()
    week_start = datetime(now.year, now.month, now.day)
    week_start = week_start.replace(day=now.day - now.weekday())
    week_start_str = week_start.strftime("%Y-%m-%d")
    week_end_str = now.strftime("%Y-%m-%d")

    report = f"""📋 *VECKORAPPORT - CORPUS STATUS*

📅 Vecka: {week_start_str} - {week_end_str}
⏰ Uppdaterad: {now.strftime('%H:%M:%S')}

📊 *DOKUMENTSAMLING*
✅ Totalt indexerade dokument: {stats.get('total_documents', 0):,}
📄 PDF-filer i cache: {stats.get('pdf_count', 0):,}

💾 *LAGRINGSANVÄNDNING*
📦 ChromaDB total: {stats.get('disk_usage', 'N/A')}
🗄️ Database fil (chroma.sqlite3): {stats.get('database_size_gb', 0)} GB
📁 PDF cache: {pdf_cache_size}

🏢 *SAMLING-UPPDELNING*
{collection_text if collection_text else '  (Ingen data tillgänglig)'}"""

    return report


def main():
    print("=" * 60)
    print("WEEKLY CORPUS REPORT - TEST EXECUTION")
    print("=" * 60)
    print()

    print("[1/3] Gathering ChromaDB statistics...")
    stats = get_chromadb_stats()

    print("[2/3] Getting PDF cache size...")
    pdf_cache_size = get_pdf_cache_size()

    print("[3/3] Formatting report...")
    report = format_report(stats, pdf_cache_size)

    print()
    print("=" * 60)
    print("GENERATED REPORT:")
    print("=" * 60)
    print()
    print(report)
    print()
    print("=" * 60)
    print("RAW DATA:")
    print("=" * 60)
    print()
    print(
        json.dumps({"stats": stats, "pdf_cache_size": pdf_cache_size}, indent=2, ensure_ascii=False)
    )
    print()
    print("=" * 60)
    print("✓ Test completed successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
