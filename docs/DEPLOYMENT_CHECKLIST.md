# Weekly Corpus Report - Deployment Checklist

## Pre-Deployment Verification

- [x] **Workflow JSON Created**
  - File: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/n8n_workflows/weekly_corpus_report.json`
  - Size: 9.6 KB
  - Status: JSON validated

- [x] **Python Test Script Created**
  - File: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/test_corpus_report.py`
  - Size: 4.7 KB
  - Status: Executable, tested successfully
  - Last test: 2025-12-15 20:22:26

- [x] **Setup Assistant Created**
  - File: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/setup_telegram_workflow.sh`
  - Size: 4.3 KB
  - Status: Executable, interactive

- [x] **Documentation Complete**
  - README_WEEKLY_CORPUS_REPORT.md (6.1 KB) - Full setup guide
  - WEEKLY_CORPUS_REPORT_SUMMARY.md (8.7 KB) - Implementation overview
  - QUICK_START.md (2.3 KB) - Quick reference
  - DEPLOYMENT_CHECKLIST.md (this file) - Verification

## Test Results (2025-12-15 20:22)

### Corpus Statistics Verified
- Total Documents: 535,024 ✓
  - riksdag_documents_p1: 230,143 ✓
  - swedish_gov_docs: 304,871 ✓
  - riksdag_documents: 10 ✓
- PDF Files: 6,912 ✓
- Storage: 34 GB total ✓

### Workflow Logic Tested
- ChromaDB query: ✓
- PDF cache counting: ✓
- Report formatting: ✓
- Swedish text encoding: ✓
- Error handling: ✓

## Deployment Steps

### Step 1: Prepare Telegram Credentials
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
./setup_telegram_workflow.sh
```
Expected output: `.env` file with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

- [ ] Bot token obtained from @BotFather
- [ ] Chat ID obtained and verified
- [ ] `.env` file created successfully

### Step 2: Test Workflow (Optional but Recommended)
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
python3 test_corpus_report.py
```
Expected: Full report output with corpus statistics

- [ ] Script executes without errors
- [ ] Statistics match expected values
- [ ] Report formatting looks correct

### Step 3: Import to n8n
1. Open n8n dashboard at `http://localhost:5678`
2. Click "+" → "Import from file"
3. Select: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/n8n_workflows/weekly_corpus_report.json`
4. Confirm import
5. Click "Save"

- [ ] Workflow imported successfully
- [ ] All 8 nodes visible
- [ ] No import errors

### Step 4: Configure Environment Variables
1. Click "Settings" (gear icon)
2. Go to "Environment Variables"
3. Add new variable:
   - Key: `TELEGRAM_BOT_TOKEN`
   - Value: (from `.env` file)
4. Add another variable:
   - Key: `TELEGRAM_CHAT_ID`
   - Value: (from `.env` file)
5. Save

- [ ] Both variables added
- [ ] Values copied correctly
- [ ] No validation errors

### Step 5: Test Execution
1. Open the workflow
2. Click "Execute Workflow" button
3. Wait for execution to complete
4. Check Telegram for report message

- [ ] Workflow executes without errors
- [ ] Telegram message received
- [ ] Report data is correct

### Step 6: Verify Scheduled Execution
1. Open the workflow
2. Click "Every Sunday 18:00" node
3. Verify schedule is set to:
   - Day of week: Sunday (0)
   - Hour: 18
   - Minute: 0 (UTC)

- [ ] Schedule configured correctly
- [ ] Cron rule shows "Every Sunday at 18:00"

### Step 7: Monitor First Execution
On the next Sunday at 18:00 UTC:
- [ ] Workflow executes automatically
- [ ] Telegram message received
- [ ] Check `/corpus_reports/` for report file
  ```bash
  ls -lah /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_reports/
  ```
- [ ] Report file created with timestamp

## Post-Deployment Verification

### Weekly Report Archive
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_reports/
ls -lth
```
Expected: JSON files with pattern `corpus_report_YYYY-MM-DD_HH-mm.json`

- [ ] Reports being created
- [ ] Filenames have correct format
- [ ] JSON content valid (spot check)

### Telegram Integration
- [ ] Message appears every Sunday at 18:00
- [ ] Report data is up-to-date
- [ ] No error messages in Telegram

### n8n Monitoring
```bash
# Check n8n service status
systemctl status n8n

# View n8n logs
journalctl -u n8n -f
```
- [ ] n8n service running
- [ ] No workflow execution errors
- [ ] Execution history shows weekly runs

## Troubleshooting Checklist

If any step fails, verify:

### Workflow Import Issues
- [ ] n8n service is running: `systemctl status n8n`
- [ ] JSON file is valid: `python3 -m json.tool weekly_corpus_report.json`
- [ ] Disk space available: `df -h`

### Telegram Issues
- [ ] Bot token is valid:
  ```bash
  curl https://api.telegram.org/bot<TOKEN>/getMe
  ```
- [ ] Chat ID is correct (negative for groups)
- [ ] Bot is added to chat/group
- [ ] Environment variables set in n8n

### Statistics Issues
- [ ] ChromaDB accessible: `ls -lah /chromadb_data/`
- [ ] chroma.sqlite3 exists and readable
- [ ] PDF cache directory exists: `ls /pdf_cache/`
- [ ] Python 3 installed: `python3 --version`
- [ ] chromadb package available: `python3 -c "import chromadb"`

### Schedule Issues
- [ ] Cron rule correctly configured in workflow node
- [ ] n8n timezone is correct (UTC)
- [ ] Server time is accurate: `date`
- [ ] n8n auto-execute is enabled

## Rollback Procedure

If issues occur, rollback is simple:

1. **Disable Workflow in n8n**
   - Open workflow
   - Toggle "Active" to OFF
   - Save

2. **Revert Manual Testing**
   ```bash
   rm -rf /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_reports/
   ```

3. **Remove Credentials** (if needed)
   ```bash
   rm /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/.env
   ```

4. **Re-run Setup**
   ```bash
   ./setup_telegram_workflow.sh
   ```

## Sign-Off

- [ ] All files created and validated
- [ ] Test script executed successfully
- [ ] Workflow imported to n8n
- [ ] Environment variables configured
- [ ] Initial test execution completed
- [ ] Telegram message received
- [ ] Ready for weekly automated execution

**Deployment Date**: _______________
**Deployed By**: _______________
**Notes**: _______________

---

**Status**: Ready for Production ✓
**Next Review**: (Next Sunday after first execution)
