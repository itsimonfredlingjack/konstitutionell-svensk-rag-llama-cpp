# JO Ämbetsberättelser Downloader

A robust Python script for downloading JO (Justitieombudsmans) annual reports (ämbetsberättelser) PDFs from jo.se.

## Features

- Downloads PDFs from jo.se with proper rate limiting
- Skips already downloaded files (resume support)
- Handles network errors and timeouts with exponential backoff
- Maintains download metadata in JSON format
- Comprehensive logging to both file and console
- Support for year ranges (e.g., 2020-2024)
- Automatic directory creation
- Configurable request timeout and retry attempts

## Requirements

```bash
pip install requests urllib3
```

## Installation

The script is located at:
```
/home/dev/juridik-ai/pipelines/jo_downloader.py
```

Downloaded PDFs are saved to:
```
/home/dev/juridik-ai/data/jo/
```

Download logs are written to:
```
/home/dev/juridik-ai/data/jo/download.log
```

Metadata is tracked in:
```
/home/dev/juridik-ai/data/jo/download_metadata.json
```

## Usage

### Basic Usage

Download default range (2020-2024):
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py
```

Download a specific year:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2023
```

Download a specific range:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2015-2024
```

### List Downloaded Files

```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py --list
```

Show status:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py --status
```

### Advanced Options

Customize output directory:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024 -o /custom/path/
```

Adjust rate limiting (seconds between requests):
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024 -d 1.0
```

Set request timeout (seconds):
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024 -t 60
```

Set maximum retry attempts:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024 -r 5
```

Enable verbose logging:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024 -v
```

## File Naming

Downloaded files follow this consistent naming pattern:
```
jo_ambetsberattelse_YYYY.pdf
```

Example:
```
jo_ambetsberattelse_2024.pdf
jo_ambetsberattelse_2023.pdf
jo_ambetsberattelse_2022.pdf
```

## Resume & Continuation

The script automatically:
1. Checks if files are already downloaded before attempting download
2. Maintains metadata in `download_metadata.json`
3. Can be interrupted and resumed (Ctrl+C)
4. Skips successfully downloaded files on subsequent runs

To resume a partial download:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024
```

It will automatically skip years that were already successfully downloaded.

## Error Handling

The script handles:
- Network timeouts (with exponential backoff)
- HTTP errors (404, 500, 502, 503, 504)
- File system errors
- Incomplete/corrupted downloads (file size validation)
- Connection interruptions

Each failed year is logged in the metadata file with status 'failed'.

## Logging

### Log Output

Logs are written to both console and file:
```
/home/dev/juridik-ai/data/jo/download.log
```

Example log entries:
```
2025-11-27 10:30:45,123 - INFO - JO Downloader initialized. Output dir: /home/dev/juridik-ai/data/jo/
2025-11-27 10:30:45,456 - INFO - Starting downloads for years 2020-2024
2025-11-27 10:30:45,789 - INFO - Year 2024 already downloaded (size: 2450123 bytes)
2025-11-27 10:30:47,890 - INFO - Downloading year 2023 from jo.se: https://www.jo.se/app/uploads/2023/ambetsberattelse_2023.pdf
2025-11-27 10:30:52,345 - INFO - Year 2023: Successfully downloaded (2341234 bytes)
```

### Verbose Mode

Enable detailed debug logging:
```bash
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024 -v
```

## Metadata File Format

The `download_metadata.json` file tracks all download attempts:

```json
{
  "2024": {
    "status": "completed",
    "timestamp": "2025-11-27T10:30:52.345678",
    "source": "jo.se",
    "size": 2450123
  },
  "2023": {
    "status": "completed",
    "timestamp": "2025-11-27T10:30:47.890123",
    "source": "jo.se",
    "size": 2341234
  },
  "2020": {
    "status": "failed",
    "timestamp": "2025-11-27T10:25:30.123456"
  },
  "2019": {
    "status": "not_found",
    "timestamp": "2025-11-27T10:25:15.654321"
  }
}
```

Status values:
- `completed`: Successfully downloaded
- `failed`: Download failed after all retries
- `not_found`: File not available (404)
- `invalid_size`: Downloaded file was too small

## Example Workflow

```bash
# First run - download 2020-2024
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2020-2024

# Check what was downloaded
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py --list

# Later - expand to include older years
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py 2015-2024

# Check final status
python3 /home/dev/juridik-ai/pipelines/jo_downloader.py --status
```

## Troubleshooting

### 404 Not Found Errors

If a year returns 404, it means that particular year's report is not available at the standard URL path. This is recorded in the metadata as `not_found`.

### Timeout Errors

If you experience frequent timeouts:
1. Increase the delay between requests: `-d 5.0`
2. Increase the request timeout: `-t 60`
3. Check your network connection

### File Size Issues

The script validates that downloaded files are at least 1KB. Suspiciously small files are rejected and logged.

## Rate Limiting

The script includes:
- Configurable delay between requests (default: 2 seconds)
- Exponential backoff for retries (2^attempt seconds)
- Automatic retry on transient failures (429, 5xx errors)

This is respectful of jo.se's servers and follows good web scraping practices.

## Return Codes

- `0`: Success (all files downloaded or already present)
- `1`: One or more downloads failed
- `130`: Interrupted by user (Ctrl+C)

## File Structure

```
/home/dev/juridik-ai/
├── pipelines/
│   ├── jo_downloader.py           # Main script
│   └── JO_DOWNLOADER_README.md    # This file
└── data/
    └── jo/
        ├── jo_ambetsberattelse_2024.pdf
        ├── jo_ambetsberattelse_2023.pdf
        ├── jo_ambetsberattelse_2022.pdf
        ├── download.log            # Activity log
        └── download_metadata.json  # Download metadata
```

## Performance

- Rate limiting: 2 seconds between requests (configurable)
- Typical download time: 5-10 seconds per file
- Full range (2020-2024): approximately 1 minute including rate limiting

## License

This script is provided as-is for accessing publicly available documents from Jo.se.

## References

- Jo.se: https://www.jo.se
- Ämbetsberättelser: https://www.jo.se/om-jo/ambetsberattelser/
- Riksdagen Database: https://www.riksdagen.se/
