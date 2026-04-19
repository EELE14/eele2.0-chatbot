#!/bin/sh
set -e

: "${DISCORD_TOKEN:?Missing required variable: DISCORD_TOKEN}"
: "${ALLOWED_GUILD_ID:?Missing required variable: ALLOWED_GUILD_ID}"

LLM_BACKEND="${LLM_BACKEND:-ollama}"

if [ "$LLM_BACKEND" = "lmstudio" ]; then
    : "${LMSTUDIO_HOST:?LLM_BACKEND=lmstudio requires LMSTUDIO_HOST}"
    : "${LMSTUDIO_MODEL:?LLM_BACKEND=lmstudio requires LMSTUDIO_MODEL}"
elif [ "$LLM_BACKEND" = "ollama" ]; then
    : "${OLLAMA_URL:?LLM_BACKEND=ollama requires OLLAMA_URL}"
    : "${OLLAMA_MODEL:?LLM_BACKEND=ollama requires OLLAMA_MODEL}"
fi

exec python3 main.py
