"""
Logbook Viso – interaktive Karte für Segel-/Motorboot-Logbücher.

Paketstruktur:
  config          – Pfade und Umgebungsvariablen
  auth_helpers    – Flask-Session und API-Decorators
  users_store     – Benutzer, Rollen, Törn-Zuordnung
  logbook_store   – Törns, Track-Punkte, Logbook-Import
  photos_store    – Medien-Dateien, Metadaten, Clustering
  api_format      – JSON-Hilfsfunktionen für Track-/Törn-Antworten
"""

__version__ = "1.0.0"
