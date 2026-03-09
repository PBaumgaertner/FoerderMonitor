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

# Felder die als Zahl gespeichert werden sollen
NUMERIC_FIELDS = {"sollzins_pct", "effektivzins_pct"}
# Felder die immer als String bleiben (nie als 297.0)
STRING_ID_FIELDS = {"programme_id", "date", "programme_name",
                    "foerderstufe", "darlehensart", "laufzeit_label"}


def normalize_row(row):
    """Typen normalisieren: IDs als String, Zinswerte als float, leer → None."""
    result = {}
    for k in KEEP_FIELDS:
        v = row.get(k, "")
        if k in STRING_ID_FIELDS:
            result[k] = v.strip()
        elif k in NUMERIC_FIELDS:
            try:
                result[k] = float(v) if v.strip() not in ("", "-,--", "–") else None
            except ValueError:
                result[k] = None
        elif k == "zinsbindung_jahre":
            # Zinsbindung: Zahl oder leer-String
            try:
                result[k] = int(float(v)) if v.strip() not in ("", "-,--", "–") else ""
            except ValueError:
                result[k] = ""
        else:
            result[k] = v.strip()
    return result


def main():
    if not CSV_PATH.exists():
        print("❌ CSV nicht gefunden – abbruch")
        return

    # CSV einlesen
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            normalize_row(row)
            for row in reader
            if row.get("foerderstufe")  # nur neue Struktur
        ]

    if not rows:
        print("❌ Keine gültigen Zeilen in CSV – abbruch")
        return

    print(f"✅ {len(rows)} Zeilen aus CSV geladen")
    # Stichprobe zur Überprüfung
    sample = rows[0]
    print(f"   Beispiel: programme_id={sample['programme_id']!r} "
          f"effektivzins={sample['effektivzins_pct']!r} "
          f"zinsbindung={sample['zinsbindung_jahre']!r}")

    # JSON kompakt serialisieren
    json_str = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))

    # In HTML ersetzen
    if not HTML_PATH.exists():
        print("❌ index.html nicht gefunden – abbruch")
        return

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
