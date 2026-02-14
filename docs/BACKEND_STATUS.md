# Constitutional AI Backend - Service Status

## Statusöversikt

| Tjänst                    | Status     | Port | Autostart   |
|---------------------------|------------|------|-------------|
| Constitutional AI Backend | 🟢 Active  | 8900 | ✅ Enabled  |
| Simons AI Backend         | 🔴 Removed | -    | ❌ Disabled |

## Bekräftade Ändringar

1. ✅ simons-ai-backend.service borttagen från systemd
2. ✅ Port 8900 ägs av constitutional-ai-backend
3. ✅ Health endpoint svarar korrekt
4. ✅ RAG queries fungerar (Ministral-3-14B-Instruct-2512 via llama-server, CRAG enabled)

## System Commands

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

## API Base URL

```
http://localhost:8900/api/constitutional
```

## Endpoints

| Endpoint                           | Method |
|------------------------------------|--------|
| /api/constitutional/health         | GET    |
| /api/constitutional/stats/overview | GET    |
| /api/constitutional/collections    | GET    |
| /api/constitutional/agent/query    | POST   |
| /api/constitutional/agent/query/stream | POST   |

## Backend Location

All Constitutional AI-logik är nu fristående i `09_CONSTITUTIONAL-AI/backend/` med egen systemd service! 🚀

**Backend Path:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/`

**Main Application:** `backend/app/main.py`

**API Routes:** `backend/app/api/constitutional_routes.py`

**Services:** `backend/app/services/`

## Migration Notes

- Backend flyttad från `02_SIMONS-AI-BACKEND` till `09_CONSTITUTIONAL-AI/backend/`
- Alla Constitutional AI-specifika services och routes är nu i eget projekt
- Gamla `simons-ai-backend` service är disabled och borttagen
- Port 8900 används nu av `constitutional-ai-backend`
