# The tracker spreadsheet

`cropdeck track` (or `cropdeck run --tracker`) builds and updates `Karten-Tracker.xlsx` from `cards.csv`. Run it after every scan
session, as often as you like. The sheet and column names are in German.

**Your edits are never overwritten.** Rows are keyed by card ID. New cards are appended; for cards
already in the sheet, the automatic columns are only filled while they are still empty, and nothing
you typed is ever cleared (`tests/test_pipeline.py` checks this).

## Sheets

| Sheet | What | |
|---|---|---|
| **Inventar** | one row per physical card — the sheet you edit | kept |
| **Übersicht** | counts per status, money in and out, cards that need attention | rebuilt each run |
| **Dubletten** | cards you own more than once | rebuilt each run |
| **Listen** | the dropdown values and settings (box size) | rebuilt each run |

## Columns in Inventar

Grey columns are automatic, yellow ones are yours.

| Column | Owner | Meaning |
|---|---|---|
| ID | auto | card number; ties the front image to the back |
| Name / Name EN | auto | as printed (OCR) / the English name |
| Set | you | e.g. Jungle, Celebrations |
| Nummer | auto | collector number, e.g. 9/25 |
| Sprache, Variante, Zustand, Grading | you | language; Normal / Holo / …; Cardmarket condition scale M NM EX GD LP PL PO; grading |
| Kopie, Anzahl, Lagerort | auto (formulas) | which copy this is, how many you own, the physical box slot computed from the ID (`--box-size`, default 60) |
| Status | you | Gescannt → Bereit → Online → Reserviert → Verkauft → Versendet, or Behalten |
| Plattform, Listing-URL, Preis CHF, Verkauft CHF, Verkauft am, Käufer / Notiz | you | the sale |
| Bild vorne / Bild hinten, OCR | auto | image file names, recognition confidence (check anything below 1.00) |

The platform list and the currency (CHF) are set at the top of `cropdeck/track.py`.
