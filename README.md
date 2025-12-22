Nuki Lock Plugin for Domoticz

Domoticz Plugin zur Anbindung von Nuki Smart Locks über die Nuki Bridge (Developer Mode) via HTTP + Callback.

Features

🔒 Steuerung von mehreren Nuki Locks

🔔 Callback-Unterstützung für sofortige Statusupdates

🔁 Polling als Fallback (konfigurierbar)

🚪 Separater Unlatch-Button pro Schloss

🔋 Batteriestatus (kritisch / ok)

🔐 Unterstützung für Plain und Hashed Token

🛡️ Stabilisiert gegen Netzwerk- und Bridge-Ausfälle (Timeouts)

Voraussetzungen

Domoticz (Python Plugin Support)

Nuki Bridge mit aktiviertem Developer Mode

Netzwerkzugriff zwischen Domoticz ↔ Nuki Bridge

Installation
cd ~/domoticz/plugins
git clone https://github.com/schurgan/domoticz-nuki.git
Danach Domoticz neu starten.

Plugin-Konfiguration

Parameter	Beschreibung
Callback Port	Port, auf dem Domoticz Callbacks empfängt
Bridge IP	IP-Adresse der Nuki Bridge
Bridge Port	Standard: 8080
Bridge Token	API-Token aus der Nuki Bridge
Token Mode	Plain oder Hashed
Poll Interval	Poll-Intervall in Minuten
Logging	Normal, Debug oder File

Domoticz Geräte

Units 1..N → Nuki Locks (Lock / Unlock)
Units N+1..2N → Unlatch (Impuls)

Hinweise

Callback wird automatisch registriert
Polling dient nur als Backup, wenn Callbacks ausfallen
Laufzeitdateien (__pycache__, http.html, Logs) sind bewusst ausgeschlossen

Lizenz

MIT License – siehe LICENCE
