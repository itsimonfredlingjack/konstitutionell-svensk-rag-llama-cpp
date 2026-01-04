#!/usr/bin/env python3
"""
SCB Quick Test - Scrapa 1200 tabeller för att verifiera systemet fungerar
"""

# Sätt MAX_TABLES_LIMIT innan vi importerar scb_scraper
import scb_scraper

scb_scraper.MAX_TABLES_LIMIT = 1200
scb_scraper.RATE_LIMIT_DELAY = 1.0  # 1 sekund delay

# Kör scrapern
import asyncio

asyncio.run(scb_scraper.main())
