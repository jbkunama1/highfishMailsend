# Dokumentationsindex – highfishMailsend

- [README](README.md): aktueller Funktionsumfang, Webverwaltung, Anbieterprofile, Zugänge, Versandregeln und Portainer-Migration.
- [Prüfstatus](IMPLEMENTATION_STATUS.md): tatsächlich ausgeführte Prüfungen und offene Verifikation.
- [Empfänger](RECIPIENTS.md), [Absender](SENDER.md), [Transporte](TRANSPORT.md): ältere Detaildokumentation.
- [Web-Admin](WEB_ADMIN.md), [direkter Zugriff](DIRECT_ACCESS.md), [CyberPanel](CYBERPANEL.md): ältere Einrichtungshinweise.

Bei abweichenden Angaben zu Anbieterprofilen, persistentem Standard oder Migration ist die README maßgeblich. Die Web-Startansicht wird aus `admin.html` unter `/admin/` ausgeliefert; keine zusätzliche `index.html` nötig.

Repository-Änderungen sind kein Deployment. Vollständigen CI-/Image-Build und Zielkonfiguration vor Produktivbetrieb prüfen.
