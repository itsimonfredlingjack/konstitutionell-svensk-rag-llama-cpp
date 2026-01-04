# Constitutional AI Dashboard

Full-stack dashboard for managing and analyzing Swedish government documents in ChromaDB.

## Project Status

**Backend**: ✅ Complete and Running
**Frontend**: ✅ React + TypeScript + Vite

### Service Status

| Tjänst                    | Status     | Port | Autostart   |
|---------------------------|------------|------|-------------|
| Constitutional AI Backend | 🟢 Active  | 8000 | ✅ Enabled  |
| Simons AI Backend         | 🔴 Removed | -    | ❌ Disabled |

**Bekräftade Ändringar:**
1. ✅ simons-ai-backend.service borttagen från systemd
2. ✅ Port 8000 ägs av constitutional-ai-backend
3. ✅ Health endpoint svarar korrekt
4. ✅ RAG queries fungerar (ministral-3:14b, ~23s)

---

## Backend API

**Location**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py`

**Service**: `constitutional-ai-backend` (systemd)
**Port**: `8000`
**Base URL**: `http://localhost:8000/api/constitutional`

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | ChromaDB connection status |
| `/stats/overview` | GET | Overview statistics |
| `/stats/documents-by-type` | GET | Document counts by type |
| `/stats/timeline` | GET | Document additions (30 days) |
| `/collections` | GET | List all collections |
| `/search` | POST | Search documents |
| `/admin/status` | GET | Admin status overview |
| `/ws/harvest` | WebSocket | Live harvest progress |

### Current Data

**Total Documents**: 535,024
- `swedish_gov_docs`: 304,871 documents
- `riksdag_documents_p1`: 230,143 documents
- `riksdag_documents`: 10 documents

**Storage**: 16.09 GB (ChromaDB) + 20.07 GB (PDF cache)

### Testing

```bash
# Quick health check
curl http://localhost:8000/api/constitutional/health | jq .

# Run full test suite
./test-api.sh

# View API documentation
open http://localhost:8000/docs#/constitutional
```

---

## Frontend Dashboard

**Tech Stack**:
- React + TypeScript
- Recharts for data visualization
- Tailwind CSS for styling
- WebSocket for live updates
- Vite for build tooling

**Development**:
```bash
# Install dependencies (if needed)
npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

**Integration**:
```typescript
const API_BASE = 'http://localhost:8000/api/constitutional';

// Fetch stats
const stats = await fetch(`${API_BASE}/stats/overview`).then(r => r.json());
console.log(`Total documents: ${stats.total_documents}`);
```

---

## File Structure

```
constitutional-dashboard/
├── README.md                    # This file
├── CONSTITUTIONAL_API.md        # Full API documentation
├── test-api.sh                  # API test script
├── src/                         # Frontend source
│   ├── App.tsx
│   ├── components/
│   │   ├── OverviewStats.tsx
│   │   ├── SearchInterface.tsx
│   │   ├── DocumentTypeChart.tsx
│   │   └── TimelineChart.tsx
│   └── api/
│       └── constitutional.ts
├── package.json                 # Frontend dependencies
└── vite.config.ts              # Vite configuration
```

---

## Development Workflow

### Backend Changes

1. Edit routes: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py`
2. Restart service: `systemctl --user restart constitutional-ai-backend`
3. Test changes: `./test-api.sh`

### Frontend Changes

The dashboard runs on Vite with HMR (Hot Module Replacement):
1. Edit files in `src/`
2. Save changes
3. Browser auto-reloads

**Port**: Development server runs on `5173` (or next available)

---

## Data Sources

### ChromaDB Collections

**riksdag_documents_p1** (Phase 1):
- 230,143 documents
- Riksdagen API harvest
- Metadata: title, doc_type, source, date, classification, sfs_refs

**swedish_gov_docs** (Phase 2):
- 304,871 documents
- Multi-agency harvest
- Metadata: title, doc_type, source, date

### Document Types

- `prop` - Propositioner (Government bills)
- `mot` - Motioner (Parliamentary motions)
- `sou` - Statens offentliga utredningar (Government investigations)
- `bet` - Betänkanden (Committee reports)
- `ds` - Departementsskrivelser (Ministry documents)

---

## Performance

| Endpoint | Response Time |
|----------|---------------|
| Health check | < 100ms |
| Overview stats | < 200ms |
| Collections | < 500ms |
| Search | 1-3s |
| Documents by type | 10-30s (full scan) |
| Timeline | 10-30s (full scan) |

**Note**: Document-by-type and timeline endpoints scan all metadata. Consider caching for production.

---

## Next Steps

### Backend
- [ ] Implement actual embeddings-based search
- [ ] Add caching for expensive operations
- [ ] Integrate WebSocket with harvest process
- [ ] Add document detail endpoint
- [ ] Add bulk export functionality

### Frontend
- [ ] Enhance overview statistics page
- [ ] Improve search interface UX
- [ ] Add real-time data visualization
- [ ] Implement WebSocket live updates
- [ ] Add responsive design for mobile

### Infrastructure
- [ ] Set up production build pipeline
- [ ] Configure nginx routing (if needed)
- [ ] Add error tracking
- [ ] Implement comprehensive logging
- [ ] Set up monitoring and alerts

---

## Related Files

**API Implementation**:
- `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py`
- `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/main.py`

**ChromaDB Data**:
- `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data/`
- `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/pdf_cache/`

**Documentation**:
- `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/CLAUDE.md`
- `/home/ai-server/.claude/skills/swedish-gov-scraper/HARVEST_STATE.md`

---

## API Documentation

Full API documentation with examples: [CONSTITUTIONAL_API.md](./CONSTITUTIONAL_API.md)

Interactive API docs: http://localhost:8000/docs#/constitutional

---

## Support

**ChromaDB**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data`
**Backend Service**: `systemctl --user status constitutional-ai-backend`
**Logs**: `journalctl --user -u constitutional-ai-backend -f`

### System Commands

```bash
# Status
systemctl --user status constitutional-ai-backend

# Restart
systemctl --user restart constitutional-ai-backend

# Live logs
journalctl --user -u constitutional-ai-backend -f

# Stop vid behov
systemctl --user stop constitutional-ai-backend
```

**API Base URL:** `http://localhost:8000/api/constitutional`

All Constitutional AI-logik är nu fristående i `09_CONSTITUTIONAL-AI/backend/` med egen systemd service! 🚀

For issues with ChromaDB connection, verify:
1. ChromaDB path exists and is readable
2. Backend service has proper permissions
3. No conflicting processes on port 8000
