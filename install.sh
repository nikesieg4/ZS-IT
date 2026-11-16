#!/usr/bin/env bash
# Installiert oder aktualisiert den ZS-IT-Bot auf Debian (als root ausfuehren).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/nikesieg4/ZS-IT-Bot.git}"
DIR=/opt/zsit-bot
SVC_USER=zsitbot
SERVICE=zsit-bot

[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen."; exit 1; }

echo "==> Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv ca-certificates >/dev/null

id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DIR" --shell /usr/sbin/nologin "$SVC_USER"

if [ -d "$DIR/.git" ]; then
  echo "==> Bot aktualisieren"
  git -c safe.directory="$DIR" -C "$DIR" pull --ff-only
else
  echo "==> Bot herunterladen"
  git clone --quiet "$REPO_URL" "$DIR"
fi

echo "==> Python-Umgebung einrichten"
[ -d "$DIR/.venv" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

if [ ! -f "$DIR/.env" ]; then
  echo
  read -rsp "Bot-Token einfügen (Eingabe bleibt unsichtbar) und Enter drücken: " TOKEN </dev/tty
  echo
  [ -n "$TOKEN" ] || { echo "Kein Token eingegeben – Abbruch."; exit 1; }
  printf 'DISCORD_TOKEN=%s\n' "$TOKEN" > "$DIR/.env"
fi
chmod 600 "$DIR/.env"
mkdir -p "$DIR/data"
chown -R "$SVC_USER":"$SVC_USER" "$DIR"

cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=ZS-IT Discord-Bot
After=network-online.target
Wants=network-online.target

[Service]
User=$SVC_USER
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/.venv/bin/python $DIR/bot.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --quiet "$SERVICE"
systemctl restart "$SERVICE"
sleep 4

echo
if systemctl is-active --quiet "$SERVICE"; then
  echo "✅ Der Bot läuft."
else
  echo "❌ Der Bot ist nicht gestartet. Letzte Meldungen:"
  journalctl -u "$SERVICE" -n 15 --no-pager
fi
echo "Logs ansehen:   journalctl -u $SERVICE -f"
echo "Neu starten:    systemctl restart $SERVICE"
echo "Token ändern:   nano $DIR/.env && systemctl restart $SERVICE"
echo "Aktualisieren:  diesen Installationsbefehl einfach erneut ausführen"
