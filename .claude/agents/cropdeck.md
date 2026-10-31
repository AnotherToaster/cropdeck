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
2. **Refuse rather than guess.** Nothing is written for a tray that fails a guard (count, backs,
   slots), and the run stops there: later trays wait, so card numbers stay in tray order. The
   summary says why and the command exits 1. A fix is a recorded choice (`fixes.py`), never an
   edit to a scan. Never weaken a guard to make a scan pass; find out why it failed.
3. **True scale.** Cards are rotated and cropped with scale fixed at 1.0 — never resized to a
   nominal box. The rectangle is normalised to the smallest rotation first (see `extract_card`).
4. **Millimetres, not pixels.** Thresholds are in mm and converted through the measured dpi.
5. **The user's edits survive**: spreadsheet edits every tracker run, and fields typed in the
   review (listed in `cards.csv`'s `typed` column) every name run (`manifest.recognised`).
6. **Nothing in `scans/` is ever written, renamed or deleted**, and finished scans are skipped via
   the state file.

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
| `cropdeck/split.py` | the split step: options (`options()` for callers that are not the command line), single scans, printing the paired run |
| `cropdeck/process.py` | the paired run, tray by tray, as events (`TrayStart`, `CardDone`, `TrayDone`, `TrayStopped`, `RunDone`); the order of guards |
| `cropdeck/trays.py` | which scans are which tray, and each tray's status (done, ready, needs backs, stopped, skipped) |
| `cropdeck/fixes.py` | the fixes for a stopped tray, recorded in the state file |
| `cropdeck/cut.py` | reading a scan and cutting its cards, without printing |
| `cropdeck/card.py` | card size in mm, dpi detection, the `_front` / `_rear` file suffixes |
| `cropdeck/layouts.py` | the four layouts (s8 default, s6, u6, u9) - the only table of them |
| `cropdeck/manifest.py` | reading and writing `cards.csv`, keeping every column |
| `cropdeck/imageio.py` | Unicode-safe image read/write, save settings, image extensions |
| `cropdeck/detect.py` | backing distance, card-shaped rects, touching cards, reading order, full-res refine |
| `cropdeck/extract.py` | rotate + fixed-window crop at true scale (`extract_card`) |
| `cropdeck/pairing.py` | `match_by_position` - fronts to backs by platen slot; `match_slots` and `moved_slots` for a tray that does not add up |
| `cropdeck/guards.py` | "is this really the backs?" check; the folder's known back designs |
| `cropdeck/state.py` | resume state (`.cardsplit-state.json`) |
| `cropdeck/output.py` | debug overlays, per-tray proof sheets, `cards.csv` |
| `cropdeck/name.py` | OCR name and collector number, fuzzy match against `data/pokemon_names.json`, rename pairs |
| `cropdeck/track.py` | `cards.csv` → `card-tracker.xlsx`, edits preserved |
| `cropdeck/texts.py` | the tracker's languages (`data/locales/<code>.json`) and currencies |
| `cropdeck/ui/` | the browser interface: `server.py` (launcher), `app.py`, `routes/`, `templates/` (pages, partials, one macro per component), `static/`; `scan_view.py`, `stop_view.py` and `review_view.py` decide what a page shows, `folders.py` the setup's folder browser and checks, `session.py` the folder and its layout, `forms.py` reads posted forms, `runner.py` runs processing in a worker thread, `live.py` the events and the folder watcher, `thumbs.py` the small images; its strings in `data/locales/ui/` |
| `tests/` | synthetic trays and behaviour tests (`test_ui.py` needs the `ui` and `test` extras) |
| `docs/` | install on Windows, scanning guide, how it works, tracker |
