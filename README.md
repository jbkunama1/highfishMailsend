# highfishMailsend

MCP-Maildienst mit separater Webverwaltung und optionaler Telegram-Administration. Mehrere Profile für SMTP, MailerSend API und CyberPanel Email API. Übersicht der Dokumentation: [INDEX.md](INDEX.md).

## Weboberfläche und Zugänge

Unter `/admin/`: Übersicht, Mail schreiben und Anbieter. Profile anlegen, bearbeiten, aktivieren/deaktivieren und ausdrücklich als Standard setzen. Bestehende ENV-Zugangsdaten bleiben als unveränderliche eingebaute Profile erhalten. Statusaktualisierung verändert keinen Mailtext.

Weblogin mit `WEB_ADMIN_USERNAME` (Standard `admin`) und separatem `WEB_ADMIN_PASSWORD` mit mindestens 16 Zeichen, verschieden von `MCP_TOKEN`. MCP unter `/mcp` mit `Authorization: Bearer MCP_TOKEN`, mindestens 32 zufällige ASCII-Zeichen; kein OAuth. Der MCP-Client muss den konkreten Versand freigeben, das MCP-Tool selbst bietet keinen zweiten Bestätigungsdialog. HTTP ist unverschlüsselt: vertrauenswürdiges LAN/VPN oder korrekt eingerichtetes HTTPS verwenden.

## Versandregeln

Jeder Aufruf benötigt ein gültiges explizites `to`; `MAIL_TO` bleibt unbenutzter Legacy-Platzhalter. Eine gesetzte `MAIL_ALLOWED_TO`-Liste gilt immer. Die Absenderdomain bleibt aus `MAIL_FROM` fest; Profile können nur den lokalen Namen vorbelegen. `DRY_RUN=true` verhindert Mail-Submission. Live-Modus kann nicht über die Weboberfläche eingeschaltet werden.

Das Webformular zeigt Anbieter, vollständigen Absender, Empfänger, Betreff und Text und verlangt eine separate Versandbestätigung. Vorschauen gelten zehn Minuten und einmalig. Profiländerung/Deaktivierung erfordert eine neue Vorschau. Keine automatischen Versand-Retries und kein Anbieter-Fallback. Bei Timeout/unklarem Ergebnis zuerst beim Provider prüfen. Annahme ist keine Zustellgarantie; keine persistente Mailhistorie.

## MCP-Anbieterwahl

`send_mail` akzeptiert zusätzlich `provider` als Profil-ID aus der authentifizierten Anbieterliste. Explizites Profil hat Vorrang; zusätzliches `transport` muss passen. Nur `transport` wählt den bisherigen ENV-Transport (`smtp`, `api`, `cyberpanel`). Ohne beide gilt der persistierte Standard, sonst der bisherige ENV-/Laufzeitstandard. `provider_revision` ist intern für Webvorschauen und bei normalen MCP-Aufrufen wegzulassen. Keine MCP-Werkzeuge zur Profiländerung. Bereits begonnene Sendungen werden durch spätere Profiländerungen nicht abgebrochen.

## Speicherung und Portainer-Migration

SQLite auf Volume `provider-data` unter `/data`; Zugangsdaten einschließlich SMTP-Benutzername mit Fernet authentifiziert verschlüsselt. Gespeicherte Secrets werden nicht zurückgegeben. Profilmetadaten sind nicht verschlüsselt. Leere Zugangsdaten beim Bearbeiten behalten die bisherigen Werte.

- `PROVIDER_ENCRYPTION_KEY`: separater dauerhafter Fernet-Schlüssel, weder MCP-Key noch Webpasswort.
- `PROVIDER_DB_PATH`: im Compose-Beispiel `/data/providers.sqlite3`.
- `SMTP_TRUSTED_PRIVATE_HOSTS`: optionale kommagetrennte Freigabe privater SMTP-Hostnamen; standardmäßig leer.

Schlüssel lokal mit installierten Abhängigkeiten erzeugen:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Nicht ins Repository oder in den Chat kopieren; separat sicher verwahren und nicht bei jedem Neustart neu erzeugen. Ohne Schlüssel bleibt die Profilverwaltung gesperrt, alte ENV-Nutzung verfügbar. Bei gesetztem, falschem Schlüssel oder defektem Speicher werden implizite Profilaufrufe abgelehnt statt auf einen anderen Anbieter auszuweichen.

Neues Image bauen und prüfen, Compose-Erweiterungen übernehmen, Schlüssel setzen, Volume bereitstellen und Container neu erstellen. Einstieg bleibt `service.py`. Zunächst `DRY_RUN=true` nutzen. Live erst bewusst in Portainer mit `DRY_RUN=false` und Containerneuerstellung aktivieren. Repository-Push ist kein Deployment.

`/data` wird im Image für UID 10001 mit Modus 0700 angelegt. Frische benannte Volumes übernehmen die Verzeichnisvorgaben; vorhandene Volumes/Bind-Mounts brauchen passende Schreibrechte für UID 10001. Non-root, read-only Root-Dateisystem und `highfishNetwork` bleiben erhalten.

Für eine einfache konsistente Sicherung Container stoppen, Datenvolume und separaten Schlüssel sichern. Gemeinsam mit demselben Schlüssel und passenden Rechten wiederherstellen. Falsche Schlüssel überschreiben keine bestehende Datenbank. Volume nicht mit `down -v` löschen. Keine automatische Schlüsselrotation oder Profil-Löschung; Deaktivieren ist möglich, beim Standard erst einen anderen wählen.

## Verbindungstest

SMTP-Prüfung baut verifiziertes TLS auf und meldet sich an, sendet aber keine Mail. API-Prüfung testet ausschließlich TLS-Erreichbarkeit des fest eingebauten HTTPS-Servers, NICHT API-Key, Domain oder Versandberechtigung. Explizite Prüfungen können auch im Dry-run Netzwerkzugriffe ausführen. Eine echte Testmail erfolgt nur über Empfänger, Vorschau und Bestätigung und wird im Dry-run nicht zugestellt.

Profil-SMTP erlaubt nur verifiziertes STARTTLS oder direktes TLS, prüft DNS-Adressen und bindet die Verbindung an eine geprüfte IP bei Zertifikatsprüfung gegen den ursprünglichen Hostnamen. Private SMTP-Ziele benötigen ausdrückliche Hostfreigabe. Loopback, Link-local/Metadatenziele, Multicast und nicht spezifizierte Ziele bleiben gesperrt. DNS folgt OS-Resolver-Timeouts. Alte ENV-Versandfunktionen behalten ihr bisheriges Verhalten. Beliebige zusätzliche HTTP-APIs benötigen einen eigenen Adapter.

## LAN-Hostfreigabe

```env
MCP_ALLOWED_HOSTS=192.168.178.8:8095,localhost:*,127.0.0.1:*,[::1]:*
```

Host:Port ohne Schema/Pfad, kommagetrennt. Browser-MCP-Origin separat über `MCP_ALLOWED_ORIGINS=http://192.168.178.8:8095` erlauben, falls benötigt. Danach Container neu erstellen; Schutz nicht pauschal abschalten.

## Prüfung und Grenzen

```bash
pip install -r requirements.txt
python -m unittest -v
```

29 isolierte Provider-Komponententests wurden erfolgreich ausgeführt. Vollständige bestehende Anwendungstests, Auth-/CSRF-Integration, MCP-Schema, Browser, Docker-Build und GitHub Actions sind dadurch NICHT verifiziert. Details: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). Keine echten Mail-/Telegram-Sends für diese Implementierung. `/health` prüft Liveness, nicht Versandberechtigungen.

Telegram-Administration und einmaliger Startstatusversuch je freigegebenem Nutzer bleiben unverändert. Der alte Telegram-Maildialog hat kein explizites Empfängerfeld und ist deshalb kein vollständiger Versandweg; dafür Web oder MCP nutzen. Kein automatischer Mailversand beim Start.

Ältere Detaildokumentation bleibt als Kontext erhalten; bei Abweichungen zu Anbieterprofilen, Persistenz und Auswahlregeln gilt diese README. Keine Arbeit an Copilot oder andere Coding-Agents delegieren.
