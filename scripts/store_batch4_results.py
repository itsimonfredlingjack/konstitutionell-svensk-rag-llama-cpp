#!/usr/bin/env python3
"""Store batch 4 results in SQLite database."""

import json
import sqlite3
from datetime import datetime

DB_PATH = "kommun_tasks.db"

BATCH4_RESULTS = [
    {
        "id": "0188",
        "status": "done",
        "result": {
            "kommun": "Norrtälje",
            "kommun_kod": "0188",
            "url": "https://norrtalje.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0583",
        "status": "done",
        "result": {
            "kommun": "Motala",
            "kommun_kod": "0583",
            "url": "https://motala.se",
            "cms": "wordpress",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0880",
        "status": "done",
        "result": {
            "kommun": "Kalmar",
            "kommun_kod": "0880",
            "url": "https://kalmar.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 4,
        },
    },
    {
        "id": "0980",
        "status": "done",
        "result": {
            "kommun": "Gotland",
            "kommun_kod": "0980",
            "url": "https://gotland.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 4,
        },
    },
    {
        "id": "1080",
        "status": "done",
        "result": {
            "kommun": "Karlskrona",
            "kommun_kod": "1080",
            "url": "https://karlskrona.se",
            "cms": "episerver",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 4,
        },
    },
    {
        "id": "1282",
        "status": "done",
        "result": {
            "kommun": "Landskrona",
            "kommun_kod": "1282",
            "url": "https://landskrona.se",
            "cms": "gatsby",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "1287",
        "status": "done",
        "result": {
            "kommun": "Trelleborg",
            "kommun_kod": "1287",
            "url": "https://trelleborg.se",
            "cms": "wordpress",
            "cms_confidence": "high",
            "diarium": "meetings-plus",
            "priority_score": 4,
        },
    },
    {
        "id": "1290",
        "status": "done",
        "result": {
            "kommun": "Kristianstad",
            "kommun_kod": "1290",
            "url": "https://kristianstad.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 4,
        },
    },
    {
        "id": "1292",
        "status": "done",
        "result": {
            "kommun": "Ängelholm",
            "kommun_kod": "1292",
            "url": "https://angelholm.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "1293",
        "status": "done",
        "result": {
            "kommun": "Hässleholm",
            "kommun_kod": "1293",
            "url": "https://hassleholm.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "troman",
            "priority_score": 4,
        },
    },
]


def store_and_report():
    conn = sqlite3.connect(DB_PATH)
    for item in BATCH4_RESULTS:
        conn.execute(
            "UPDATE kommuner SET status='done', batch_id=4, completed_at=?, result=? WHERE id=?",
            (datetime.now().isoformat(), json.dumps(item["result"]), item["id"]),
        )
    conn.commit()

    # Get aggregated stats
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending
        FROM kommuner
    """)
    total, done, failed, pending = cursor.fetchone()

    # CMS distribution
    cursor = conn.execute("""
        SELECT json_extract(result, '$.cms') as cms, COUNT(*) as cnt
        FROM kommuner WHERE status='done' AND result IS NOT NULL
        GROUP BY cms ORDER BY cnt DESC
    """)
    cms_dist = dict(cursor.fetchall())

    # Diarium distribution
    cursor = conn.execute("""
        SELECT json_extract(result, '$.diarium') as diarium, COUNT(*) as cnt
        FROM kommuner WHERE status='done' AND result IS NOT NULL
        GROUP BY diarium ORDER BY cnt DESC
    """)
    diarium_dist = dict(cursor.fetchall())

    conn.close()

    print("=" * 60)
    print("KOMMUN SWARM PROGRESS REPORT")
    print("=" * 60)
    print(f"Total: {done}/{total} ({done/total*100:.1f}%)")
    print(f"Failed: {failed}")
    print(f"Pending: {pending}")
    print("\nCMS Distribution:")
    for cms, cnt in cms_dist.items():
        print(f"  {cms or 'unknown'}: {cnt}")
    print("\nDiarium Distribution:")
    for diarium, cnt in diarium_dist.items():
        print(f"  {diarium or 'unknown'}: {cnt}")


if __name__ == "__main__":
    store_and_report()
