# RPI Picture Show

Vollbild-Slideshow fuer den Raspberry Pi.
Zeigt abwechselnd Bilder aus zwei Ordnern (Logos und Pictures) an - ohne Desktop-Umgebung, direkt ueber KMS/DRM bzw. Framebuffer.
Hochgeladene Bilder werden bevorzugt angezeigt und danach automatisch in den Papierkorb verschoben.
Ein einfaches Webinterface ermoeglicht das Hochladen von Bildern per Browser.

## Why

In meiner Bar steht ein TV und dort soll das Bar-Logo angezeigt werden. Ab und zu werden auch Fotos angezeigt. Gäste haben die Möglichkeit Bilder hochzuladen. Diese werden dann ebenfalls eingeblendet.

## Features

- Abwechselnde Anzeige: Logo -> Bild -> Logo -> Bild ...
- Anzeigedauer pro Ordner separat einstellbar
- **Upload-Prioritaet**: Hochgeladene Bilder werden bevorzugt statt normaler Bilder angezeigt
- **Automatischer Papierkorb**: Angezeigte Uploads werden in den Trash verschoben
- **Papierkorb-Cleanup**: Alte Dateien werden nach konfigurierbarer Frist geloescht
- **Web-Upload**: Einfaches Webinterface zum Hochladen von Bildern per Browser/Handy
- **Dark/Light Mode**: Theme-Umschaltung per Button auf allen Seiten (wird im Browser gespeichert)
- **Upload-Log**: Alle Uploads werden mit Zeitpunkt, Dateiname, Ordner und IP-Adresse protokolliert
- Konfigurierbare Uebergangseffekte (Fade, Slide, Zoom, Wipe, Dissolve, Random)
- Automatischer Start beim Booten via systemd
- Laeuft ohne Desktop (X11/Wayland) direkt ueber KMS/DRM bzw. Framebuffer
- Rekursive Unterordner-Unterstuetzung
- Optionales Mischen der Bildreihenfolge
- **Admin-Panel**: Passwortgeschuetztes Panel fuer Einstellungen, Bildverwaltung und System-Steuerung
- **System-Steuerung**: Slideshow starten/stoppen, System neustarten/herunterfahren - alles ueber den Browser
- **Update-Funktion**: Software-Update direkt aus dem Admin-Panel oder per `install.sh`
- **Versionierung**: Versionsnummer im Webinterface sichtbar, Auto-Inkrement per release.sh

## Voraussetzungen

- Raspberry Pi (getestet: Model 3B mit Trixie, Zero W v1.1)
- Raspberry Pi OS Lite (ohne Desktop) - **Trixie** (empfohlen), Bookworm
- Python 3
- pygame, Flask, git

## Installation

### 1. Repository auf den Pi klonen

```bash
ssh pi@<IP-ADRESSE>
git clone https://github.com/stratiman/rpi_picture_show.git /home/pi/rpi-picture-show
```

### 2. Installationsscript ausfuehren

```bash
cd /home/pi/rpi-picture-show
chmod +x install.sh
./install.sh
```

Das Script installiert alle Abhaengigkeiten, kopiert Platzhalterbilder und richtet die systemd-Services ein.

### 3. Bilder ablegen

```
/home/pi/slideshow/
  logo/           <-- Logos hier ablegen
  pictures/       <-- Bilder hier ablegen
  uploaded/       <-- Hochgeladene Bilder (per Web-Upload)
  trash/          <-- Papierkorb (automatisch verwaltet)
```

Unterordner werden automatisch mit durchsucht.
Bei der Erstinstallation werden Platzhalterbilder in die Ordner kopiert.

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
- **Update**: Software-Update von GitHub direkt aus dem Admin-Panel
- **System**: Slideshow starten/stoppen/neustarten, System neustarten oder herunterfahren

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
logo_display_seconds = 30
pictures_display_seconds = 10
uploaded_display_seconds = 10

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
upload_log_max = 2000

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

- Per Admin-Panel: **System-Tab** -> **Slideshow stoppen** (Konsole wird wiederhergestellt)
- Per Service: `sudo systemctl stop rpi-slideshow`
- Per Tastatur: **ESC** oder **Q** (falls Tastatur angeschlossen)

## Update

### Per install.sh (empfohlen)

```bash
cd /home/pi/rpi-picture-show
./install.sh
```

Das Script erkennt die bestehende Installation automatisch und fuehrt ein Update durch:
1. Sichert die `config.ini`
2. Holt die neueste Version per `git pull`
3. Stellt die `config.ini` wieder her
4. Kopiert aktualisierte Service-Dateien
5. Startet die Services neu

### Ueber das Admin-Panel

Im Admin-Panel gibt es den Tab **Update**:
1. **Auf Updates pruefen** klicken - vergleicht lokale mit der GitHub-Version
2. Falls Update verfuegbar: **Jetzt aktualisieren** klicken
3. Die Software wird aktualisiert und die Services automatisch neu gestartet
4. Die Seite laedt sich nach 5 Sekunden automatisch neu

Lokale Einstellungen (config.ini) bleiben bei einem Update erhalten.

### Manuell per SSH

```bash
cd /home/pi/rpi-picture-show
git pull
sudo cp rpi-slideshow.service rpi-slideshow-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart rpi-slideshow rpi-slideshow-web
```

## Unterstuetzte Bildformate

JPG, JPEG, PNG, BMP, GIF (statisch)

## Fehlerbehebung

**Kein Bild sichtbar (schwarzer Bildschirm):**
- Pruefen ob Bilder in den Ordnern liegen: `ls /home/pi/slideshow/logo/`
- Log pruefen: `journalctl -u rpi-slideshow -f`
- Auf Trixie/Bookworm: Service muss auf eigenem VT laufen (wird durch Service-Datei sichergestellt)
- Konsole ueberlagert Slideshow: `install.sh` erneut ausfuehren um Service-Datei zu aktualisieren

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

**Update fehlgeschlagen ("Kein Git-Repository"):**
- Die Installation muss per `git clone` erfolgt sein
- Falls manuell kopiert: Repository neu klonen und `install.sh` ausfuehren

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

## Versionshistorie

### v1.1.1
- **Multi-Upload**: Mehrere Bilder gleichzeitig hochladen per Dateiauswahl oder Drag & Drop
- **Vorschau-Grid**: Thumbnails aller ausgewaehlten Bilder vor dem Upload
- **Rescan-Trigger**: Slideshow erkennt neue Uploads sofort statt erst nach vollem Durchlauf

### v1.1.0
- **Volle Trixie-Unterstuetzung**: Laeuft jetzt zuverlaessig auf Raspberry Pi OS Trixie (Debian 13) mit SDL 2.28+ und vc4-kms-v3d
- **Direktes Framebuffer-Rendering**: Schreibt Bilder direkt nach `/dev/fb0` via mmap - umgeht kmsdrm-Probleme auf modernen Pi-Systemen vollstaendig
- **System-Tab im Admin-Panel**: Slideshow starten/stoppen/neustarten, System neustarten und herunterfahren - alles ueber den Browser
- **install.sh Update-Modus**: Erkennt bestehende Installation automatisch und fuehrt `git pull` statt Neuinstallation durch, sichert und stellt `config.ini` wieder her
- **Git-Repo-Pruefung**: Update-Funktion zeigt verstaendliche Fehlermeldung wenn kein Git-Repository vorhanden
- **Platzhalterbilder**: `install.sh` kopiert Beispielbilder bei Erstinstallation in die Bilderordner

### v1.0.2
- **Unicode-Fix**: Theme-Toggle Emojis korrekt escaped (behebt Internal Server Error auf allen Seiten)

### v1.0.1
- **Port 80 Binding**: Fix fuer Web-Service auf privilegiertem Port
- **Platzhalterbilder**: Beispielbilder fuer Logo und Pictures im Repository

### v1.0.0
- **Slideshow**: Vollbild-Anzeige mit konfigurierbaren Uebergangseffekten (Fade, Slide, Zoom, Wipe, Dissolve, Random)
- **Web-Upload**: Upload-Seite mit Drag & Drop, Bildvorschau, Dark/Light Mode
- **Admin-Panel**: Passwortgeschuetzter Bereich fuer Einstellungen, Bildverwaltung, Papierkorb, Upload-Log, Passwort-Aenderung und Software-Update
- **Upload-Log**: Protokollierung aller Uploads mit Zeitpunkt, Dateiname, Ordner und IP-Adresse (konfigurierbare Max-Eintraege)
- **Papierkorb**: Automatisches Cleanup nach konfigurierbarer Frist
- **Versionierung**: VERSION-Datei, Anzeige im Webinterface, release.sh fuer automatische Versionierung
- **systemd-Services**: Automatischer Start beim Booten, Neustart bei Fehler
