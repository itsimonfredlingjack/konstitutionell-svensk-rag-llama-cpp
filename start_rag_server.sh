#!/bin/bash
# RAG Server Startup Script - 12GB VRAM Optimized
# Model: Ministral-3-14B-Instruct-2512-Q4_K_M.gguf (8.24GB) + Qwen2.5-0.5B-Instruct-Q8_0.gguf (grading)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Binary
LLAMA_BIN="./llama.cpp/build/bin/llama-server"

# MODELS
MODEL_PATH="models/Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"

echo "=============================================="
echo "🚀 STARTING RAG ENGINE (12GB VRAM OPTIMIZED)"
echo "=============================================="
echo ""
echo "Binary: $LLAMA_BIN"
echo "Main Model: $MODEL_PATH"
echo ""
echo "⚙️  Critical Flags:"
echo "  -ctk q8_0 -ctv q8_0           (8-bit KV Cache)"
echo "  -ngl 99                        (GPU Offload all layers)"
echo "  -c 8192                        (Context window 8K)"
echo "  --spec-type ngram-simple       (N-gram speculative decoding)"
echo "  --draft-max 64                 (Max draft tokens)"
echo "  -fa on                         (Flash Attention)"
echo ""

# Verify binary
if [ ! -f "$LLAMA_BIN" ]; then
    echo "❌ ERROR: Binary not found at $LLAMA_BIN"
    exit 1
fi
echo "✅ Binary verified"

# Verify model
if [ ! -f "$MODEL_PATH" ]; then
    echo "❌ ERROR: Main model not found at $MODEL_PATH"
    exit 1
fi
MAIN_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
echo "✅ Main model verified: $MAIN_SIZE"

# Clean up port 8080
echo ""
echo "🧹 Cleaning up port 8080..."
fuser -k 8080/tcp 2>/dev/null || true
sleep 2

echo ""
echo "🔥 STARTING SERVER..."
echo "=============================================="

# Build command
CMD="$LLAMA_BIN -m '$MODEL_PATH' -c 8192 -ngl 99 -ctk q8_0 -ctv q8_0 --spec-type ngram-simple --draft-max 64 --port 8080 --host 0.0.0.0 --ctx-size 8192 --parallel 2 -fa on"

# Execute
eval $CMD
