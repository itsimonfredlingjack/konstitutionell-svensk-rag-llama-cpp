#!/bin/bash
# Daily news scraper - runs at 06:00
# Scrapes SR sitemap + SVT RSS feeds, embeds to Qdrant

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$(dirname "$SCRIPT_DIR")/venv"
LOG_FILE="$SCRIPT_DIR/logs/daily_scrape_$(date +%Y%m%d).log"

mkdir -p "$SCRIPT_DIR/logs"

echo "========================================" >> "$LOG_FILE"
echo "Daily scrape started: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

cd "$SCRIPT_DIR"
source "$VENV_DIR/bin/activate"

# Scrape SR sitemap
echo "--- SR Sitemap ---" >> "$LOG_FILE"
python sitemap_crawler.py 2>&1 >> "$LOG_FILE"

# Scrape SVT RSS feeds
echo "--- SVT RSS ---" >> "$LOG_FILE"
python sitemap_crawler.py svt 2>&1 >> "$LOG_FILE"

# Embed new articles to Qdrant
echo "--- Embedding ---" >> "$LOG_FILE"
python embed_news.py 2>&1 >> "$LOG_FILE"

# Summary
echo "" >> "$LOG_FILE"
echo "--- Summary ---" >> "$LOG_FILE"
wc -l data/*.jsonl 2>&1 >> "$LOG_FILE"
echo "Completed: $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
