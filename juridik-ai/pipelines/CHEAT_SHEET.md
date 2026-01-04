# Riksdagen Client - Cheat Sheet

## Import
```python
from pipelines.riksdagen_client import RiksdagenClient, Document, DocumentType
```

## Initialize
```python
client = RiksdagenClient()
# Custom config:
client = RiksdagenClient(
    base_dir="/path/to/dir",
    rate_limit_delay=1.0,
    timeout=60
)
```

## Search
```python
# Basic search
docs = client.search_documents(
    doktyp="prop",
    year_from=2024,
    year_to=2024
)

# With filter
docs = client.search_documents(
    doktyp="mot",
    year_from=2023,
    year_to=2024,
    search_term="hälsa",
    max_results=100
)
```

## Get Single Document
```python
doc = client.get_document("1984:1234")
if doc:
    print(doc.titel)
    print(doc.dokumentstatus)
```

## Download
```python
# Single document
filepath = client.download_document(doc, file_format='pdf')

# Multiple documents
for doc in documents[:10]:
    filepath = client.download_document(doc, file_format='pdf')

# Batch with resume
total, downloaded, failed = client.download_all(
    doktyp="mot",
    year_range=(2024, 2024),
    file_format="pdf",
    resume=True
)
```

## Export & Stats
```python
# Export metadata
metadata_file = client.export_metadata(documents)

# Get statistics
stats = client.get_statistics()
print(f"Total: {stats['total_documents']}")
print(f"Size: {stats['total_size_mb']} MB")
```

## Document Types
```python
DocumentType.PROPOSITION.value      # "prop"
DocumentType.MOTION.value           # "mot"
DocumentType.SOU.value              # "sou"
DocumentType.BETANKANDE.value       # "bet"
DocumentType.INTERPELLATION.value   # "ip"
DocumentType.FRÅGA_UTAN_SVAR.value  # "fsk"
DocumentType.DIREKTIV.value         # "dir"
DocumentType.DEPARTEMENTSSKRIVELSE.value  # "ds"
DocumentType.SKRIVELSE.value        # "skr"
```

## Document Attributes
```python
doc.dokid               # ID: "1984:1234"
doc.titel              # Title
doc.subtitel           # Subtitle
doc.doktyp             # Type: "prop", "mot", etc.
doc.publicerad         # Date: "2024-01-15"
doc.rm                 # Session: "2023/24"
doc.beteckning         # Designation
doc.dokumentstatus     # Status
doc.url                # Text URL
doc.html_url           # HTML URL
doc.pdf_url            # PDF URL
doc.dokstat            # Status code
```

## Error Handling
```python
try:
    docs = client.search_documents(doktyp="prop", year_from=2024, year_to=2024)
except Exception as e:
    print(f"Error: {e}")
```

## Resume Download
```python
# Interrupted? Just run again:
total, downloaded, failed = client.download_all(
    doktyp="prop",
    year_range=(2023, 2024),
    resume=True  # Automatically continues from checkpoint
)
```

## Configuration
```python
# Faster (use with caution)
client = RiksdagenClient(rate_limit_delay=0.25)

# Slower (safer)
client = RiksdagenClient(rate_limit_delay=2.0)

# Longer timeout
client = RiksdagenClient(timeout=60)
```

## File Output
```
/home/dev/juridik-ai/data/riksdagen/
├── prop/          # Downloaded propositions
├── mot/           # Downloaded motions
├── sou/           # Downloaded SOU reports
├── metadata_*.json   # Metadata export
└── session.log       # Activity log
```

## CLI Usage
```bash
# Search and download propositions from 2024
python examples/riksdagen_bulk_download.py \
    --doktyp prop \
    --year-from 2024 \
    --year-to 2024

# Download motions from 2023-2024 as HTML
python examples/riksdagen_bulk_download.py \
    --doktyp mot \
    --year-from 2023 \
    --year-to 2024 \
    --format html

# Show statistics
python examples/riksdagen_bulk_download.py --stats

# Custom rate limit (slower)
python examples/riksdagen_bulk_download.py \
    --doktyp sou \
    --rate-limit 1.0 \
    --year-from 2020 \
    --year-to 2024
```

## Run Tests
```bash
# All tests
pytest tests/test_riksdagen_client.py -v

# Specific test
pytest tests/test_riksdagen_client.py::TestRiksdagenClientInit -v

# With coverage
pytest tests/test_riksdagen_client.py --cov=pipelines.riksdagen_client
```

## Run Examples
```bash
# All examples
python examples/riksdagen_examples.py

# Specific example
python examples/riksdagen_examples.py 1    # Basic search
python examples/riksdagen_examples.py 5    # Batch download
python examples/riksdagen_examples.py 10   # Resume capability
```

## Logging
```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
```

## Common Patterns
```python
# Search and download
docs = client.search_documents(doktyp="prop", year_from=2024, year_to=2024)
for doc in docs[:10]:
    client.download_document(doc, file_format='pdf')

# Search, export, and download
docs = client.search_documents(doktyp="bet", year_from=2024, year_to=2024)
client.export_metadata(docs)
total, downloaded, failed = client.download_all(
    doktyp="bet",
    year_range=(2024, 2024)
)

# Get statistics
stats = client.get_statistics()
for dtype, info in stats['document_types'].items():
    print(f"{dtype}: {info['count']} docs")
```

## Troubleshooting
```python
# No documents found?
# 1. Check doktyp is valid
# 2. Try different year range
# 3. Remove search_term filter

# Download fails?
# 1. Increase timeout: RiksdagenClient(timeout=60)
# 2. Decrease rate: RiksdagenClient(rate_limit_delay=2.0)

# Resume not working?
# 1. Delete checkpoints: rm /path/to/riksdagen/.checkpoint_*.json
# 2. Start fresh with resume=False
```

## API Limits
- Max page size: 500 documents
- Default rate limit: 0.5 seconds (2 req/sec)
- Timeout: 30 seconds per request
- Retry: Auto-retry on 429/50x errors

## Documentation Links
- Full docs: `pipelines/RIKSDAGEN_CLIENT_README.md`
- Quick start: `pipelines/RIKSDAGEN_QUICK_START.md`
- Summary: `RIKSDAGEN_MODULE_SUMMARY.md`
- Index: `RIKSDAGEN_INDEX.md`
- Examples: `examples/riksdagen_examples.py`
- Tests: `tests/test_riksdagen_client.py`
