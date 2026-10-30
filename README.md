<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img alt="cropdeck" src="docs/assets/logo-light.svg" height="72">
  </picture>
</h1>

True-scale scans of trading cards (TCG), front and back paired. Turn flatbed scans into clean,
correctly paired front/back images, optionally named by what is printed on the card and tracked
in a spreadsheet.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/demo-dark.png">
  <img alt="Two flatbed scans - six cards face up, then the same six flipped in place - and cropdeck's output: each card cut out upright, its front next to its own back." src="docs/assets/demo-light.png">
</picture>

<sub>Synthetic cards drawn by <code>tools/demo_image.py</code>; the right-hand side is real cropdeck output.</sub>

```
scan 6 cards  →  flip each in place  →  scan the backs  →  one command
                                                            │
             ┌──────────────────────────────────────────────┼──────────────────────┐
             ▼                                              ▼                      ▼
  0001_Snivy_5-25_front.png                            cards.csv          Karten-Tracker.xlsx
  0001_Snivy_5-25_back.png                       (machine-readable)       (the sheet you edit)
```

Built for Pokémon cards (63 × 88 mm), in five languages (EN, DE, FR, ES, IT). Runs offline on
Linux, WSL, macOS or Windows.

## Why it exists

A scanner's own "auto crop" cuts trading cards off (business-card presets are 33 mm too short),
trims holo cards whose edges reflect, and knows nothing about fronts and backs. With a hundred
cards and identical backs, a mispaired front/back is invisible and cannot be undone. cropdeck uses
the scanner for one thing only — an uncropped image of the whole glass — and does everything else
where it can be checked.

What it guarantees, in order of importance:

1. **A front stays with its own back.** Pairing is by where the card lay on the glass, checked
   four ways, and the run stops rather than guesses.
2. **True scale.** Cards are rotated and cropped, never stretched: 63 × 88 mm plus a 1 mm margin,
   identical for every card.
3. **Cards identify themselves.** Name and collector number are read off the card and matched
   against 2 755 printed names of all 1 025 species.

## Quick start

```bash
pip install ".[all]"                 # from a clone of this repo; needs a recent pip (21.3+)

mkdir -p mycards/scans               # put your scans here: odd = fronts, even = their backs
cropdeck run mycards                 # crop and pair -> mycards/sorted
cropdeck run mycards --names --tracker   # also read names and update the spreadsheet
```

Cropping and pairing need only OpenCV and NumPy. `--names` needs the Tesseract engine
(Linux `sudo apt install tesseract-ocr`, macOS `brew install tesseract`, Windows
<https://github.com/UB-Mannheim/tesseract/wiki>); `--tracker` needs openpyxl, both included in
`[all]`. Without a folder argument, `cropdeck run` uses `$CROPDECK_HOME` or the current directory.

The steps can also be run on their own, with every option:

```bash
cropdeck split mycards/scans -o mycards/sorted --pair --expect 8   # find, crop, pair
cropdeck name  mycards/sorted                                     # read names, rename
cropdeck track mycards/sorted -o mycards/Karten-Tracker.xlsx      # update the sheet
cropdeck status mycards                                           # how far along, changes nothing
```

Re-run as often as you like: finished scans are skipped, numbering continues, the CSV is appended
to, and nothing you typed into the spreadsheet is ever overwritten.

## What you get

| Output | What |
|---|---|
| `NNNN_<name>_<number>_front.png` / `_back.png` | the cards; the same number = the same physical card |
| `cards.csv` | one row per card: name, English name, collector number, OCR confidence, file names, plus empty `set`, `condition`, `price_chf`, `notes` |
| `_pairs/<scan>_pairs.jpg` | a proof sheet per tray: every front beside the back it was matched with |
| `_debug/` | with `--debug`: what was detected on each scan |
| `Karten-Tracker.xlsx` | inventory, duplicates and a summary, built from `cards.csv` (German sheet names) |

## Documentation

| | |
|---|---|
| [docs/scanning.md](docs/scanning.md) | how to scan: settings, layout, the daily loop, troubleshooting |
| [docs/how-it-works.md](docs/how-it-works.md) | every step of the pipeline, why it is built that way, and its limits |
| [docs/tracker.md](docs/tracker.md) | the spreadsheet: sheets, columns, what is yours and what is automatic |

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests draw their own abstract cards of true size (`tests/synth.py`), so no card artwork is
needed or included. They cover pairing by position, true scale, orientation, resume, the
"is this really the backs?" guard, dark and light backing, name matching and the tracker keeping
your edits.

## Working on it with Claude Code

The repo ships a subagent, [`.claude/agents/cropdeck.md`](.claude/agents/cropdeck.md), that knows
the pipeline, its guarantees and its tests. Open the repo in Claude Code and ask for it by name
("use the cropdeck agent to …"), or let Claude pick it for card-scanning work.

## Data and names

`cropdeck/data/pokemon_names.json` maps printed names to English names. It was generated from the
[PokéAPI](https://pokeapi.co/) species data. Pokémon and all character names are trademarks of
Nintendo, Creatures Inc. and GAME FREAK inc.; this project is not affiliated with them. No card
images are included in this repository.

## Contributing

Bug reports and pull requests are welcome - see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests
and commit conventions, and [CHANGELOG.md](CHANGELOG.md) for what changed between versions.
Security problems go privately to cropdeck@dr-dev.ch ([SECURITY.md](SECURITY.md)).

## Licence

[MIT](LICENSE) © 2026 dr-dev
