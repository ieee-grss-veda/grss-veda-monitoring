#!/usr/bin/env bash
#
# Export every dashboard from a Grafana instance as JSON.
#
# Auth uses a service account token (Grafana > Administration > Users and
# access > Service accounts), so it works with SSO logins where there is no
# local password.
#
# Usage:
#   GRAFANA_URL=https://grafana.example.org \
#   GRAFANA_TOKEN=glsa_xxx \
#     ./scripts/export-grafana-dashboards.sh [outdir]
#
# Files are written as <outdir>/<uid>-<slug>.json. Dashboards already
# provisioned from this repo are skipped by default (they are already in
# git); pass ALL=1 to export those too.
#
# To turn an exported dashboard into a provisioned one, move it into
# grafana/provisioning/dashboards/ — the export already strips the numeric
# "id" and "version" fields that must not be present in provisioned JSON.

set -euo pipefail

: "${GRAFANA_URL:?set GRAFANA_URL, e.g. https://grafana.example.org}"
: "${GRAFANA_TOKEN:?set GRAFANA_TOKEN (service account token)}"
OUTDIR="${1:-grafana-dashboard-export}"
ALL="${ALL:-0}"

command -v jq >/dev/null || { echo "jq is required (brew install jq)"; exit 1; }

api() { curl -sfL -H "Authorization: Bearer ${GRAFANA_TOKEN}" "${GRAFANA_URL}$1"; }

mkdir -p "$OUTDIR"

count=0
skipped=0
while IFS=$'\t' read -r uid title; do
  [ -z "$uid" ] && continue
  body=$(api "/api/dashboards/uid/${uid}") || { echo "!! failed: $uid ($title)"; continue; }

  # meta.provisioned marks dashboards loaded from files by a provisioner
  if [ "$ALL" != "1" ] && [ "$(printf '%s' "$body" | jq -r '.meta.provisioned')" = "true" ]; then
    echo "skip (provisioned): $title"
    skipped=$((skipped + 1))
    continue
  fi

  slug=$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
  file="${OUTDIR}/${uid}-${slug}.json"
  # Provisioned dashboards must not carry a database id or version
  printf '%s' "$body" | jq '.dashboard | del(.id, .version)' > "$file"
  echo "saved: $file"
  count=$((count + 1))
done < <(api "/api/search?type=dash-db&limit=5000" | jq -r '.[] | "\(.uid)\t\(.title)"')

echo
echo "exported $count dashboard(s) to $OUTDIR/ (skipped $skipped provisioned)"
