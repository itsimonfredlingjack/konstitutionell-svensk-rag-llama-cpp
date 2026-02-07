# 🔄 Överlämning: Väck liv i AI-modellerna

**Datum:** 2025-12-02
**Föregående session:** Polish features för Kiosk Dashboard (auto-rotate, ripple, ljud, lazy-load)

---

## 📊 Nuläge

### Backend (FastAPI) - FUNGERAR ✅
- **URL:** http://192.168.86.32:8900
- **Docs:** http://192.168.86.32:8900/docs
- **WebSocket:** ws://192.168.86.32:8900/api/chat

### Ollama-modeller installerade
```
sven-gpt:latest    13 GB   ← GPT-OSS 20B (custom Modelfile) - används i Ollama
gpt-oss:20b        13 GB   ← Basmodell
devstral:24b       14 GB   ← Mistral kodmodell
```

**OBS:** Profile-IDs i backend/frontend är `gpt-oss` och `devstral`, men Ollama-modellnamnet för GPT-OSS är `sven-gpt`.

### Frontend (Vite) - FUNGERAR ✅
- **URL:** http://192.168.86.32:5173
- **Kiosk:** http://192.168.86.32:5173/kiosk

---

## 🏗️ Arkitektur

```
Frontend (React)
    ↓ WebSocket
Backend_Chat_Stream.py  ← Huvud-WebSocket endpoint
    ↓
Backend_Fraga_Router.py ← Routar till rätt agent/modell
    ↓
Backend_Agent_Prompts.py ← System prompts per agent
    ↓
ollama_client.py ← Ollama API-anrop
```

### Nyckelfilar
| Fil | Ansvar |
|-----|--------|
| `app/api/Backend_Chat_Stream.py` | WebSocket, streaming, GPU telemetry |
| `app/services/Backend_Fraga_Router.py` | Agent routing logic |
| `app/models/Backend_Agent_Prompts.py` | Profile definitions & prompts |
| `app/services/ollama_client.py` | Ollama HTTP client |
| `app/services/gpu_monitor.py` | nvidia-smi parsing |

---

## 🤖 Agenter (Profiles)

### Nuvarande konfiguration
```python
# Från /api/profiles endpoint:
"gpt-oss"    → model: "sven-gpt"   (13GB)  # Arkitekten (GPT-OSS 20B)
"devstral"   → model: "devstral"   (14GB)  # Kodaren (Devstral 24B)
"qwen"       → model: "sven-gpt"   (Legacy)
```

### Kiosk Dashboard visar
- **GPT-OSS** (cyan) - id: `gpt-oss`
- **Devstral** (gold) - id: `devstral`

✅ **Status:** Frontend och backend använder nu samma profile-IDs (gpt-oss, devstral)

---

## 🔌 API Endpoints att testa

```bash
# Health check
curl http://192.168.86.32:8900/health

# GPU stats
curl http://192.168.86.32:8900/api/gpu/stats

# Lista profiler
curl http://192.168.86.32:8900/api/profiles

# Warmup en modell (ladda i VRAM)
curl -X POST http://192.168.86.32:8900/api/profiles/gpt-oss/warmup
curl -X POST http://192.168.86.32:8900/api/profiles/devstral/warmup

# Unload modeller (frigör VRAM)
curl -X POST http://192.168.86.32:8900/api/system/unload-models

# WebSocket test (behöver wscat eller liknande)
wscat -c ws://192.168.86.32:8900/api/chat
```

---

## 🎯 Uppgifter för nästa session

### 1. Synka Frontend ↔ Backend profiles
- Kolla `frontend/src/config/KioskConfig.ts`
- Matcha agent IDs med backend `/api/profiles`
- Uppdatera `KIOSK_AGENTS` om nödvändigt

### 2. Verifiera warmup-flödet
```
Kiosk "Tap to Load" → handleAgentSelect()
  → POST /api/profiles/{id}/warmup  (ex: gpt-oss eller devstral)
  → ollama_client.warmup_model()
  → Ollama laddar modell i VRAM (sven-gpt eller devstral)
```

### 3. Testa chat-streaming
```
Frontend skickar via WebSocket:
{
  "type": "chat_message",
  "content": "Hej!",
  "profile": "gpt-oss"
}

Backend svarar med streaming tokens:
{
  "type": "stream_token",
  "token": "Hej",
  "agent_id": "gpt-oss"
}
```

### 4. Koppla modeller i Kiosk
- Testa att trycka på agent i Kiosk
- Verifiera att modell faktiskt laddas (`ollama ps`)
- Kolla att `is_active` uppdateras i frontend

---

## 🛠️ Debug-kommandon

```bash
# Se vad som körs i Ollama
ollama ps

# Se alla modeller
ollama list

# Testa modeller direkt i Ollama
ollama run sven-gpt "Hej, vem är du?"  # GPT-OSS 20B
ollama run devstral "Write a Python function"  # Devstral 24B

# Backend logs
journalctl -u simons-ai -f

# Frontend dev server
cd frontend && npm run dev
```

---

## 📁 Projektstruktur

```
/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/
├── app/                    # FastAPI backend
│   ├── api/
│   │   └── Backend_Chat_Stream.py
│   ├── models/
│   │   └── Backend_Agent_Prompts.py
│   ├── services/
│   │   ├── Backend_Fraga_Router.py
│   │   ├── ollama_client.py
│   │   └── gpu_monitor.py
│   └── main.py
├── frontend/               # Vite React
│   ├── src/
│   │   ├── KioskDashboard.tsx      # ← Kiosk huvudfil
│   │   ├── config/KioskConfig.ts   # ← Agent definitions
│   │   └── components/
│   │       └── SystemControlCard.tsx
│   └── dist/               # Built files
└── docs/
    └── HANDOVER_AI_MODELS.md  # ← Denna fil
```

---

## 💡 Tips

1. **Kör alltid `ollama ps`** för att se vilka modeller som är laddade
2. **VRAM är 12GB** - bara en 13-14GB modell åt gången
3. **WebSocket reconnect** - Frontend har auto-reconnect efter 3s
4. **Kiosk auto-rotate** - Stängs av vid touch, återaktiveras efter 30s

Lycka till! 🚀
