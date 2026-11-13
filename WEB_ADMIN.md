# Web-Admin und Telegram-Startmeldung

Der Container startet jetzt service.py. Dieser Einstiegspunkt trennt den Webzugang vom MCP-Bearer-Key; runner.py allein ist kein oeffentlicher Produktionseinstiegspunkt mehr.

In Portainer WEB_ADMIN_USERNAME (Standard admin) und ein eigenes WEB_ADMIN_PASSWORD mit mindestens 16 Zeichen setzen. Nicht den MCP_TOKEN wiederverwenden. Kein Passwort wird im Repository hinterlegt, automatisch versendet oder ins Browser-LocalStorage geschrieben. Fehlen geeignete Zugangsdaten, antwortet die Web-API mit 503; MCP und Healthcheck bleiben verfuegbar. Zugangsdaten anlegen bedeutet hier die getrennte Konfiguration bereitstellen, nicht ein produktives Passwort ins Git schreiben.

Websitzungen bestehen eine Stunde im Serverspeicher, enden beim Abmelden oder Containerneustart und verwenden HttpOnly/SameSite=Strict-Cookies. Auf HTTPS werden Secure-Cookies gesetzt. Der Dienst vertraut keinen Forwarded-Headers. HTTP uebertraegt Passwoerter und Sitzungen unverschluesselt: nur ueber vertrauenswuerdiges LAN/VPN oder HTTPS betreiben. Ein MCP-Key allein oeffnet die Web-API nicht. Ein Web-Cookie berechtigt nicht zu MCP. Interne Admin-Funktionen bleiben fuer Telegram verfuegbar.

Die Oberflaeche trennt Status, Mailformular, Vorschau/Versand und globale Einstellungen. Standardabsender und aktueller Versandweg werden nach Anmeldung vorausgefuellt. Empfaenger ist immer Pflichtfeld pro Mail; MAIL_TO ist kein Fallback. Aktualisieren ueberschreibt keine Mailtexte. Globale Versandwegaenderungen gelten nur fuer neue Entwuerfe bis Neustart. Testmodus kann eingeschaltet, Live-Modus nicht per Web eingeschaltet werden.

Nach jedem Dienststart wird einmal je TELEGRAM_ALLOWED_USER_IDS eine private Statusmeldung versucht, sofern TELEGRAM_BOT_TOKEN gesetzt ist. Der Nutzer muss den Bot zuvor gestartet haben. Die Meldung enthaelt Betriebsmodus, Standard-Versandweg und Web-/MCP-Status, keine Passwoerter, Schluessel oder Mailinhalte. Kein automatischer Retry bei Fehler oder unklarem Ergebnis; Fehler blockieren den Dienst nicht. Neustarts erzeugen jeweils neue Meldungen. Es wird keine Start-E-Mail versendet. HTTP-Client-Info-Logs werden unterdrueckt, da Telegram-URLs den Bot-Token enthalten.

Image aus diesem Commit neu bauen, anschliessend Portainer-Stack mit neuem Image und den Web-ENV-Werten aktualisieren. highfishNetwork bleibt unveraendert.
