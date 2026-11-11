# highfishMailsend

MCP-Maildienst, Web-Adminpanel und Telegram-Adminbot in einem Docker-Container. Selbst implementiert. Kein eigener KI-Server: ein externer MCP-Client formuliert Mails und ruft send_mail auf. Web und Telegram verwenden unveraendert eingegebenen Betreff und Plaintext. Keine Anhaenge.

## Funktionen

| Zugang | Funktionen |
|---|---|
| MCP /mcp | send_mail(subject, text, to optional), Bearer-Key |
| Web /admin/ | Key-Anmeldung, Status, Konfiguration ohne Passwoerter, Entwurf/Vorschau, bestaetigter Versand, Testmodus einschalten |
| Telegram | Private Chats mit Benutzer-Allowlist, Inline-Adminmenue, Status/Konfiguration, Mailentwurf und Sendecode, Testmodus einschalten |

Alle drei Zugaenge teilen Mailversand, Empfaenger-Allowlist und Dry-run-Modus. Adminpanel bietet noch keine Bearbeitung von SMTP-Zugangsdaten, keine Containersteuerung und keinen Logbrowser. Zugangsdaten und Live-Modus bleiben in Portainer. Ein per Admin eingeschalteter Testmodus gilt nur bis zum Neustart; dann gilt wieder DRY_RUN aus der Umgebung.

## Build und Portainer

GitHub Actions: erst automatisierte Tests, danach Multiarch-Build fuer linux/amd64 und linux/arm64. Push auf main veroeffentlicht latest und Commit-SHA unter ghcr.io/jbkunama1/highfishmailsend. Pull Requests bauen ohne Push. Ein oeffentliches Repository garantiert kein oeffentliches GHCR-Paket: Sichtbarkeit pruefen oder GHCR-Zugang in Portainer hinterlegen.

1. Erfolgreichen Build unter GitHub Actions abwarten.
2. Portainer Git-Stack: https://github.com/jbkunama1/highfishMailsend, main, docker-compose.yml. Der Zielserver zieht nur das Image, kein lokaler Build.
3. Variablen setzen (Tabelle unten), zuerst DRY_RUN=true.
4. http://SERVER-IP:8095/admin/ oeffnen und mit MCP_TOKEN anmelden. Eine Vorschau erstellen und im Testmodus verarbeiten.
5. Telegram optional konfigurieren und /admin senden.
6. Erst nach Tests DRY_RUN=false in Portainer setzen und Stack neu deployen. Das aktiviert echten Versand fuer alle Zugaenge.

## Konfiguration

| Variable | Bedeutung / Standard |
|---|---|
| MCP_TOKEN | Pflicht: zufaelliger geheimer Key mit mindestens 32 ASCII-Zeichen; z.B. openssl rand -hex 32. Gilt fuer MCP und Web-Admin |
| MAIL_FROM | Pflicht: volle Absenderadresse einer verifizierten MailerSend-Domain |
| MAIL_TO | Pflicht: Standardempfaenger |
| MAIL_ALLOWED_TO | Kommagetrennte erlaubte Adressen; leer = nur MAIL_TO |
| DRY_RUN | true = Vorschau, keine echte Mail; false = echter Versand |
| MAIL_TRANSPORT | smtp (Standard) oder api |
| SMTP_HOST / SMTP_PORT | smtp.mailersend.net / 587; verpflichtendes STARTTLS mit Zertifikatspruefung |
| SMTP_USERNAME / SMTP_PASSWORD | MailerSend-SMTP-Zugangsdaten, kein normaler Account-Login |
| MAILERSEND_API_TOKEN | Nur bei api: HTTP-API-Token statt SMTP-Benutzer/Passwort |
| MCP_ALLOWED_HOSTS | Pflicht im Stack: tatsaechliche Server-IP/Hostname mit extern verwendetem Port; mehrere kommagetrennt |
| MCP_ALLOWED_ORIGINS | Optional: benoetigte Browser-Origins fuer MCP |
| TELEGRAM_BOT_TOKEN | Optional: Bot-Token, leer = Telegram aus |
| TELEGRAM_ALLOWED_USER_IDS | Bei Telegram Pflicht: numerische persoenliche Benutzer-IDs, kommagetrennt |
| BIND_ADDRESS / APP_PORT | 0.0.0.0 / 8095 |

Beispiel fuer direkten LAN-Zugriff: MCP_ALLOWED_HOSTS=192.168.1.10:8095. Bei Portweiterleitung externen Host/Port ebenfalls eintragen. Keine globale Host-Wildcard. Netzwerk-, Router- und Firewallfreigaben werden nicht automatisch eingerichtet. Alte .env.example ggf. anpassen: deren Loopback-Bindung verhindert direkten LAN-Zugriff. Niemals echte Keys/Passwoerter in Git speichern.

## Web-Adminpanel

http://SERVER-IP:8095/admin/ (auch /admin wird dorthin umgeleitet). Die Login-Seite selbst ist oeffentlich, alle Admin-API-Daten und Aktionen erfordern den Key im Authorization-Header. Kein Key in der URL, kein localStorage, keine Drittanbieter-Skripte. Key bleibt nur im Seitenspeicher bis Abmeldung/Neuladen. Abmelden loescht lokale Formularwerte. Konfigurationsansicht zeigt nur, ob Passwoerter/Tokens gesetzt sind, nicht deren Werte.

Versand ist zweistufig: Vorschau erstellen -> unveraenderte Vorschau bestaetigen. Entwurf ist 10 Minuten gueltig und einmalig; Aenderungen im Formular verlangen neue Vorschau. Moduswechsel invalidiert den Entwurf. Maximal 100 offene Webentwuerfe, nur im RAM.

## Telegram-Administration

Long Polling laeuft im selben Container und benoetigt keinen eingehenden Telegram-Port. Nur private Chats freigegebener Benutzer. Bestehender Webhook muss vorab entfernt sein; der Dienst loescht ihn nicht automatisch. Pro Bot nur einen Poller starten. Alte wartende Updates werden beim Start uebersprungen.

| Befehl | Funktion |
|---|---|
| /admin oder /start | Inline-Adminmenue |
| /status oder /config | Modus, Transport, Konfiguration ohne Secrets, Pollerstatus |
| /dryrun | Testmodus fuer MCP, Web und Telegram einschalten; bis Neustart |
| /mail Betreff gefolgt von neuer Zeile und Mailtext | Entwurf an MAIL_TO |
| /send CODE | Entwurf innerhalb 10 Minuten bestaetigen |
| /cancel | Eigenen Entwurf verwerfen |
| /help | Hilfe und Menue |

Keine eigene KI-Textinterpretation im Bot. Bei langen Mails ist die Telegram-Vorschau gekuerzt. Entwuerfe gehen beim Neustart verloren. Passwoerter und Tokens nicht in Telegram-Nachrichten eingeben.

## MCP-Anbindung

Streamable HTTP: http://SERVER-IP:8095/mcp

Authorization: Bearer DEIN_MCP_TOKEN

Der Client muss benutzerdefinierte Authorization-Header unterstuetzen; kein OAuth. Vor echtem MCP-Versand muss der Client Nutzerfreigabe fuer Empfaenger und Inhalt einholen. Anders als Web/Telegram hat MCP keinen serverseitigen Entwurfsfreigabe-Schritt.

## Sicherheit und Grenzen

Kein Proxy erforderlich, aber HTTP verschluesselt weder Key noch Mailinhalt! Key-Authentifizierung ersetzt kein TLS. Direkten unverschluesselten Zugriff auf vertrauenswuerdiges LAN/VPN begrenzen, nicht ungeschuetzt im Internet betreiben. Dieses Projekt implementiert noch kein direktes HTTPS. SMTP nutzt STARTTLS, MailerSend-API und Telegram ausgehend HTTPS.

Non-root-Container, read-only Dateisystem, entfernte Linux-Capabilities. Kein allgemeines Rate-Limit und keine persistente Deduplizierung. accepted bedeutet Provider-Annahme, nicht Postfachzustellung. Bei Fehler/Timeout kann der Versandstatus unklar bleiben: Provider pruefen, nicht blind erneut senden.

GET /health meldet nur HTTP-Liveness, keine SMTP-Zugangsdatenpruefung. Adminstatus zeigt Telegram-Pollerzustand, keine Garantie fuer Zustellbarkeit. Keine Mailhistorie oder Mailtexte in persistenter Datenbank.

## Tests

pip install -r requirements.txt

python -m unittest -v

Tests umfassen MCP-Dry-run, Auth, Eingabepruefung, SMTP-Mocks, MCP initialize/list/call sowie Web-Admin-Auth, Empfaengerpruefung, Vorschau, einmalige Freigabe und Moduswechsel. Telegram-Menue und Browser muessen zusaetzlich in der Zielumgebung getestet werden. Ein Commit bedeutet noch keinen erfolgreichen CI-Build oder echten Versandtest. Abhaengigkeiten sind versionsbegrenzt, noch nicht gelockt.
