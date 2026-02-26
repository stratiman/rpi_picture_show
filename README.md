# RPI Picture Show

Vollbild-Slideshow fuer den Raspberry Pi.
Zeigt abwechselnd Bilder aus zwei Ordnern (Logos und Pictures) an - ohne Desktop-Umgebung, direkt ueber KMS/DRM bzw. Framebuffer.
Hochgeladene Bilder werden bevorzugt angezeigt und danach automatisch in den Papierkorb verschoben.
Ein einfaches Webinterface ermoeglicht das Hochladen von Bildern per Browser.

## Features

- Abwechselnde Anzeige: Logo -> Bild -> Logo -> Bild ...
- Anzeigedauer pro Ordner separat einstellbar
- **Upload-Prioritaet**: Hochgeladene Bilder werden bevorzugt statt normaler Bilder angezeigt
- **Automatischer Papierkorb**: Angezeigte Uploads werden in den Trash verschoben
- **Papierkorb-Cleanup**: Alte Dateien werden nach konfigurierbarer Frist geloescht
- **Web-Upload**: Einfaches Webinterface zum Hochladen von Bildern per Browser/Handy
- **Dark/Light Mode**: Theme-Umschaltung per Button auf allen Seiten (wird im Browser gespeichert)
- **Upload-Log**: Alle Uploads werden mit Zeitpunkt, Dateiname, Ordner und IP-Adresse protokolliert
- Konfigurierbare Uebergangseffekte (Fade, Slide, kein Effekt)
- Automatischer Start beim Booten via systemd
- Laeuft ohne Desktop (X11/Wayland) direkt ueber KMS/DRM bzw. Framebuffer
- Rekursive Unterordner-Unterstuetzung
- Optionales Mischen der Bildreihenfolge
- **Versionierung**: Versionsnummer im Webinterface sichtbar, Auto-Inkrement per release.sh

## Voraussetzungen

- Raspberry Pi (getestet: Zero W v1.1, Model 3B)
- Raspberry Pi OS Lite (ohne Desktop) - Bookworm oder Trixie
- Python 3
- pygame, Flask

## Installation

### 1. Projekt auf den Pi kopieren

```bash
scp -r rpi-picture-show/ pi@<IP-ADRESSE>:/home/pi/
```

### 2. Installationsscript ausfuehren

```bash
cd /home/pi/rpi-picture-show
chmod +x install.sh
./install.sh
```

Das Script installiert alle Abhaengigkeiten, kopiert die Dateien und richtet die systemd-Services ein.

### 3. Bilder ablegen

```
/home/pi/slideshow/
  logo/           <-- Logos hier ablegen
  pictures/       <-- Bilder hier ablegen
  uploaded/       <-- Hochgeladene Bilder (per Web-Upload)
  trash/          <-- Papierkorb (automatisch verwaltet)
```

Unterordner werden automatisch mit durchsucht.

### 4. Starten

```bash
# Beide Services sofort starten
sudo systemctl start rpi-slideshow
sudo systemctl start rpi-slideshow-web

# Oder einfach neu starten - die Services starten automatisch
sudo reboot
```

## Web-Upload

Nach dem Start ist das Upload-Interface erreichbar unter:

```
http://<PI-IP-ADRESSE>
```

- Zeigt ein Logo aus dem Logo-Ordner an
- Konfigurierbarer Titel und Begruessungstext
- Drag & Drop oder Datei auswaehlen
- Bildvorschau vor dem Upload
- Funktioniert auch auf dem Handy
- Dark/Light Mode umschaltbar (wird im Browser gespeichert)

Hochgeladene Bilder landen im `uploaded/` Ordner und werden beim naechsten Bildwechsel
bevorzugt angezeigt. Nach der Anzeige werden sie automatisch in den Papierkorb verschoben.

## Admin-Panel

Das Admin-Panel ist passwortgeschuetzt erreichbar unter:

```
http://<PI-IP-ADRESSE>/admin
```

**Standard-Passwort: `admin`** (bitte nach der Installation aendern!)

### Funktionen

- **Einstellungen**: Anzeigedauer fuer Logos, Bilder und Uploads konfigurieren, Papierkorb-Aufbewahrungsdauer anpassen
- **Logos verwalten**: Logo-Bilder hochladen und loeschen
- **Bilder verwalten**: Picture-Bilder hochladen und loeschen
- **Papierkorb**: Einzelne oder alle Bilder im Papierkorb loeschen
- **Upload-Log**: Tabelle aller Uploads mit Zeitpunkt, Dateiname, Ordner und IP-Adresse
- **Passwort**: Admin-Passwort aendern

Einstellungsaenderungen werden sofort in die `config.ini` geschrieben.
Die Slideshow uebernimmt neue Timings beim naechsten Ordner-Rescan automatisch.

## Anzeigelogik

```
Schleife:
  1. Logo anzeigen (logo_display_seconds)
  2. Bilder in uploaded/?
     -> Ja:  Uploaded-Bild anzeigen, dann in trash/ verschieben
     -> Nein: Bild aus pictures/ anzeigen
  3. Zurueck zu 1.
```

## Konfiguration

Alle Einstellungen befinden sich in `/home/pi/rpi-picture-show/config.ini`:

```ini
[paths]
base_path = /home/pi/slideshow
logo_folder = logo
pictures_folder = pictures
uploaded_folder = uploaded
trash_folder = trash

[timing]
logo_display_seconds = 5
pictures_display_seconds = 10
uploaded_display_seconds = 8

[display]
transition = fade
transition_duration_min_ms = 300
transition_duration_max_ms = 800
transition_duration_random = true
background_color = #000000

[slideshow]
shuffle = false
recursive = true

[trash]
delete_after_days = 30

[web]
enabled = true
port = 80
title = RPI Picture Show
greeting = Willkommen! Laden Sie hier Ihre Bilder hoch.
min_free_space_mb = 100

[logging]
upload_log_max = 200

[admin]
# Passwort-Hash (SHA-256) - Standard: admin
password_hash = 8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918
```

### Pfade

| Einstellung | Beschreibung |
|---|---|
| `base_path` | Basispfad zu den Bildordnern |
| `logo_folder` | Name des Logo-Ordners (relativ zum base_path) |
| `pictures_folder` | Name des Bilder-Ordners (relativ zum base_path) |
| `uploaded_folder` | Name des Upload-Ordners (relativ zum base_path) |
| `trash_folder` | Name des Papierkorb-Ordners (relativ zum base_path) |

### Timing

| Einstellung | Beschreibung |
|---|---|
| `logo_display_seconds` | Wie lange ein Logo angezeigt wird (in Sekunden) |
| `pictures_display_seconds` | Wie lange ein Bild angezeigt wird (in Sekunden) |
| `uploaded_display_seconds` | Wie lange ein hochgeladenes Bild angezeigt wird (in Sekunden) |

### Uebergangseffekte

| Wert | Beschreibung |
|---|---|
| `none` | Sofortiger Bildwechsel |
| `fade` | Sanftes Ueberblenden |
| `slide_left` | Horizontales Schieben nach links |
| `slide_right` | Horizontales Schieben nach rechts |
| `slide_up` | Vertikales Schieben nach oben |
| `slide_down` | Vertikales Schieben nach unten |
| `zoom_in` | Neues Bild waechst aus der Mitte |
| `zoom_out` | Altes Bild schrumpft zur Mitte |
| `wipe_left` | Aufdecken von links nach rechts |
| `wipe_right` | Aufdecken von rechts nach links |
| `wipe_down` | Aufdecken von oben nach unten |
| `wipe_up` | Aufdecken von unten nach oben |
| `dissolve` | Pixelweises Aufloesen in zufaelligen Bloecken |
| `random` | **Zufaellige Auswahl** eines Effekts pro Bildwechsel |

### Uebergangsdauer

| Einstellung | Beschreibung |
|---|---|
| `transition_duration_min_ms` | Minimale Dauer des Uebergangs (ms) |
| `transition_duration_max_ms` | Maximale Dauer des Uebergangs (ms) |
| `transition_duration_random` | `true` = zufaellige Dauer zwischen min/max, `false` = immer min |

### Slideshow

| Einstellung | Beschreibung |
|---|---|
| `shuffle` | `true` = Zufaellige Reihenfolge, `false` = Alphabetisch |
| `recursive` | `true` = Unterordner mit durchsuchen |

### Papierkorb

| Einstellung | Beschreibung |
|---|---|
| `delete_after_days` | Dateien im Papierkorb nach X Tagen loeschen (0 = nie) |

### Web-Upload

| Einstellung | Beschreibung |
|---|---|
| `enabled` | Webinterface aktivieren (`true`/`false`) |
| `port` | Port fuer das Webinterface |
| `title` | Titel der Upload-Seite |
| `greeting` | Begruessungstext auf der Upload-Seite |
| `min_free_space_mb` | Mindest-Freispeicher in MB (Upload wird abgelehnt wenn weniger frei) |

### Logging

| Einstellung | Beschreibung |
|---|---|
| `upload_log_max` | Maximale Anzahl Upload-Log-Eintraege (aeltere werden verworfen) |

### Admin

| Einstellung | Beschreibung |
|---|---|
| `password_hash` | SHA-256 Hash des Admin-Passworts (Standard: `admin`) |

## Service-Befehle

### Slideshow

```bash
sudo systemctl start rpi-slideshow      # Starten
sudo systemctl stop rpi-slideshow       # Stoppen
sudo systemctl restart rpi-slideshow    # Neustarten
sudo systemctl status rpi-slideshow     # Status anzeigen
journalctl -u rpi-slideshow -f          # Log live anzeigen
```

### Web-Upload

```bash
sudo systemctl start rpi-slideshow-web      # Starten
sudo systemctl stop rpi-slideshow-web       # Stoppen
sudo systemctl restart rpi-slideshow-web    # Neustarten
sudo systemctl status rpi-slideshow-web     # Status anzeigen
journalctl -u rpi-slideshow-web -f          # Log live anzeigen
```

## Beenden

- Per Service: `sudo systemctl stop rpi-slideshow`
- Per Tastatur: **ESC** oder **Q** (falls Tastatur angeschlossen)

## Unterstuetzte Bildformate

JPG, JPEG, PNG, BMP, GIF (statisch)

## Fehlerbehebung

**Kein Bild sichtbar:**
- Pruefen ob Bilder in den Ordnern liegen: `ls /home/pi/slideshow/logo/`
- Log pruefen: `journalctl -u rpi-slideshow -f`

**Service startet nicht:**
- Status pruefen: `sudo systemctl status rpi-slideshow`
- Manuell testen: `python3 /home/pi/rpi-picture-show/slideshow.py`

**Web-Upload nicht erreichbar:**
- Status pruefen: `sudo systemctl status rpi-slideshow-web`
- Port pruefen: `ss -tlnp | grep 80`
- Log pruefen: `journalctl -u rpi-slideshow-web -f`

**Falscher Bildpfad:**
- `config.ini` pruefen und Pfade anpassen
- Services neustarten: `sudo systemctl restart rpi-slideshow rpi-slideshow-web`

## Versionierung

Die aktuelle Version steht in der Datei `VERSION` und wird im Webinterface (Footer) angezeigt.

### Release erstellen

Statt `git push` das Wrapper-Script verwenden:

```bash
./release.sh
```

Das Script:
1. Liest die aktuelle Version aus `VERSION`
2. Inkrementiert die Patch-Version (z.B. 1.0.0 -> 1.0.1)
3. Schreibt die neue Version in `VERSION`
4. Committet und pusht automatisch

Optionale Git-Push-Argumente werden weitergeleitet:

```bash
./release.sh origin main
```
