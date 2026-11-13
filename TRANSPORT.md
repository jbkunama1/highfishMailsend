# Versandweg und Geltungsbereich

SMTP und CyberPanel API bleiben gleichzeitig konfiguriert. Keine zusaetzlichen Container oder Netzwerkports.

## Beide konfigurieren

In Portainer MAIL_TRANSPORT als Startstandard setzen (smtp oder cyberpanel). Fuer beide Wege SMTP_HOST=mail.cyberpersons.com, SMTP_PORT=587, SMTP_USERNAME, SMTP_PASSWORD und CYBERPANEL_API_KEY hinterlegen. Echte Secrets ausschliesslich in Portainer. MAIL_FROM/MAIL_TO, MCP-Key, Host-Allowlist und Telegram-Variablen unveraendert. DRY_RUN=true fuer erste Tests. SMTP verwendet STARTTLS, CyberPanel HTTPS. Bestehender MailerSend-Modus api bleibt kompatibel, ist aber keine der beiden Menueoptionen.

## Web

/admin/: Versandweg SMTP oder CyberPanel API, daneben Gilt fuer: Nur diese Mail oder Alle ab jetzt (global bis Neustart). Auswahl wird beim Erstellen der Vorschau uebernommen. Fuer Alle ab jetzt muss ein konkreter Weg ausgewaehlt und die globale Aenderung separat bestaetigt werden. Das aendert den gemeinsamen Standard fuer neue Web-/Telegram-/MCP-Mails, sendet selbst keine Mail. Anschliessend wird die Mailvorschau nochmals separat zum Versand bestaetigt. Nach globaler Uebernahme springt der Geltungsbereich auf Nur diese zurueck.

## Telegram

/admin -> Versandweg waehlen oder /transport. Buttons kombinieren Weg und Geltung. Nur diese gilt fuer den naechsten erfolgreich erstellten eigenen /mail-Entwurf innerhalb 10 Minuten und wird danach verbraucht. Bei neu gewaehltem Einmal-Weg wird ein eigener bestehender Entwurf verworfen, damit eine neue Vorschau bestaetigt wird. Abgelaufene Auswahl wird nicht stillschweigend durch den Standard ersetzt. Alle ab jetzt verlangt einen zweiten Bestaetigungsbutton (120 Sekunden gueltig); gilt global bis Neustart, nicht nur fuer den jeweiligen Telegram-Nutzer. /cancel verwirft offene Auswahl/Bestaetigung und eigenen Entwurf.

## Entwurf und Standard

Jeder Web-/Telegram-Entwurf speichert seinen konkreten Versandweg. Spaetere Standardaenderungen beeinflussen ihn nicht. Die Vorschau nennt Versandweg, vollstaendigen Absender und Empfaenger. Sendebestaetigung nutzt ausschliesslich gespeicherte Werte. Dry-run-Moduswechsel kann weiterhin eine neue Vorschau erfordern. Bestehende Mails werden durch Standardaenderungen nicht versendet oder erneut zugestellt.

MCP send_mail hat optional transport=smtp oder cyberpanel; leer verwendet den aktuellen Standard. Ein einzelner MCP-Aufruf aendert den Standard nicht.

## Laufzeit und Fehler

Alle ab jetzt wird nur im RAM gespeichert; nach Neustart gilt MAIL_TRANSPORT aus Portainer. Fuer dauerhaften Startstandard diese ENV anpassen. Bei mehreren Replikaten waere der Standard nicht synchron; vorgesehen ist ein einzelner Container/Prozess. Keine automatische Wiederholung und kein automatischer Fallback. Fehlende Zugangsdaten duerfen keinen anderen Versandweg ausloesen. Im Live-Modus werden bei Admin-Auswahl/Entwurf die benoetigten Zugangsdaten auf Vorhandensein geprueft; das ist kein Verbindungstest. Dry-run kann ohne echte Provider-Zugangsdaten getestet werden.

Neue Tests: explizite Auswahl ohne Standardaenderung, getrennte Transportaufrufe, kein Fallback bei Fehler, globale Aenderung nur mit Bestaetigung, gespeicherter Entwurfsweg trotz Standardwechsel und ungueltige Transporte. python -m unittest -v ausfuehren; noch kein CI-/Browser-/Telegram-Laufzeiterfolg behauptet.
