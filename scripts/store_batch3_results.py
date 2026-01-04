#!/usr/bin/env python3
"""Store batch 3 results in SQLite database."""

import json
import sqlite3
from datetime import datetime

DB_PATH = "kommun_tasks.db"

BATCH3_RESULTS = [
    {
        "id": "0114",
        "status": "done",
        "result": {
            "kommun": "Upplands Väsby",
            "kommun_kod": "0114",
            "url": "https://upplandsvasby.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "netpublicator",
            "priority_score": 3,
        },
    },
    {
        "id": "0117",
        "status": "failed",
        "error": "SSL certificate verification issues and WAF/anti-bot protection blocking all requests",
    },
    {
        "id": "0123",
        "status": "done",
        "result": {
            "kommun": "Järfälla",
            "kommun_kod": "0123",
            "url": "https://jarfalla.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0126",
        "status": "done",
        "result": {
            "kommun": "Huddinge",
            "kommun_kod": "0126",
            "url": "https://huddinge.se",
            "cms": "episerver",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0127",
        "status": "done",
        "result": {
            "kommun": "Botkyrka",
            "kommun_kod": "0127",
            "url": "https://botkyrka.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0136",
        "status": "done",
        "result": {
            "kommun": "Haninge",
            "kommun_kod": "0136",
            "url": "https://haninge.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0160",
        "status": "done",
        "result": {
            "kommun": "Täby",
            "kommun_kod": "0160",
            "url": "https://taby.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "mediaflowportal",
            "diarium_url": "https://taby.mediaflowportal.com/play",
            "priority_score": 4,
        },
    },
    {
        "id": "0163",
        "status": "done",
        "result": {
            "kommun": "Sollentuna",
            "kommun_kod": "0163",
            "url": "https://sollentuna.se",
            "cms": "unknown",
            "cms_confidence": "low",
            "diarium": "unknown",
            "priority_score": 3,
        },
    },
    {
        "id": "0182",
        "status": "done",
        "result": {
            "kommun": "Nacka",
            "kommun_kod": "0182",
            "url": "https://nacka.se",
            "cms": "episerver",
            "cms_confidence": "high",
            "diarium": "unknown",
            "priority_score": 4,
        },
    },
    {
        "id": "0184",
        "status": "done",
        "result": {
            "kommun": "Solna",
            "kommun_kod": "0184",
            "url": "https://solna.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "diarium": "unknown",
            "diarium_url": "https://solna.se/om-solna-stad/politik-och-namnder/sok-i-diariet",
            "priority_score": 3,
        },
    },
]


def store_results():
    conn = sqlite3.connect(DB_PATH)
    done = 0
    failed = 0
    for item in BATCH3_RESULTS:
        if item["status"] == "done":
            conn.execute(
                "UPDATE kommuner SET status='done', batch_id=3, completed_at=?, result=? WHERE id=?",
                (datetime.now().isoformat(), json.dumps(item["result"]), item["id"]),
            )
            done += 1
        else:
            conn.execute(
                "UPDATE kommuner SET status='failed', batch_id=3, completed_at=?, error=? WHERE id=?",
                (datetime.now().isoformat(), item.get("error", "Unknown"), item["id"]),
            )
            failed += 1
    conn.commit()
    conn.close()
    print(f"Batch 3: {done} done, {failed} failed")


def get_progress():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done, SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed FROM kommuner"
    )
    row = cursor.fetchone()
    conn.close()
    return row


if __name__ == "__main__":
    store_results()
    total, done, failed = get_progress()
    print(f"Progress: {done}/{total} ({done/total*100:.1f}%), Failed: {failed}")
