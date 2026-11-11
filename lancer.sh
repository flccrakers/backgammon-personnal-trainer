#!/usr/bin/env bash
# Lance l'entraîneur de backgammon (crée l'environnement au premier lancement).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [ ! -x .venv/bin/python ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv .venv
    .venv/bin/pip install -q -e ".[test]"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ "${1:-}" = "scan" ] || [ "${1:-}" = "stats" ]; then
    exec bgtrainer-cli "$@"
fi
exec bgtrainer "$@"
