# 🏗 KfW Neubau – Zinskonditionen Monitor

Automatisches tägliches Tracking der KfW-Zinskonditionen für Neubau-Förderprogramme.

## Programme

| ID | Name | Zielgruppe |
|----|------|-----------|
| 300 | Wohneigentum für Familien | Familien mit Kindern |
| 297 | Klimafreundlicher Neubau Wohngebäude | Privatpersonen |
| 298 | Klimafreundlicher Neubau Wohngebäude | Unternehmen/Projektentwickler |
| 296 | Klimafreundlicher Neubau Niedrigpreissegment | Privatpersonen & Unternehmen |

## Daten

Die tagesaktuellen Konditionen werden in [`data/kfw_rates.csv`](data/kfw_rates.csv) gespeichert.

### Spalten

| Spalte | Beschreibung |
|--------|-------------|
| `date` | Datum der Abfrage (YYYY-MM-DD) |
| `programme_id` | KfW-Programmnummer |
| `programme_name` | Programmbezeichnung |
| `laufzeit_label` | Laufzeit-Klasse (z.B. "4–10 Jahre") |
| `zinsbindung_jahre` | Zinsbindungsdauer in Jahren |
| `sollzins_pct` | Sollzins in % p.a. |
| `effektivzins_pct` | Effektiver Jahreszins in % |
| `scraped_at` | Zeitstempel der Abfrage |
| `source_url` | Quell-URL |

## Automatisierung

Der Scraper läuft automatisch jeden Werktag um **08:15 Uhr MEZ** via GitHub Actions.  
Manueller Start ist jederzeit über `Actions → KfW Zinsen – Täglicher Scraper → Run workflow` möglich.

## Lokale Ausführung

```bash
pip install -r requirements.txt
playwright install chromium
python scraper/kfw_scraper.py
```

## Projektstruktur

```
kfw-foerder-monitor/
├── .github/
│   └── workflows/
│       └── daily_scraper.yml   # Cron-Job Definition
├── scraper/
│   └── kfw_scraper.py          # Haupt-Scraper
├── data/
│   └── kfw_rates.csv           # Zeitreihendaten (wächst täglich)
├── requirements.txt
└── README.md
```

## Datenquelle

Alle Daten stammen direkt von [kfw.de](https://www.kfw.de) und werden täglich automatisch aktualisiert.  
Die KfW-Zinskonditionen orientieren sich am Kapitalmarkt und werden laufend angepasst.

---
*Entwickelt für all3.com – Immobilienentwicklung*
