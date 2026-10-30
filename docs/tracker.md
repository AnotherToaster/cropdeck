# The tracker spreadsheet

`cropdeck track` (or `cropdeck run --tracker`) builds and updates `card-tracker.xlsx` from
`cards.csv`. Run it after every scan session, as often as you like.

**Your edits are never overwritten.** Rows are keyed by card ID. New cards are appended; for cards
already in the sheet, the automatic columns are only filled while they are still empty, and nothing
you typed is ever cleared (`tests/test_pipeline.py` checks this).

## Language and currency

```bash
cropdeck track sorted                               # English, EUR
cropdeck track sorted --lang de --currency CHF      # German, Swiss francs
```

A workbook keeps the language and currency it was created with - they are stored on its *Lists*
sheet - so a later run never half-translates it or relabels your prices. Asking for another one on
an existing workbook is reported and ignored; start a new file for that.

| | available |
|---|---|
| languages | English (`en`), German (`de`) |
| currencies | EUR, USD, GBP, CHF - each with the platforms offered in the *Platform* dropdown |

**Adding a language** is adding one file: copy `cropdeck/data/locales/en.json` to `<code>.json` and
translate the values (not the keys). A test checks that every language has exactly the texts
English has. **Adding a currency** is one entry in `cropdeck/data/currencies.json` with its
platforms.

## Sheets

| Sheet | What | |
|---|---|---|
| **Inventory** | one row per physical card - the sheet you edit | kept |
| **Overview** | counts per status, money in and out, cards that need attention | rebuilt each run |
| **Duplicates** | cards you own more than once, grouped by name, number and variant - read from the inventory, so your corrections count | rebuilt each run |
| **Lists** | settings (box size, currency, language) and the dropdown values | rebuilt, settings kept |

## Columns in Inventory

Grey columns are automatic, yellow ones are yours.

| Column | Owner | Meaning |
|---|---|---|
| ID | auto | card number; ties the front image to the back |
| Name / Name EN | auto | as printed (OCR) / the English name |
| Set | you | e.g. Jungle, Celebrations |
| Number | auto | collector number, e.g. 9/25 |
| Language, Variant, Condition, Grading | you | EN if the printed name is the English one, otherwise yours to fill in; Normal / Holo / ...; Cardmarket condition scale M NM EX GD LP PL PO; grading |
| Copy, Count, Location | auto (formulas) | which copy this is, how many you own, the physical box slot computed from the ID (`--box-size`, default 60, kept once set) |
| Status | you | Scanned → Ready → Listed → Reserved → Sold → Shipped, or Keeping |
| Platform, Listing URL, Price, Sold, Sold on, Buyer / note | you | the sale; prices in the workbook's currency |
| Front image / Back image, OCR | auto | image file names, recognition confidence (check anything below 1.00) |
