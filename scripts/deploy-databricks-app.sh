#!/usr/bin/env bash
# Package and deploy the FastAPI app to Databricks Apps.
#
# This script stages a slim runtime bundle under deploy/databricks-app/ and then
# runs `databricks bundle validate` + `databricks bundle deploy`.
#
# Required environment variables:
#   DATABRICKS_HOST           Workspace hostname or URL
#   POSTGRES_BRANCH           Lakebase branch path (projects/.../branches/...)
#   POSTGRES_DATABASE         Lakebase database path (.../databases/db-...)
#   SQL_WAREHOUSE_ID          Warehouse id (or full /sql/1.0/warehouses/... path)
#   FAISS_VOLUME_FULL_NAME    UC volume full name: catalog.schema.volume
#
# Optional environment variables:
#   APP_NAME                  Databricks App name (default: edim-dde-ai-agents-api)
#   APP_DESCRIPTION           App description for bundle resource
#   BUNDLE_TARGET             Bundle target (default: dev)
#   DATABRICKS_PROFILE        CLI profile passed to `databricks -p`
#   FAISS_INDEX_SUBPATH       Path within the volume (default: faiss_index)
#   USE_LOCAL_DATA            true|false (default: false)
#   LOCAL_DATA_PATH           CSV path when USE_LOCAL_DATA=true
#   USE_MOCK_LLM             true|false (default: true)
#   APP_ENV                   App env string (default: production)
#   LOG_LEVEL                 Log level (default: INFO)
#   SKIP_VALIDATE             1 to skip `databricks bundle validate`
#   SKIP_DEPLOY               1 to skip `databricks bundle deploy`
#
# Example:
#   DATABRICKS_HOST=adb-123.azuredatabricks.net \
#   POSTGRES_BRANCH=projects/p/branches/main \
#   POSTGRES_DATABASE=projects/p/branches/main/databases/db-123 \
#   SQL_WAREHOUSE_ID=a37a133da7c13757 \
#   FAISS_VOLUME_FULL_NAME=dim_engineering_dev.sabbineni_adhoc.faiss_volume \
#   ./scripts/deploy-databricks-app.sh

# Example: DATABRICKS_HOST=adb-1137828170459102.2.azuredatabricks.net POSTGRES_BRANCH=projects/<project>/branches/<branch> POSTGRES_DATABASE=projects/<project>/branches/<branch>/databases/<db-id> SQL_WAREHOUSE_ID=a37a133da7c13757 FAISS_VOLUME_FULL_NAME=dim_engineering_dev.sabbineni_adhoc.<volume_name> ./scripts/deploy-databricks-app.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGING_DIR="${ROOT}/deploy/databricks-app"

APP_NAME="${APP_NAME:-edim-dde-ai-agents-api}"
APP_DESCRIPTION="${APP_DESCRIPTION:-Cluster advisor FastAPI Databricks App}"
BUNDLE_TARGET="${BUNDLE_TARGET:-dev}"
FAISS_INDEX_SUBPATH="${FAISS_INDEX_SUBPATH:-faiss_index}"
USE_LOCAL_DATA="${USE_LOCAL_DATA:-false}"
LOCAL_DATA_PATH="${LOCAL_DATA_PATH:-data/sample_job_metrics.csv}"
USE_MOCK_LLM="${USE_MOCK_LLM:-true}"
APP_ENV="${APP_ENV:-production}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

usage() {
  sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

databricks_cmd() {
  if [[ -n "${MSYSTEM:-}" || "${OSTYPE:-}" == msys* ]]; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
      databricks ${DATABRICKS_PROFILE:+-p "$DATABRICKS_PROFILE"} "$@"
    return
  fi
  if [[ -n "${DATABRICKS_PROFILE:-}" ]]; then
    databricks -p "${DATABRICKS_PROFILE}" "$@"
  else
    databricks "$@"
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_env() {
  local key="$1"
  [[ -n "${!key:-}" ]] || die "Missing required environment variable: ${key}"
}

normalize_host() {
  local raw="${1:-}"
  raw="${raw#https://}"
  raw="${raw#http://}"
  raw="${raw%/}"
  printf '%s' "$raw"
}

normalize_http_path() {
  local raw="${1:-}"
  if [[ -z "$raw" ]]; then
    die "SQL_WAREHOUSE_ID must not be empty"
  fi
  if [[ "$raw" == /sql/* ]]; then
    printf '%s' "$raw"
  else
    printf '/sql/1.0/warehouses/%s' "$raw"
  fi
}

faiss_index_path_from_volume() {
  local volume_full_name="$1"
  local volume_path="/Volumes/${volume_full_name//./\/}"
  printf '%s/%s' "$volume_path" "$FAISS_INDEX_SUBPATH"
}

stage_runtime_bundle() {
  log "Preparing staging folder at ${STAGING_DIR}"
  rm -rf "${STAGING_DIR}"
  mkdir -p "${STAGING_DIR}" "${STAGING_DIR}/data"

  local paths=(API AI DE shared config)
  local path
  for path in "${paths[@]}"; do
    rsync -a \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude '.pytest_cache' \
      --exclude 'node_modules' \
      --exclude 'tests' \
      --exclude '.mypy_cache' \
      --exclude '.ruff_cache' \
      "${ROOT}/${path}" "${STAGING_DIR}/"
  done

  cp "${ROOT}/requirements.txt" "${STAGING_DIR}/requirements.txt"
  if [[ -f "${ROOT}/data/sample_job_metrics.csv" ]]; then
    cp "${ROOT}/data/sample_job_metrics.csv" "${STAGING_DIR}/data/sample_job_metrics.csv"
  fi
}

write_app_yaml() {
  local app_yaml="${STAGING_DIR}/app.yaml"
  local host="$1"
  local http_path="$2"
  local faiss_index_path="$3"
  cat >"${app_yaml}" <<EOF
command:
  - uvicorn
  - API.src.main:app
  - --host
  - 0.0.0.0
  - --port
  - "8000"

env:
  - name: PYTHONPATH
    value: "."
  - name: CONFIG_DIR
    value: "config"
  - name: USE_POSTGRES
    value: "true"
  - name: POSTGRES_BACKEND
    value: "lakebase"
  - name: POSTGRES_LAKEBASE_ENDPOINT
    valueFrom: postgres
  - name: USE_LOCAL_DATA
    value: "${USE_LOCAL_DATA}"
  - name: LOCAL_DATA_PATH
    value: "${LOCAL_DATA_PATH}"
  - name: USE_MOCK_LLM
    value: "${USE_MOCK_LLM}"
  - name: APP_ENV
    value: "${APP_ENV}"
  - name: LOG_LEVEL
    value: "${LOG_LEVEL}"
  - name: FAISS_VOLUME_ROOT
    valueFrom: faiss-volume
  - name: FAISS_INDEX_PATH
    value: "${faiss_index_path}"
  - name: DATABRICKS_HOST
    value: "${host}"
  - name: DATABRICKS_HTTP_PATH
    value: "${http_path}"
EOF
}

bundle_var_args() {
  BUNDLE_VAR_ARGS=(
    --var "app_name=${APP_NAME}"
    --var "app_description=${APP_DESCRIPTION}"
    --var "postgres_branch=${POSTGRES_BRANCH}"
    --var "postgres_database=${POSTGRES_DATABASE}"
    --var "sql_warehouse_id=${SQL_WAREHOUSE_ID}"
    --var "faiss_volume_full_name=${FAISS_VOLUME_FULL_NAME}"
  )
}

print_manual_steps() {
  cat <<EOF

Manual post-deploy checks:
  1. Compute → Apps → ${APP_NAME} → User authorization → enable "Databricks SQL"
  2. In the app UI / Lakebase, keep the default metrics connection and dataset configured
  3. Grant the app service principal:
       - USE CATALOG on the metrics catalog
       - USE SCHEMA on the metrics schema
       - SELECT on the metrics table
  4. Ensure the SQL warehouse is running before testing browse APIs

Useful commands:
  databricks ${DATABRICKS_PROFILE:+-p "${DATABRICKS_PROFILE}"} apps get ${APP_NAME}
  databricks ${DATABRICKS_PROFILE:+-p "${DATABRICKS_PROFILE}"} apps logs ${APP_NAME}

EOF
}

main() {
  case "${1:-}" in
    -h|--help) usage 0 ;;
  esac

  require_cmd databricks
  require_cmd python3
  require_cmd rsync

  require_env DATABRICKS_HOST
  require_env POSTGRES_BRANCH
  require_env POSTGRES_DATABASE
  require_env SQL_WAREHOUSE_ID
  require_env FAISS_VOLUME_FULL_NAME

  local host http_path faiss_index_path
  host="$(normalize_host "${DATABRICKS_HOST}")"
  http_path="$(normalize_http_path "${SQL_WAREHOUSE_ID}")"
  faiss_index_path="$(faiss_index_path_from_volume "${FAISS_VOLUME_FULL_NAME}")"

  log "App name:        ${APP_NAME}"
  log "Bundle target:   ${BUNDLE_TARGET}"
  log "Workspace host:  ${host}"
  log "Warehouse path:  ${http_path}"
  log "FAISS index:     ${faiss_index_path}"

  stage_runtime_bundle
  write_app_yaml "${host}" "${http_path}" "${faiss_index_path}"
  bundle_var_args

  if [[ "${SKIP_VALIDATE:-0}" != "1" ]]; then
    log "Validating bundle"
    databricks_cmd bundle validate -t "${BUNDLE_TARGET}" "${BUNDLE_VAR_ARGS[@]}"
  else
    log "Skipping bundle validate (SKIP_VALIDATE=1)"
  fi

  if [[ "${SKIP_DEPLOY:-0}" != "1" ]]; then
    log "Deploying bundle"
    databricks_cmd bundle deploy -t "${BUNDLE_TARGET}" "${BUNDLE_VAR_ARGS[@]}"
  else
    log "Skipping bundle deploy (SKIP_DEPLOY=1)"
  fi

  print_manual_steps
}

main "$@"
