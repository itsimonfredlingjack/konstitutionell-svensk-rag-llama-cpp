# Weekly Corpus Report - Quick Start

## 30-Second Setup

```bash
# 1. Run setup assistant (5 minutes)
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
./setup_telegram_workflow.sh

# 2. Test the workflow (2 minutes)
python3 test_corpus_report.py

# 3. Check the output
cat corpus_reports/$(ls -t corpus_reports/ | head -1) | jq .
```

## In n8n (5 minutes)

1. **Import Workflow**
   - Click "+" → "Import from file"
   - Select: `n8n_workflows/weekly_corpus_report.json`
   - Save

2. **Add Environment Variables**
   - Settings → Environment Variables
   - `TELEGRAM_BOT_TOKEN` = (from setup)
   - `TELEGRAM_CHAT_ID` = (from setup)
   - Save

3. **Test It**
   - Open workflow
   - Click "Execute Workflow"
   - Check Telegram for message

4. **Done!**
   - Workflow will run automatically every Sunday at 18:00

## Files You Need

| File | Purpose | Location |
|------|---------|----------|
| `weekly_corpus_report.json` | n8n workflow | `n8n_workflows/` |
| `test_corpus_report.py` | Test script | Root directory |
| `setup_telegram_workflow.sh` | Setup helper | Root directory |
| `.env` | Credentials | Root directory (auto-created) |

## What It Does

- Runs every Sunday at 18:00
- Counts documents in ChromaDB (535K+ docs)
- Measures storage usage (34GB total)
- Sends nice report to Telegram
- Saves report to disk

## Sample Report

```
📋 *VECKORAPPORT - CORPUS STATUS*

📅 Vecka: 2025-12-08 - 2025-12-15
⏰ Uppdaterad: 18:00:00

📊 *DOKUMENTSAMLING*
✅ Totalt indexerade dokument: 535,024
📄 PDF-filer i cache: 6,912

💾 *LAGRINGSANVÄNDNING*
📦 ChromaDB total: 16G
🗄️ Database fil: 14.14 GB
📁 PDF cache: 18G

🏢 *SAMLING-UPPDELNING*
  • riksdag_documents: 10
  • swedish_gov_docs: 304,871
  • riksdag_documents_p1: 230,143
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot token invalid | Re-run `./setup_telegram_workflow.sh` |
| No Telegram message | Run `python3 test_corpus_report.py` to test |
| Statistics wrong | Check `/chromadb_data/` permissions |
| Scheduled execution fails | Check n8n is running: `systemctl status n8n` |

## Full Documentation

See `README_WEEKLY_CORPUS_REPORT.md` for complete details.

---

**That's it! Your corpus reporting is ready to go.** 🚀
