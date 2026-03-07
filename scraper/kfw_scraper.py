"""
KfW Neubau Zinskonditionen Scraper
===================================
Scrapet täglich die aktuellen Zinssätze der wichtigsten KfW Neubau-Programme:
  - 300  Wohneigentum für Familien
  - 297/298  Klimafreundlicher Neubau – Wohngebäude
  - 296  Klimafreundlicher Neubau im Niedrigpreissegment

Ergebnis wird in data/kfw_rates.csv gespeichert (append-Modus für Zeitreihe).
"""

import csv
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Konfiguration ─────────────────────────────────────────────────────────────

PROGRAMMES = [
    {
        "id": "300",
        "name": "Wohneigentum für Familien – Neubau",
        "url": "https://www.kfw.de/inlandsfoerderung/Privatpersonen/Neubau/F%C3%B6rderprodukte/Wohneigentum-f%C3%BCr-Familien-(300)/",
    },
    {
        "id": "297/298",
        "name": "Klimafreundlicher Neubau Wohngebäude",
        "url": "https://www.kfw.de/inlandsfoerderung/Privatpersonen/Neubau/F%C3%B6rderprodukte/Klimafreundlicher-Neubau-Wohngeb%C3%A4ude-(297-298)/",
    },
    {
        "id": "296",
        "name": "Klimafreundlicher Neubau im Niedrigpreissegment",
        "url": "https://www.kfw.de/inlandsfoerderung/Privatpersonen/Neubau/F%C3%B6rderprodukte/Klimafreundlicher-Neubau-im-Niedrigpreissegment-(296)/",
    },
]

OUTPUT_CSV = Path(__file__).parent.parent / "data" / "kfw_rates.csv"
CSV_HEADER = [
    "date",
    "programme_id",
    "programme_name",
    "laufzeit_label",
    "zinsbindung_jahre",
    "sollzins_pct",
    "effektivzins_pct",
    "scraped_at",
    "source_url",
]

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def clean_rate(raw: str):
    raw = raw.strip()
    if not raw or re.match(r"^[-,\s]+%?$", raw):
        return None
    raw = raw.replace("%", "").replace("\xa0", "").strip()
    raw = raw.replace(",", ".")
    try:
        return str(round(float(raw), 4))
    except ValueError:
        return None


def parse_rate_table(page) -> list[dict]:
    records = []

    # Warte bis JavaScript die Zinsen geladen hat
    try:
        page.wait_for_function(
            """() => {
                const cells = document.querySelectorAll('table td');
                for (const c of cells) {
                    if (/\\d,\\d+/.test(c.innerText)) return true;
                }
                return false;
            }""",
            timeout=20_000,
        )
    except PlaywrightTimeout:
        print(f"  ⚠  Zinsen nicht dynamisch geladen – versuche trotzdem")

    tables = page.query_selector_all("table")
    for table in tables:
        rows = table.query_selector_all("tr")
        headers = []
        for row in rows:
            cells = row.query_selector_all("th, td")
            texts = [c.inner_text().strip() for c in cells]
            if not any(texts):
                continue

            if row.query_selector_all("th"):
                headers = texts
                continue

            if not any("%" in t or re.search(r"\d,\d", t) for t in texts):
                continue

            laufzeit = texts[0] if texts else "unbekannt"

            rates_found = re.findall(
                r"([\d]+[,.][\d]+)\s*%\s*(?:\(?\s*([\d]+[,.][\d]+)\s*%\s*\)?)?",
                " ".join(texts),
            )

            if rates_found:
                sollzins_raw, effzins_raw = rates_found[0]
                zinsbindung = None
                for h, v in zip(headers, texts):
                    if "zins" in h.lower() and "bindung" in h.lower():
                        m = re.search(r"\d+", v)
                        zinsbindung = int(m.group()) if m else None

                records.append({
                    "laufzeit_label": laufzeit,
                    "zinsbindung_jahre": zinsbindung,
                    "sollzins_pct": clean_rate(sollzins_raw + "%"),
                    "effektivzins_pct": clean_rate(effzins_raw + "%") if effzins_raw else None,
                })

    return records


# ── Haupt-Scraper ──────────────────────────────────────────────────────────────

def scrape_all() -> list[dict]:
    today = date.today().isoformat()
    scraped_at = datetime.now().isoformat(timespec="seconds")
    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        for prog in PROGRAMMES:
            print(f"📡 Scraping KfW {prog['id']} …")
            try:
                page.goto(prog["url"], wait_until="domcontentloaded", timeout=45_000)
                records = parse_rate_table(page)

                if records:
                    for rec in records:
                        all_rows.append({
                            "date": today,
                            "programme_id": prog["id"],
                            "programme_name": prog["name"],
                            **rec,
                            "scraped_at": scraped_at,
                            "source_url": prog["url"],
                        })
                    print(f"  ✅ {len(records)} Zeilen gefunden")
                else:
                    # Fallback: Zinsen direkt aus dem Text extrahieren
                    text = page.inner_text("body")
                    rates = re.findall(r"([\d]+,[\d]+)\s*%\s*(?:effektiv|p\.a\.)?", text)
                    if rates:
                        print(f"  ℹ️  Fallback: {rates[:4]}")
                        all_rows.append({
                            "date": today,
                            "programme_id": prog["id"],
                            "programme_name": prog["name"],
                            "laufzeit_label": "Aus Seitentext",
                            "zinsbindung_jahre": None,
                            "sollzins_pct": clean_rate(rates[0] + "%"),
                            "effektivzins_pct": clean_rate(rates[1] + "%") if len(rates) > 1 else None,
                            "scraped_at": scraped_at,
                            "source_url": prog["url"],
                        })
                    else:
                        print(f"  ❌ Keine Zinsen gefunden")

            except Exception as exc:
                print(f"  ❌ Fehler: {exc}")

        browser.close()

    return all_rows


def save_to_csv(rows: list[dict]):
    # Ordner anlegen falls nicht vorhanden
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    file_exists = OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    print(f"\n💾 {len(rows)} Zeilen → {OUTPUT_CSV}")


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"🏗  KfW Neubau Scraper – {date.today()}\n")
    rows = scrape_all()

    if rows:
        save_to_csv(rows)
        print("\n📊 Ergebnis-Vorschau:")
        for r in rows:
            print(
                f"  [{r['programme_id']}] {r['laufzeit_label']:30s} "
                f"Sollzins: {r['sollzins_pct'] or 'n/a':>6} %  "
                f"Effektivzins: {r['effektivzins_pct'] or 'n/a':>6} %"
            )
    else:
        print("⚠  Keine Daten extrahiert.")
        sys.exit(1)
