#!/bin/bash
# ============================================================
# RPI Picture Show - Release Script
# Inkrementiert die Patch-Version, committet und pusht.
# Nutzung: ./release.sh [git push argumente]
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

if [ ! -f "${VERSION_FILE}" ]; then
    echo "FEHLER: VERSION Datei nicht gefunden: ${VERSION_FILE}"
    exit 1
fi

# Aktuelle Version lesen
CURRENT_VERSION=$(cat "${VERSION_FILE}" | tr -d '[:space:]')
echo "Aktuelle Version: ${CURRENT_VERSION}"

# Version aufsplitten (Major.Minor.Patch)
IFS='.' read -r MAJOR MINOR PATCH <<< "${CURRENT_VERSION}"

# Patch-Version inkrementieren
PATCH=$((PATCH + 1))
NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"

# Neue Version schreiben
echo -n "${NEW_VERSION}" > "${VERSION_FILE}"
echo "Neue Version:     ${NEW_VERSION}"

# Git commit und push
git add "${VERSION_FILE}"
git commit -m "v${NEW_VERSION}"
git push "$@"

echo ""
echo "Release v${NEW_VERSION} erfolgreich gepusht."
