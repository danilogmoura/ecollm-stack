#!/bin/bash

# Start Ollama in the background
/bin/ollama serve &

# Save the PID of the Ollama process
pid=$!

# Wait for the Ollama server to respond on port 11434 using native bash TCP connection
echo "Waiting for Ollama to start..."
while !</dev/tcp/localhost/11434; do
    sleep 2
done

echo "Ollama started successfully! Pulling models..."

# Pull the fallback chat model (skips if already present).
# Fallback role only: rag-chat -> Gemini primary, this loads on demand if Gemini fails.
# Tag note: the bare "qwen3:4b-instruct-2507" does NOT exist in the registry —
# the -q4_K_M quantization suffix is mandatory.
ollama pull qwen3:4b-instruct-2507-q4_K_M

# NO WARMUP by design (decided 2026-09-25): the model is a rarely-hit emergency
# fallback, so keeping ~2.5 GB of VRAM pinned at boot is pure waste. Ollama loads
# it on demand (~2-3 s cold) the first time the fallback actually fires, then
# evicts it after OLLAMA_KEEP_ALIVE (15m) of idleness.

echo "Initialization complete. Model loads on demand (keep_alive from env). Keeping container running..."

# Keep the container running attached to the main process
wait $pid
