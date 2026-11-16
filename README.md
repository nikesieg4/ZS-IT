# ZS-IT-Bot

Discord-Bot „Zentraler Service Informationstechnik“ für die Berufsfeuerwehr (ER:LC-Roleplay).

## Funktionen

| Bereich | Befehle |
|---|---|
| Tickets | `/ticket-panel` (Panel mit Kategorien senden), `/ticket-hinzufuegen`; Buttons „Übernehmen“ und „Schließen“, Transkript im Log |
| Ränge | `/uprank`, `/downrank`, `/rank` – Rollentausch, Nickname `[Kürzel] Name`, Log in `rang-log`, DM |
| Verwarnungen | `/warn`, `/warns`, `/unwarn` – Rollen „Verwarnung 1–3“, Ablauf nach 30 Tagen, bei 3 aktiven Warns automatisch „Außendienstsperre“ |

Rang- und Warn-Befehle dürfen: Höherer Dienst, `[ZS-P]`, Wachleiter und Administratoren.

## Installation (Debian 13, als root)

```bash
apt update && apt install -y curl && bash <(curl -fsSL https://raw.githubusercontent.com/nikesieg4/ZS-IT-Bot/main/install.sh)
```

Das Skript fragt einmal nach dem Bot-Token, richtet alles unter `/opt/zsit-bot` ein und startet den
Dienst `zsit-bot` (Autostart). Derselbe Befehl aktualisiert den Bot später.

## Einmalig in Discord

1. Developer Portal → Bot → **Message Content Intent** einschalten (für Ticket-Transkripte).
2. Bot mit den Rechten *Rollen verwalten, Kanäle verwalten, Nicknames verwalten* einladen.
3. Die Bot-Rolle in den Servereinstellungen **über alle Rangrollen** ziehen.
4. Im Kanal `ticket-support` einmal `/ticket-panel` ausführen.

## Konfiguration

Rollen und Kanäle werden über ihre Namen aus der Servervorlage gefunden (`config.json`). Weicht etwas
ab, eigene Werte (Namen oder IDs) in `/opt/zsit-bot/config.local.json` eintragen – gleiche Struktur,
überschreibt `config.json` und bleibt bei Updates erhalten. Danach `systemctl restart zsit-bot`.
