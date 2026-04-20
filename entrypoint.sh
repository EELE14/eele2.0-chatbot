#!/bin/sh
RESTART_DELAY=30


die() {
    echo ""
    echo "FATAL: $1"
    echo "Waiting ${RESTART_DELAY}s before restart so you can read this..."
    sleep $RESTART_DELAY
    exit 1
}

require() {
    eval _val=\$$1
    [ -n "$_val" ] || die "Missing required environment variable: $1"
}


require DISCORD_TOKEN
require ALLOWED_GUILD_ID

LLM_BACKEND="${LLM_BACKEND:-ollama}"

case "$LLM_BACKEND" in
    lmstudio)
        require LMSTUDIO_HOST
        require LMSTUDIO_MODEL
        ;;
    ollama)
        ;;
    groq)
        require GROQ_API_KEY
        require GROQ_MODEL
        ;;
    *)
        die "Unknown LLM_BACKEND='$LLM_BACKEND' — must be 'ollama', 'lmstudio', or 'groq'"
        ;;
esac


python3 src/main.py &
PY_PID=$!

trap "kill -TERM $PY_PID 2>/dev/null" TERM INT

wait $PY_PID
EXIT=$?

if [ $EXIT -ne 0 ]; then
    echo ""
    echo "Bot exited with code $EXIT. Waiting ${RESTART_DELAY}s before restart..."
    sleep $RESTART_DELAY
fi

exit $EXIT
