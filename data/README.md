# Logbuch-DB hier ablegen als:
#   data/logbook.sqlite
#
# Auf dem Docker-Host (falls Docker zuvor einen Ordner namens logbook.sqlite angelegt hat):
#   docker compose down
#   rm -rf ./logbook.sqlite          # nur wenn es ein VERZEICHNIS ist
#   mkdir -p data
#   cp /pfad/zur/echten/logbook.sqlite ./data/logbook.sqlite
#   docker compose up -d --build
