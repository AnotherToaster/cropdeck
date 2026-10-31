# How it works

What each step does, why it is built that way, and where the limits are. Read this when something
behaves oddly. The numbers quoted were measured on real scans during development.

```
scans/                       cropdeck split              sorted/
  tray_0001.jpg  ──┐                                         card_0001_front.png
  tray_0002.jpg  ──┴──▶  detect → refine → crop  ──▶         card_0001_rear.png
  tray_0003.jpg  ──┐     pair by platen position             ...
  tray_0004.jpg  ──┘                                         cards.csv, _pairs/, _debug/
                                    │
                                    ▼
                              cropdeck name  ── OCR name + number, fuzzy match in 5 languages (optional)
                                    │
                                    ▼
                              0001_Charmander_9-25_front.png / _rear.png
                                    │
                                    ▼
                              cropdeck track  ── card-tracker.xlsx (optional)
```

Dependencies: Python 3.10+, OpenCV, NumPy; pytesseract and the Tesseract engine for naming;
openpyxl for the tracker; FastAPI, Uvicorn and Jinja2 for the browser interface. No requests to the
internet at runtime.

## 1. cropdeck split — from platen scan to single cards

### Resolution
The scan's short edge divided by A4's width (210 mm), snapped to the nearest standard setting
(75 … 1200 dpi). Everything downstream is in millimetres, so the same code works at any resolution.
`--dpi` overrides the guess.

### Card versus backing
A brightness threshold does not work: a dark blue card back on black paper is dark on dark. So the
backing colour is **measured**: the scan is converted to CIE-Lab, the median of a frame of pixels
around the edge of the glass is the backing, and every pixel's distance from it becomes a "cardness"
map. A card is anything that does not look like the backing — which is why white lid and black
paper both work without a switch. Any threshold between 15 and 40 found all cards on both.

### The mask
- Holes are filled by redrawing outer contours solid, so dark artwork does not punch holes into a
  card — without growing its outline, which is the measurement.
- An opening (erode, then dilate) separates touching cards and restores their shape.
- **Closing is never used**: it dilates first and fuses neighbouring cards (an early version turned
  nine cards into four).
- Threshold (8 values) and opening size (7 sizes) are swept as a grid; the combination with the
  most card-shaped rectangles wins. `--expect N` stops the sweep at N.

### What counts as a card
Each contour's `minAreaRect` must have an area within (1 ± tolerance)² of 63 × 88 mm, an aspect
within the tolerance of 0.716, and fill at least 85 % of its own box. Tolerance defaults to 0.18.
A blob larger than 1.5 cards is read as a grid of whole cards and cut back into them, so touching
cards are recovered instead of dropped.

### Reading order
Rows are found by **gaps**, not fixed bands: sorted by y, a new row starts when a card sits more
than 0.6 card heights below the current row's top. (Fixed bands once split a physical row in two;
fronts came out right-then-left and backs left-then-right, and every card got its neighbour's back.)

### Refinement at full resolution
Detection runs on a 1600 px copy (fast, and it suppresses foil speckle). Each card is then
re-measured alone at full resolution with five thresholds; the one closest to 63 × 88 mm on its
**worst axis** wins. This removed soft-shadow errors of up to 16 mm; cards measure within 0.2 % of
true size. `--no-refine` skips it.

### Cutting out — rotate and crop, never rescale
A rotation about the card's centre with **scale locked at 1.0**, a translation to centre it, and a
fixed window of 63 × 88 mm plus `--pad` cut out. Rigid, so every card is at true scale; a detection
that ran wide shows a hair more backing, never a squeezed card. Pixels outside the scan are filled
with the measured backing colour.

The rectangle is first normalised to the **smallest rotation** (±45°). Without that, a card tilted
slightly counter-clockwise is reported as a landscape box at ~87° and the later 90° turn stands it
up upside down (fixed in this repository, found by `tests/test_pipeline.py`). A card that really
lies sideways is turned 90° clockwise; `--no-upright` keeps the glass orientation, `--rotate 180`
fixes an upside-down card.

### Pairing fronts with backs
Odd scans are fronts, even scans the same tray's backs. **Each front is matched to the back whose
centre lies nearest to it on the platen** (with `--back-order mirror`, x is mirrored first). Order
is used to number cards, never to decide which back belongs to which front. Matching is greedy from
the closest pair outward (one-to-one); the acceptance radius is half the smallest distance between
two fronts, so a card that moved halfway towards a neighbour's slot refuses the tray.

### The four guards
1. Front and back scans must hold the same number of cards.
2. The backs scan must contain backs: each card becomes a 48 × 66 greyscale thumbnail; backs are
   all alike, fronts are not. Against a reference stored from the first good tray, backs scored
   11–26 and fronts 60–73 (limit 40). On the first tray, before a reference exists, backs must be
   alike among themselves (limit 26).
3. The slots must line up geometrically (above).
4. A proof sheet per tray in `_pairs/` — the last line of defence, for a human eye.

Nothing is ever written for a tray that fails a guard. A count mismatch (1), or a tray where no
cards are found, skips **that tray only** - the run goes on with the next one. A failed backs check
(2) or slot check (3) **stops the run**: every later tray waits too, because a missing or swapped
scan shifts everything after it. Either way the summary names each tray that was left out, and the
command ends with exit code 1, so `cropdeck run` does not go on to `--names` or `--tracker` and a
script notices.

### Resume
`sorted/.cardsplit-state.json` holds the next card number, every scan already processed (by name and
byte size) and the backs reference. Finished scans can stay in `scans/`; `--status` reports,
`--restart` starts over.

## 2. cropdeck name — identifying the card

### The name
Two bands across the top of the card are tried (older cards place the name lower). The name plate
sits on a colour gradient, so the band is divided by a heavily closed copy of itself to flatten the
illumination before Otsu thresholding; rows that are almost solid ink (the border) are dropped.
Tesseract runs in sparse-text mode (`psm 11`), with `psm 8` as backup — single-line mode returned
nothing on bands that were perfectly legible.

### Matching
Each token is reduced to bare lowercase letters (accents folded, punctuation and digits removed). An
exact hit wins; otherwise `difflib` against names of similar length (±2 letters), accepting
≥ `--min-ratio` (0.82). Tokens shorter than four letters are ignored — short names are too easy to
read out of noise. A token where the name is glued to OCR junk (`asic}Charmander`) is therefore
**not** matched; the name only counts when Tesseract returns it as its own word.

`cropdeck/data/pokemon_names.json` holds 2 755 printed names of all 1 025 species in English, German, French,
Spanish and Italian, each mapped to the English name, so a German card is filed as `Pummeluff`
with `Jigglypuff` beside it. `--lang en` names files in English.

### The collector number
`9/25`-style numbers are small and italic at the bottom, left on older cards, right on modern ones.
Three bands at 3× upscale, two segmentation modes each; candidates are **voted on** (a single pass
read `21/25` as `2/25` about as often as right), filtered for plausibility, and the first reading
seen twice wins.

### Time budget and renaming
Each card gets `--timeout` seconds (15), half for the name, half for the number; no number is
searched when no name was found. `card_0007_front.png` becomes `0007_Snivy_5-25_front.png` and its
back is renamed with it. **The leading number is always kept** — it is what ties front to back — and
an unknown card becomes `0007_unknown_front.png`. Only the split step's raw names are matched, so
re-running never renames a file twice. `cards.csv` is merged, not replaced: a named card's row keeps the tray and slot it came from and
any column you added yourself. `--dry-run` shows the
guesses without renaming.

## 3. cropdeck track

See [tracker.md](tracker.md).

## 4. cropdeck ui — the browser interface (early)

A local web page for the whole loop, served from this computer only (`127.0.0.1:8737`, never the
network) and opened in the browser; installable as an app window. Built in phases from the design
handoff: foundations, the shell (header, navigation, folder and layout) and the components are in;
the scan loop, setup, guard stops, review, collection and settings follow. The cards folder given
to `cropdeck ui FOLDER` is remembered for the next start.

## Design decisions

- **Millimetres, not pixels** — change the resolution and nothing needs retuning.
- **Measure, don't assume** — backing colour, card size, rows and pairing come from the image.
- **Refuse rather than guess** — for a job where a silent error is invisible, a stopped run is fine
  and a wrong answer is not.
- **Sweep instead of tune** — where one threshold could be brittle, several are tried and scored.

## Known limitations

- A black-bordered card on black backing (or white on white) cannot be separated — change backing.
- Only standard 63 × 88 mm cards; jumbo or mini sizes need the constants in `cropdeck/card.py`.
- Trainer and Energy cards are never named — there is no Pokémon name on them.
- Sets are not identified; two sets can share `9/25`. The `set` column is for you.
- Condition and centring are not assessed — the images are faithful enough to judge by eye.
- Tilt beyond ~10° starts to fail the size filters.
- OCR is weaker on older cards (other fonts, ornate plates). Check anything below 1.00 confidence.

## Command reference

```
cropdeck run [FOLDER]   crop + pair FOLDER/scans -> FOLDER/sorted
  --expect N  --dpi N  --debug
  --names               also run the name step
  --tracker             also run the track step
cropdeck status [FOLDER]
cropdeck ui [FOLDER]     the browser interface (early, in development): 127.0.0.1:8737,
                         the cards folder remembered for next time; installable as an app window
  --port N  --no-browser
  --dev                  design checks: ?theme=dark|light, and /_components (every component)

cropdeck split [input ...] [-o OUT]
  --pair                odd scans = fronts, even = their backs
  --back-order same|mirror
  --expect N            cards per scan
  --status / --restart
  --dpi / --out-dpi     scan resolution / resample the output (uniformly)
  --pad MM              backing kept around each card (1.0)
  --tolerance F         size/shape slack (0.18)
  --format / --quality / --max-px
  --rotate / --rotate-back  0|90|180|270, clockwise
  --prefix / --flat     output naming
  --debug               detection overlays in _debug/
  --no-sheet --no-back-check --no-refine --no-upright --no-split-merged

cropdeck name FOLDER
  --dry-run  --lang printed|en  --min-ratio F  --timeout SEC  --no-number

cropdeck track [SORTED_DIR] [-o XLSX]  --lang en|de  --currency EUR|USD|GBP|CHF  --box-size N
```

Defaults for the folders: `$CROPDECK_HOME/scans`, `$CROPDECK_HOME/sorted` and
`$CROPDECK_HOME/card-tracker.xlsx`, or the current directory when `CROPDECK_HOME` is not set.
