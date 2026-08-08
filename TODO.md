# TrainingsPlanner – TODO-Liste

## Erledigt

### Google-Login (Multi-User)
- [x] **Google OAuth 2.0 / OpenID Connect implementiert**: Benutzer können sich mit ihrem Google-Konto anmelden. Der Server verifiziert das ID-Token und erstellt bei Erstanmeldung automatisch einen neuen User-Datensatz.
- [x] **Session-Verwaltung per JWT-Cookie**: Nach dem Login wird ein HttpOnly-Cookie gesetzt, das die Session für 7 Tage gültig hält.
- [x] **Alle Daten pro Benutzer getrennt**: Events, Aktivitäten, Mahlzeiten und Strava-Verbindungen sind jeweils einem Benutzer (user_id) zugeordnet.
- [x] **Login-Screen im Frontend**: Nicht angemeldete Benutzer sehen einen Login-Screen mit "Mit Google anmelden"-Button.
- [x] **Logout-Funktion**: Benutzer können sich über einen "Abmelden"-Button in der Toolbar abmelden.
- [x] **Strava pro Benutzer**: Jeder Benutzer verbindet sein eigenes Strava-Konto. Die Tokens werden als ConnectedAccount in der Datenbank gespeichert (nicht mehr in einer globalen JSON-Datei).

## Offene Punkte

### Strava-Synchronisation
- [ ] **Anzahl der synchronisierten Aktivitäten überdenken**: Aktuell werden nur die letzten 30 Aktivitäten (eine Seite) abgerufen. Es muss entschieden werden, wie viele Aktivitäten heruntergeladen werden sollen (z.B. alle der letzten 30 Tage, alle über mehrere Seiten, oder per_page auf 200 erhöhen).

### Kalender-Ansicht
- [ ] **Zeitbereich der Wochenansicht benutzerdefiniert machen**: Aktuell ist die Wochenansicht auf 09:00–19:00 Uhr beschränkt. Dieser Zeitbereich soll später vom Benutzer konfigurierbar sein.

### Aktivitäten-Liste (Strava-Panel)
- [ ] **Sinn und Umfang der Aktivitäten-Liste klären**: Die Liste unter dem "Strava Synchronisieren"-Button zeigt aktuell die letzten 10 Aktivitäten. Es muss geklärt werden, welchen Zweck diese Liste erfüllen soll und ob 10 Einträge die richtige Anzahl sind.
