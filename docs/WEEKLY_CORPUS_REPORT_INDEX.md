# Weekly Corpus Report - Complete File Index

**Date Created**: 2025-12-15
**Status**: Production Ready
**Last Updated**: 2025-12-15 20:23

## Main Deliverable

### N8N Workflow JSON
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/n8n_workflows/weekly_corpus_report.json`

Complete, importable n8n workflow for automated weekly corpus reporting.

**Specifications**:
- 8 nodes (Trigger, Execute, Parse, Format, Send, Check, Log)
- Cron schedule: Every Sunday 18:00 UTC
- JSON validated: YES
- Size: 9.6 KB
- Import: n8n UI → "+" → "Import from file" → select this JSON

---

## Documentation (4 Files)

### 1. Quick Start Guide
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/QUICK_START.md`

- **Duration**: 2-minute read
- **Best For**: Getting started immediately
- **Contents**:
  - 30-second setup
  - File list
  - Quick troubleshooting
  - Example report

### 2. Detailed Setup & Reference
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/n8n_workflows/README_WEEKLY_CORPUS_REPORT.md`

- **Duration**: 10-minute read
- **Best For**: Complete technical reference
- **Contents**:
  - Full workflow explanation
  - Environment variable setup
  - Telegram credential guide
  - Troubleshooting section
  - Performance notes

### 3. Implementation Overview
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/WEEKLY_CORPUS_REPORT_SUMMARY.md`

- **Duration**: 15-minute read
- **Best For**: Understanding the complete system
- **Contents**:
  - Architecture overview
  - Node details (all 8)
  - Deployment steps
  - Current corpus statistics
  - Performance metrics

### 4. Deployment Checklist
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/DEPLOYMENT_CHECKLIST.md`

- **Duration**: Ongoing reference during deployment
- **Best For**: Step-by-step verification
- **Contents**:
  - Pre-deployment checklist
  - 7 deployment steps
  - Test results
  - Post-deployment verification
  - Troubleshooting table
  - Rollback procedures

---

## Executable Scripts (2 Files)

### 1. Telegram Setup Assistant
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/setup_telegram_workflow.sh`

**Status**: Executable, Interactive

**Usage**:
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
./setup_telegram_workflow.sh
```

**Purpose**:
- Guides through Telegram bot creation
- Validates bot token
- Creates `.env` file with credentials
- Sets permissions (600)

**Output**: `.env` file with:
```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIJKlmnoPQRstuvWXYZabcdefGHI
TELEGRAM_CHAT_ID=-1001234567890
```

### 2. Standalone Test Script
**File**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/test_corpus_report.py`

**Status**: Executable, Tested

**Usage**:
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
python3 test_corpus_report.py
```

**Purpose**:
- Test workflow logic without n8n
- Verify ChromaDB access
- Generate sample report
- Output formatted Markdown + JSON

**Output Example**:
```
============================================================
GENERATED REPORT:
============================================================

📋 *VECKORAPPORT - CORPUS STATUS*

📅 Vecka: 2025-12-15 - 2025-12-15
⏰ Uppdaterad: 20:22:26

📊 *DOKUMENTSAMLING*
✅ Totalt indexerade dokument: 535,024
📄 PDF-filer i cache: 6,912
...
```

---

## Auto-Generated Directories

### Report Archive
**Path**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_reports/`

**Created By**: Workflow node "Log Report to File"

**Contents**: Weekly JSON reports
- Filename format: `corpus_report_YYYY-MM-DD_HH-mm.json`
- Created: Every workflow execution
- Example: `corpus_report_2025-12-21_18-00.json`

**Usage**:
```bash
ls -lth corpus_reports/ | head -5    # View latest 5 reports
cat corpus_reports/[filename] | jq . # View specific report
```

### Environment File
**Path**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/.env`

**Created By**: `setup_telegram_workflow.sh` script

**Contents**:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

**Permissions**: 600 (read/write owner only)

---

## Directory Structure

```
/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/
│
├── n8n_workflows/
│   ├── weekly_corpus_report.json ← MAIN WORKFLOW
│   └── README_WEEKLY_CORPUS_REPORT.md
│
├── QUICK_START.md ← START HERE (2 min)
├── WEEKLY_CORPUS_REPORT_INDEX.md (this file)
├── WEEKLY_CORPUS_REPORT_SUMMARY.md ← Full overview
├── DEPLOYMENT_CHECKLIST.md ← Step-by-step guide
│
├── test_corpus_report.py ← Test script
├── setup_telegram_workflow.sh ← Setup assistant
│
├── .env (auto-created)
│   ├── TELEGRAM_BOT_TOKEN
│   └── TELEGRAM_CHAT_ID
│
├── corpus_reports/ (auto-created)
│   ├── corpus_report_2025-12-21_18-00.json
│   ├── corpus_report_2025-12-28_18-00.json
│   └── ...
│
├── chromadb_data/ (existing, 16 GB)
│   ├── chroma.sqlite3
│   └── [collection directories]
│
└── pdf_cache/ (existing, 18 GB)
    └── [6,912 PDF files]
```

---

## Quick Navigation

### "I want to..."

**...get started immediately**
→ Read: `QUICK_START.md` (2 min)
→ Run: `./setup_telegram_workflow.sh` (5 min)

**...understand how it works**
→ Read: `WEEKLY_CORPUS_REPORT_SUMMARY.md` (15 min)

**...deploy it step by step**
→ Read: `DEPLOYMENT_CHECKLIST.md`
→ Follow: 7 deployment steps

**...test it without n8n**
→ Run: `python3 test_corpus_report.py` (instant)

**...troubleshoot an issue**
→ Read: `DEPLOYMENT_CHECKLIST.md` → Troubleshooting section

**...reference technical details**
→ Read: `n8n_workflows/README_WEEKLY_CORPUS_REPORT.md`

**...see what reports look like**
→ Read: Any section with "Report Example"
→ Or: `cat corpus_reports/[latest].json | jq .`

---

## File Manifest

| File | Type | Size | Purpose | Usage |
|------|------|------|---------|-------|
| weekly_corpus_report.json | JSON | 9.6K | n8n workflow | Import to n8n |
| test_corpus_report.py | Python | 4.7K | Test script | `python3 test_corpus_report.py` |
| setup_telegram_workflow.sh | Bash | 4.3K | Setup helper | `./setup_telegram_workflow.sh` |
| README_WEEKLY_CORPUS_REPORT.md | Markdown | 6.1K | Technical docs | Reference |
| QUICK_START.md | Markdown | 2.3K | Quick ref | First read |
| WEEKLY_CORPUS_REPORT_SUMMARY.md | Markdown | 8.7K | Overview | Architecture |
| DEPLOYMENT_CHECKLIST.md | Markdown | 5.2K | Deployment | Step-by-step |
| WEEKLY_CORPUS_REPORT_INDEX.md | Markdown | (this) | Navigation | Browse files |

---

## Workflow Node Details

| # | Node Name | Type | Purpose |
|---|-----------|------|---------|
| 1 | Every Sunday 18:00 | Schedule Trigger | Weekly cron trigger |
| 2 | Get ChromaDB Statistics | Execute Command | Query corpus database |
| 3 | Get PDF Cache Size | Execute Command | Measure storage (parallel) |
| 4 | Parse Statistics | Code | Combine parallel outputs |
| 5 | Format Report | Code | Create Markdown report |
| 6 | Send to Telegram | HTTP Request | Post to Telegram API |
| 7 | Error Occurred? | Conditional | Check for errors |
| 8 | Log Report to File | Code | Save to disk |

---

## Current Corpus Metrics (2025-12-15 20:22)

**Documents**: 535,024
- riksdag_documents_p1: 230,143
- swedish_gov_docs: 304,871
- riksdag_documents: 10

**Storage**: 34 GB total
- ChromaDB dir: 16 GB
- chroma.sqlite3: 14.14 GB
- pdf_cache: 18 GB

**Files**: 6,912 PDFs

---

## Deployment Timeline

| Step | Action | Time | Status |
|------|--------|------|--------|
| 1 | Read QUICK_START.md | 2 min | Before start |
| 2 | Run setup_telegram_workflow.sh | 5 min | Interactive |
| 3 | Run test_corpus_report.py | <1 min | Instant feedback |
| 4 | Import JSON to n8n | 2 min | UI action |
| 5 | Configure env vars | 2 min | UI action |
| 6 | Test execution | <1 min | Verify |
| 7 | Monitor Sunday 18:00 | - | Ongoing |
| **Total** | **Complete Setup** | **12 min** | **Ready** |

---

## Production Checklist

Before running in production:

- [ ] Telegram bot token obtained
- [ ] Chat ID verified
- [ ] `.env` file created
- [ ] Test script runs successfully
- [ ] JSON imports to n8n without errors
- [ ] Environment variables configured in n8n
- [ ] Test execution sends Telegram message
- [ ] Report directory created
- [ ] Cron schedule verified (Sunday 18:00 UTC)

---

## Support & Troubleshooting

### Common Issues

**"Command execution failed"**
- Check Python 3 installed: `python3 --version`
- Check chromadb package: `python3 -c "import chromadb"`
- Check paths exist: `ls -la chromadb_data/`

**"Telegram authentication failed"**
- Verify token: `curl https://api.telegram.org/botTOKEN/getMe`
- Check chat ID (negative for groups): `-1001234567890`
- Verify bot added to chat

**"No report file created"**
- Check directory: `ls -la corpus_reports/`
- Check permissions: `ls -la .env`
- Run test script: `python3 test_corpus_report.py`

### Getting Help

1. **Instant**: Run `python3 test_corpus_report.py` for diagnostics
2. **Quick**: Read `QUICK_START.md` or `README_WEEKLY_CORPUS_REPORT.md`
3. **Detailed**: Check `DEPLOYMENT_CHECKLIST.md` troubleshooting section
4. **Full**: Review `WEEKLY_CORPUS_REPORT_SUMMARY.md`

---

## Version Info

- **Created**: 2025-12-15
- **Last Updated**: 2025-12-15 20:23
- **Status**: Production Ready
- **n8n Compatibility**: 0.195+
- **Python Version**: 3.8+
- **ChromaDB Version**: 0.3+

---

## Quick Commands Reference

```bash
# Setup
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
./setup_telegram_workflow.sh

# Test
python3 test_corpus_report.py

# View reports
ls -lth corpus_reports/
cat corpus_reports/$(ls -t corpus_reports/ | head -1) | jq .

# Check n8n
systemctl status n8n

# View logs
journalctl -u n8n -f

# Validate JSON
python3 -m json.tool n8n_workflows/weekly_corpus_report.json
```

---

**All files ready for production deployment.**
**Next step**: Read `QUICK_START.md` and run `./setup_telegram_workflow.sh`

Good luck! 🚀
