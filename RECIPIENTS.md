# Empfaenger pro Aufruf

MAIL_TO ist nur ein optionaler, ungepruefter Legacy-Platzhalter. Beliebige Werte, ein leerer Wert oder eine fehlende Variable verhindern den Start nicht. Der Wert ist niemals ein Versandziel oder Fallback.

MCP send_mail verlangt to bei jedem Aufruf. Web-Entwuerfe verlangen ebenfalls eine explizite Adresse. Fehlende oder ungueltige Adressen werden vor dem Versand abgelehnt, auch im Testmodus. Eine leere MAIL_ALLOWED_TO erlaubt gueltige dynamische Empfaenger fuer authentifizierte Aufrufe. Eine gesetzte Liste beschraenkt die Empfaenger weiterhin.

Start und Healthcheck versenden keine E-Mail. DRY_RUN=true bleibt unveraendert. Das externe Docker-Netzwerk bleibt highfishNetwork. Fuer die Python-Aenderung muss das Container-Image neu gebaut und anschliessend aktualisiert werden; eine reine Compose-Aenderung reicht nicht.

Der bisherige Telegram-Befehl /mail hat kein Empfaengerfeld. Ohne explizite Adresse wird sein Entwurf abgelehnt; er verwendet MAIL_TO nicht mehr. Fuer dynamischen Versand vorerst MCP oder Web mit explizitem to verwenden.
