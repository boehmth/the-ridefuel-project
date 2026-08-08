# RideFuel – Deployment und Cloud-Architektur

> **Lehrdokumentation**
>
> Dieses Dokument beschreibt Schritt für Schritt, wie die Anwendung **RideFuel / TrainingsPlanner** von einer lokal laufenden Python-Anwendung zu einer Anwendung auf **Google Cloud Run** entwickelt wurde.
>
> Ziel ist nicht nur zu dokumentieren, **welche Befehle** ausgeführt wurden, sondern auch zu erklären, **warum** die einzelnen Komponenten benötigt werden und wie sie zusammenhängen.

---

# 1. Ausgangspunkt

RideFuel ist eine Webanwendung mit:

* einem Python-/FastAPI-Backend
* HTML/CSS/JavaScript als Frontend
* SQLite als Datenbank
* Google OAuth für die Anmeldung
* Strava OAuth für Sportdaten
* KI-Diensten für bestimmte Funktionen

Lokal sieht die Anwendung zunächst sehr einfach aus:

```text
┌──────────────────────────────┐
│       eigener Computer       │
│                              │
│  Browser                     │
│      │                       │
│      ▼                       │
│  FastAPI                     │
│      │                       │
│      ▼                       │
│  SQLite                      │
│  trainingsplanner.db         │
└──────────────────────────────┘
```

Das funktioniert für Entwicklung und Tests hervorragend.

Für einen öffentlich erreichbaren Dienst entstehen aber neue Anforderungen:

* Die Anwendung soll über HTTPS erreichbar sein.
* Der Server soll nicht dauerhaft selbst betrieben werden müssen.
* Docker soll die Anwendung reproduzierbar verpacken.
* Secrets sollen nicht im Quellcode liegen.
* Daten müssen Neustarts überleben.
* Mehrere Benutzer müssen voneinander getrennt sein.
* OAuth-Logins müssen korrekt funktionieren.

Damit beginnt die Cloud-Architektur.

---

# 2. Grundentscheidung: Container statt klassischer Server

Die Anwendung wird nicht direkt auf einer virtuellen Maschine installiert.

Stattdessen wird sie als Docker-Container verpackt.

```text
Quellcode
   │
   ▼
Dockerfile
   │
   ▼
Docker Image
   │
   ▼
Container
   │
   ▼
Cloud Run
```

## Warum Docker?

Ein Docker-Image beschreibt die Laufzeitumgebung der Anwendung:

* Python-Version
* installierte Python-Pakete
* Anwendungscode
* Startbefehl

Dadurch entsteht ein reproduzierbares Paket.

Statt zu sagen:

> „Installiere Python 3.12, diese 20 Bibliotheken und konfiguriere alles so ...“

sagen wir:

> „Starte diesen Container.“

Das ist ein wesentlicher Grund, warum Container für Cloud-Deployments praktisch sind.

---

# 3. Das erste Hello-World-Deployment

Bevor RideFuel selbst deployt wurde, wurde zunächst ein minimales Docker-Projekt erstellt.

Es bestand aus:

```text
GoogleDockerTest/
├── app.py
├── Dockerfile
└── .dockerignore
```

Das Ziel war bewusst klein:

> Funktioniert Docker lokal?

und danach:

> Können wir dasselbe Image in Google Cloud speichern und über Cloud Run ausführen?

Diese Trennung ist didaktisch wichtig.

Wenn das Hello-World-Projekt funktioniert, wissen wir:

```text
Docker
   ↓
Artifact Registry
   ↓
Cloud Run
```

funktioniert grundsätzlich.

---

# 4. Google Cloud Projekt

Für RideFuel wurde das Projekt:

```text
Projektname:
Gemini Ride Fuel

Project ID:
gen-lang-client-0462444162

Project Number:
885495221381
```

verwendet.

## Project ID vs. Project Number

Google Cloud verwendet zwei verschiedene Identifikatoren.

### Project ID

```text
gen-lang-client-0462444162
```

Das ist der lesbare technische Name des Projekts.

### Project Number

```text
885495221381
```

Das ist eine von Google vergebene numerische ID.

Für viele CLI-Befehle ist die **Project ID** wichtig.

Beispiel:

```bat
gcloud config set project gen-lang-client-0462444162
```

Danach verwendet `gcloud` dieses Projekt standardmäßig.

---

# 5. Google Cloud APIs

Google Cloud besteht aus vielen einzelnen Diensten.

Eine Anwendung kann beispielsweise:

* Container speichern
* Container ausführen
* Dateien speichern
* Logs schreiben
* Benutzerberechtigungen verwalten

Für viele dieser Dienste muss die entsprechende API aktiviert sein.

In unserem Projekt wurden zunächst die benötigten APIs aktiviert.

Teilweise wurden APIs auch automatisch aktiviert, als ein Dienst erstmals verwendet wurde.

Beispielsweise beim ersten Cloud-Run-Deployment:

```text
The following APIs are not enabled:
run.googleapis.com
```

Danach bestätigten wir:

```text
y
```

Google aktivierte die Cloud-Run-API automatisch.

## Lehrpunkt

Eine API-Aktivierung bedeutet nicht:

> „Wir benutzen diese API jetzt.“

Sie bedeutet zunächst:

> „Dieser Google-Cloud-Dienst darf in diesem Projekt verwendet werden.“

---

# 6. Artifact Registry

Ein Docker-Image liegt nicht automatisch irgendwo in Google Cloud.

Wir brauchen ein **Container-Repository**.

Dafür verwenden wir:

**Artifact Registry**

Das Repository wurde erstellt:

```text
Repository:
ridefuel

Format:
DOCKER

Region:
europe-west3
```

Die Region wurde bewusst passend zum geplanten Cloud-Run-Standort gewählt.

```text
europe-west3
      │
      ├── Artifact Registry
      │
      └── Cloud Run
```

Das reduziert unnötige Entfernungen zwischen den Diensten.

---

# 7. Docker-Authentifizierung für Artifact Registry

Damit Docker Images nach Google pushen kann, wurde Docker für die Registry konfiguriert:

```bat
gcloud auth configure-docker europe-west3-docker.pkg.dev
```

Dadurch weiß Docker:

> Wenn du mit `europe-west3-docker.pkg.dev` kommunizierst, verwende die Google-Cloud-Authentifizierung.

---

# 8. Docker Image taggen

Ein lokales Image kann beispielsweise heißen:

```text
ridefuel-hello
```

Für Artifact Registry braucht es einen vollständigen Namen:

```text
europe-west3-docker.pkg.dev/
gen-lang-client-0462444162/
ridefuel/
ridefuel-hello:1.0
```

Die Struktur ist:

```text
REGION-docker.pkg.dev/
    PROJECT_ID/
        REPOSITORY/
            IMAGE:TAG
```

Daher:

```bat
docker tag ridefuel-hello europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0
```

---

# 9. Image nach Google pushen

Danach wurde das Image hochgeladen:

```bat
docker push europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0
```

Google bestätigte unter anderem:

```text
1.0: digest: sha256:...
```

Das Image befindet sich damit in Artifact Registry.

Man kann die Images auflisten:

```bat
gcloud artifacts docker images list ^
  europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel
```

---

# 10. Ein wichtiger Fehler: Project Number statt Project ID

Anfangs wurde versehentlich verwendet:

```text
885495221381
```

statt:

```text
gen-lang-client-0462444162
```

Dadurch entstand beispielsweise:

```text
Permission "artifactregistry.repositories.uploadArtifacts" denied
```

Der Grund war nicht primär ein Docker-Problem.

Der falsche Projektbezeichner führte dazu, dass wir auf ein anderes bzw. nicht passend adressiertes Google-Cloud-Projekt/Repository zeigten.

Die Korrektur war:

```bat
gcloud config set project gen-lang-client-0462444162
```

Danach funktionierte der Push.

## Lehrpunkt

Bei Google Cloud immer unterscheiden:

```text
Project ID      gen-lang-client-0462444162
Project Number  885495221381
```

Für unsere CLI-Befehle verwenden wir grundsätzlich die Project ID.

---

# 11. Cloud Run

**Cloud Run** ist der Dienst, der unser Docker-Image ausführt.

Die Architektur wird:

```text
                         Internet
                            │
                            ▼
                     HTTPS / Browser
                            │
                            ▼
                    ┌───────────────┐
                    │   Cloud Run   │
                    │               │
                    │ RideFuel      │
                    │ Container     │
                    └───────────────┘
                            ▲
                            │
                            │ Docker Image
                            │
                    ┌───────────────┐
                    │    Artifact   │
                    │    Registry   │
                    └───────────────┘
```

Deployment:

```bat
gcloud run deploy ridefuel-hello ^
  --image=europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0 ^
  --region=europe-west3 ^
  --platform=managed ^
  --allow-unauthenticated
```

Cloud Run erzeugte daraufhin eine öffentliche URL:

```text
https://ridefuel-hello-885495221381.europe-west3.run.app
```

---

# 12. Warum `$PORT` wichtig ist

Lokal kann eine Anwendung beispielsweise auf Port `8000` laufen.

Cloud Run bestimmt jedoch den Port, auf dem der Container erreichbar sein muss.

Deshalb verwendet das Produktions-Dockerfile:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Wichtig sind zwei Dinge:

```text
0.0.0.0
```

und:

```text
$PORT
```

`0.0.0.0` bedeutet:

> Lausche nicht nur auf localhost, sondern auf allen Netzwerkschnittstellen des Containers.

`$PORT` bedeutet:

> Verwende den Port, den die Cloud-Plattform vorgibt.

---

# 13. RideFuel wird containerisiert

Die eigentliche Anwendung verwendet:

```text
app/
static/
requirements.txt
```

Das Produktions-Dockerfile basiert auf:

```text
python:3.12-slim
```

Die Anwendung wird als ein Container betrieben.

Das ist möglich, weil FastAPI gleichzeitig die statischen Dateien aus `static/` ausliefert.

```text
┌─────────────────────────────┐
│ RideFuel Container          │
│                             │
│ FastAPI                     │
│    │                        │
│    ├── API                  │
│    │                        │
│    └── static/              │
│          HTML               │
│          CSS                │
│          JavaScript         │
└─────────────────────────────┘
```

Ein separater Frontend-Container ist deshalb momentan nicht notwendig.

---

# 14. SQLite und Cloud Run – das zentrale Problem

Lokal funktioniert:

```text
FastAPI
   │
   ▼
trainingsplanner.db
```

Cloud Run hat jedoch ein anderes Dateisystemmodell.

Das Dateisystem eines Containers ist **nicht dauerhaft**. Wenn die Instanz verschwindet, verschwindet auch die lokal darin liegende SQLite-Datei. Google beschreibt das Cloud-Run-Dateisystem deshalb ausdrücklich als „disposable“. Für dauerhafte Dateien müssen externe Speicher verwendet werden.

Das ist die zentrale Architekturfrage:

> Wo lebt unsere Datenbank, wenn der Container nicht mehr existiert?

---

# 15. Die zunächst diskutierte Lösung: PostgreSQL

Eine klassische Cloud-Architektur wäre:

```text
Cloud Run
    │
    ▼
PostgreSQL / Cloud SQL
```

Das hätte viele Vorteile:

* echte Server-Datenbank
* dauerhafte Speicherung
* mehrere Instanzen möglich
* parallele Zugriffe
* produktionsgeeignet

Für die aktuelle Entwicklungsphase wurde PostgreSQL aber bewusst **nicht** gewählt.

Grund:

> Wir wollen momentan keine zusätzliche dauerhaft laufende Datenbank bezahlen und die Architektur möglichst einfach halten.

---

# 16. Die gewählte Entwicklungs-Lösung: SQLite + Cloud Storage

Statt PostgreSQL verwenden wir zunächst:

```text
SQLite
   +
Google Cloud Storage
```

Die SQLite-Datei wird als Datei in einem GCS-Bucket gespeichert.

```text
              Cloud Run
        ┌──────────────────┐
        │                  │
        │ SQLite           │
        │                  │
        │ trainingsplanner │
        │ .db              │
        │       │          │
        └───────┼──────────┘
                │
                │ Upload / Download
                ▼
        ┌──────────────────┐
        │ Cloud Storage    │
        │                  │
        │ trainingsplanner │
        │ .db              │
        └──────────────────┘
```

Das ist **keine ideale Produktionsdatenbankarchitektur**.

Für unsere Entwicklungs-/Lehrphase ist sie aber sehr praktisch:

* keine PostgreSQL-Instanz
* Daten bleiben erhalten
* SQLite bleibt erhalten
* Architektur ist leicht verständlich
* Cloud Storage ist dauerhaft
* Container dürfen verschwinden

---

# 17. Google Cloud Storage Bucket

Wir haben einen Bucket angelegt:

```text
ridefuel-sqlite-gen-lang-client-0462444162
```

Region:

```text
EUROPE-WEST3
```

Der Bucket wird über:

```text
gs://ridefuel-sqlite-gen-lang-client-0462444162/
```

angesprochen.

Er ist ein dauerhafter Speicher.

Man kann sich einen Bucket vereinfacht wie ein Verzeichnis vorstellen:

```text
Bucket
│
└── trainingsplanner.db
```

Technisch ist GCS allerdings kein normales Dateisystem, sondern ein Objektspeicher.

---

# 18. Service Account

Cloud Run braucht eine Identität, mit der es auf Google-Dienste zugreifen kann.

Dafür wurde ein eigener Service Account erstellt:

```text
ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com
```

Er repräsentiert die RideFuel-Anwendung gegenüber Google Cloud.

Man kann sich das vorstellen als:

```text
RideFuel
   │
   │ „Wer bist du?“
   ▼
Service Account
   │
   │ „Ich bin RideFuel.“
   ▼
IAM
   │
   │ „Was darf RideFuel?“
   ▼
Cloud Storage
```

---

# 19. IAM – Berechtigungen

IAM steht für:

**Identity and Access Management**

IAM beantwortet zwei Fragen:

1. Wer bist du?
2. Was darfst du?

Für unseren Service Account wurde Zugriff auf den SQLite-Bucket gegeben:

```bat
gcloud storage buckets add-iam-policy-binding ^
  gs://ridefuel-sqlite-gen-lang-client-0462444162 ^
  --member="serviceAccount:ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com" ^
  --role="roles/storage.objectAdmin"
```

Damit darf dieser Service Account mit Objekten in diesem Bucket arbeiten.

## Warum kein JSON-Key?

Wir erzeugen bewusst **keine Service-Account-JSON-Datei**.

Cloud Run kennt seine eigene Identität bereits.

Die Anwendung kann deshalb über Google Application Default Credentials auf GCS zugreifen.

Das ist sicherer und einfacher, als einen privaten Schlüssel in eine `.env`-Datei oder ein Docker-Image zu legen.

---

# 20. Service Account für Cloud Run konfigurieren

Danach wurde der Cloud-Run-Service mit diesem Service Account gestartet:

```bat
gcloud run services update ridefuel-hello ^
  --region=europe-west3 ^
  --service-account=ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com
```

Cloud Run erzeugte dabei eine neue Revision:

```text
ridefuel-hello-00003-9g6
```

## Was ist eine Revision?

Eine Revision ist eine konkrete Version eines Cloud-Run-Deployments.

Beispielsweise:

```text
Revision 1
    ↓
Revision 2
    ↓
Revision 3
```

Cloud Run kann den Traffic auf eine bestimmte Revision leiten.

Das ist praktisch für:

* Updates
* Rollbacks
* Tests
* Versionierung

---

# 21. Authentifizierung: Google OAuth

RideFuel verwendet Google OAuth für die Benutzeranmeldung.

Das bedeutet:

```text
Browser
   │
   │ „Ich möchte mich anmelden.“
   ▼
RideFuel
   │
   ▼
Google
   │
   │ Benutzer bestätigt
   ▼
RideFuel
   │
   ▼
Session
```

Die Anwendung speichert nicht das Google-Passwort.

Google authentifiziert den Benutzer und RideFuel erhält eine Identität.

---

# 22. Serverseitige Sessions statt JWT

Während der Entwicklung wurde zunächst ein JWT-basiertes Session-Modell verwendet.

Dabei wurde festgestellt:

> Das Löschen eines Cookies löscht nicht automatisch die Gültigkeit eines JWT.

Ein noch gültiges JWT konnte deshalb theoretisch nach einem Logout weiterverwendet werden.

Für RideFuel wurde deshalb entschieden, JWT als Sessionmechanismus vollständig zu entfernen.

Stattdessen verwenden wir:

```text
Cookie
   │
   ▼
zufällige Session-ID
   │
   ▼
sessions-Tabelle
   │
   ▼
user_id
```

Die Session-ID selbst enthält keine Benutzerinformationen.

---

# 23. Serverseitige Session-Architektur

Vereinfacht:

```text
Browser
   │
   │ Cookie: tp_session = zufällige ID
   ▼
RideFuel
   │
   │ SELECT session
   ▼
sessions
   │
   ├── session_id
   ├── user_id
   ├── expires_at
   └── revoked_at
          │
          ▼
        users
```

Beim Request fragt RideFuel:

> Existiert diese Session und ist sie noch gültig?

Beim Logout wird die Session serverseitig ungültig gemacht.

Damit ist Logout wirklich ein Logout.

---

# 24. Warum das für mehrere Benutzer wichtig ist

Wir wollen:

```text
User A
   │
   ├── Google Account A
   ├── Session A
   ├── Strava Account A
   └── Activities A

User B
   │
   ├── Google Account B
   ├── Session B
   ├── Strava Account B
   └── Activities B
```

Die Benutzer-ID ist dabei der zentrale Bezugspunkt.

Beispiel:

```text
activities
──────────────────────────────
user_id       strava_id
──────────────────────────────
A             123
A             456
B             789
B             999
```

Ein Request von B darf nur:

```sql
WHERE user_id = B
```

sehen.

---

# 25. Strava OAuth

Strava verwendet ebenfalls OAuth.

Der grundsätzliche Ablauf:

```text
RideFuel User
      │
      │ „Mit Strava verbinden“
      ▼
RideFuel
      │
      ▼
Strava
      │
      │ Benutzer autorisiert
      ▼
Strava Callback
      │
      ▼
RideFuel
      │
      ▼
connected_accounts
```

Die Strava Client-ID und das Client-Secret sind **App-Credentials**.

Sie sind nicht der persönliche Strava Access Token eines Benutzers.

---

# 26. Strava Credentials vs. Benutzer-Token

Diese Unterscheidung ist wichtig.

Global:

```text
STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET
```

Sie identifizieren die RideFuel-Anwendung gegenüber Strava.

Pro Benutzer:

```text
access_token
refresh_token
expires_at
provider_user_id
```

Diese Werte gehören zu einem konkreten RideFuel-Benutzer.

```text
users
  │
  └── connected_accounts
          │
          ├── provider = STRAVA
          ├── provider_user_id
          ├── access_token
          └── refresh_token
```

---

# 27. Strava-State

OAuth benötigt außerdem einen `state`-Wert.

Der Zweck:

> Ein Callback von Strava muss dem ursprünglichen Login-/Verbindungsversuch zugeordnet werden können.

Für RideFuel wird der State an die Session bzw. den Benutzer gebunden.

Vereinfacht:

```text
Session B
    │
    ▼
OAuth State B
    │
    ▼
Strava
    │
    ▼
Callback
    │
    ▼
State B
    │
    ▼
Session B / User B
```

Damit soll verhindert werden, dass ein OAuth-Callback von User A versehentlich User B zugeordnet wird.

---

# 28. Ein wichtiger Strava-Testbefund

Bei Tests zeigte sich ein zunächst verdächtiges Verhalten:

> Wenn im Browser bereits ein Strava-Konto angemeldet war, konnte Strava dieses Konto für den OAuth-Flow verwenden.

Das war kein Fehler der RideFuel-Datenbank.

Der Browser bzw. Strava selbst hatte bereits eine aktive Strava-Anmeldung.

Deshalb kann der OAuth-Ablauf vereinfacht so aussehen:

```text
RideFuel
   │
   ▼
Strava
   │
   │ „Du bist bereits als User A angemeldet.“
   │
   ▼
User A wird autorisiert
```

Wenn man sich explizit aus Strava abmeldet oder einen Inkognito-Browser verwendet, kann man einen anderen Strava-Benutzer auswählen.

## Lehrpunkt

OAuth bedeutet nicht:

> „RideFuel entscheidet, welcher Strava-Benutzer verwendet wird.“

Strava entscheidet anhand der dort vorhandenen Anmeldung und Autorisierung, welches Strava-Konto den OAuth-Vorgang bestätigt.

---

# 29. Docker-Produktionsimage

Für RideFuel wurde ein Produktions-Dockerfile erstellt.

Wichtige Eigenschaften:

```text
python:3.12-slim
```

Die Anwendung läuft als nicht-root Benutzer.

Außerdem:

```text
reload=False
```

bzw. kein Entwicklungsmodus.

Der Start erfolgt über:

```text
uvicorn
```

mit:

```text
0.0.0.0:$PORT
```

---

# 30. `.dockerignore`

Bestimmte Dateien dürfen nicht ins Docker-Image gelangen.

Insbesondere:

```text
.env
*.db
google_secret.json
strava_key.txt
.git/
```

Das Prinzip:

```text
Quellcode
   │
   ├── Anwendung ─────────────► Docker Image
   │
   └── Secrets / lokale Daten ─► NICHT ins Image
```

Das ist wichtig, weil ein Docker-Image dauerhaft in einer Registry liegen kann.

---

# 31. Warum Secrets nicht ins Image gehören

Ein Docker-Image kann von mehreren Personen und Systemen verwendet werden.

Wenn beispielsweise:

```text
STRAVA_CLIENT_SECRET=...
```

im Image gespeichert wäre, könnte jeder mit Zugriff auf das Image versuchen, dieses Secret auszulesen.

Deshalb gilt:

```text
Code → Image
Secrets → Secret Manager / Environment / IAM
```

Die konkrete Secret-Manager-Integration ist ein späterer Schritt.

---

# 32. Cloud Run und „Scale to Zero“

Cloud Run ist kein klassischer Server.

Wenn niemand die Anwendung verwendet, kann Cloud Run die Anzahl der Instanzen auf:

```text
0
```

reduzieren.

```text
Traffic
  │
  ├── hoch ──► mehrere Container
  │
  ├── wenig ─► eine Instanz
  │
  └── null ──► null Instanzen
```

Das ist einer der großen Vorteile von Cloud Run.

Wir bezahlen bei normaler request-basierter Abrechnung nicht dafür, dass ein Container einfach dauerhaft untätig herumsteht.

---

# 33. Warum das für SQLite problematisch ist

Stellen wir uns vor:

```text
10:00
User arbeitet
   ↓
Cloud Run
   ↓
SQLite wird verändert
```

Danach:

```text
10:10
niemand arbeitet mehr
```

Cloud Run kann die Instanz beenden.

Dann:

```text
SQLite im Container
       ↓
Container gelöscht
       ↓
SQLite gelöscht
```

Deshalb brauchen wir GCS.

---

# 34. SQLite + GCS Persistenz

Unsere aktuelle Lösung:

```text
                    Cloud Run
                ┌────────────────┐
                │                │
Request ───────►│ FastAPI        │
                │                │
                │ SQLite         │
                │      │         │
                └──────┼─────────┘
                       │
                       │ synchronisieren
                       ▼
                ┌────────────────┐
                │ Google Cloud   │
                │ Storage        │
                │                │
                │ trainings-     │
                │ planner.db     │
                └────────────────┘
```

Beim Start:

```text
GCS
 │
 ▼
SQLite
 │
 ▼
FastAPI
```

Während des Betriebs:

```text
SQLite
 │
 │ Datenänderung
 ▼
dirty
 │
 ▼
periodischer Sync
 │
 ▼
GCS
```

---

# 35. Warum alle 30 Sekunden?

Wir wollen nicht bei jedem SQL-Statement die komplette SQLite-Datei nach GCS übertragen.

Das wäre ineffizient:

```text
INSERT
 ↓
Upload

UPDATE
 ↓
Upload

INSERT
 ↓
Upload
```

Stattdessen:

```text
INSERT
 ↓
dirty = true

UPDATE
 ↓
dirty = true

INSERT
 ↓
dirty = true

       ...

30 Sekunden
 ↓
ein Upload
```

Damit wird die Zahl der Uploads reduziert.

---

# 36. Warum 30 Sekunden keine Garantie sind

Der 30-Sekunden-Timer läuft **nur solange die Cloud-Run-Instanz lebt und tatsächlich Hintergrundverarbeitung durchführen kann**.

Cloud Run kann eine inaktive Instanz herunterfahren. Eine inaktive Instanz wird standardmäßig nicht dauerhaft gehalten; Cloud Run nennt für Idle-Instanzen einen Zeitraum von bis zu 15 Minuten, wobei eine Instanz auch früher beendet werden kann.

Deshalb:

```text
30-Sekunden-Sync
      │
      ├── gut für normale Laufzeit
      │
      └── keine Garantie beim plötzlichen Shutdown
```

Beim Shutdown sendet Cloud Run `SIGTERM` und gibt normalerweise 10 Sekunden für das Aufräumen.

Daher verwenden wir zusätzlich:

```text
SIGTERM
  │
  ▼
letzter Upload-Versuch
```

Dieser ist aber nur **Best Effort**.

---

# 37. Die eigentliche Persistenzgarantie

Die wichtigste Regel lautet:

> Daten sollen möglichst zeitnah nach GCS geschrieben werden, nicht erst beim Shutdown.

Deshalb:

```text
Datenänderung
    │
    ▼
dirty
    │
    ▼
max. ca. 30 Sekunden
    │
    ▼
GCS
```

Damit beträgt das geplante normale Datenverlustfenster ungefähr die Zeit zwischen Datenänderung und erfolgreichem Upload.

Bei einem unerwarteten Absturz kann natürlich mehr verloren gehen.

---

# 38. Aktuelle Gesamtarchitektur

Damit ergibt sich momentan:

```text
                         INTERNET
                            │
                            ▼
                    ┌───────────────┐
                    │   Cloud Run   │
                    │               │
                    │   RideFuel    │
                    │               │
                    │ ┌───────────┐ │
                    │ │  FastAPI  │ │
                    │ └─────┬─────┘ │
                    │       │       │
                    │ ┌─────▼─────┐ │
                    │ │  SQLite   │ │
                    │ └─────┬─────┘ │
                    │       │       │
                    │   Sync Worker │
                    └───────┼───────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │ Cloud Storage   │
                   │                 │
                   │ trainingsplanner│
                   │ .db             │
                   └─────────────────┘

                    Google OAuth
                         │
                         ▼
                      Google

                    Strava OAuth
                         │
                         ▼
                       Strava
```

---

# 39. Die wichtigsten Google-Cloud-Komponenten

| Komponente               | Aufgabe                                                       |
| ------------------------ | ------------------------------------------------------------- |
| **Google Cloud Project** | Container für Ressourcen, APIs, Berechtigungen und Abrechnung |
| **Artifact Registry**    | Speichert Docker Images                                       |
| **Cloud Run**            | Führt den Docker Container aus                                |
| **Cloud Storage**        | Persistiert die SQLite-Datei                                  |
| **IAM**                  | Regelt, wer auf welche Ressourcen zugreifen darf              |
| **Service Account**      | Identität der RideFuel-Anwendung                              |
| **Cloud Logging**        | Logs der Anwendung und Cloud-Dienste                          |
| **Cloud Monitoring**     | Überwachung und Metriken                                      |

---

# 40. Wichtige CLI-Befehle

## Aktuelles Projekt anzeigen

```bat
gcloud config get-value project
```

## Projekte auflisten

```bat
gcloud projects list
```

## Projekt setzen

```bat
gcloud config set project gen-lang-client-0462444162
```

## Artifact-Repository auflisten

```bat
gcloud artifacts repositories list --location=europe-west3
```

## Docker für Artifact Registry konfigurieren

```bat
gcloud auth configure-docker europe-west3-docker.pkg.dev
```

## Docker Image bauen

```bat
docker build -t ridefuel .
```

## Image taggen

```bat
docker tag ridefuel \
  europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel:VERSION
```

Unter Windows `cmd` kann die Zeile entsprechend mit `^` fortgesetzt werden.

## Image pushen

```bat
docker push europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel:VERSION
```

## Images anzeigen

```bat
gcloud artifacts docker images list ^
  europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel
```

## Cloud Run deployen

```bat
gcloud run deploy ridefuel-hello ^
  --image=europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel:VERSION ^
  --region=europe-west3 ^
  --platform=managed ^
  --allow-unauthenticated
```

## Cloud-Run-Service aktualisieren

```bat
gcloud run services update ridefuel-hello ^
  --region=europe-west3 ^
  --service-account=ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com
```

---

# 41. Google Cloud Storage CLI

## Buckets anzeigen

```bat
gcloud storage buckets list --project=gen-lang-client-0462444162
```

## Bucket anzeigen

```bat
gcloud storage ls gs://ridefuel-sqlite-gen-lang-client-0462444162
```

## Bucket-IAM anzeigen

```bat
gcloud storage buckets get-iam-policy ^
  gs://ridefuel-sqlite-gen-lang-client-0462444162
```

## Service Accounts anzeigen

```bat
gcloud iam service-accounts list ^
  --project=gen-lang-client-0462444162
```

---

# 42. Service Account anlegen

Der RideFuel-Service-Account wurde angelegt mit:

```bat
gcloud iam service-accounts create ridefuel-cloud-run ^
  --project=gen-lang-client-0462444162 ^
  --display-name="RideFuel Cloud Run"
```

Dadurch entstand:

```text
ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com
```

---

# 43. Bucket-Berechtigung vergeben

```bat
gcloud storage buckets add-iam-policy-binding ^
  gs://ridefuel-sqlite-gen-lang-client-0462444162 ^
  --member="serviceAccount:ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com" ^
  --role="roles/storage.objectAdmin"
```

---

# 44. Typische Fehler und was sie bedeuten

## Fehler: Project Number statt Project ID

```text
The value of core/project property is set to project number
```

Lösung:

```bat
gcloud config set project gen-lang-client-0462444162
```

---

## Fehler: falscher Docker-Tag

```text
tag does not exist
```

Dann stimmt der lokale Docker-Tag nicht mit dem Push-Ziel überein.

Beispiel:

```text
docker tag
        ↓
docker push
```

müssen exakt denselben vollständigen Image-Namen verwenden.

---

## Fehler: Artifact Registry Permission denied

```text
artifactregistry.repositories.uploadArtifacts denied
```

Typische Ursachen:

* falsches Projekt
* falsches Repository
* fehlende IAM-Berechtigung
* falscher Registry-Hostname

---

## Fehler: Service Account does not exist

```text
Service account ... does not exist
```

Dann wurde versucht, einen noch nicht existierenden Service Account zu verwenden.

Zuerst:

```bat
gcloud iam service-accounts list
```

---

# 45. Warum wir nicht alles sofort automatisieren

Eine mögliche Produktionsarchitektur wäre später:

```text
GitHub
   │
   ▼
Cloud Build / GitHub Actions
   │
   ▼
Docker Build
   │
   ▼
Artifact Registry
   │
   ▼
Cloud Run
   │
   ├── Cloud SQL PostgreSQL
   ├── Secret Manager
   └── weitere Dienste
```

Für die aktuelle Lern- und Entwicklungsphase wäre das unnötig komplex.

Deshalb bauen wir bewusst schrittweise:

```text
1. Docker
   ↓
2. Artifact Registry
   ↓
3. Cloud Run
   ↓
4. IAM / Service Account
   ↓
5. Cloud Storage
   ↓
6. SQLite-Persistenz
   ↓
7. Secrets
   ↓
8. Automatisierung / CI/CD
   ↓
9. später PostgreSQL
```

Jeder Schritt löst ein konkretes Problem.

---

# 46. Aktueller Entwicklungsstand

Zum aktuellen Zeitpunkt ist folgende Infrastruktur vorhanden:

```text
Google Cloud Project
        │
        ├── Artifact Registry
        │       └── ridefuel
        │
        ├── Cloud Run
        │       └── ridefuel-hello
        │
        ├── Cloud Storage
        │       └── ridefuel-sqlite-gen-lang-client-0462444162
        │
        └── IAM
                └── ridefuel-cloud-run
```

Die Anwendung soll nun die SQLite-Persistenz über diesen Storage aufbauen.

---

# 47. Was noch nicht produktionsreif ist

Die aktuelle SQLite/GCS-Lösung ist eine **Entwicklungs- und Lehrlösung**.

Sie hat insbesondere folgende Grenzen:

### 1. SQLite ist keine verteilte Datenbank

Wenn mehrere Cloud-Run-Instanzen gleichzeitig laufen:

```text
Instance A → SQLite A
Instance B → SQLite B
```

können beide unterschiedliche Datenstände haben.

### 2. GCS ist kein Datenbank-Locking-System

Zwei Instanzen könnten theoretisch dieselbe SQLite-Datei überschreiben.

### 3. Upload-Verzögerung

Zwischen Datenänderung und GCS-Synchronisation existiert ein kleines Zeitfenster.

### 4. Cloud Run kann Instanzen jederzeit ersetzen

Daher darf die lokale SQLite-Datei nie als dauerhafter Speicher betrachtet werden.

---

# 48. Spätere Produktionsarchitektur

Für einen echten produktiven Betrieb wäre langfristig sinnvoll:

```text
                         Cloud Run
                            │
                            │
                            ▼
                    ┌───────────────┐
                    │    RideFuel   │
                    └───────┬───────┘
                            │
                            │ SQL
                            ▼
                    ┌───────────────┐
                    │ PostgreSQL    │
                    │ / Cloud SQL   │
                    └───────────────┘

                         Secrets
                            │
                            ▼
                    ┌───────────────┐
                    │ Secret Manager│
                    └───────────────┘
```

Dann liegt die Datenbank nicht mehr als Datei im Container.

Die SQLite/GCS-Lösung ist deshalb ein bewusst gewählter **Zwischenschritt**:

```text
lokale SQLite
      ↓
SQLite + GCS
      ↓
PostgreSQL
```

---

# 49. Der wichtigste Architekturgedanke

Die Cloud ersetzt nicht einfach unseren Computer.

Stattdessen werden einzelne Verantwortlichkeiten auf verschiedene Dienste verteilt:

```text
Docker
  = Verpackung

Artifact Registry
  = Aufbewahrung des Pakets

Cloud Run
  = Ausführung des Pakets

Cloud Storage
  = dauerhafte Dateien

IAM
  = Berechtigungen

Service Account
  = Identität der Anwendung

Google OAuth
  = Identität des Benutzers

Strava OAuth
  = Verbindung zum Strava-Konto

SQLite
  = aktuelle Datenhaltung

PostgreSQL
  = spätere produktionsfähige Datenhaltung
```

Das ist der zentrale Gedanke hinter der gesamten Architektur.

---

# 50. Rekonstruktionsanleitung

Wenn die Infrastruktur später komplett neu aufgebaut werden müsste, sollte die grobe Reihenfolge sein:

```text
Google Cloud Projekt
        │
        ▼
APIs aktivieren
        │
        ▼
Artifact Registry
        │
        ▼
Docker konfigurieren
        │
        ▼
Image bauen
        │
        ▼
Image pushen
        │
        ▼
Cloud Run deployen
        │
        ▼
Service Account anlegen
        │
        ▼
GCS Bucket anlegen
        │
        ▼
IAM Berechtigung vergeben
        │
        ▼
Cloud Run Service Account setzen
        │
        ▼
GCS SQLite-Persistenz konfigurieren
        │
        ▼
OAuth Redirect URLs anpassen
        │
        ▼
Secrets konfigurieren
        │
        ▼
End-to-End-Test
```

Damit ist die Umgebung nicht mehr nur eine Sammlung von Befehlen, sondern eine nachvollziehbare Architektur.

---

# 51. Zusammenfassung

RideFuel hat sich von einer lokalen Anwendung:

```text
Python
 +
SQLite
```

zu einer Cloud-Anwendung entwickelt:

```text
                    Internet
                       │
                       ▼
                  Cloud Run
                       │
                    Docker
                       │
              ┌────────┴────────┐
              │                 │
           FastAPI            SQLite
                                │
                                ▼
                         Cloud Storage

Google OAuth ───────────────► Benutzer
Strava OAuth ───────────────► Strava-Konto
IAM ────────────────────────► Berechtigungen
Artifact Registry ──────────► Docker Images
```

Die wichtigste technische Erkenntnis dabei lautet:

> **Cloud Run ist für die Ausführung zuständig, nicht für die dauerhafte Speicherung unserer Dateien.**

Der Container darf verschwinden.

Die Daten müssen deshalb außerhalb des Containers liegen.

Für die aktuelle Entwicklungsphase übernimmt diese Aufgabe Google Cloud Storage.

Für einen späteren produktiven Betrieb soll diese Aufgabe eine echte relationale Datenbank wie PostgreSQL übernehmen.

# 10. End-to-End-Test der SQLite-Persistenz mit Google Cloud Storage

Nachdem die GCS-Persistenz implementiert wurde, wurde sie nicht nur mit Unit-Tests, sondern auch als vollständiger Laufzeit-Test überprüft.

Ziel des Tests war die Beantwortung einer zentralen Frage:

> **Bleiben die Daten erhalten, wenn ein Docker-Container beendet und anschließend ein komplett neuer Container gestartet wird?**

Das ist für unsere Architektur entscheidend, weil SQLite normalerweise nur eine Datei im Container ist. Ein Cloud-Run-Container kann jedoch jederzeit beendet und später durch eine neue Instanz ersetzt werden. Deshalb darf die SQLite-Datei nicht die einzige Datenquelle sein.

---

## 10.1 Grundidee des Tests

Der Test simuliert einen Neustart bzw. Austausch einer Cloud-Run-Instanz.

Der Ablauf:

```text
┌───────────────────────┐
│ Docker-Container      │
│                       │
│ SQLite                │
│ trainingsplanner.db   │
└───────────┬───────────┘
            │
            │ Upload
            ▼
┌───────────────────────────────┐
│ Google Cloud Storage          │
│                               │
│ trainingsplanner.db           │
└───────────────────────────────┘
            │
            │ Download
            ▼
┌───────────────────────┐
│ Neuer Docker-Container│
│                       │
│ SQLite                │
│ trainingsplanner.db   │
└───────────────────────┘
```

Wenn die Testdaten nach diesem Vorgang noch vorhanden sind, ist bewiesen, dass die SQLite-Datenbank erfolgreich über GCS zwischen Container-Instanzen persistiert wird.

---

## 10.2 Wichtige Unterscheidung: lokal vs. Cloud Run

Die Anwendung läuft während dieses Tests **lokal auf dem Windows-Rechner**.

Das bedeutet aber nicht, dass auch die Persistenz lokal erfolgt.

Tatsächlich sieht der Datenfluss so aus:

```text
Windows-PC
    │
    │
    ▼
┌─────────────────────────────┐
│ Docker-Container            │
│                             │
│ FastAPI                     │
│ SQLite                      │
│ app/storage.py              │
└──────────────┬──────────────┘
               │
               │ HTTPS
               ▼
┌─────────────────────────────┐
│ Google Cloud Storage        │
│                             │
│ ridefuel-sqlite-...         │
│   └── trainingsplanner.db   │
└─────────────────────────────┘
```

Der lokale Docker-Container greift also bereits auf den **echten Google-Cloud-Storage-Bucket** zu.

Das ist ein wichtiger Architekturtest: Wir testen damit nicht nur SQLite oder Docker, sondern den tatsächlichen Zusammenschluss von

* Docker
* FastAPI
* SQLite
* Google Cloud Storage
* Google-Authentifizierung
* unserer Storage-Abstraktion.

---

## 10.3 GCS-Persistenz für den Test aktivieren

In der normalen lokalen `.env` war GCS zunächst deaktiviert:

```text
GCS_SQLITE_ENABLED=false
```

Für den Persistenztest wurde GCS explizit beim Start des Containers aktiviert.

Zusätzlich wurde das Google-Cloud-Projekt explizit angegeben:

```text
GOOGLE_CLOUD_PROJECT=gen-lang-client-0462444162
```

Das war notwendig, weil `google.cloud.storage.Client()` ansonsten im Container das Projekt nicht automatisch bestimmen konnte.

Der relevante Fehler war zunächst:

```text
OSError: Project was not passed and could not be determined from the environment.
```

Die Lösung war:

```text
-e GOOGLE_CLOUD_PROJECT=gen-lang-client-0462444162
```

---

## 10.4 Google-Credentials in den lokalen Container geben

Auf dem Entwicklungsrechner existieren Google Application Default Credentials.

Diese Datei wurde schreibgeschützt in den Container eingebunden:

```text
-v "%APPDATA%\gcloud\application_default_credentials.json:/tmp/gcloud/application_default_credentials.json:ro"
```

Anschließend wurde dem Google-Client mitgeteilt, wo sich die Credentials befinden:

```text
-e GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcloud/application_default_credentials.json
```

Damit kann der **lokale Docker-Container** auf Google Cloud zugreifen.

Das ist bewusst nur eine Lösung für die lokale Entwicklung.

In Cloud Run wird keine Credential-Datei in den Container kopiert. Dort verwendet der Container die Identität des ihm zugewiesenen **Service Accounts**.

Damit ergeben sich zwei unterschiedliche Authentifizierungswege:

```text
Lokale Entwicklung
──────────────────

Docker
   │
   │ Application Default Credentials
   ▼
Google Cloud Storage


Cloud Run
─────────

Docker
   │
   │ Cloud-Run-Service-Account
   ▼
Google Cloud Storage
```

Die Anwendung selbst muss diese Unterschiede nicht kennen. `app/storage.py` verwendet einfach die Google-Cloud-Storage-API.

---

## 10.5 Container mit GCS-Persistenz starten

Der Container wurde mit folgendem Befehl gestartet:

```cmd
docker run --name ridefuel-test ^
  --env-file .env ^
  -e GCS_SQLITE_ENABLED=true ^
  -e GCS_SQLITE_BUCKET=ridefuel-sqlite-gen-lang-client-0462444162 ^
  -e GCS_SQLITE_OBJECT=trainingsplanner.db ^
  -e GCS_SQLITE_SYNC_INTERVAL_SECONDS=30 ^
  -e GOOGLE_CLOUD_PROJECT=gen-lang-client-0462444162 ^
  -e PORT=8000 ^
  -p 8000:8000 ^
  -v "%APPDATA%\gcloud\application_default_credentials.json:/tmp/gcloud/application_default_credentials.json:ro" ^
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcloud/application_default_credentials.json ^
  ridefuel
```

Die wichtigsten Parameter:

| Parameter                               | Bedeutung                                    |
| --------------------------------------- | -------------------------------------------- |
| `GCS_SQLITE_ENABLED=true`               | Aktiviert die GCS-Persistenz                 |
| `GCS_SQLITE_BUCKET=...`                 | Name des GCS-Buckets                         |
| `GCS_SQLITE_OBJECT=trainingsplanner.db` | Name der SQLite-Datei im Bucket              |
| `GCS_SQLITE_SYNC_INTERVAL_SECONDS=30`   | Maximales reguläres Sync-Intervall           |
| `GOOGLE_CLOUD_PROJECT=...`              | Google-Cloud-Projekt                         |
| `GOOGLE_APPLICATION_CREDENTIALS=...`    | Credentials innerhalb des Containers         |
| `-p 8000:8000`                          | Macht die FastAPI-Anwendung lokal erreichbar |

Nach dem Start war die Anwendung unter

```text
http://localhost:8000
```

erreichbar.

---

## 10.6 Testdaten erzeugen

Nach dem Start wurde die Anwendung geöffnet und eine eindeutig erkennbare Test-Mahlzeit angelegt.

Beispielsweise:

```text
Test-Persistenz 08.08.2026
```

Damit wurde bewusst eine echte Datenänderung in der SQLite-Datenbank erzeugt.

Der interne Ablauf ist:

```text
Benutzer legt Mahlzeit an
          │
          ▼
FastAPI
          │
          ▼
SQLite INSERT
          │
          ▼
conn.total_changes erkennt Änderung
          │
          ▼
Database Dirty Flag = TRUE
```

Der Hintergrund-Worker erkennt die Änderung anschließend und synchronisiert die Datenbank nach dem konfigurierten Intervall nach GCS.

---

## 10.7 Kontrolle des GCS-Objekts

Mit folgendem Befehl kann überprüft werden, ob die SQLite-Datei tatsächlich im Bucket liegt:

```cmd
gcloud storage ls -l gs://ridefuel-sqlite-gen-lang-client-0462444162/trainingsplanner.db
```

Zusätzliche Informationen zum Objekt können mit folgendem Befehl angezeigt werden:

```cmd
gcloud storage objects describe gs://ridefuel-sqlite-gen-lang-client-0462444162/trainingsplanner.db
```

Damit lässt sich beispielsweise überprüfen, wann die Datei zuletzt aktualisiert wurde.

---

## 10.8 Bedeutung des 30-Sekunden-Intervalls

Die Einstellung

```text
GCS_SQLITE_SYNC_INTERVAL_SECONDS=30
```

bedeutet **nicht**, dass Cloud Run alle 30 Sekunden irgendetwas macht.

Die 30 Sekunden sind ausschließlich die Frequenz unseres eigenen Hintergrund-Workers:

```text
Container läuft
      │
      ▼
Worker wartet
      │
      ▼
30 Sekunden
      │
      ▼
Ist DB dirty?
      │
   ┌──┴───┐
   │      │
  Nein   Ja
   │      │
   │      ▼
   │    Upload
   │      │
   └──────┘
```

Wichtig ist außerdem:

> Der Worker läuft nur, solange die betreffende Container-Instanz tatsächlich läuft.

Bei einem vollständig heruntergefahrenen Container läuft kein Worker weiter.

Zusätzlich gibt es deshalb einen **Best-Effort-Sync beim Shutdown**, sodass eine letzte Datenänderung möglichst noch nach GCS geschrieben wird.

---

## 10.9 Container beenden

Nachdem die Testdaten erfolgreich gespeichert und synchronisiert wurden, wurde der Container beendet.

```text
CTRL+C
```

Beim Shutdown versucht die Anwendung nochmals, eine eventuell noch nicht synchronisierte Datenbank nach GCS hochzuladen.

---

## 10.10 Alten Container vollständig löschen

Um wirklich einen neuen Container zu simulieren, wurde anschließend der alte Container entfernt:

```cmd
docker rm ridefuel-test
```

Das ist wichtig.

Ein bloßes Neustarten desselben Containers wäre kein vollständiger Persistenztest, weil sich möglicherweise noch lokale Containerdaten erhalten könnten.

Mit dem Entfernen des Containers simulieren wir:

> Die bisherige Cloud-Run-Instanz existiert nicht mehr.

---

## 10.11 Neuen Container starten

Anschließend wurde mit demselben `docker run`-Befehl ein komplett neuer Container erzeugt.

Beim Start passiert nun etwas Entscheidendes.

Da im GCS-Bucket bereits

```text
trainingsplanner.db
```

existiert, lädt `app/storage.py` diese Datei zunächst herunter.

Der Startup-Ablauf lautet:

```text
Neuer Container
      │
      ▼
GCS SQLite-Datei vorhanden?
      │
      ├── Nein ──► neue lokale DB
      │
      └── Ja
           │
           ▼
     DB herunterladen
           │
           ▼
     lokale SQLite-Datei
           │
           ▼
        init_db()
           │
           ▼
     FastAPI startet
```

Ein besonders wichtiger Sicherheitsaspekt der Implementierung:

> Wenn eine Datenbank in GCS existiert, der Download aber fehlschlägt, startet die Anwendung nicht einfach mit einer leeren SQLite-Datenbank.

Dadurch wird verhindert, dass eine bestehende Datenbank versehentlich durch eine neue leere Datenbank ersetzt wird.

---

## 10.12 Ergebnis des End-to-End-Tests

Nach dem Start des **neuen** Containers wurde die Anwendung erneut geöffnet:

```text
http://localhost:8000
```

Die zuvor angelegte Test-Mahlzeit war weiterhin vorhanden.

Damit wurde der komplette Persistenzweg erfolgreich nachgewiesen:

```text
             Container A
                  │
                  │
             SQLite INSERT
                  │
                  ▼
             Dirty Flag
                  │
                  ▼
                  │ Upload
                  ▼
        ┌──────────────────┐
        │ Google Cloud     │
        │ Storage          │
        │                  │
        │ trainingsplanner │
        │ .db              │
        └────────┬─────────┘
                 │
                 │ Download
                 ▼
             Container B
                 │
                 ▼
              SQLite
                 │
                 ▼
        Test-Mahlzeit
        noch vorhanden
```

### Ergebnis

**Der Test war erfolgreich.**

Die Daten haben einen vollständigen Container-Lebenszyklus überlebt:

```text
Container A
    │
    ├── Daten schreiben
    │
    ├── SQLite ändern
    │
    ├── nach GCS synchronisieren
    │
    ▼
Container A wird gelöscht
    │
    ▼
Container B wird erstellt
    │
    ├── SQLite aus GCS herunterladen
    │
    ▼
Daten wieder vorhanden
```

Damit funktioniert die geplante SQLite-Persistenz über Google Cloud Storage sowohl für lokale Docker-Container als auch als Grundlage für den späteren Betrieb auf Cloud Run.

---

## 10.13 Warum diese Architektur für die aktuelle Entwicklungsphase sinnvoll ist

Für die aktuelle Phase wird bewusst **keine PostgreSQL-Datenbank** verwendet.

Stattdessen bleibt SQLite die eigentliche Datenbank:

```text
RideFuel
   │
   ▼
SQLite
   │
   │ Persistenz
   ▼
Google Cloud Storage
```

Das hat mehrere Vorteile:

* keine laufenden PostgreSQL-Kosten
* kein zusätzlicher Datenbankdienst
* bestehender SQLite-Code kann weiterverwendet werden
* Docker-Container bleibt einfach
* Cloud Run kann weiterhin verwendet werden
* Daten bleiben über Container-Neustarts hinweg erhalten

Die Architektur ist allerdings **nicht als endgültige Produktionsarchitektur gedacht**.

SQLite + GCS ist eine pragmatische Übergangslösung für die Entwicklungs- und Lehrphase.

Bei einem späteren echten Mehrbenutzerbetrieb wäre eine relationale Datenbank wie PostgreSQL die sauberere Lösung, weil Datenbankzugriffe dann nicht über das Kopieren einer kompletten SQLite-Datei zwischen Container und Storage synchronisiert werden müssen.

---

## 10.14 Aktuelle Architektur im Überblick

```text
                         Benutzer
                            │
                            ▼
                    ┌───────────────┐
                    │   Cloud Run   │
                    │               │
                    │  FastAPI      │
                    │      │        │
                    │      ▼        │
                    │    SQLite     │
                    │      │        │
                    │      │ Sync   │
                    └──────┼────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Google Cloud    │
                  │ Storage         │
                  │                 │
                  │ SQLite-Datei    │
                  └─────────────────┘
```

Für lokale Entwicklung sieht die gleiche Architektur so aus:

```text
                      Windows-PC
                          │
                          ▼
                   Docker Container
                          │
                    ┌─────┴─────┐
                    │           │
                 FastAPI      SQLite
                    │           │
                    └─────┬─────┘
                          │
                          │ HTTPS
                          ▼
                  Google Cloud Storage
```

**Entscheidend:** Die Anwendung muss nicht wissen, ob sie lokal oder auf Cloud Run läuft. Sie verwendet dieselbe `storage.py`-Abstraktion. Lediglich die Art, wie der Container gegenüber Google Cloud authentifiziert wird, unterscheidet sich.

Damit ist die aktuelle Architektur sowohl **rekonstruierbar** als auch als Lehrbeispiel geeignet: Man kann nachvollziehen, wie aus einer zunächst rein lokalen SQLite-Anwendung Schritt für Schritt eine Docker-basierte Cloud-Anwendung mit persistenter Speicherung entsteht.

# 11. Cloud Run Deployment des persistierenden Containers

Nachdem die SQLite-Persistenz mit Google Cloud Storage lokal erfolgreich getestet wurde, kann derselbe Container auf **Google Cloud Run** betrieben werden.

Das ist ein wichtiger nächster Schritt: Bis hierhin haben wir bewiesen, dass

1. die Anwendung als Docker-Container funktioniert,
2. SQLite innerhalb des Containers funktioniert,
3. die SQLite-Datei nach Google Cloud Storage synchronisiert wird,
4. ein neuer Container die SQLite-Datei wieder aus GCS laden kann.

Nun soll genau dieser Mechanismus unter echten Cloud-Run-Bedingungen funktionieren.

---

## 11.1 Zielarchitektur

Der lokale Test sah so aus:

```text
Windows-PC
    │
    ▼
Docker Container
    │
    ├── FastAPI
    ├── SQLite
    └── storage.py
           │
           │ HTTPS
           ▼
    Google Cloud Storage
```

Beim produktionsnahen Betrieb kommt Cloud Run dazwischen:

```text
                         Internet
                            │
                            ▼
                    ┌───────────────┐
                    │   Cloud Run   │
                    │               │
                    │ RideFuel      │
                    │ Docker        │
                    │               │
                    │ FastAPI       │
                    │ SQLite        │
                    │ storage.py    │
                    └───────┬───────┘
                            │
                            │ Google Cloud API
                            ▼
                  ┌─────────────────────┐
                  │ Google Cloud        │
                  │ Storage             │
                  │                     │
                  │ trainingsplanner.db │
                  └─────────────────────┘
```

Der entscheidende Punkt ist:

> **Cloud Run speichert die SQLite-Datei nicht dauerhaft. Google Cloud Storage ist die dauerhafte Kopie.**

Cloud Run darf einen Container jederzeit beenden und später eine neue Instanz starten. Deshalb muss die Anwendung beim Start die Datenbank aus GCS laden.

---

## 11.2 Voraussetzungen

Für das Deployment benötigen wir:

* ein Google-Cloud-Projekt
* ein Artifact-Registry-Repository
* einen GCS-Bucket
* einen Cloud-Run-Service
* einen Service Account mit Zugriff auf den GCS-Bucket
* ein Docker-Image der Anwendung

In unserem Projekt wurden bereits folgende Ressourcen eingerichtet:

```text
Projekt-ID:
gen-lang-client-0462444162

Projekt-Nummer:
885495221381

Region:
europe-west3

Artifact Registry:
ridefuel

GCS Bucket:
ridefuel-sqlite-gen-lang-client-0462444162
```

---

## 11.3 Docker-Image bauen

Zunächst wird aus dem aktuellen Quellcode ein Docker-Image erstellt:

```cmd
docker build -t ridefuel .
```

Das Dockerfile enthält unter anderem:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Die Verwendung von `${PORT}` ist für Cloud Run wichtig.

Cloud Run teilt dem Container über die Umgebungsvariable `PORT` mit, auf welchem Port die Anwendung Verbindungen entgegennehmen soll.

Lokal verwenden wir beispielsweise:

```text
PORT=8000
```

Cloud Run verwendet normalerweise:

```text
PORT=8080
```

Deshalb darf die Anwendung den Port nicht dauerhaft auf `8000` fest verdrahten.

---

## 11.4 Docker-Image in Artifact Registry speichern

Google Cloud Run benötigt ein Container-Image. Dafür verwenden wir **Artifact Registry**.

Das Repository wurde zuvor mit dem Namen

```text
ridefuel
```

in der Region

```text
europe-west3
```

angelegt.

Das Image erhält deshalb folgenden vollständigen Namen:

```text
europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0
```

Vor dem Push muss das lokale Image entsprechend getaggt werden:

```cmd
docker tag ridefuel-hello ^
  europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0
```

Anschließend wird es nach Artifact Registry übertragen:

```cmd
docker push ^
  europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0
```

Die erfolgreiche Ausgabe enthält unter anderem einen Digest:

```text
digest: sha256:...
```

Dieser Digest identifiziert exakt die Version des Images.

---

## 11.5 Überprüfung des Images

Mit folgendem Befehl kann kontrolliert werden, ob das Image tatsächlich in Artifact Registry angekommen ist:

```cmd
gcloud artifacts docker images list ^
  europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel
```

Das Ergebnis zeigt die vorhandenen Images und deren Digests.

Damit haben wir nun folgende Kette:

```text
Quellcode
   │
   ▼
Docker Build
   │
   ▼
lokales Docker Image
   │
   │ docker push
   ▼
Artifact Registry
   │
   ▼
Cloud Run
```

---

## 11.6 Google Cloud Storage Bucket

Die SQLite-Datenbank wird nicht in Artifact Registry gespeichert.

Artifact Registry und Cloud Storage haben unterschiedliche Aufgaben:

```text
Artifact Registry
─────────────────
Speichert:
Docker Images

Beispiel:
ridefuel-hello:1.0


Cloud Storage
─────────────
Speichert:
Anwendungsdaten

Beispiel:
trainingsplanner.db
```

Unser Bucket lautet:

```text
ridefuel-sqlite-gen-lang-client-0462444162
```

Die SQLite-Datei liegt darin als:

```text
trainingsplanner.db
```

---

## 11.7 Warum Cloud Run einen Service Account benötigt

Ein Container auf Cloud Run soll auf den GCS-Bucket zugreifen können.

Dafür benötigt er eine Identität.

Diese Identität wird durch einen **Service Account** bereitgestellt.

Das Prinzip ist:

```text
Cloud Run Container
        │
        │ "Wer bin ich?"
        ▼
Service Account
        │
        │ "Was darf ich?"
        ▼
IAM-Berechtigungen
        │
        ▼
Google Cloud Storage
```

Der Service Account ersetzt dabei die lokalen Application-Default-Credentials.

Lokal hatten wir:

```text
GOOGLE_APPLICATION_CREDENTIALS
        │
        ▼
credentials.json
```

Auf Cloud Run wird dagegen die Identität der Cloud-Run-Instanz verwendet.

Das ist sicherer, weil keine Credential-Datei in das Docker-Image kopiert werden muss.

---

## 11.8 Service Account anlegen

Falls noch kein eigener Service Account vorhanden ist, kann dieser mit folgendem Befehl erstellt werden:

```cmd
gcloud iam service-accounts create ridefuel-cloud-run ^
  --project=gen-lang-client-0462444162 ^
  --display-name="RideFuel Cloud Run"
```

Danach sollte er beispielsweise unter folgender Adresse erreichbar sein:

```text
ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com
```

Vor der Verwendung sollte überprüft werden, ob der Service Account tatsächlich existiert:

```cmd
gcloud iam service-accounts list ^
  --project=gen-lang-client-0462444162
```

---

## 11.9 Zugriff auf den GCS-Bucket erlauben

Der Cloud-Run-Service-Account benötigt Zugriff auf das SQLite-Objekt.

Dafür kann beispielsweise die Rolle

```text
roles/storage.objectAdmin
```

vergeben werden:

```cmd
gcloud storage buckets add-iam-policy-binding ^
  gs://ridefuel-sqlite-gen-lang-client-0462444162 ^
  --member="serviceAccount:ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com" ^
  --role="roles/storage.objectAdmin"
```

### Was bedeutet diese Berechtigung?

`storage.objectAdmin` erlaubt dem Service Account unter anderem:

* Objekte lesen
* Objekte schreiben
* Objekte aktualisieren
* Objekte löschen

Für unsere aktuelle Architektur ist das notwendig, weil RideFuel sowohl

```text
GCS → Container
```

als auch

```text
Container → GCS
```

benötigt.

Für einen späteren Produktivbetrieb könnte die Berechtigung noch stärker eingeschränkt werden.

---

## 11.10 Service Account für Cloud Run konfigurieren

Der Cloud-Run-Service wird mit dem entsprechenden Service Account betrieben:

```cmd
gcloud run services update ridefuel-hello ^
  --region=europe-west3 ^
  --service-account=ridefuel-cloud-run@gen-lang-client-0462444162.iam.gserviceaccount.com
```

Dadurch erhalten neue Cloud-Run-Instanzen diese Identität.

Der Zugriff auf GCS funktioniert anschließend ohne Credential-Datei im Container.

---

## 11.11 Cloud Run Deployment

Das eigentliche Deployment erfolgt mit:

```cmd
gcloud run deploy ridefuel-hello ^
  --image=europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0 ^
  --region=europe-west3 ^
  --platform=managed ^
  --allow-unauthenticated
```

Die Option

```text
--allow-unauthenticated
```

bedeutet, dass der Cloud-Run-Service öffentlich erreichbar ist.

Das ist für RideFuel derzeit sinnvoll, weil die Anwendung selbst den Benutzer über Google OAuth authentifiziert.

Wichtig ist die Unterscheidung:

```text
Cloud Run Zugriff
        │
        ▼
öffentlich erreichbar
        │
        ▼
RideFuel
        │
        ▼
Google Login
        │
        ▼
authentifizierter RideFuel-Benutzer
```

„Öffentlich erreichbar“ bedeutet also nicht automatisch „ohne Login nutzbar“.

---

## 11.12 GCS-Konfiguration in Cloud Run

Die Anwendung benötigt folgende Umgebungsvariablen:

```text
GCS_SQLITE_ENABLED=true
GCS_SQLITE_BUCKET=ridefuel-sqlite-gen-lang-client-0462444162
GCS_SQLITE_OBJECT=trainingsplanner.db
GCS_SQLITE_SYNC_INTERVAL_SECONDS=30
```

Diese können beim Deployment angegeben werden:

```cmd
gcloud run deploy ridefuel-hello ^
  --image=europe-west3-docker.pkg.dev/gen-lang-client-0462444162/ridefuel/ridefuel-hello:1.0 ^
  --region=europe-west3 ^
  --platform=managed ^
  --allow-unauthenticated ^
  --set-env-vars="GCS_SQLITE_ENABLED=true,GCS_SQLITE_BUCKET=ridefuel-sqlite-gen-lang-client-0462444162,GCS_SQLITE_OBJECT=trainingsplanner.db,GCS_SQLITE_SYNC_INTERVAL_SECONDS=30"
```

Das Projekt wird dabei über die Cloud-Run-Konfiguration bzw. das Deployment bestimmt.

Die lokalen Credentials werden **nicht** übernommen.

Insbesondere wird **nicht** benötigt:

```text
GOOGLE_APPLICATION_CREDENTIALS
```

Der Container verwendet stattdessen automatisch den Cloud-Run-Service-Account.

---

## 11.13 Ablauf beim Start einer Cloud-Run-Instanz

Wenn Cloud Run eine neue Instanz startet, sieht der Ablauf vereinfacht so aus:

```text
HTTP Request
     │
     ▼
Cloud Run
     │
     │ neue Instanz notwendig
     ▼
Docker Container starten
     │
     ▼
FastAPI Lifespan
     │
     ▼
GCS-Datei prüfen
     │
     ├── vorhanden
     │      │
     │      ▼
     │   Download
     │      │
     │      ▼
     │   SQLite
     │
     └── nicht vorhanden
            │
            ▼
        neue SQLite DB
            │
            ▼
        init_db()
            │
            ▼
        Server bereit
```

Dadurch kann eine neue Cloud-Run-Instanz auf dieselben Daten zugreifen wie die vorherige Instanz.

---

## 11.14 Ablauf bei einer Datenänderung

Wenn ein Benutzer beispielsweise eine Mahlzeit anlegt:

```text
Benutzer
   │
   ▼
FastAPI
   │
   ▼
SQLite INSERT
   │
   ▼
Dirty Flag
   │
   ▼
Sync Worker
   │
   ▼
Google Cloud Storage
```

Die Daten werden also zunächst lokal in der SQLite-Datenbank der jeweiligen Container-Instanz geschrieben.

Anschließend wird die Datenbankdatei nach GCS synchronisiert.

---

## 11.15 Was passiert beim Herunterfahren einer Instanz?

Cloud Run kann eine Instanz beenden, wenn sie nicht mehr benötigt wird.

Deshalb darf die Anwendung nicht davon ausgehen:

> „Meine SQLite-Datei bleibt im Container erhalten.“

Stattdessen sorgt der Shutdown-Mechanismus für einen letzten Best-Effort-Sync:

```text
Cloud Run beendet Instanz
          │
          ▼
FastAPI Shutdown
          │
          ▼
letzter SQLite → GCS Upload
          │
          ▼
Container beendet
```

Die dauerhafte Kopie befindet sich anschließend in GCS.

---

## 11.16 Was passiert beim nächsten Start?

Startet Cloud Run später eine neue Instanz:

```text
Neue Instanz
     │
     ▼
GCS
     │
     │ trainingsplanner.db
     ▼
SQLite im neuen Container
     │
     ▼
FastAPI
     │
     ▼
Anwendung verfügbar
```

Damit überlebt die Datenbank den Austausch einer Container-Instanz.

---

## 11.17 Cloud Run ist nicht gleich „ein dauerhaft laufender Server“

Ein wichtiger konzeptioneller Unterschied zu einem klassischen Server:

```text
Klassischer Server
──────────────────

Server läuft
     │
     └── SQLite bleibt auf Festplatte


Cloud Run
─────────

Request
   │
   ▼
Instanz starten
   │
   ▼
Anfrage bearbeiten
   │
   ▼
keine Aktivität
   │
   ▼
Instanz kann beendet werden
```

Cloud Run ist daher **zustandslos (stateless)** gedacht.

Die lokale SQLite-Datei ist nur temporärer Zustand.

Unser GCS-Mechanismus macht daraus für die aktuelle Entwicklungsphase eine einfache Form von Persistenz:

```text
Cloud Run
   │
   │ temporärer Zustand
   ▼
SQLite
   │
   │ dauerhafter Zustand
   ▼
GCS
```

---

## 11.18 Kostenverhalten

Ein wesentlicher Vorteil von Cloud Run für die aktuelle Entwicklungsphase ist, dass nicht zwingend eine dauerhaft laufende virtuelle Maschine bezahlt werden muss.

Wenn keine Anfragen eingehen, kann Cloud Run die Instanzen herunterfahren.

Das bedeutet:

```text
Keine Requests
      │
      ▼
keine aktive Container-Instanz notwendig
      │
      ▼
keine dauerhaft laufende VM
```

Allerdings bleibt der GCS-Bucket bestehen und verursacht geringe Storage-/Operationskosten.

Der genaue Preis hängt von Nutzung, Speichergröße und Anzahl der Operationen ab.

Für eine kleine Entwicklungsanwendung mit einer einzelnen SQLite-Datei ist der Storage-Anteil typischerweise sehr klein.

---

## 11.19 Wichtige Einschränkung der aktuellen Architektur

Die Lösung

```text
SQLite + GCS
```

ist bewusst eine **Entwicklungs- und Lehrarchitektur**.

Sie ist nicht mit einer echten serverseitigen Datenbank gleichzusetzen.

Ein Problem entsteht beispielsweise, wenn mehrere Container gleichzeitig schreiben:

```text
              GCS
               │
        ┌──────┴──────┐
        ▼             ▼
   Container A    Container B
      SQLite          SQLite
        │               │
        └──────┬────────┘
               │
             Uploads
               │
               ▼
        trainingsplanner.db
```

Hier könnten konkurrierende Änderungen entstehen.

Deshalb sollte diese Architektur nicht einfach auf beliebig viele parallel laufende Instanzen skaliert werden.

Für den aktuellen Zweck ist das akzeptabel, weil wir eine kleine Anwendung mit wenigen Benutzern und kontrollierter Skalierung betreiben.

Für einen echten Produktivbetrieb wäre PostgreSQL die bessere Lösung:

```text
Entwicklungsphase:

Cloud Run
    │
    ▼
 SQLite
    │
    ▼
   GCS


späterer Produktivbetrieb:

Cloud Run
    │
    ▼
PostgreSQL
```

---

## 11.20 Gesamtarchitektur des aktuellen Systems

Damit ergibt sich für RideFuel aktuell folgende Gesamtarchitektur:

```text
                         ┌──────────────────┐
                         │     Benutzer     │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Cloud Run     │
                         │                  │
                         │  Docker Image    │
                         │       │          │
                         │    FastAPI       │
                         │       │          │
                         │    SQLite        │
                         └───────┬──────────┘
                                 │
                     ┌───────────┴───────────┐
                     │                       │
                     ▼                       ▼
              Google OAuth              GCS Bucket
                     │                       │
                     │                 trainingsplanner.db
                     │                       │
                     ▼                       │
              RideFuel User                 │
                                             │
                     ┌───────────────────────┘
                     │
                     ▼
              persistente Daten
```

Die wichtigsten Verantwortlichkeiten sind damit getrennt:

| Komponente        | Aufgabe                                        |
| ----------------- | ---------------------------------------------- |
| Docker            | Verpackt die Anwendung reproduzierbar          |
| Artifact Registry | Speichert das Docker-Image                     |
| Cloud Run         | Führt den Container aus                        |
| FastAPI           | Stellt Backend und Webanwendung bereit         |
| Google OAuth      | Authentifiziert Benutzer                       |
| SQLite            | Temporäre operative Datenbank im Container     |
| `storage.py`      | Synchronisiert SQLite mit GCS                  |
| Cloud Storage     | Persistente Speicherung der SQLite-Datei       |
| Service Account   | Identität des Cloud-Run-Containers             |
| IAM               | Regelt, was der Container in Google Cloud darf |

---

## 11.21 Rekonstruktion des Deployments

Soll das System später auf einem neuen Rechner oder in einem neuen Google-Cloud-Projekt rekonstruiert werden, ist die grundlegende Reihenfolge:

```text
1. Google-Cloud-Projekt auswählen
          │
          ▼
2. APIs aktivieren
          │
          ▼
3. Artifact Registry Repository erstellen
          │
          ▼
4. GCS Bucket erstellen
          │
          ▼
5. Service Account erstellen
          │
          ▼
6. IAM-Berechtigungen vergeben
          │
          ▼
7. Docker Image bauen
          │
          ▼
8. Image nach Artifact Registry pushen
          │
          ▼
9. Cloud Run Service deployen
          │
          ▼
10. GCS-Umgebungsvariablen konfigurieren
          │
          ▼
11. Anwendung testen
          │
          ▼
12. Persistenz durch Container-Neustart testen
```

Damit ist die Cloud-Infrastruktur nicht nur eingerichtet, sondern auch **nachvollziehbar dokumentiert und reproduzierbar**.

---

## 11.22 Zusammenfassung

Mit diesem Schritt wurde aus der lokal getesteten Docker-Anwendung ein Cloud-Run-Service.

Die entscheidende Architekturentscheidung lautet:

> **Der Container darf vergänglich sein. Die Daten dürfen es nicht sein.**

Deshalb werden Anwendung und Daten bewusst getrennt:

```text
Container
─────────
vergänglich
        │
        │
        ▼
Cloud Storage
─────────────
persistent
```

Das Docker-Image enthält den **Code**.

Google Cloud Storage enthält die **Daten**.

Cloud Run führt den **Code** aus.

Der Service Account regelt den **Zugriff**.

Diese Trennung ist das zentrale Konzept hinter der aktuellen Cloud-Architektur von RideFuel.
