#!/bin/bash
# ============================================================
# RPI Picture Show - Installationsscript
# Fuer Raspberry Pi (Zero W, Model 3B und kompatible)
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/home/pi/rpi-picture-show"
SLIDESHOW_DIR="/home/pi/slideshow"
SERVICE_NAME="rpi-slideshow"
WEB_SERVICE_NAME="rpi-slideshow-web"

echo "========================================"
echo " RPI Picture Show - Installation"
echo "========================================"

# --- 1. Abhaengigkeiten installieren ---
echo ""
echo "[1/6] Installiere Abhaengigkeiten ..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pygame python3-flask

# --- 2. Programmverzeichnis einrichten ---
echo ""
echo "[2/6] Kopiere Programm nach ${INSTALL_DIR} ..."
sudo mkdir -p "${INSTALL_DIR}"
sudo cp "${SCRIPT_DIR}/slideshow.py" "${INSTALL_DIR}/"
sudo cp "${SCRIPT_DIR}/web_upload.py" "${INSTALL_DIR}/"
sudo cp "${SCRIPT_DIR}/config.ini" "${INSTALL_DIR}/"
sudo chown -R pi:pi "${INSTALL_DIR}"
sudo chmod +x "${INSTALL_DIR}/slideshow.py"
sudo chmod +x "${INSTALL_DIR}/web_upload.py"

# --- 3. Bilderordner anlegen ---
echo ""
echo "[3/6] Erstelle Bilderordner in ${SLIDESHOW_DIR} ..."
mkdir -p "${SLIDESHOW_DIR}/logo"
mkdir -p "${SLIDESHOW_DIR}/pictures"
mkdir -p "${SLIDESHOW_DIR}/uploaded"
mkdir -p "${SLIDESHOW_DIR}/trash"
echo "  -> ${SLIDESHOW_DIR}/logo/"
echo "  -> ${SLIDESHOW_DIR}/pictures/"
echo "  -> ${SLIDESHOW_DIR}/uploaded/"
echo "  -> ${SLIDESHOW_DIR}/trash/"

# --- 4. systemd Slideshow-Service einrichten ---
echo ""
echo "[4/6] Richte Slideshow-Service ein ..."
sudo cp "${SCRIPT_DIR}/rpi-slideshow.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
echo "  -> Slideshow-Service aktiviert"

# --- 5. systemd Web-Upload-Service einrichten ---
echo ""
echo "[5/6] Richte Web-Upload-Service ein ..."
sudo cp "${SCRIPT_DIR}/rpi-slideshow-web.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "${WEB_SERVICE_NAME}.service"
echo "  -> Web-Upload-Service aktiviert (Port 8080)"

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
echo "   http://<PI-IP-ADRESSE>:8080"
echo ""
echo " Zum sofortigen Starten:"
echo "   sudo systemctl start ${SERVICE_NAME}"
echo "   sudo systemctl start ${WEB_SERVICE_NAME}"
echo ""
