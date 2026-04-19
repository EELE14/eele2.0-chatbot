#!/bin/sh
set -e

# Required — container will refuse to start if any of these are missing.
: "${DISCORD_TOKEN:?Missing required variable: DISCORD_TOKEN}"
: "${ALLOWED_GUILD_ID:?Missing required variable: ALLOWED_GUILD_ID}"
: "${LLM_BACKEND:?Missing required variable: LLM_BACKEND}"

# Backend-specific requirements
if [ "$LLM_BACKEND" = "lmstudio" ]; then
    : "${LMSTUDIO_HOST:?LLM_BACKEND=lmstudio requires LMSTUDIO_HOST}"
    : "${LMSTUDIO_MODEL:?LLM_BACKEND=lmstudio requires LMSTUDIO_MODEL}"
elif [ "$LLM_BACKEND" = "ollama" ]; then
    : "${OLLAMA_URL:?LLM_BACKEND=ollama requires OLLAMA_URL}"
    : "${OLLAMA_MODEL:?LLM_BACKEND=ollama requires OLLAMA_MODEL}"
fi

exec python3 main.py
