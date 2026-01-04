# JO Downloader - Quick Start Guide

## Installation

No installation required beyond the standard library. Dependencies:
```bash
pip install requests urllib3
```

Both are typically already installed. The script works with Python 3.6+.

## Quick Commands

### Download Default Range (2020-2024)
```bash
cd /home/dev/juridik-ai
python3 pipelines/jo_downloader.py
```

### Download Specific Year
```bash
python3 pipelines/jo_downloader.py 2023
```

### Download Custom Range
```bash
python3 pipelines/jo_downloader.py 2015-2024
```

### List Downloaded Files
```bash
python3 pipelines/jo_downloader.py --list
```

### Show Full Status
```bash
python3 pipelines/jo_downloader.py --status
```

### Resume Interrupted Download
Just run the same command again - it will skip already downloaded files:
```bash
python3 pipelines/jo_downloader.py 2020-2024
```

## Output

Files are saved to:
```
/home/dev/juridik-ai/data/jo/
```

Naming format:
```
jo_ambetsberattelse_2024.pdf
jo_ambetsberattelse_2023.pdf
```

## Logs

View download progress and errors:
```bash
tail -f /home/dev/juridik-ai/data/jo/download.log
```

Download metadata:
```bash
cat /home/dev/juridik-ai/data/jo/download_metadata.json
```

## Common Tasks

### Download All Years from 1970s to 2024
```bash
# This will attempt years that may not exist - they'll be marked as "not_found"
python3 pipelines/jo_downloader.py 1970-2024
```

### Increase Rate Limit (for faster downloads)
```bash
python3 pipelines/jo_downloader.py 2020-2024 -d 1.0
```

### Slow Down (for network issues)
```bash
python3 pipelines/jo_downloader.py 2020-2024 -d 5.0
```

### Set Longer Timeout (for slow connections)
```bash
python3 pipelines/jo_downloader.py 2020-2024 -t 60
```

### Verbose Debug Mode
```bash
python3 pipelines/jo_downloader.py 2020-2024 -v
```

### Download to Custom Location
```bash
python3 pipelines/jo_downloader.py 2020-2024 -o /tmp/jo_reports/
```

## What Gets Downloaded

The script downloads official annual reports from:
- **Source:** https://www.jo.se/
- **Collection:** Ämbetsberättelser (Official Reports)
- **Years:** Available from 1970s onwards
- **Format:** PDF

## Troubleshooting

### Connection Issues
- Increase delay: `-d 5.0`
- Increase timeout: `-t 60`
- Increase retries: `-r 5`

### Network Interrupted
Just run the command again - downloads are resumed automatically.

### File Permission Issues
Ensure the output directory is writable:
```bash
mkdir -p /home/dev/juridik-ai/data/jo
chmod 755 /home/dev/juridik-ai/data/jo
```

### Check What's Been Downloaded
```bash
ls -lh /home/dev/juridik-ai/data/jo/jo_*.pdf
```

## Performance

- Average download time: 5-10 seconds per file
- With rate limiting (2 sec default): ~1 minute for 5 files
- Full range (2020-2024): ~1 minute total

## For More Details

See `JO_DOWNLOADER_README.md` for complete documentation.
