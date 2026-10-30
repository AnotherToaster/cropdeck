"""
cropdeck track - build / update Karten-Tracker.xlsx from the scanner's cards.csv.

Run it after cropdeck split (and name), as often as you like:

    cropdeck track                           # uses the default folders
    cropdeck track <sorted-folder> -o <tracker.xlsx>

What it guarantees: YOUR EDITS ARE NEVER OVERWRITTEN. Rows are keyed by card ID.
New cards are appended; for cards already in the sheet, machine-owned columns are
only filled in when they are still empty, and nothing you typed is ever cleared.

Sheets:
  Übersicht  - status counts, money, things needing attention   (rebuilt each run)
  Inventar   - one row per physical card, the thing you edit    (preserved)
  Dubletten  - cards you own more than one of                   (rebuilt each run)
  Listen     - dropdown values + settings (box size)            (rebuilt each run)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import manifest, paths

MAX_ROWS = 3000  # how far the summary formulas look down the sheet

# --------------------------------------------------------------------------
# Column layout. "auto" = written by this script, "you" = yours to fill in.
# --------------------------------------------------------------------------
COLUMNS = [
    # header,           width, owner,  note
    ("ID", 7, "auto", "Kartennummer - verbindet Vorder- und Rückseite"),
    ("Name", 18, "auto", "wie auf der Karte gedruckt (OCR)"),
    ("Name EN", 18, "auto", "englischer Name"),
    ("Set", 22, "you", "z.B. Jungle, Celebrations, Fusion Strike"),
    ("Nummer", 9, "auto", "Sammlernummer, z.B. 9/25"),
    ("Sprache", 9, "you", "DE / EN / FR / IT / ES / JP"),
    ("Variante", 14, "you", "Normal, Reverse Holo, Holo, 1st Edition, Promo, Graded"),
    ("Zustand", 9, "you", "Cardmarket-Skala: M NM EX GD LP PL PO"),
    ("Grading", 12, "you", "leer, oder z.B. PSA 9 / BGS 9.5 + Zertifikatsnummer"),
    ("Kopie", 7, "auto", "die wievielte Kopie dieser Karte (Formel)"),
    ("Anzahl", 8, "auto", "wie viele du davon hast (Formel)"),
    ("Lagerort", 18, "auto", "physischer Platz, aus der ID berechnet (Formel)"),
    (
        "Status",
        13,
        "you",
        "Gescannt / Bereit / Online / Reserviert / Verkauft / Versendet / Behalten",
    ),
    ("Plattform", 20, "you", "swiss-tcg-market.ch, Cardmarket, eBay, Ricardo, tutti.ch"),
    ("Listing-URL", 34, "you", "Link zum Inserat"),
    ("Preis CHF", 11, "you", "Verkaufspreis, den du verlangst"),
    ("Verkauft CHF", 12, "you", "was du tatsächlich bekommen hast"),
    ("Verkauft am", 12, "you", "Datum"),
    ("Käufer / Notiz", 26, "you", ""),
    ("Bild vorne", 30, "auto", "Dateiname der Vorderseite"),
    ("Bild hinten", 30, "auto", "Dateiname der Rückseite"),
    ("OCR", 6, "auto", "Erkennungssicherheit; alles unter 1.00 kurz prüfen"),
]
HEAD = {h: i + 1 for i, (h, *_) in enumerate(COLUMNS)}
AUTO_COLS = ["Name", "Name EN", "Nummer", "Bild vorne", "Bild hinten", "OCR"]
FORMULA_COLS = ["Kopie", "Anzahl", "Lagerort"]

STATUSES = ["Gescannt", "Bereit", "Online", "Reserviert", "Verkauft", "Versendet", "Behalten"]
CONDITIONS = ["M", "NM", "EX", "GD", "LP", "PL", "PO"]
VARIANTS = ["Normal", "Reverse Holo", "Holo", "1st Edition", "Shadowless", "Promo", "Graded"]
LANGUAGES = ["DE", "EN", "FR", "IT", "ES", "JP", "PT", "KR", "ZH"]
PLATFORMS = ["swiss-tcg-market.ch", "Cardmarket", "eBay", "Ricardo", "tutti.ch"]

FONT = "Arial"
YELLOW = PatternFill("solid", fgColor="FFF2CC")  # you fill this in
GREY = PatternFill("solid", fgColor="EDEDED")  # automatic, don't type here
HEADFILL = PatternFill("solid", fgColor="1F3864")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# --------------------------------------------------------------------------
def read_cards(sorted_dir: Path) -> list[dict]:
    if not (sorted_dir / manifest.FILE).exists():
        print(f"! no {manifest.FILE} in {sorted_dir} - run cropdeck split first", file=sys.stderr)
        sys.exit(1)
    rows = [r for r in manifest.read(sorted_dir) if (r.get("card") or "").strip()]
    rows.sort(key=lambda r: r["card"])
    return rows


def style_header(ws):
    for col, (head, width, _owner, note) in enumerate(COLUMNS, 1):
        c = ws.cell(row=1, column=col, value=head)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HEADFILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER
        if note:
            c.comment = None
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}1"


def row_formulas(r: int) -> dict:
    """Formulas that keep themselves right as you edit names and variants."""
    n, num, var = f"$B{r}", f"$E{r}", f"$G{r}"
    kn, knum, kvar = f'""&{n}', f'""&{num}', f'""&{var}'
    return {
        # which copy of this card this row is (1st, 2nd, ...) - counts rows above
        "Kopie": f'=IF({n}="","",COUNTIFS($B$2:{n},{kn},$E$2:{num},{knum},$G$2:{var},{kvar}))',
        # how many of this card you own in total
        "Anzahl": (
            f'=IF({n}="","",COUNTIFS($B$2:$B${MAX_ROWS},{kn},'
            f"$E$2:$E${MAX_ROWS},{knum},$G$2:$G${MAX_ROWS},{kvar}))"
        ),
        # physical slot, derived from the card ID and the box size on 'Listen'
        "Lagerort": (
            f'=IF($A{r}="","","Box "&INT((VALUE($A{r})-1)/Listen!$B$2)+1'
            f'&" / Platz "&MOD(VALUE($A{r})-1,Listen!$B$2)+1)'
        ),
    }


def write_row(ws, r: int, card: dict, only_if_empty: bool):
    """Write one card. only_if_empty=True protects rows the user has already touched."""
    src = {
        "ID": card.get("card", ""),
        "Name": card.get("name", ""),
        "Name EN": card.get("name_en", ""),
        "Nummer": card.get("number", ""),
        "Bild vorne": card.get("front", ""),
        "Bild hinten": card.get("back", ""),
        "OCR": card.get("confidence", ""),
    }
    try:
        src["OCR"] = float(src["OCR"])
    except (TypeError, ValueError):
        src["OCR"] = ""
    for head in ["ID"] + AUTO_COLS:
        cell = ws.cell(row=r, column=HEAD[head])
        if only_if_empty and cell.value not in (None, ""):
            continue
        if src[head] != "":
            cell.value = src[head]

    for head, f in row_formulas(r).items():
        ws.cell(row=r, column=HEAD[head]).value = f

    if not only_if_empty:
        ws.cell(row=r, column=HEAD["Status"]).value = "Gescannt"
        ws.cell(row=r, column=HEAD["Sprache"]).value = (
            "DE" if card.get("name") != card.get("name_en") else ""
        )
        ws.cell(row=r, column=HEAD["Variante"]).value = "Normal"


def style_body(ws, last_row: int):
    for r in range(2, last_row + 1):
        for col, (head, _w, owner, _n) in enumerate(COLUMNS, 1):
            c = ws.cell(row=r, column=col)
            c.font = Font(name=FONT, size=10)
            c.border = BORDER
            c.fill = GREY if owner == "auto" else YELLOW
            if head in ("Preis CHF", "Verkauft CHF"):
                c.number_format = "#,##0.00;-#,##0.00;-"
            elif head == "Verkauft am":
                c.number_format = "DD.MM.YYYY"
            elif head == "OCR":
                c.number_format = "0.00"
                c.alignment = Alignment(horizontal="center")
            elif head in ("ID", "Nummer", "Kopie", "Anzahl", "Zustand", "Sprache"):
                c.alignment = Alignment(horizontal="center")

    def dv(values, cols, allow_blank=True):
        d = DataValidation(
            type="list",
            formula1='"' + ",".join(values) + '"',
            allow_blank=allow_blank,
            showDropDown=False,
        )
        ws.add_data_validation(d)
        for head in cols:
            letter = get_column_letter(HEAD[head])
            d.add(f"{letter}2:{letter}{max(last_row, 2)}")

    dv(STATUSES, ["Status"])
    dv(CONDITIONS, ["Zustand"])
    dv(VARIANTS, ["Variante"])
    dv(LANGUAGES, ["Sprache"])
    dv(PLATFORMS, ["Plattform"])

    st = get_column_letter(HEAD["Status"])
    rng = f"{st}2:{st}{max(last_row, 2)}"
    green = PatternFill("solid", fgColor="C6EFCE")
    blue = PatternFill("solid", fgColor="DDEBF7")
    amber = PatternFill("solid", fgColor="FFE699")
    for value, fill in (
        ("Verkauft", green),
        ("Versendet", green),
        ("Online", blue),
        ("Reserviert", amber),
    ):
        ws.conditional_formatting.add(
            rng, CellIsRule(operator="equal", formula=[f'"{value}"'], fill=fill)
        )

    # flag anything the OCR wasn't sure about
    oc = get_column_letter(HEAD["OCR"])
    ws.conditional_formatting.add(
        f"{oc}2:{oc}{max(last_row, 2)}",
        CellIsRule(operator="lessThan", formula=["1"], fill=PatternFill("solid", fgColor="FFC7CE")),
    )


# --------------------------------------------------------------------------
def build_listen(wb, box_size: int):
    ws = wb["Listen"] if "Listen" in wb.sheetnames else wb.create_sheet("Listen")
    ws.delete_rows(1, ws.max_row or 1)
    ws["A1"] = "Einstellung"
    ws["B1"] = "Wert"
    ws["A2"] = "Karten pro Box (für Lagerort)"
    ws["B2"] = box_size
    ws["A3"] = "→ Lagerort in 'Inventar' rechnet sich daraus neu"
    for cell in ("A1", "B1"):
        ws[cell].font = Font(name=FONT, bold=True)
    ws["B2"].fill = YELLOW

    lists = [
        ("Status", STATUSES),
        ("Zustand", CONDITIONS),
        ("Variante", VARIANTS),
        ("Sprache", LANGUAGES),
        ("Plattform", PLATFORMS),
    ]
    col = 4
    for title, values in lists:
        ws.cell(row=1, column=col, value=title).font = Font(name=FONT, bold=True)
        for i, v in enumerate(values, 2):
            ws.cell(row=i, column=col, value=v).font = Font(name=FONT, size=10)
        ws.column_dimensions[get_column_letter(col)].width = 20
        col += 1
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 10

    r = 12
    ws.cell(row=r, column=1, value="Zustand (Cardmarket-Skala)").font = Font(name=FONT, bold=True)
    for i, (code, txt) in enumerate(
        [
            ("M", "Mint - perfekt, kein Spielraum für Abnutzung"),
            ("NM", "Near Mint - minimale Fehler; Clouding schliesst NM aus"),
            ("EX", "Excellent - sichtbar benutzt, aber gepflegt"),
            ("GD", "Good - deutliche Abnutzung"),
            ("LP", "Light Played - starke Gebrauchsspuren"),
            ("PL", "Played - schwer abgenutzt, Wasserschaden, Wellen"),
            ("PO", "Poor - Pflicht bei altered, geschwärzten Rändern, Stempeln, Tinte"),
        ],
        1,
    ):
        ws.cell(row=r + i, column=1, value=code).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r + i, column=2, value=txt).font = Font(name=FONT, size=10)
    ws.cell(row=r + 9, column=1, value="Quelle: help.cardmarket.com/en/CardCondition").font = Font(
        name=FONT, size=9, italic=True
    )


def build_uebersicht(wb, last_row: int):
    ws = wb["Übersicht"] if "Übersicht" in wb.sheetnames else wb.create_sheet("Übersicht", 0)
    ws.delete_rows(1, ws.max_row or 1)
    inv, hi = "Inventar", MAX_ROWS

    def A(h):
        return f"{inv}!${get_column_letter(HEAD[h])}$2:${get_column_letter(HEAD[h])}${hi}"

    ws["A1"] = "Pokémon-Karten – Übersicht"
    ws["A1"].font = Font(name=FONT, bold=True, size=16, color="1F3864")
    ws["A2"] = (
        "Wird bei jedem Lauf von cropdeck track neu berechnet. "
        "Nicht hier tippen – alles in 'Inventar'."
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="808080")

    rows = [
        ("Bestand", None),
        ("Karten total", f'=COUNTIF({A("ID")},"<>")'),
        ("davon nicht erkannt", f'=COUNTIFS({A("ID")},"<>",{A("Name")},"")'),
        ("davon unsicher erkannt (OCR < 1.00)", f'=COUNTIFS({A("OCR")},"<1",{A("OCR")},"<>")'),
        ("verschiedene Karten (ohne Dubletten)", f'=COUNTIFS({A("ID")},"<>",{A("Kopie")},1)'),
        ("Karten mit Dubletten", f'=COUNTIFS({A("ID")},"<>",{A("Anzahl")},">1")'),
        ("", None),
        ("Status", None),
    ]
    for s in STATUSES:
        rows.append((s, f'=COUNTIF({A("Status")},"{s}")'))
    rows += [
        ("ohne Status", f'=COUNTIFS({A("ID")},"<>",{A("Status")},"")'),
        ("", None),
        ("Geld (CHF)", None),
        ("Wert aller Inserate online", f'=SUMIF({A("Status")},"Online",{A("Preis CHF")})'),
        ("bereits verkauft", f"=SUM({A('Verkauft CHF')})"),
        ("davon noch zu versenden", f'=SUMIF({A("Status")},"Verkauft",{A("Verkauft CHF")})'),
        (
            "Ø Verkaufspreis",
            f'=IFERROR(SUM({A("Verkauft CHF")})/COUNTIF({A("Verkauft CHF")},">0"),0)',
        ),
        ("", None),
        ("Zu tun", None),
        ("Set noch nicht eingetragen", f'=COUNTIFS({A("ID")},"<>",{A("Set")},"")'),
        ("Zustand noch nicht eingetragen", f'=COUNTIFS({A("ID")},"<>",{A("Zustand")},"")'),
        ("Preis noch nicht gesetzt", f'=COUNTIFS({A("ID")},"<>",{A("Preis CHF")},"")'),
    ]

    r = 4
    for label, formula in rows:
        if formula is None and label:
            ws.cell(row=r, column=1, value=label).font = Font(
                name=FONT, bold=True, size=11, color="1F3864"
            )
        elif label:
            ws.cell(row=r, column=1, value=label).font = Font(name=FONT, size=10)
            c = ws.cell(row=r, column=2, value=formula)
            c.font = Font(name=FONT, size=10, bold=True)
            if "CHF" in label or "verkauft" in label or "Wert" in label or "Ø" in label:
                c.number_format = "#,##0.00"
        r += 1
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 14

    legend = [
        ("", ""),
        ("Legende", ""),
        ("Gelbe Felder in 'Inventar'", "die füllst du aus"),
        ("Graue Felder in 'Inventar'", "kommen vom Scanner / sind Formeln – nicht überschreiben"),
        ("Rote OCR-Zahl", "Name wurde unsicher erkannt – kurz nachschauen"),
        (
            "Beispielzeile",
            "0007 | Snivy | Snivy | Celebrations | 5/25 | DE | Reverse Holo | "
            "NM | | 1 | 2 | Box 1 / Platz 7 | Online | swiss-tcg-market.ch | "
            "https://… | 4.50 | | | | …",
        ),
    ]
    for label, txt in legend:
        if label == "Legende":
            ws.cell(row=r, column=1, value=label).font = Font(
                name=FONT, bold=True, size=11, color="1F3864"
            )
        elif label:
            ws.cell(row=r, column=1, value=label).font = Font(name=FONT, size=10, bold=True)
            ws.cell(row=r, column=2, value=txt).font = Font(name=FONT, size=9)
        r += 1


def build_dubletten(wb, cards: list[dict], inv_rows: dict):
    """Rebuilt from scratch every run - it is a report, not something you edit."""
    ws = wb["Dubletten"] if "Dubletten" in wb.sheetnames else wb.create_sheet("Dubletten")
    ws.delete_rows(1, ws.max_row or 1)

    groups: dict[tuple, list[str]] = {}
    for c in cards:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        groups.setdefault((name, (c.get("number") or "").strip()), []).append(c["card"])
    dupes = sorted(
        ((k, v) for k, v in groups.items() if len(v) > 1), key=lambda kv: (-len(kv[1]), kv[0][0])
    )

    ws["A1"] = "Karten, von denen du mehr als eine hast"
    ws["A1"].font = Font(name=FONT, bold=True, size=13, color="1F3864")
    ws["A2"] = (
        "Nach Name + Sammlernummer gruppiert. Jede Kopie ist ein eigenes Objekt "
        "mit eigenem Zustand und eigenem Inserat – die IDs sagen dir welche."
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="808080")

    for i, h in enumerate(["Name", "Nummer", "Anzahl", "Karten-IDs"], 1):
        c = ws.cell(row=4, column=i, value=h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HEADFILL
    for r, ((name, number), ids) in enumerate(dupes, 5):
        ws.cell(row=r, column=1, value=name).font = Font(name=FONT, size=10)
        ws.cell(row=r, column=2, value=number).font = Font(name=FONT, size=10)
        ws.cell(row=r, column=3, value=len(ids)).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r, column=4, value=", ".join(ids)).font = Font(name=FONT, size=10)
    if not dupes:
        ws.cell(row=5, column=1, value="(noch keine Dubletten)").font = Font(
            name=FONT, size=10, italic=True
        )
    for col, w in zip("ABCD", (22, 10, 9, 60), strict=True):
        ws.column_dimensions[col].width = w
    return len(dupes)


# --------------------------------------------------------------------------
def add_arguments(p: argparse.ArgumentParser):
    p.add_argument(
        "sorted_dir",
        nargs="?",
        default=None,
        help=f"folder holding cards.csv [default: $CROPDECK_HOME/{paths.SORTED}]",
    )
    p.add_argument(
        "-o",
        "--out",
        default=None,
        help=f"tracker workbook [default: $CROPDECK_HOME/{paths.TRACKER}]",
    )
    p.add_argument(
        "--box-size",
        type=int,
        default=60,
        help="cards per storage box, for the Lagerort column (default 60)",
    )


def run(args) -> int:
    sorted_dir = Path(args.sorted_dir or paths.home() / paths.SORTED).expanduser()
    out = Path(args.out or paths.home() / paths.TRACKER).expanduser()
    cards = read_cards(sorted_dir)

    if out.exists():
        wb = load_workbook(out)
        if "Inventar" not in wb.sheetnames:
            wb.create_sheet("Inventar")
        fresh = False
    else:
        wb = Workbook()
        wb.remove(wb.active)
        wb.create_sheet("Übersicht")
        wb.create_sheet("Inventar")
        wb.create_sheet("Dubletten")
        wb.create_sheet("Listen")
        fresh = True

    inv = wb["Inventar"]
    style_header(inv)

    # index the rows that are already there, by card ID
    existing = {}
    for r in range(2, (inv.max_row or 1) + 1):
        v = inv.cell(row=r, column=HEAD["ID"]).value
        if v not in (None, ""):
            existing[str(v).strip()] = r

    added, updated = 0, 0
    next_row = max(existing.values(), default=1) + 1
    for card in cards:
        cid = card["card"].strip()
        if cid in existing:
            write_row(inv, existing[cid], card, only_if_empty=True)
            updated += 1
        else:
            write_row(inv, next_row, card, only_if_empty=False)
            existing[cid] = next_row
            next_row += 1
            added += 1

    last_row = max(existing.values(), default=1)
    style_body(inv, last_row)

    n_dupes = build_dubletten(wb, cards, existing)
    build_listen(wb, args.box_size)
    build_uebersicht(wb, last_row)
    wb.move_sheet("Übersicht", offset=-wb.sheetnames.index("Übersicht"))

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    print(f"{'Created' if fresh else 'Updated'}: {out}")
    print(f"  {len(cards)} card(s) in cards.csv")
    print(f"  {added} new row(s) added, {len(existing) - added} kept as they were")
    print(f"  {n_dupes} card(s) you own more than one of -> see the 'Dubletten' sheet")
    if not fresh:
        print("  Nothing you typed was overwritten.")
    return 0
