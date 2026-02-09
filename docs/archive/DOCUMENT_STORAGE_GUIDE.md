# Document Storage & Backup Guide

## 📁 Current State

### ChromaDB (Embeddings Only)
- **Location**: `chromadb_data/`
- **Collections**: 4
- **Documents**: 538,039 embedded
- **Status**: ✅ Working
- **Size**: ~15GB

### Raw Documents (MISSING)
- **Location**: Not on server
- **Status**: ❌ Deleted after embedding (standard RAG setup)
- **Backup**: ✅ On USB sticks

---

## 🔐 IMPORTANT: Backup Your USB Sticks!

### Why You Need Raw Documents
1. **Re-embedding**: If embedding model changes, you need raw files
2. **Bug recovery**: If ChromaDB corrupts, you can re-index
3. **New collections**: Different embedding strategies need raw files
4. **Auditing**: View original source documents

---

## 📋 What To Do When You Have USB Sticks

### Step 1: Mount USB Sticks
```bash
# Plug in USB stick, check mount point
df -h | grep -E "usb|media"

# Should see something like:
# /dev/sdb1  64G  40G  24G  62% /mnt/usb
```

### Step 2: Copy to Server
```bash
# Create backup directory
mkdir -p data/documents_raw/usb_backup

# Copy from USB
cp -r /mnt/usb/* data/documents_raw/usb_backup/

# Verify copy
du -sh data/documents_raw/usb_backup/
```

### Step 3: Organize by Source
```bash
# Typical structure for Swedish government documents:
data/documents_raw/
├── riksdagen/
│   ├── betankanden/
│   ├── protokoll/
│   └── skrivelser/
├── myndigheter/
│   ├── boverket/
│   ├── energimyndigheten/
│   ├── folkhalsomyndigheten/
│   └── ...
├── sfs/
│   ├── sfs-2024/
│   └── sfs-2023/
└── backup/
    ├── usb_backup/
    └── cloud_backup/
```

### Step 4: Test Re-Embedding (Optional)
```bash
# Test that you can re-embed if needed
cd scrapers
./boverket_scraper.py --test-embed \
  --input ../data/documents_raw/boverket/
```

---

## 🔄 Maintenance Checklist

### Weekly
- [ ] Sync USB changes to `data/documents_raw/backup/`
- [ ] Run ChromaDB backup: `cp chromadb_data/chroma.sqlite3 backups/`
- [ ] Check ChromaDB health: `curl http://localhost:8900/api/constitutional/health`

### Monthly
- [ ] Test re-embedding sample documents
- [ ] Verify backup integrity
- [ ] Update documentation

### Quarterly
- [ ] Review embedding model performance
- [ ] Consider model upgrades (test on sample data)
- [ ] Archive old embeddings

---

## 📊 Storage Requirements

### Raw Documents (USB Sticks)
- **Estimate**: 2 million documents
- **Size**: ~50-100GB (depending on PDF/images)
- **Location**: Should be on server + USB backup

### Embeddings (ChromaDB)
- **Current**: 538,039 documents
- **Size**: ~15GB
- **Growth**: ~30MB per 1000 docs

### Backup Strategy
```
USB Sticks (Primary)
    ↓ Copy monthly
Server: data/documents_raw/ (Secondary)
    ↓ Backup weekly
Server: backups/documents_raw.tar.gz (Tertiary)
    ↓ Offsite
Cloud Storage (Quaternary)
```

---

## ⚠️ Warnings

### DON'T Delete Raw Files After Embedding
- Keep them on server!
- You'll need them for re-embedding
- Backup to multiple locations

### DON'T Rely on USB Sticks Alone
- USB sticks fail
- Create server backup
- Cloud backup if possible

### DON'T Use USB for Daily Work
- Copy to server first
- Work from server copy
- Keep USB as backup

---

## 🔧 Scripts to Help

### Backup Script (Create Later)
```bash
# scripts/backup_raw_docs.sh
# Copies raw docs to backup location
# Runs via cron job weekly
```

### Sync Script (Create Later)
```bash
# scripts/sync_usb_to_server.sh
# Syncs USB stick to server
# Checks for new/changed files
```

### Verify Script (Create Later)
```bash
# scripts/verify_embeddings.sh
# Samples documents and checks embeddings exist
# Reports missing or corrupted embeddings
```

---

## 📞 If Something Goes Wrong

### ChromaDB Corrupted
1. Stop backend: `systemctl --user stop constitutional-ai-backend`
2. Restore backup: `cp backups/chroma.sqlite3 chromadb_data/`
3. Restart backend: `systemctl --user start constitutional-ai-backend`

### Need to Re-Embed
1. Use raw documents in `data/documents_raw/`
2. Run scrapers with `--reembed` flag
3. Monitor progress in logs

### USB Stick Failure
1. Check server backup: `ls data/documents_raw/usb_backup/`
2. Check cloud backup (if exists)
3. Re-index from server backup if needed

---

## ✅ Action Items

### ASAP (This Week)
- [ ] Copy USB sticks to `data/documents_raw/`
- [ ] Create backup structure
- [ ] Verify copy integrity
- [ ] Create cron job for weekly backups

### Soon (This Month)
- [ ] Create backup scripts
- [ ] Set up cloud backup (optional)
- [ ] Test re-embedding process

### Later (Next Quarter)
- [ ] Review storage costs
- [ ] Optimize backup strategy
- [ ] Document lessons learned

---

**Created**: 2026-01-04
**Purpose**: Guide for backing up 2M documents from USB sticks
**Next Steps**: Copy USB to server when ready
