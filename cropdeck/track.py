"""
cropdeck track - build / update the tracker workbook from the scanner's cards.csv.

Run it after cropdeck split (and name), as often as you like:

    cropdeck track                                   # default folders, English, EUR
    cropdeck track <sorted-folder> -o <tracker.xlsx> --lang de --currency CHF

What it guarantees: YOUR EDITS ARE NEVER OVERWRITTEN. Rows are keyed by card ID.
New cards are appended; for cards already in the sheet, machine-owned columns are
only filled in when they are still empty, and nothing you typed is ever cleared.

Every text in the workbook comes from data/locales/<language>.json and every currency from
data/currencies.json (see texts.py). A workbook keeps the language and currency it was created
with - they are stored on its lists sheet, or for older workbooks read from the sheet names and
the price column - so a later run never half-translates it.

Sheets (names from the language file):
  overview    - status counts, money, things needing attention   (rebuilt each run)
  inventory   - one row per physical card, the thing you edit    (preserved)
  duplicates  - cards you own more than once, from the inventory (rebuilt each run)
  lists       - settings and dropdown values                     (rebuilt, settings kept)
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

from . import manifest, paths, texts

MAX_ROWS = 3000  # how far the summary formulas look down the sheet
DEFAULT_BOX_SIZE = 60

# The inventory's columns, in order: key (its texts are in the language file), width, and who
# fills it - "auto" is written by this step, "you" is yours.
COLUMNS = [
    ("id", 7, "auto"),
    ("name", 18, "auto"),
    ("name_en", 18, "auto"),
    ("set", 22, "you"),
    ("number", 9, "auto"),
    ("language", 9, "you"),
    ("variant", 14, "you"),
    ("condition", 9, "you"),
    ("grading", 12, "you"),
    ("copy", 7, "auto"),
    ("count", 8, "auto"),
    ("location", 18, "auto"),
    ("status", 13, "you"),
    ("platform", 20, "you"),
    ("listing_url", 34, "you"),
    ("price", 11, "you"),
    ("sold_price", 12, "you"),
    ("sold_on", 12, "you"),
    ("buyer_note", 26, "you"),
    ("image_front", 30, "auto"),
    ("image_back", 30, "auto"),
    ("ocr", 6, "auto"),
]
COL = {key: i + 1 for i, (key, *_) in enumerate(COLUMNS)}
AUTO = ["name", "name_en", "number", "image_front", "image_back", "ocr"]
CONDITIONS = ["M", "NM", "EX", "GD", "LP", "PL", "PO"]
CARD_LANGUAGES = ["EN", "DE", "FR", "IT", "ES", "PT", "JP", "KR", "ZH"]

# settings on the lists sheet; the location formula reads the box size from BOX_SIZE
BOX_SIZE, CURRENCY, LANGUAGE = "B2", "B3", "B4"

FONT = "Arial"
YELLOW = PatternFill("solid", fgColor="FFF2CC")  # you fill this in
GREY = PatternFill("solid", fgColor="EDEDED")  # automatic, don't type here
HEADFILL = PatternFill("solid", fgColor="1F3864")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = "#,##0.00;-#,##0.00;-"


def letter(key: str) -> str:
    return get_column_letter(COL[key])


def title(t: dict, key: str, currency: str) -> str:
    return t["columns"][key][0].format(currency=currency)


def ref(sheet: str, cell: str) -> str:
    """A reference to another sheet; quoted, so any sheet name in any language works."""
    return f"'{sheet}'!{cell}"


# --------------------------------------------------------------------------
def read_cards(sorted_dir: Path) -> list[dict]:
    if not (sorted_dir / manifest.FILE).exists():
        print(f"! no {manifest.FILE} in {sorted_dir} - run cropdeck split first", file=sys.stderr)
        sys.exit(1)
    rows = [r for r in manifest.read(sorted_dir) if (r.get("card") or "").strip()]
    rows.sort(key=lambda r: r["card"])
    return rows


def detect(wb) -> tuple[str | None, str | None, int | None]:
    """The language, currency and box size an existing workbook was made with (None if unknown)."""
    lang = next(
        (c for c in texts.languages() if texts.language(c)["sheets"]["inventory"] in wb.sheetnames),
        None,
    )
    if lang is None:
        return None, None, None
    t = texts.language(lang)
    currency = box = None
    if t["sheets"]["lists"] in wb.sheetnames:
        lists = wb[t["sheets"]["lists"]]
        currency = lists[CURRENCY].value if lists[CURRENCY].value in texts.currencies() else None
        box = lists[BOX_SIZE].value if isinstance(lists[BOX_SIZE].value, int) else None
    if currency is None:  # older workbooks: the code is the last word of the price header
        head = str(wb[t["sheets"]["inventory"]].cell(row=1, column=COL["price"]).value or "")
        currency = next((c for c in texts.currencies() if head.endswith(c)), None)
    return lang, currency, box


def style_header(ws, t: dict, currency: str):
    for key, width, _owner in COLUMNS:
        c = ws.cell(row=1, column=COL[key], value=title(t, key, currency))
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HEADFILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER
        ws.column_dimensions[letter(key)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}1"


def row_formulas(r: int, t: dict) -> dict:
    """Formulas that keep themselves right as you edit names and variants."""
    n, num, var = (f"${letter(k)}" for k in ("name", "number", "variant"))
    same = f'{n}$2:{n}{r},""&{n}{r},{num}$2:{num}{r},""&{num}{r},{var}$2:{var}{r},""&{var}{r}'
    every = (
        f'{n}$2:{n}${MAX_ROWS},""&{n}{r},{num}$2:{num}${MAX_ROWS},""&{num}{r},'
        f'{var}$2:{var}${MAX_ROWS},""&{var}{r}'
    )
    cid = f"${letter('id')}{r}"
    box = ref(t["sheets"]["lists"], f"${BOX_SIZE[0]}${BOX_SIZE[1:]}")
    return {
        # which copy of this card this row is (1st, 2nd, ...) - counts rows above
        "copy": f'=IF({n}{r}="","",COUNTIFS({same}))',
        # how many of this card you own in total
        "count": f'=IF({n}{r}="","",COUNTIFS({every}))',
        # physical slot, derived from the card ID and the box size on the lists sheet
        "location": (
            f'=IF({cid}="","","{t["location"]["box"]}"&INT((VALUE({cid})-1)/{box})+1'
            f'&"{t["location"]["slot"]}"&MOD(VALUE({cid})-1,{box})+1)'
        ),
    }


def write_row(ws, r: int, card: dict, t: dict, only_if_empty: bool):
    """Write one card. only_if_empty=True protects rows the user has already touched."""
    src = {
        "id": card.get("card", ""),
        "name": card.get("name", ""),
        "name_en": card.get("name_en", ""),
        "number": card.get("number", ""),
        "image_front": card.get("front", ""),
        "image_back": card.get("back", ""),
        "ocr": card.get("confidence", ""),
    }
    try:
        src["ocr"] = float(src["ocr"])
    except (TypeError, ValueError):
        src["ocr"] = ""
    for key in ["id"] + AUTO:
        cell = ws.cell(row=r, column=COL[key])
        if only_if_empty and cell.value not in (None, ""):
            continue
        if src[key] != "":
            cell.value = src[key]

    for key, f in row_formulas(r, t).items():
        ws.cell(row=r, column=COL[key]).value = f

    if not only_if_empty:
        ws.cell(row=r, column=COL["status"]).value = t["statuses"]["scanned"]
        ws.cell(row=r, column=COL["variant"]).value = t["variants"]["normal"]
        # a printed name equal to the English one says EN; anything else is for you to say
        if src["name"] and src["name"] == src["name_en"]:
            ws.cell(row=r, column=COL["language"]).value = "EN"


def style_body(ws, last_row: int, t: dict, platforms: list[str]):
    centred = ("id", "number", "copy", "count", "condition", "language")
    for r in range(2, last_row + 1):
        for key, _w, owner in COLUMNS:
            c = ws.cell(row=r, column=COL[key])
            c.font = Font(name=FONT, size=10)
            c.border = BORDER
            c.fill = GREY if owner == "auto" else YELLOW
            if key in ("price", "sold_price"):
                c.number_format = MONEY
            elif key == "sold_on":
                c.number_format = t["date_format"]
            elif key == "ocr":
                c.number_format = "0.00"
                c.alignment = Alignment(horizontal="center")
            elif key in centred:
                c.alignment = Alignment(horizontal="center")

    def dropdown(values, key):
        d = DataValidation(
            type="list",
            formula1='"' + ",".join(values) + '"',
            allow_blank=True,
            showDropDown=False,
        )
        ws.add_data_validation(d)
        d.add(f"{letter(key)}2:{letter(key)}{max(last_row, 2)}")

    dropdown(t["statuses"].values(), "status")
    dropdown(CONDITIONS, "condition")
    dropdown(t["variants"].values(), "variant")
    dropdown(CARD_LANGUAGES, "language")
    dropdown(platforms, "platform")

    rng = f"{letter('status')}2:{letter('status')}{max(last_row, 2)}"
    green = PatternFill("solid", fgColor="C6EFCE")
    blue = PatternFill("solid", fgColor="DDEBF7")
    amber = PatternFill("solid", fgColor="FFE699")
    for status, fill in (
        ("sold", green),
        ("shipped", green),
        ("listed", blue),
        ("reserved", amber),
    ):
        ws.conditional_formatting.add(
            rng,
            CellIsRule(operator="equal", formula=[f'"{t["statuses"][status]}"'], fill=fill),
        )

    # flag anything the OCR wasn't sure about
    ocr = f"{letter('ocr')}2:{letter('ocr')}{max(last_row, 2)}"
    red = PatternFill("solid", fgColor="FFC7CE")
    ws.conditional_formatting.add(ocr, CellIsRule(operator="lessThan", formula=["1"], fill=red))


# --------------------------------------------------------------------------
def sheet(wb, name: str, index: int | None = None):
    """The named sheet, emptied - or a new one."""
    if name in wb.sheetnames:
        ws = wb[name]
        ws.delete_rows(1, ws.max_row or 1)
        return ws
    return wb.create_sheet(name, index)


def build_lists(wb, t: dict, lang: str, currency: str, box_size: int, platforms: list[str]):
    ws = sheet(wb, t["sheets"]["lists"])
    lt = t["lists"]
    ws["A1"], ws["B1"] = lt["setting"], lt["value"]
    rows = [(BOX_SIZE, lt["box_size"], box_size), (CURRENCY, lt["currency"], currency)]
    rows.append((LANGUAGE, lt["language"], lang))
    for cell, label, value in rows:
        ws[f"A{cell[1:]}"] = label
        ws[cell] = value
    ws["A5"] = lt["note"]
    for cell in ("A1", "B1"):
        ws[cell].font = Font(name=FONT, bold=True)
    ws[BOX_SIZE].fill = YELLOW
    ws["A5"].font = Font(name=FONT, size=9, italic=True, color="808080")

    lists = [
        (title(t, "status", currency), list(t["statuses"].values())),
        (title(t, "condition", currency), CONDITIONS),
        (title(t, "variant", currency), list(t["variants"].values())),
        (title(t, "language", currency), CARD_LANGUAGES),
        (title(t, "platform", currency), platforms),
    ]
    for col, (head, values) in enumerate(lists, 4):
        ws.cell(row=1, column=col, value=head).font = Font(name=FONT, bold=True)
        for i, v in enumerate(values, 2):
            ws.cell(row=i, column=col, value=v).font = Font(name=FONT, size=10)
        ws.column_dimensions[get_column_letter(col)].width = 20
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 10

    r = 12
    ws.cell(row=r, column=1, value=t["conditions"]["title"]).font = Font(name=FONT, bold=True)
    for i, code in enumerate(CONDITIONS, 1):
        ws.cell(row=r + i, column=1, value=code).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r + i, column=2, value=t["conditions"][code]).font = Font(name=FONT, size=10)
    source = ws.cell(row=r + 9, column=1, value=t["conditions"]["source"])
    source.font = Font(name=FONT, size=9, italic=True)


def build_overview(wb, t: dict, currency: str):
    ws = sheet(wb, t["sheets"]["overview"], 0)
    o, st = t["overview"], t["statuses"]

    def A(key):
        c = letter(key)
        return ref(t["sheets"]["inventory"], f"${c}$2:${c}${MAX_ROWS}")

    ws["A1"] = o["title"]
    ws["A1"].font = Font(name=FONT, bold=True, size=16, color="1F3864")
    ws["A2"] = o["note"]
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="808080")

    rows = [
        (o["stock"], None),
        (o["total"], f'=COUNTIF({A("id")},"<>")'),
        (o["unrecognised"], f'=COUNTIFS({A("id")},"<>",{A("name")},"")'),
        (o["unsure"], f'=COUNTIFS({A("ocr")},"<1",{A("ocr")},"<>")'),
        (o["distinct"], f'=COUNTIFS({A("id")},"<>",{A("copy")},1)'),
        (o["with_duplicates"], f'=COUNTIFS({A("id")},"<>",{A("count")},">1")'),
        ("", None),
        (o["status"], None),
    ]
    rows += [(s, f'=COUNTIF({A("status")},"{s}")') for s in st.values()]
    rows += [
        (o["no_status"], f'=COUNTIFS({A("id")},"<>",{A("status")},"")'),
        ("", None),
        (o["money"].format(currency=currency), None),
    ]
    money_rows = [  # amounts of money, formatted as such
        (o["listed_value"], f'=SUMIF({A("status")},"{st["listed"]}",{A("price")})'),
        (o["sold_total"], f"=SUM({A('sold_price')})"),
        (o["to_ship"], f'=SUMIF({A("status")},"{st["sold"]}",{A("sold_price")})'),
        (
            o["average"],
            f'=IFERROR(SUM({A("sold_price")})/COUNTIF({A("sold_price")},">0"),0)',
        ),
    ]
    rows += money_rows + [
        ("", None),
        (o["todo"], None),
        (o["no_set"], f'=COUNTIFS({A("id")},"<>",{A("set")},"")'),
        (o["no_condition"], f'=COUNTIFS({A("id")},"<>",{A("condition")},"")'),
        (o["no_price"], f'=COUNTIFS({A("id")},"<>",{A("price")},"")'),
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
            if (label, formula) in money_rows:
                c.number_format = "#,##0.00"
        r += 1
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 14

    r += 1
    ws.cell(row=r, column=1, value=o["legend"]).font = Font(
        name=FONT, bold=True, size=11, color="1F3864"
    )
    for key in ("yellow", "grey", "red"):
        r += 1
        label, text = o[key]
        ws.cell(row=r, column=1, value=label).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r, column=2, value=text).font = Font(name=FONT, size=9)


def build_duplicates(wb, t: dict, currency: str) -> int:
    """
    Rebuilt every run from the inventory - so a name or number you corrected there counts,
    not what the OCR first read into cards.csv. Grouped like the copy and count formulas:
    by name, number and variant.
    """
    inv = wb[t["sheets"]["inventory"]]
    groups: dict[tuple, list[str]] = {}
    for r in range(2, (inv.max_row or 1) + 1):
        cid = inv.cell(row=r, column=COL["id"]).value
        name = str(inv.cell(row=r, column=COL["name"]).value or "").strip()
        if cid in (None, "") or not name:
            continue
        number = str(inv.cell(row=r, column=COL["number"]).value or "").strip()
        variant = str(inv.cell(row=r, column=COL["variant"]).value or "").strip()
        groups.setdefault((name, number, variant), []).append(str(cid))
    dupes = sorted(
        ((k, v) for k, v in groups.items() if len(v) > 1), key=lambda kv: (-len(kv[1]), kv[0])
    )

    ws = sheet(wb, t["sheets"]["duplicates"])
    d = t["duplicates"]
    ws["A1"] = d["title"]
    ws["A1"].font = Font(name=FONT, bold=True, size=13, color="1F3864")
    ws["A2"] = d["note"]
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="808080")

    heads = [title(t, k, currency) for k in ("name", "number", "variant", "count")] + [d["ids"]]
    for i, h in enumerate(heads, 1):
        c = ws.cell(row=4, column=i, value=h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HEADFILL
    for r, ((name, number, variant), ids) in enumerate(dupes, 5):
        for i, v in enumerate((name, number, variant, len(ids), ", ".join(ids)), 1):
            ws.cell(row=r, column=i, value=v).font = Font(name=FONT, size=10, bold=i == 4)
    if not dupes:
        ws.cell(row=5, column=1, value=d["none"]).font = Font(name=FONT, size=10, italic=True)
    for col, w in zip("ABCDE", (22, 10, 14, 9, 60), strict=True):
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
        "--lang",
        choices=texts.languages(),
        default=None,
        help=f"language of a new workbook (default {texts.DEFAULT_LANGUAGE}); "
        "an existing one keeps its own",
    )
    p.add_argument(
        "--currency",
        choices=sorted(texts.currencies()),
        default=None,
        help=f"currency of a new workbook (default {texts.DEFAULT_CURRENCY}); "
        "an existing one keeps its own",
    )
    p.add_argument(
        "--box-size",
        type=int,
        default=None,
        help=f"cards per storage box, for the location column (default {DEFAULT_BOX_SIZE}, "
        "or what the workbook already says)",
    )


def run(args) -> int:
    sorted_dir = Path(args.sorted_dir or paths.home() / paths.SORTED).expanduser()
    out = Path(args.out or paths.home() / paths.TRACKER).expanduser()
    cards = read_cards(sorted_dir)

    wb = load_workbook(out) if out.exists() else None
    lang, currency, box = detect(wb) if wb else (None, None, None)
    for asked, kept, what in ((args.lang, lang, "language"), (args.currency, currency, "currency")):
        if asked and kept and asked != kept:
            print(f"  ! {out.name} was made in {what} {kept} and stays so - {asked} ignored")
    lang = lang or args.lang or texts.DEFAULT_LANGUAGE
    currency = currency or args.currency or texts.DEFAULT_CURRENCY
    box = args.box_size or box or DEFAULT_BOX_SIZE
    t = texts.language(lang)
    platforms = texts.currencies()[currency]["platforms"]

    fresh = wb is None
    if fresh:
        wb = Workbook()
        wb.remove(wb.active)
        for key in ("overview", "inventory", "duplicates", "lists"):
            wb.create_sheet(t["sheets"][key])
    inv = sheet_or_new(wb, t["sheets"]["inventory"])
    style_header(inv, t, currency)

    # index the rows that are already there, by card ID
    existing = {}
    for r in range(2, (inv.max_row or 1) + 1):
        v = inv.cell(row=r, column=COL["id"]).value
        if v not in (None, ""):
            existing[str(v).strip()] = r

    added = 0
    next_row = max(existing.values(), default=1) + 1
    for card in cards:
        cid = card["card"].strip()
        if cid in existing:
            write_row(inv, existing[cid], card, t, only_if_empty=True)
        else:
            write_row(inv, next_row, card, t, only_if_empty=False)
            existing[cid] = next_row
            next_row += 1
            added += 1

    last_row = max(existing.values(), default=1)
    style_body(inv, last_row, t, platforms)
    n_dupes = build_duplicates(wb, t, currency)
    build_lists(wb, t, lang, currency, box, platforms)
    build_overview(wb, t, currency)
    overview = t["sheets"]["overview"]
    wb.move_sheet(overview, offset=-wb.sheetnames.index(overview))

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    print(f"{'Created' if fresh else 'Updated'}: {out}  ({t['name']}, {currency})")
    print(f"  {len(cards)} card(s) in cards.csv")
    print(f"  {added} new row(s) added, {len(existing) - added} kept as they were")
    print(f"  {n_dupes} card(s) you own more than once -> see '{t['sheets']['duplicates']}'")
    if not fresh:
        print("  Nothing you typed was overwritten.")
    return 0


def sheet_or_new(wb, name: str):
    """The named sheet as it is, or a new one - for the inventory, which is never emptied."""
    return wb[name] if name in wb.sheetnames else wb.create_sheet(name)
