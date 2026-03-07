"""
inject_dashboard.py
───────────────────
Liest data/kfw_rates.csv und ersetzt den SEED_DATA Block in docs/index.html.
Wird nach dem Scraper aufgerufen – danach enthält die HTML immer aktuelle Daten,
ohne dass ein HTTP-Fetch auf die CSV nötig ist.
"""
import csv
import json
import re
from pathlib import Path

ROOT       = Path(__file__).parent.parent
CSV_PATH   = ROOT / "data" / "kfw_rates.csv"
HTML_PATH  = ROOT / "docs" / "index.html"

KEEP_FIELDS = [
    "date", "programme_id", "programme_name", "foerderstufe",
    "darlehensart", "laufzeit_label", "zinsbindung_jahre",
    "sollzins_pct", "effektivzins_pct",
]

def main():
    if not CSV_PATH.exists():
        print("❌ CSV nicht gefunden – abbruch")
        return

    # CSV einlesen
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            {k: row[k] for k in KEEP_FIELDS if k in row}
            for row in reader
            if row.get("foerderstufe")  # nur neue Struktur
        ]

    if not rows:
        print("❌ Keine gültigen Zeilen in CSV – abbruch")
        return

    print(f"✅ {len(rows)} Zeilen aus CSV geladen")

    # JSON kompakt serialisieren
    json_str = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))

    # In HTML ersetzen
    html = HTML_PATH.read_text(encoding="utf-8")

    new_block = (
        f"// INJECT_DATA_START\n"
        f"const SEED_DATA = {json_str};\n"
        f"// INJECT_DATA_END"
    )

    html_new = re.sub(
        r"// INJECT_DATA_START.*?// INJECT_DATA_END",
        new_block,
        html,
        flags=re.DOTALL,
    )

    if html_new == html:
        print("❌ Marker nicht gefunden – HTML nicht aktualisiert")
        return

    HTML_PATH.write_text(html_new, encoding="utf-8")
    print(f"✅ docs/index.html aktualisiert (Stand: {rows[-1]['date']})")

if __name__ == "__main__":
    main()
