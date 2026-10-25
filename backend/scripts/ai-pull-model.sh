#!/usr/bin/env sh
# Download the assistant model once (needs internet); afterwards the stand runs offline.
#   backend/scripts/ai-pull-model.sh                 # model from ASSISTANT_LLM_MODEL or the default
#   backend/scripts/ai-pull-model.sh qwen2.5:1.5b    # the light model for 8 GB machines
#   OLLAMA_OUTSIDE_DOCKER=1 backend/scripts/ai-pull-model.sh   # Ollama installed on the host
set -eu
MODEL="${1:-${ASSISTANT_LLM_MODEL:-qwen3:4b-instruct-2507-q4_K_M}}"
if [ "${OLLAMA_OUTSIDE_DOCKER:-0}" = "1" ]; then
  ollama pull "$MODEL"
  ollama list
else
  docker compose --profile ai up -d ollama
  docker compose --profile ai exec ollama ollama pull "$MODEL"
  docker compose --profile ai exec ollama ollama list
fi
echo "Model $MODEL is ready: ASSISTANT_LLM_MODEL=$MODEL docker compose --profile ai up -d"
