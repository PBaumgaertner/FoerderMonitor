"""
KfW Neubau Scraper – Zinsen + Programmdefinitionen
====================================================
Schreibt zwei Dateien:

  data/kfw_rates.csv      – täglich wachsende Zeitreihe der Zinssätze
                            (Programm | Förderstufe | Darlehensart | Laufzeit | Zinsen)

  data/kfw_programme.json – Programmdefinitionen (wird täglich überschrieben)
                            (Kredithöhe | Förderstufen-Definitionen | Zielgruppen | Was wird gefördert)
"""

import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Konfiguration ─────────────────────────────────────────────────────────────

PROGRAMMES = [
    {
        "id": "297/298",
        "name": "Klimafreundlicher Neubau Wohngebäude",
        "url": "https://www.kfw.de/inlandsfoerderung/Privatpersonen/Neubau/F%C3%B6rderprodukte/Klimafreundlicher-Neubau-Wohngeb%C3%A4ude-(297-298)/",
    },
    {
        "id": "300",
        "name": "Wohneigentum für Familien – Neubau",
        "url": "https://www.kfw.de/inlandsfoerderung/Privatpersonen/Neubau/F%C3%B6rderprodukte/Wohneigentum-f%C3%BCr-Familien-(300)/",
    },
    {
        "id": "296",
        "name": "Klimafreundlicher Neubau im Niedrigpreissegment",
        "url": "https://www.kfw.de/inlandsfoerderung/Privatpersonen/Neubau/F%C3%B6rderprodukte/Klimafreundlicher-Neubau-im-Niedrigpreissegment-(296)/",
    },
]

DATA_DIR     = Path(__file__).parent.parent / "data"
OUTPUT_CSV   = DATA_DIR / "kfw_rates.csv"
OUTPUT_JSON  = DATA_DIR / "kfw_programme.json"

RATES_HEADER = [
    "date", "programme_id", "programme_name",
    "foerderstufe", "darlehensart", "laufzeit_label",
    "zinsbindung_jahre", "sollzins_pct", "effektivzins_pct",
    "scraped_at", "source_url",
]

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def clean_rate(raw: str):
    if not raw:
        return None
    raw = raw.replace("%", "").replace("\xa0", "").replace(",", ".").strip()
    if re.match(r"^[-.\s]+$", raw):
        return None
    try:
        return str(round(float(raw), 4))
    except ValueError:
        return None

def extract_rates(text: str):
    matches = re.findall(r"([\d]+[,.][\d]+)\s*%", text)
    sollzins = clean_rate(matches[0]) if len(matches) > 0 else None
    effzins  = clean_rate(matches[1]) if len(matches) > 1 else None
    return sollzins, effzins

def clean_list(items: list[str]) -> list[str]:
    return [i.strip() for i in items if i.strip() and len(i.strip()) > 3]

# ── Seiten-Scraper ─────────────────────────────────────────────────────────────

def scrape_page(page, prog: dict, today: str, scraped_at: str) -> tuple[list[dict], dict]:
    """
    Gibt zurück:
      rates    – Liste der Zins-Zeilen für kfw_rates.csv
      prog_def – Programmdefinition für kfw_programme.json
    """
    rates = []

    # Warte auf dynamische Zinsen
    try:
        page.wait_for_function(
            "() => [...document.querySelectorAll('table td')]"
            ".some(c => /\\d,\\d+/.test(c.innerText))",
            timeout=20_000,
        )
    except PlaywrightTimeout:
        print("  ⚠  Zinsen nicht dynamisch geladen – versuche trotzdem")

    # ── Programmdefinition scrapen ─────────────────────────────────────────────
    prog_def = {
        "programme_id":   prog["id"],
        "programme_name": prog["name"],
        "source_url":     prog["url"],
        "scraped_at":     scraped_at,
        "foerderstufen":  {},
        "zielgruppen":    [],
        "was_wird_gefoerdert": [],
        "kredithoehe":    {},
        "nicht_fuer":     [],
    }

    # Förderstufen-Definitionen (h3 + folgende ul)
    foerderstufen_mapping = {
        "effizienzhaus 55":  "EH55",
        "klimafreundliches wohngebäude":  "KFW40",
        "mit qualitätssiegel": "KFW40+QNG",
        "mit qng": "KFW40+QNG",
    }

    # Alle Abschnitte der Seite lesen
    body_text = page.inner_text("body")

    # Zielgruppen extrahieren (nach "Wen fördern wir?")
    wen_match = re.search(
        r"Wen fördern wir\?(.*?)(?:Was fördern wir\?|Konditionen|So funktioniert)",
        body_text, re.DOTALL
    )
    if wen_match:
        lines = [l.strip() for l in wen_match.group(1).splitlines() if l.strip()]
        prog_def["zielgruppen"] = clean_list(lines)

    # Was wird gefördert (nach "Was fördern wir?")
    was_match = re.search(
        r"Was fördern wir\?(.*?)(?:Wen fördern wir\?|Konditionen)",
        body_text, re.DOTALL
    )
    if was_match:
        lines = [l.strip() for l in was_match.group(1).splitlines() if l.strip()]
        prog_def["was_wird_gefoerdert"] = clean_list(lines[:20])

    # Kredithöhe extrahieren
    kredit_matches = re.findall(
        r"([\d\.]+\.[\d]+|[\d]+\.[\d]+)\s*Euro(?:\s*je\s*Wohn(?:ung|einheit))?",
        body_text
    )
    if not kredit_matches:
        kredit_matches = re.findall(r"(\d+(?:\.\d+)?)\s*Euro", body_text)

    # Förderstufen-spezifische Kredithöhen
    for stufe_key, stufe_id in foerderstufen_mapping.items():
        pattern = rf"{re.escape(stufe_key)}.*?(\d{{2,3}}\.?\d{{3}})\s*Euro"
        m = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
        if m:
            prog_def["kredithoehe"][stufe_id] = m.group(1) + " Euro je Wohneinheit"

    # Generelle Kredithöhe falls keine stufen-spezifische gefunden
    kredit_section = re.search(
        r"Kredithöhe(.*?)(?:Auszahlung|Vorzeitige)", body_text, re.DOTALL
    )
    if kredit_section:
        prog_def["kredithoehe"]["beschreibung"] = " ".join(
            kredit_section.group(1).split()
        )[:500]

    # Nicht gefördert
    nicht_match = re.search(
        r"nicht in Frage für:(.*?)(?:Wen fördern|##|\Z)",
        body_text, re.DOTALL
    )
    if nicht_match:
        lines = [l.strip() for l in nicht_match.group(1).splitlines() if l.strip()]
        prog_def["nicht_fuer"] = clean_list(lines[:10])

    # Förderstufen-Definitionen
    for stufe_key, stufe_id in foerderstufen_mapping.items():
        pattern = rf"(?:Effizienzhaus 55|Klimafreundliches Wohngebäude[^–]*?{'mit QNG' if 'qng' in stufe_key else ''})\s*\n(.*?)(?=\n###|\n##|\Z)"
        m = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
        if m:
            definition = " ".join(m.group(1).split())[:600]
            prog_def["foerderstufen"][stufe_id] = definition

    # ── Zinssätze scrapen ──────────────────────────────────────────────────────
    elements = page.query_selector_all("h2, h3, h4, h5, table")

    current_darlehensart = "Annuitätendarlehen"
    current_foerderstufe = "Unbekannt"
    current_prog_id      = prog["id"]
    current_prog_name    = prog["name"]

    for el in elements:
        tag  = el.evaluate("e => e.tagName.toLowerCase()")
        text = el.inner_text().strip()
        tl   = text.lower()

        if tag in ("h2", "h3", "h4", "h5"):
            if "annuitäten" in tl:
                current_darlehensart = "Annuitätendarlehen"
            elif "endfällig" in tl:
                current_darlehensart = "Endfälliges Darlehen"

            if "effizienzhaus 55" in tl:
                current_foerderstufe = "EH55"
            elif "qng" in tl:
                current_foerderstufe = "KFW40+QNG"
            elif "klimafreundlich" in tl:
                current_foerderstufe = "KFW40"

            if "297" in text and "298" not in text:
                current_prog_id   = "297"
                current_prog_name = "Klimafreundlicher Neubau – private Selbstnutzung (297)"
            elif "298" in text and "297" not in text:
                current_prog_id   = "298"
                current_prog_name = "Klimafreundlicher Neubau – Vermietung (298)"
            elif prog["id"] not in ("297/298",):
                current_prog_id   = prog["id"]
                current_prog_name = prog["name"]
            continue

        if tag == "table":
            for row in el.query_selector_all("tr"):
                cells = row.query_selector_all("td")
                if len(cells) < 2:
                    continue
                cell_texts  = [c.inner_text().strip() for c in cells]
                sollzins, effzins = extract_rates(cell_texts[-1])
                if not sollzins:
                    continue

                zinsbindung = None
                if len(cell_texts) >= 2:
                    m = re.search(r"(\d+)\s*Jahre?", cell_texts[1])
                    if m:
                        zinsbindung = int(m.group(1))

                rates.append({
                    "date":              today,
                    "programme_id":      current_prog_id,
                    "programme_name":    current_prog_name,
                    "foerderstufe":      current_foerderstufe,
                    "darlehensart":      current_darlehensart,
                    "laufzeit_label":    cell_texts[0],
                    "zinsbindung_jahre": zinsbindung,
                    "sollzins_pct":      sollzins,
                    "effektivzins_pct":  effzins,
                    "scraped_at":        scraped_at,
                    "source_url":        prog["url"],
                })

    return rates, prog_def

# ── Speichern ──────────────────────────────────────────────────────────────────

def save_rates(rows: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RATES_HEADER)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    print(f"  💾 {len(rows)} Zeilen → {OUTPUT_CSV.name}")

def save_programme(programme_list: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(programme_list, f, ensure_ascii=False, indent=2)
    print(f"  💾 {len(programme_list)} Programme → {OUTPUT_JSON.name}")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    today      = date.today().isoformat()
    scraped_at = datetime.now().isoformat(timespec="seconds")
    all_rates  = []
    all_progs  = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ))
        page = context.new_page()

        for prog in PROGRAMMES:
            print(f"\n📡 Scraping KfW {prog['id']} …")
            try:
                page.goto(prog["url"], wait_until="domcontentloaded", timeout=45_000)
                rates, prog_def = scrape_page(page, prog, today, scraped_at)

                if rates:
                    all_rates.extend(rates)
                    print(f"  ✅ {len(rates)} Zins-Zeilen")
                else:
                    print(f"  ❌ Keine Zinsen")

                all_progs.append(prog_def)

            except Exception as exc:
                print(f"  ❌ Fehler: {exc}")

        browser.close()

    print(f"\n{'─'*60}")
    if all_rates:
        save_rates(all_rates)
    save_programme(all_progs)

    # Vorschau
    print(f"\n📊 Zinsen-Vorschau:")
    for r in all_rates[:6]:
        print(
            f"  [{r['programme_id']:8s}] {r['foerderstufe']:12s} | "
            f"{r['darlehensart']:25s} | {r['laufzeit_label']:20s} | "
            f"Soll: {r['sollzins_pct'] or 'n/a':>6}%  Eff: {r['effektivzins_pct'] or 'n/a':>6}%"
        )

    print(f"\n📋 Programme-Vorschau:")
    for p in all_progs:
        print(f"  [{p['programme_id']}] Kredithöhe: {p['kredithoehe']}")
        print(f"       Zielgruppen: {len(p['zielgruppen'])} Einträge")
        print(f"       Förderstufen: {list(p['foerderstufen'].keys())}")

    if not all_rates:
        sys.exit(1)

if __name__ == "__main__":
    print(f"🏗  KfW Neubau Scraper – {date.today()}\n")
    main()
