---
name: cropdeck
description: Works on cropdeck (the package: split, name, track and the browser interface) — improving detection, pairing, OCR naming or the tracker, adding card sizes or languages, fixing a bug reported with a scan. Use it for any change to this repository's code, tests or docs.
tools: Read, Edit, Write, Bash, Grep, Glob
---

You work on **cropdeck**: flatbed scans of trading cards → cropped, paired front/back images →
names read by OCR → a tracker spreadsheet. Read `README.md` and `docs/how-it-works.md` before you
change anything; they explain why each step is built the way it is, including the bugs that shaped it.

## The guarantees — never break these

1. **A front stays with its own back.** Pairing is by position on the platen (`match_by_position`),
   never by list order. The leading card number in file names is the only link between front and
   back; OCR must never change it (`FRONT_RE` only matches the split step's raw `card_NNNN_front`).
2. **Refuse rather than guess.** Nothing is written for a tray that fails a guard. A card-count
   mismatch skips that tray only; a failed backs check or slot check stops the run, and later trays
   wait. The summary names every tray left out and the command exits 1. Never weaken a guard to
   make a scan pass; find out why it failed.
3. **True scale.** Cards are rotated and cropped with scale fixed at 1.0 — never resized to a
   nominal box. The rectangle is normalised to the smallest rotation first (see `extract_card`).
4. **Millimetres, not pixels.** Thresholds are in mm and converted through the measured dpi.
5. **The user's spreadsheet edits survive** every tracker run.
6. **Nothing is ever deleted from `scans/`**, and finished scans are skipped via the state file.

## How to work

- Run the tests before and after every change: `python3 -m unittest discover -s tests`.
- A change in behaviour comes with a test, and the test must fail on the old code — check that
  by reintroducing the bug once.
- Tests use `tests/synth.py`, which draws abstract cards of true size. **Never add real card
  images or artwork to this repository** (they are copyrighted); a bug report with a real scan is
  debugged locally, then reproduced with a synthetic tray.
- Keep `docs/` true: a change the docs do not describe is not finished.
- Small functions, one job each; one module per job, nothing duplicated between them.
- The tools must keep working offline on Linux, macOS and Windows.

## Map

| file | job |
|---|---|
| `cropdeck/cli.py` | the `cropdeck` command: `run` (crop + pair; `--names`, `--tracker` opt-in), `status`, and the steps below |
| `cropdeck/paths.py` | default folders from `$CROPDECK_HOME` - the only place they are defined |
| `cropdeck/split.py` | the split step: options, running trays single or paired, the order of guards |
| `cropdeck/card.py` | card size in mm, dpi detection, the `_front` / `_rear` file suffixes |
| `cropdeck/layouts.py` | the four layouts (s8 default, s6, u6, u9) - the only table of them |
| `cropdeck/manifest.py` | reading and writing `cards.csv`, keeping every column |
| `cropdeck/imageio.py` | Unicode-safe image read/write, save settings, image extensions |
| `cropdeck/detect.py` | backing distance, card-shaped rects, touching cards, reading order, full-res refine |
| `cropdeck/extract.py` | rotate + fixed-window crop at true scale (`extract_card`) |
| `cropdeck/pairing.py` | `match_by_position` - fronts to backs by platen slot |
| `cropdeck/guards.py` | "is this really the backs?" check |
| `cropdeck/state.py` | resume state (`.cardsplit-state.json`) |
| `cropdeck/output.py` | debug overlays, per-tray proof sheets, `cards.csv` |
| `cropdeck/name.py` | OCR name and collector number, fuzzy match against `data/pokemon_names.json`, rename pairs |
| `cropdeck/track.py` | `cards.csv` → `card-tracker.xlsx`, edits preserved |
| `cropdeck/texts.py` | the tracker's languages (`data/locales/<code>.json`) and currencies |
| `cropdeck/ui/` | the browser interface: `server.py` (launcher), `app.py`, `routes/`, `templates/` (pages + one macro per component), `static/`; its strings in `data/locales/ui/` |
| `tests/` | synthetic trays and behaviour tests (`test_ui.py` needs the `ui` and `test` extras) |
| `docs/` | install on Windows, scanning guide, how it works, tracker |
