# highfishMailsend

Kleiner MCP-Maildienst im Docker-Container. Die KI laeuft im externen MCP-Client und ruft send_mail(subject, text, to optional) auf. Kein eigenes LLM, keine Datenbank, kein Webformular. Plaintext ohne Anhaenge.

## Ablauf

KI-Client -> geschuetzter MCP-Endpunkt /mcp -> MailerSend SMTP oder HTTP-API. GitHub Actions testet zuerst, baut danach AMD64/ARM64 und pusht auf main nach ghcr.io/jbkunama1/highfishmailsend. Portainer zieht das fertige Image und baut nicht selbst.

## Portainer

1. Erfolgreichen Workflow Test and publish GHCR auf main abwarten. Vorher ist kein verifiziertes Image verfuegbar.
2. Neuen Git-Stack mit https://github.com/jbkunama1/highfishMailsend, Branch main, Datei docker-compose.yml erstellen.
3. Stack-Variablen setzen: MCP_TOKEN (zufaellig, mindestens 32 ASCII-Zeichen), MAIL_FROM, MAIL_TO, SMTP_USERNAME, SMTP_PASSWORD. Token z.B. mit openssl rand -hex 32 erzeugen. Keine echten Secrets in Git!
4. DRY_RUN=true lassen, deployen und MCP-Test durchfuehren. Der Testmodus versendet nichts.
5. Fuer echten Versand bewusst DRY_RUN=false setzen und Stack neu deployen.

Das oeffentliche Repository macht das GHCR-Paket nicht automatisch oeffentlich. Paket-Sichtbarkeit auf GitHub pruefen oder in Portainer eine GHCR-Registry mit geeigneten read:packages-Zugangsdaten hinterlegen.

## Konfiguration

| Variable | Bedeutung / Default |
|---|---|
| MCP_TOKEN | Pflicht: geheimer Bearer-Token, mindestens 32 zufaellige ASCII-Zeichen |
| MAIL_FROM | Pflicht: vollstaendige Absenderadresse einer verifizierten MailerSend-Domain |
| MAIL_TO | Pflicht: Standardempfaenger |
| MAIL_ALLOWED_TO | Erlaubte Adressen, kommagetrennt; leer bedeutet nur MAIL_TO |
| DRY_RUN | true: Vorschau statt Versand |
| MAIL_TRANSPORT | smtp oder api |
| SMTP_HOST | smtp.mailersend.net |
| SMTP_PORT | 587; SMTP immer mit verpflichtendem STARTTLS und Zertifikatspruefung |
| SMTP_USERNAME / SMTP_PASSWORD | SMTP-Zugangsdaten aus MailerSend, kein normaler Account-Login |
| MAILERSEND_API_TOKEN | Nur bei api: API-Token statt SMTP-Zugangsdaten |
| MCP_ALLOWED_HOSTS | Erlaubte Host-Header, kommagetrennt; produktive Domain explizit ergaenzen |
| MCP_ALLOWED_ORIGINS | Erlaubte Origins, kommagetrennt; z.B. https://mail.example.com |
| BIND_ADDRESS / APP_PORT | 127.0.0.1 / 8095 |

Eine Absenderdomain allein reicht nicht: MAIL_FROM muss eine vollstaendige Mailadresse sein. Eine Konfigurationsvorlage steht in .env.example. Es gibt keinen separaten Protokollschalter: SMTP verwendet bewusst ausschliesslich STARTTLS, die API HTTPS.

## MCP-Anbindung und Netzwerk

Streamable HTTP URL: https://DEINE-DOMAIN/mcp
Header: Authorization: Bearer DEIN_MCP_TOKEN

MCP-Client muss statische Authorization-Header unterstuetzen; kein OAuth-Server. Reverse-Proxy und HTTPS selbst einrichten. MCP_ALLOWED_HOSTS um die tatsaechliche Domain (ggf. mit Port) und MCP_ALLOWED_ORIGINS um den HTTPS-Origin ergaenzen. DNS-Rebinding-Schutz bleibt aktiv.

Default-Portbindung nur am Host-Loopback: lokaler Host-Proxy erreicht 127.0.0.1:8095. Ein Proxy in einem anderen Container erreicht damit NICHT den Host; gemeinsames Docker-Netz mit Ziel mail:8000 konfigurieren oder Bind-Adresse bewusst aendern und Firewall setzen. Nicht ungeschuetzt ins Internet stellen.

## Sicherheit und Grenzen

Empfaenger-Allowlist, Token, Non-root-Container, read-only Dateisystem und verpflichtendes SMTP-TLS. Der Client muss vor einem echten Toolaufruf Empfaenger, Betreff und Text vom Nutzer freigeben lassen; diese Freigabe wird serverseitig nicht separat erzwungen. Kein Rate-Limit, keine persistente Deduplizierung in Version 1. Zugangsdaten/Mailtexte werden nicht explizit geloggt; Infrastruktur- und Client-Logs ebenfalls entsprechend schuetzen.

GET /health prueft nur den laufenden Prozess, nicht SMTP-Zugang oder Zustellbarkeit. accepted bedeutet Provider-Annahme, nicht Postfachzustellung. Bei Fehlern kann der Versandstatus unklar bleiben: Provider pruefen, nicht blind wiederholen.

## Tests und Status

Lokal: pip install -r requirements.txt und python -m unittest -v. Tests verwenden Dry-run bzw. Mocks fuer Versand, pruefen Auth, Empfaenger, Header und MCP initialize/tools/list/tools/call mit ASGI-Lifespan. CI muss reale Ergebnisse liefern; es wird kein bereits erfolgreicher Build oder echter Mailversand behauptet. Abhaengigkeiten sind versionsbegrenzt, noch nicht per Lockdatei fixiert.
