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