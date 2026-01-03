# INSTRUKTIONER FÖR AI-ASSISTENTER

## INNAN DU GÖR ÄNDRINGAR

1. Läs denna fil
2. Fråga vilken komponent användaren vill ändra:
   - **Huvudchatt** (`/`) - 3D WebGL interface
   - **Kiosk Dashboard** (`/kiosk`) - Nest Hub touch-dashboard
   - **Backend API** - FastAPI + Ollama
   - **Mobilapp** - `03_NEON-UNICORN-AI` (ANNAT PROJEKT!)

## PORTAR - RÖR EJ UTAN TILLÅTELSE

| Port | Tjänst | Status |
|------|--------|--------|
| 5173 | Frontend dev | Kan ändras |
| 8000 | Backend | Kan ändras |
| 3000 | STABLE BACKUP | ALDRIG ÄNDRA |
| 11434 | Ollama | System-tjänst |

## BEROENDEN PER ROUTE

| Route | Three.js | Framer Motion | TailwindCSS |
|-------|----------|---------------|-------------|
| `/` (Huvudchatt) | JA | JA | JA |
| `/kiosk` (Dashboard) | NEJ | JA | JA |

## VANLIGA MISSTAG - UNDVIK DESSA

| Misstag | Konsekvens |
|---------|------------|
| Ta bort Three.js | Kraschar huvudchatten (`/`) |
| Ändra IP utan uppdatering | Bryter CORS och WebSocket |
| Köra på port 3000 | Skriver över stable backup |
| Blanda mobilapp med webb | Fel projekt! |

## PROJEKTSTRUKTUR

```
01_PROJECTS/
├── 01_AI-VIBE-WORLD/          ← DETTA PROJEKT
│   ├── app/                   ← Backend (FastAPI)
│   ├── frontend/              ← Frontend (React)
│   │   └── src/
│   │       ├── App.tsx        ← Router
│   │       ├── Frontend_*.tsx ← Huvudchatt-komponenter
│   │       └── KioskDashboard.tsx ← Nest Hub
│   ├── PROJECT.md             ← Teknisk översikt
│   └── CLAUDE.md              ← Denna fil
│
├── 01_AI-VIBE-WORLD-STABLE/   ← BACKUP - RÖR EJ
├── 03_NEON-UNICORN-AI/        ← MOBILAPP - ANNAT PROJEKT
└── 04_NERDY-AI-DASHBOARD/     ← ANNAT PROJEKT
```

## EFTER KODÄNDRINGAR

```bash
# Backend-ändringar
./simons-ai restart

# Frontend-ändringar
./simons-ai rebuild

# Se loggar
./simons-ai logs

# Verifiera status
./simons-ai status
```

## IP-ADRESS

**192.168.86.32** är RESERVERAD i routern.

Filer som använder denna IP:
- `app/config.py` (CORS)
- `frontend/src/KioskDashboard.tsx` (API URLs)

## CHECKLIST INNAN PUSH

- [ ] Har jag testat båda routes (`/` och `/kiosk`)?
- [ ] Är Three.js fortfarande installerat?
- [ ] Fungerar WebSocket-anslutningen?
- [ ] Har jag kört `./simons-ai rebuild`?

---
*Skapad: 2025-11-29 för att förhindra förvirring mellan komponenter*
