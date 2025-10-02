#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root even when invoked from a subdirectory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_ROOT="${REPO_ROOT}/docker-data"

mkdir -p "${DATA_ROOT}/config" \
         "${DATA_ROOT}/cache" \
         "${DATA_ROOT}/workspace/input" \
         "${DATA_ROOT}/workspace/output"

export COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-pdfmathtranslate}

docker compose -f "${REPO_ROOT}/docker-compose.yml" up --build -d "$@"

echo "PDFMathTranslate WebUI is starting..."
echo "Once healthy, visit: http://localhost:${PDF2ZH_WEBUI_PORT:-7860}/"
