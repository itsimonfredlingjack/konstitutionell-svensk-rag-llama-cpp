# Simons AI Server

**QWENY BENY** - The Robot Unicorn
Hybrid AI Orchestrator med Qwen 2.5 Coder 14B

## Quick Reference

```bash
# Alla kommandon körs från /home/ai-server/local-llm-backend

./simons-ai status    # Visa status
./simons-ai start     # Starta tjänster
./simons-ai stop      # Stoppa tjänster
./simons-ai restart   # Starta om tjänster
./simons-ai logs      # Visa backend-loggar (Ctrl+C för att avsluta)
./simons-ai rebuild   # Bygg om frontend efter ändringar
```

## URLs

| Service | URL |
|---------|-----|
| Frontend | http://192.168.86.32:5173 |
| Backend API | http://192.168.86.32:8000 |
| API Docs | http://192.168.86.32:8000/docs |

## Arkitektur

```
┌─────────────────┐      ┌─────────────────┐
│  Robot Unicorn  │─────▶│  Backend API    │
│  Frontend :5173 │ WS   │  :8000          │
└─────────────────┘      └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │   Hybrid Orchestrator     │
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
        ┌──────────┐       ┌──────────┐       ┌──────────┐
        │  AUTO    │       │  FAST    │       │  DEEP    │
        │ Routing  │       │ Gemini*  │       │  Qwen    │
        └──────────┘       └──────────┘       └──────────┘
                                                   │
                                            ┌──────┴──────┐
                                            │   Ollama    │
                                            │ RTX 4070    │
                                            └─────────────┘

* Gemini API kommer senare
```

## Modes

- **AUTO**: Intelligent routing baserat på query
- **FAST**: Gemini API (cloud) - ej konfigurerad än
- **DEEP**: Qwen 2.5 Coder 14B (lokal GPU)

## Tjänster

Båda körs som systemd services och startar automatiskt vid boot:

```bash
# Manuell kontroll (om nödvändigt)
sudo systemctl status simons-ai-backend
sudo systemctl status simons-ai-frontend
sudo systemctl status ollama

# Visa loggar
sudo journalctl -u simons-ai-backend -f
sudo journalctl -u simons-ai-frontend -f
```

## Filer

```
/home/ai-server/local-llm-backend/
├── simons-ai              # Management script
├── app/                   # Backend kod
│   ├── api/websocket.py   # WebSocket handler
│   ├── services/
│   │   ├── orchestrator.py
│   │   ├── ollama_client.py
│   │   └── intelligence.py
│   └── models/profiles.py # QWENY BENY prompt
├── systemd/               # Service-filer
└── .venv/                 # Python venv

/home/ai-server/.gemini/antigravity/scratch/robot_unicorn_agent/frontend/
├── dist/                  # Byggd frontend
├── src/                   # React kod
└── package.json
```

## Felsökning

**Services startar inte:**
```bash
./simons-ai status
sudo journalctl -u simons-ai-backend --since "5 min ago"
```

**Frontend visar "OFFLINE":**
- Kontrollera att backend körs
- Verifiera WebSocket URL i browser console

**Ollama-fel:**
```bash
ollama list              # Visa modeller
ollama ps                # Visa körande modeller
sudo systemctl restart ollama
```

**Efter kodändringar:**
```bash
./simons-ai restart      # Backend
./simons-ai rebuild      # Frontend (bygger om + restart)
```

## GPU

RTX 4070 12GB VRAM hanterar Qwen 2.5 Coder 14B.

```bash
nvidia-smi               # Visa GPU-status
```
