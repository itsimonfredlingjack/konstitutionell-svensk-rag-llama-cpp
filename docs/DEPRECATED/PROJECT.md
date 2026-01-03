# Simons AI - Projektöversikt

## KOMPONENTER

| Komponent | Route/Port | Beskrivning |
|-----------|------------|-------------|
| Huvudchatt | :5173/ | 3D-interface med WebGL-kristall |
| Kiosk Dashboard | :5173/kiosk | Touch-dashboard för Google Nest Hub |
| Backend API | :8000 | FastAPI + Ollama orchestrator |
| Stable backup | :3000 | Fungerande fallback-version |

## PORTAR (192.168.86.32)

| Port | Tjänst | Systemd |
|------|--------|---------|
| 5173 | Frontend (Vite dev) | simons-ai-frontend |
| 8000 | Backend (FastAPI) | simons-ai-backend |
| 3000 | Stable backup | manuell start |
| 11434 | Ollama | ollama |

## ROUTES

- `/` - Huvudchatt (3D WebGL, kräver Three.js)
- `/kiosk` - Nest Hub Dashboard (CSS-only, ej Three.js)
- `/api/*` - Backend endpoints

## FÖR AI-ASSISTENTER

Se `CLAUDE.md` för detaljerade instruktioner.

Kritiskt:
- `/` och `/kiosk` är OLIKA appar i samma frontend
- Three.js behövs ENDAST för `/`, inte för `/kiosk`
- Port 3000 = STABLE, rör ej utan tillåtelse
- IP 192.168.86.32 är RESERVERAD i routern

## FILER

### Frontend (`frontend/src/`)
| Fil | Beskrivning |
|-----|-------------|
| `App.tsx` | Router - dirigerar till / eller /kiosk |
| `Frontend_Huvudsida.tsx` | Huvudchatt-interface |
| `Frontend_3D_Bakgrund.tsx` | 3D WebGL-kristall |
| `KioskDashboard.tsx` | Nest Hub dashboard |
| `hooks/useBackend.ts` | WebSocket-koppling |

### Backend (`app/`)
| Fil | Beskrivning |
|-----|-------------|
| `main.py` | FastAPI startpunkt |
| `api/routes.py` | REST endpoints |
| `api/Backend_Chat_Stream.py` | WebSocket chat |
| `models/Backend_Agent_Prompts.py` | Agent-profiler |
| `services/ollama_client.py` | Ollama integration |

## KOMMANDON

```bash
./simons-ai status    # Se vad som körs
./simons-ai restart   # Starta om backend
./simons-ai rebuild   # Bygg om frontend
./simons-ai logs      # Visa loggar
```

## EFTER ÄNDRING

- **Backend (app/)** → `./simons-ai restart`
- **Frontend (frontend/src/)** → `./simons-ai rebuild`

---
*Senast uppdaterad: 2025-11-29*
