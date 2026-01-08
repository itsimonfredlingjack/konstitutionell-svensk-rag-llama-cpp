#!/bin/bash
echo "🛑 STOPPING RAG SYSTEM..."

# Hitta och döda processer på portarna
fuser -k 8900/tcp > /dev/null 2>&1 && echo "✅ Backend stopped."
fuser -k 8080/tcp > /dev/null 2>&1 && echo "✅ LLM Engine stopped."
fuser -k 3001/tcp > /dev/null 2>&1 && echo "✅ Frontend stopped."

# Extra säkerhetsåtgärd: döda baserat på namn om portarna hänger
pkill -f "llama-server" > /dev/null 2>&1
pkill -f "uvicorn app.main" > /dev/null 2>&1
pkill -f "vite" > /dev/null 2>&1

echo "System shutdown complete."
