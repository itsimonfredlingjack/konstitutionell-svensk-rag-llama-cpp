# Nerve Center

Real-time system monitoring dashboard for AI server infrastructure. Provides comprehensive monitoring of GPU metrics, service health, Ollama models, and the Constitutional AI agent loop pipeline.

## Architecture

- **Backend**: FastAPI (Python) - REST API and WebSocket server
- **Frontend**: React + TypeScript + Vite - Modern SPA dashboard
- **Real-time Updates**: WebSocket connections for live metrics

## Features

- **GPU Monitoring**: NVIDIA GPU stats (temperature, utilization, memory, power, processes)
- **Service Health**: Monitor systemd services, Docker containers, and port-based services
- **Ollama Integration**: Track available models, running models, and VRAM usage
- **Agent Loop Pipeline**: Monitor Constitutional AI pipeline stages (chat, assist, evidence, guardian)
- **Vector Database**: Qdrant health monitoring
- **Real-time Updates**: Live metrics via WebSocket or polling

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- NVIDIA GPU with nvidia-smi (for GPU monitoring)
- Ollama installed (optional, for model monitoring)
- Qdrant running (optional, for vector DB monitoring)

### Backend Setup

1. Install Python dependencies:

```bash
cd api
pip install -r requirements.txt
```

2. (Optional) Create `.env` file for configuration:

```env
OLLAMA_URL=http://localhost:11434
QDRANT_URL=http://localhost:6333
CONSTITUTIONAL_API_URL=http://localhost:8000
API_PORT=3003
```

3. Run the API server:

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 3003
```

The API will be available at `http://localhost:3003`

### Frontend Setup

1. Install Node.js dependencies:

```bash
npm install
```

2. Start development server:

```bash
npm run dev
```

The frontend dev server runs on `http://localhost:5174` with proxy to the API.

3. Build for production:

```bash
npm run build
```

Built files will be in the `dist/` directory, which the FastAPI server can serve.

## Configuration

### Environment Variables

- `OLLAMA_URL`: Ollama API endpoint (default: `http://localhost:11434`)
- `QDRANT_URL`: Qdrant vector database endpoint (default: `http://localhost:6333`)
- `CONSTITUTIONAL_API_URL`: Constitutional AI API endpoint (default: `http://localhost:8000`)
- `API_PORT`: Port for the Nerve Center API server (default: `3003`)

### Monitored Services

The following services are monitored by default (configurable in code):

- Ollama (systemd, port 11434)
- Nginx (systemd, port 80)
- Docker (systemd)
- Qdrant (Docker container, port 6333)
- PostgreSQL (Docker container, port 5434)
- Various services on ports: 8000, 5173, 5174, 8081, 3003

## API Endpoints

### REST Endpoints

- `GET /api/metrics` - Get complete system metrics
- `GET /api/gpu` - Get GPU stats only
- `GET /api/services` - Get all service statuses
- `GET /api/ollama` - Get Ollama models and status
- `GET /api/agent-loop` - Get Constitutional AI pipeline status
- `POST /api/ollama/load/{model_name}` - Load an Ollama model
- `POST /api/ollama/unload` - Unload current Ollama model

### WebSocket

- `WS /ws/metrics` - Real-time metrics stream (updates every 2 seconds)

## Running in Production

1. Build the frontend:

```bash
npm run build
```

2. Run the API server (the built frontend will be served automatically):

```bash
cd api
uvicorn main:app --host 0.0.0.0 --port 3003
```

The API server will automatically serve the built frontend from the `dist/` directory.

## Development

### Project Structure

```
nerve-center/
├── api/
│   ├── main.py           # FastAPI backend
│   └── requirements.txt  # Python dependencies
├── src/
│   ├── components/       # React components
│   ├── hooks/           # React hooks
│   ├── pages/           # Page components
│   └── types/           # TypeScript types
├── dist/                # Built frontend (generated)
└── package.json         # Node.js dependencies
```

### Routes

- `/` - Main dashboard (GPU, services, Ollama)
- `#nest` or `#/nest` - Nest Dashboard (Agent Loop pipeline visualization)

## License

Private project - All rights reserved
