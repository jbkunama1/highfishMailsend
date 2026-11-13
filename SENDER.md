# Absenderauswahl bei fester Domain

Die Domain hinter @ stammt ausschliesslich aus MAIL_FROM und ist nicht pro Nachricht aenderbar. SMTP_HOST und SMTP-Zugangsdaten bleiben unveraendert. Beispiel MAIL_FROM=info@example.com: sender=shop wird shop@example.com; leer bleibt info@example.com. Keine neue Portainer-Variable erforderlich.

## MCP

send_mail(subject, text, to optional, sender optional). sender ist nur der Adressteil vor @, kein Anzeigename und keine volle Adresse. Bestehende Aufrufe ohne sender bleiben kompatibel.

## Web

/admin/: Feld Absendername vor @, feste Domain daneben. Vorschau zeigt die vollstaendige Von-Adresse. Jede Aenderung erfordert neue Vorschau. Der Server sendet ausschliesslich den gespeicherten Entwurf, nicht nachtraeglich uebergebene Absenderwerte.

## Telegram

/sender shop waehlt shop@FESTE-DOMAIN fuer neue eigene Entwuerfe. /sender zeigt die aktuelle Adresse. /sender default setzt auf MAIL_FROM zurueck (default ist dabei reservierter Befehl). Auswahl ist pro freigegebenem Nutzer, nur im RAM, bis Neustart. Absenderwechsel verwirft den eigenen offenen Entwurf. /mail und /send CODE bleiben unveraendert. Vollstaendige Von-Adresse steht in der Vorschau.

## Pruefung und Grenzen

Alternative Absendernamen sind ASCII, maximal 64 Zeichen und enthalten nur Buchstaben, Ziffern, Punkt, Unterstrich, Plus oder Bindestrich; zusaetzlich gilt E-Mail-Syntaxvalidierung. Kein @, keine Leerzeichen, Anzeigenamen, Header-Zeilenumbrueche oder andere Domains. Standardadresse wird weiterhin als vollstaendige MAIL_FROM konfiguriert. Die Domain muss beim Provider fuer deinen Account zum Versand zugelassen/verifiziert sein. Anwendung baut nur die Adresse; Annahme/Zustellung entscheidet der Provider.

Test: python -m unittest -v. Zusaetzliche Tests fuer feste Domain, ungueltige Namen, Dry-run, SMTP-From, API-From und gespeicherten Web-Absender. Telegram und Browser weiterhin in Zielumgebung pruefen. Keine echten Mails durch diese Tests.
