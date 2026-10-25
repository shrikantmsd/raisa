#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/api"
export DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg2://raisa_synapse:devpassword_local_only@localhost:5432/raisa_synapse_test}"
./.venv/bin/python -m pytest -v "$@"
