# Logbook Viso

Interaktive Karte für Segel-/Motorboot-Logbuch-Tracks aus `logbook.sqlite`.

## Start

```bash
pip install -r requirements.txt
python server.py
```

Dann im Browser: [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Funktionen

- Zoom und Verschieben der Karte (Leaflet / OpenStreetMap)
- Törn-Auswahl (Filter über Spalte `toern`)
- Track als farbige Linie + Punkte
- Hover-Popup mit Time, COG, LAT, LON, SOG, M/H, LOG, GEO, Freitext und Wetterdaten
- `recordtype = 1` → größere Punkte (manuelle Einträge)
- Status-Farben: 0 Segeln, 1 Festgemacht, 2 Motor, 3 Anker
