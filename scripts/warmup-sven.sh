#!/bin/bash
# Warmup script - Preloads GPT-OSS into GPU VRAM
# Keeps model warm for 24 hours

echo "[$(date)] Starting GPT-OSS warmup..."

# Wait for Ollama to be ready
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "[$(date)] Ollama is ready"
        break
    fi
    echo "[$(date)] Waiting for Ollama... ($i/30)"
    sleep 2
done

# Preload GPT-OSS (Arkitekten) with 24h keep_alive
curl -s -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{
        "model": "gpt-oss",
        "prompt": "Hej!",
        "keep_alive": "24h",
        "options": {
            "num_ctx": 8192
        }
    }' > /dev/null

if [ $? -eq 0 ]; then
    echo "[$(date)] GPT-OSS preloaded successfully - model will stay warm for 24 hours"
else
    echo "[$(date)] Failed to preload GPT-OSS"
    exit 1
fi
