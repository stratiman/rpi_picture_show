#!/bin/bash
# ============================================================
# RPI Picture Show - Installations- und Update-Script
# Fuer Raspberry Pi (Zero W, Model 3B und kompatible)
#
# Erkennt automatisch ob Erstinstallation oder Update.
# ============================================================

set -e

INSTALL_DIR="/home/pi/rpi-picture-show"
SLIDESHOW_DIR="/home/pi/slideshow"
SERVICE_NAME="rpi-slideshow"
WEB_SERVICE_NAME="rpi-slideshow-web"
REPO_URL="https://github.com/stratiman/rpi_picture_show.git"

# --- Erkennung: Update oder Erstinstallation? ---
IS_UPDATE=false
if [ -d "${INSTALL_DIR}/.git" ]; then
    IS_UPDATE=true
fi

if [ "$IS_UPDATE" = true ]; then
    # ==============================================================
    # UPDATE-MODUS
    # ==============================================================
    echo "========================================"
    echo " RPI Picture Show - Update"
    echo "========================================"

    # --- 1. config.ini sichern ---
    echo ""
    echo "[1/4] Sichere Konfiguration ..."
    CONFIG_BACKUP=""
    if [ -f "${INSTALL_DIR}/config.ini" ]; then
        CONFIG_BACKUP=$(cat "${INSTALL_DIR}/config.ini")
        echo "  -> config.ini gesichert"
    fi

    # --- 2. Git Pull ---
    echo ""
    echo "[2/4] Aktualisiere aus Repository ..."
    # Lokale Aenderungen an versionierten Dateien verwerfen (config.ini etc.)
    git -C "${INSTALL_DIR}" checkout -- . 2>/dev/null || true
    if git -C "${INSTALL_DIR}" pull --ff-only; then
        echo "  -> Update erfolgreich"
    else
        echo "  -> WARNUNG: git pull fehlgeschlagen, versuche mit Reset ..."
        git -C "${INSTALL_DIR}" fetch origin
        git -C "${INSTALL_DIR}" reset --hard origin/master
        echo "  -> Reset auf neueste Version durchgefuehrt"
    fi

    # --- 3. config.ini wiederherstellen ---
    echo ""
    echo "[3/4] Stelle Konfiguration wieder her ..."
    if [ -n "${CONFIG_BACKUP}" ]; then
        echo "${CONFIG_BACKUP}" > "${INSTALL_DIR}/config.ini"
        echo "  -> config.ini wiederhergestellt"
    fi

    # --- 4. Services aktualisieren und neu starten ---
    echo ""
    echo "[4/4] Aktualisiere Services ..."
    sudo cp "${INSTALL_DIR}/rpi-slideshow.service" /etc/systemd/system/
    sudo cp "${INSTALL_DIR}/rpi-slideshow-web.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl restart "${SERVICE_NAME}.service" 2>/dev/null || true
    sudo systemctl restart "${WEB_SERVICE_NAME}.service" 2>/dev/null || true
    echo "  -> Services neu gestartet"

    NEW_VERSION="unbekannt"
    if [ -f "${INSTALL_DIR}/VERSION" ]; then
        NEW_VERSION=$(cat "${INSTALL_DIR}/VERSION")
    fi

    echo ""
    echo "========================================"
    echo " Update auf v${NEW_VERSION} abgeschlossen!"
    echo "========================================"
    echo ""

else
    # ==============================================================
    # ERSTINSTALLATION
    # ==============================================================
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    echo "========================================"
    echo " RPI Picture Show - Installation"
    echo "========================================"

    # --- 1. Abhaengigkeiten installieren ---
    echo ""
    echo "[1/6] Installiere Abhaengigkeiten ..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pygame python3-flask git

    # --- 2. Programmverzeichnis einrichten ---
    echo ""
    echo "[2/6] Richte Programmverzeichnis ein ..."
    if [ "${SCRIPT_DIR}" = "${INSTALL_DIR}" ]; then
        echo "  -> Wird bereits aus dem Installationsverzeichnis ausgefuehrt"
    else
        echo "  -> Klone Repository nach ${INSTALL_DIR} ..."
        sudo mkdir -p "$(dirname "${INSTALL_DIR}")"
        git clone "${REPO_URL}" "${INSTALL_DIR}"
    fi
    # config.ini nur kopieren wenn noch nicht vorhanden (User-Einstellungen erhalten)
    if [ ! -f "${INSTALL_DIR}/config.ini" ]; then
        echo "  -> Erstelle Standard-Konfiguration"
        cp "${SCRIPT_DIR}/config.ini" "${INSTALL_DIR}/config.ini"
    fi
    sudo chown -R pi:pi "${INSTALL_DIR}"
    sudo chmod +x "${INSTALL_DIR}/slideshow.py"
    sudo chmod +x "${INSTALL_DIR}/web_upload.py"
    sudo chmod +x "${INSTALL_DIR}/release.sh"

    # --- 3. Bilderordner anlegen ---
    echo ""
    echo "[3/6] Erstelle Bilderordner in ${SLIDESHOW_DIR} ..."
    mkdir -p "${SLIDESHOW_DIR}/logo"
    mkdir -p "${SLIDESHOW_DIR}/pictures"
    mkdir -p "${SLIDESHOW_DIR}/uploaded"
    mkdir -p "${SLIDESHOW_DIR}/trash"
    # Platzhalterbilder kopieren falls Ordner leer sind
    if [ -z "$(ls -A "${SLIDESHOW_DIR}/logo/" 2>/dev/null)" ] && [ -d "${INSTALL_DIR}/logo" ]; then
        cp "${INSTALL_DIR}"/logo/*.{jpg,jpeg,png,bmp,gif} "${SLIDESHOW_DIR}/logo/" 2>/dev/null || true
        echo "  -> Platzhalterbilder nach ${SLIDESHOW_DIR}/logo/ kopiert"
    fi
    if [ -z "$(ls -A "${SLIDESHOW_DIR}/pictures/" 2>/dev/null)" ] && [ -d "${INSTALL_DIR}/pictures" ]; then
        cp "${INSTALL_DIR}"/pictures/*.{jpg,jpeg,png,bmp,gif} "${SLIDESHOW_DIR}/pictures/" 2>/dev/null || true
        echo "  -> Platzhalterbilder nach ${SLIDESHOW_DIR}/pictures/ kopiert"
    fi
    echo "  -> ${SLIDESHOW_DIR}/logo/"
    echo "  -> ${SLIDESHOW_DIR}/pictures/"
    echo "  -> ${SLIDESHOW_DIR}/uploaded/"
    echo "  -> ${SLIDESHOW_DIR}/trash/"

    # --- 4. systemd Slideshow-Service einrichten ---
    echo ""
    echo "[4/6] Richte Slideshow-Service ein ..."
    sudo cp "${INSTALL_DIR}/rpi-slideshow.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable "${SERVICE_NAME}.service"
    echo "  -> Slideshow-Service aktiviert"

    # --- 5. systemd Web-Upload-Service einrichten ---
    echo ""
    echo "[5/6] Richte Web-Upload-Service ein ..."
    sudo cp "${INSTALL_DIR}/rpi-slideshow-web.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable "${WEB_SERVICE_NAME}.service"
    echo "  -> Web-Upload-Service aktiviert"

    # --- 6. Zusammenfassung ---
    echo ""
    echo "[6/6] Fertig!"
    echo ""
    echo "========================================"
    echo " Installation abgeschlossen!"
    echo "========================================"
    echo ""
    echo " Bilder ablegen in:"
    echo "   Logos:      ${SLIDESHOW_DIR}/logo/"
    echo "   Bilder:     ${SLIDESHOW_DIR}/pictures/"
    echo "   Uploads:    ${SLIDESHOW_DIR}/uploaded/"
    echo "   Papierkorb: ${SLIDESHOW_DIR}/trash/"
    echo ""
    echo " Konfiguration anpassen:"
    echo "   ${INSTALL_DIR}/config.ini"
    echo ""
    echo " Service-Befehle (Slideshow):"
    echo "   sudo systemctl start ${SERVICE_NAME}"
    echo "   sudo systemctl stop ${SERVICE_NAME}"
    echo "   sudo systemctl restart ${SERVICE_NAME}"
    echo "   sudo systemctl status ${SERVICE_NAME}"
    echo "   journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo " Service-Befehle (Web-Upload):"
    echo "   sudo systemctl start ${WEB_SERVICE_NAME}"
    echo "   sudo systemctl stop ${WEB_SERVICE_NAME}"
    echo "   sudo systemctl status ${WEB_SERVICE_NAME}"
    echo ""
    echo " Web-Upload erreichbar unter:"
    echo "   http://<PI-IP-ADRESSE>"
    echo ""
    echo " Zum sofortigen Starten:"
    echo "   sudo systemctl start ${SERVICE_NAME}"
    echo "   sudo systemctl start ${WEB_SERVICE_NAME}"
    echo ""
fi
