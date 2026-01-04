#!/bin/bash
# JO Downloader - Usage Examples
# This file shows common usage patterns and commands

# Navigate to project directory
cd /home/dev/juridik-ai

# ==============================================================================
# BASIC USAGE
# ==============================================================================

# 1. Download default range (2020-2024)
python3 pipelines/jo_downloader.py

# 2. Download single year
python3 pipelines/jo_downloader.py 2023

# 3. Download custom year range
python3 pipelines/jo_downloader.py 2015-2024

# 4. Download historical range
python3 pipelines/jo_downloader.py 1970-2024


# ==============================================================================
# CHECKING DOWNLOADS
# ==============================================================================

# List all downloaded files
python3 pipelines/jo_downloader.py --list

# Show download status
python3 pipelines/jo_downloader.py --status

# List files directly
ls -lh data/jo/jo_ambetsberattelse_*.pdf

# View metadata
cat data/jo/download_metadata.json | python3 -m json.tool

# Check log file
tail -f data/jo/download.log


# ==============================================================================
# ADVANCED OPTIONS
# ==============================================================================

# Faster downloads (reduce rate limit)
python3 pipelines/jo_downloader.py 2020-2024 -d 1.0

# Slower downloads (for network issues)
python3 pipelines/jo_downloader.py 2020-2024 -d 5.0

# Longer timeout for slow connections
python3 pipelines/jo_downloader.py 2020-2024 -t 60

# More retry attempts for unstable connections
python3 pipelines/jo_downloader.py 2020-2024 -r 5

# Verbose debug mode
python3 pipelines/jo_downloader.py 2020-2024 -v

# Download to custom location
python3 pipelines/jo_downloader.py 2020-2024 -o /tmp/jo_reports/

# Combine multiple options
python3 pipelines/jo_downloader.py 2015-2024 -d 1.5 -t 45 -r 4 -v


# ==============================================================================
# RESUMING DOWNLOADS
# ==============================================================================

# Start download (will be interrupted)
python3 pipelines/jo_downloader.py 2020-2024
# [Press Ctrl+C to interrupt]

# Resume - just run the same command again
# It will automatically skip completed files and continue
python3 pipelines/jo_downloader.py 2020-2024

# Check what was downloaded during the partial run
python3 pipelines/jo_downloader.py --list


# ==============================================================================
# TROUBLESHOOTING
# ==============================================================================

# Test with verbose logging
python3 pipelines/jo_downloader.py 2024 -v

# Check for partial or corrupted files
ls -lah data/jo/jo_ambetsberattelse_*.pdf

# View error messages in log
grep ERROR data/jo/download.log

# View all attempts in metadata
cat data/jo/download_metadata.json

# Test single year with debug info
python3 pipelines/jo_downloader.py 2023 -v -d 1.0


# ==============================================================================
# BATCH OPERATIONS
# ==============================================================================

# Download in multiple batches (if needed for stability)
python3 pipelines/jo_downloader.py 2020-2022
python3 pipelines/jo_downloader.py 2023-2024

# Download with conservative settings
python3 pipelines/jo_downloader.py 2015-2024 -d 3.0 -t 45 -r 5

# Download and save detailed log
python3 pipelines/jo_downloader.py 2020-2024 -v | tee data/jo/detailed_download_$(date +%Y%m%d_%H%M%S).log


# ==============================================================================
# FILE OPERATIONS
# ==============================================================================

# Count downloaded files
find data/jo -name "jo_ambetsberattelse_*.pdf" | wc -l

# Check total file size
du -sh data/jo/

# List by size
ls -lhS data/jo/jo_ambetsberattelse_*.pdf

# Verify all files are readable
file data/jo/jo_ambetsberattelse_*.pdf

# Extract pages from a PDF (requires pdfinfo/pdftotext)
pdfinfo data/jo/jo_ambetsberattelse_2024.pdf


# ==============================================================================
# SCHEDULING (Cron Examples)
# ==============================================================================

# Run weekly update (add to crontab)
# 0 2 * * 0 python3 pipelines/jo_downloader.py 2020-2024

# Run monthly with verbose logging
# 0 3 1 * * cd /home/dev/juridik-ai && python3 pipelines/jo_downloader.py 2010-2024 -v >> data/jo/cron_$(date +\%Y\%m).log 2>&1


# ==============================================================================
# INTEGRATION WITH OTHER TOOLS
# ==============================================================================

# Use with xargs to process each file
ls data/jo/jo_ambetsberattelse_*.pdf | xargs -I {} sh -c 'echo "Processing: {}"; pdftotext "{}" "{}.txt"'

# Find all files modified in the last 7 days
find data/jo -name "jo_ambetsberattelse_*.pdf" -mtime -7

# Archive old downloads
tar -czf data/jo/archive_before_2020.tar.gz data/jo/jo_ambetsberattelse_201*.pdf

# Remove files for specific years
rm data/jo/jo_ambetsberattelse_2015.pdf
# Note: Also remove from download_metadata.json to allow re-download


# ==============================================================================
# MONITORING
# ==============================================================================

# Watch for new downloads in real-time
watch -n 1 'ls -lh data/jo/jo_ambetsberattelse_*.pdf | tail -5'

# Monitor the log file in real-time
tail -f data/jo/download.log

# Parse log for statistics
grep "Successfully downloaded" data/jo/download.log | wc -l

# Show failed downloads
grep "failed\|Failed\|error\|Error" data/jo/download.log


# ==============================================================================
# HELP AND DOCUMENTATION
# ==============================================================================

# Show script help
python3 pipelines/jo_downloader.py --help

# View README
less pipelines/JO_DOWNLOADER_README.md

# View quick start
less pipelines/QUICK_START.md
