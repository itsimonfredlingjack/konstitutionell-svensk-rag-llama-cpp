# 🚀 AUTO-CAST: Constitutional Dashboard → Google Nest Hub (Sovis)

## Snabbstart

### Starta Dashboard + Auto-Cast (Rekommenderat)

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/apps/constitutional-dashboard
./START_AUTO_CAST.sh
```

Detta startar:
1. ✅ Flask dashboard server (port 5000)
2. ✅ Auto-cast manager som automatiskt castar till Sovis
3. ✅ Keepalive-loop som återcastar om användaren byter app

### Endast Dashboard (utan casting)

```bash
./START_DASHBOARD.sh
```

## Konfiguration

### Miljövariabler

```bash
# Dashboard
export DASHBOARD_HOST="0.0.0.0"           # Bind address
export DASHBOARD_PORT="5000"               # Port
export DASHBOARD_PUBLIC_URL="http://192.168.86.32:5000"  # URL som castas

# Cast
export CAST_DISPLAY_NAME="Sovis"           # Nest Hub namn
export CAST_KEEPALIVE_SECONDS="30.0"       # Kontrollera cast-status var 30s
export CAST_RECAST_BACKOFF_SECONDS="5.0"  # Väntetid vid fel
export DASHBOARD_STARTUP_WAIT_SECONDS="20.0"  # Vänta på server-start

# Optional
export CATT_BIN="/path/to/catt"            # Om catt inte finns på PATH
export CAST_EXPECTED_APP_ID="84912283"     # Chromecast app ID för web browser
```

### Hitta din Nest Hub

```bash
catt scan
```

Exempel output:
```
192.168.86.28 - Sovis - Google Inc. Google Nest Hub
```

## Funktioner

### ✅ Auto-Cast Manager (`cast_manager.py`)

- **Automatisk casting**: Castar dashboarden när servern startar
- **Keepalive**: Kontrollerar var 30:e sekund om casten fortfarande är aktiv
- **Auto-recast**: Återcastar automatiskt om användaren byter app på Nest Hub
- **Healthcheck**: Väntar på att dashboard-servern är redo innan casting
- **Felhantering**: Automatisk retry vid fel med backoff

### 📊 Dashboard Endpoints

- `GET /` - Huvudsida (v2 layout, 1024x600)
- `GET /api/stats` - V2 stats (VRAM, TPS, Context, Status)
- `GET /api/status` - Legacy status endpoint
- `POST /api/action/restart` - Starta om systemet
- `POST /api/action/flush` - Rensa minne
- `POST /api/action/ping` - Väck modell

## Testa Casting

```bash
./test_cast.sh
```

Detta startar dashboarden, väntar på att den är redo, castar en gång, och stänger sedan ner.

## Felsökning

### Dashboard startar inte

```bash
# Kolla logs
cat /tmp/dashboard.log

# Verifiera Flask installation
source ../../venv/bin/activate
python3 -c "import flask; print(flask.__version__)"
```

### Casting fungerar inte

```bash
# Verifiera att catt finns
which catt

# Lista tillgängliga enheter
catt scan

# Testa manuell cast
catt -d Sovis cast_site http://192.168.86.32:5000

# Kolla cast_manager logs
cat /tmp/cast_manager.log
```

### Dashboard är inte synlig på nätverket

```bash
# Verifiera att servern lyssnar på rätt interface
netstat -tlnp | grep 5000

# Kolla firewall
sudo firewall-cmd --list-all

# Testa från annan maskin
curl http://192.168.86.32:5000/api/stats
```

## Stoppa AUTO-CAST

```bash
# Hitta processer
ps aux | grep -E "(app.py|cast_manager)"

# Stoppa manuellt
kill <DASHBOARD_PID> <CAST_PID>

# Eller använd Ctrl+C om du kör i foreground
```

## Arkitektur

```
┌─────────────────┐
│  Flask Server   │  Port 5000
│   (app.py)      │  ──────────┐
└─────────────────┘            │
                               │ HTTP
┌─────────────────┐            │
│ Cast Manager    │  ──────────┘
│ (cast_manager)  │
└─────────────────┘
        │
        │ catt cast_site
        ▼
┌─────────────────┐
│  Google Nest    │
│  Hub (Sovis)    │  1024x600
└─────────────────┘
```

## Uppdateringar v2.0

- ✅ Ny 3-kolumns layout (Vitals | Monitor | Actions)
- ✅ Night mode design (Stone-900 bakgrund)
- ✅ VRAM gauge med färgkodning
- ✅ Status Pulse Orb (ONLINE/SEARCHING/GENERATING/OFFLINE)
- ✅ Black Box log stream (3 rader)
- ✅ TPS performance metric
- ✅ Touch-friendly action buttons
- ✅ Polling var 1000ms med offline-detektering
- ✅ V2 API endpoints (`/api/stats`)
