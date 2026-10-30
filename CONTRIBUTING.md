# Contributing

Thanks for helping. A few things keep cropdeck reliable.

## Setup

```bash
git clone https://github.com/AnotherToaster/cropdeck.git && cd cropdeck
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[all,dev]"
pre-commit install                                 # ruff lint + format before every commit
```

`--names` and the naming test need the Tesseract engine (see the README).

## Tests

```bash
python -m unittest discover -s tests
```

The tests draw abstract cards of true size (`tests/synth.py`). **Never add real card images or
scans** - card artwork is copyrighted. If a bug shows up on a real scan, reproduce it with a
synthetic tray and add that as the test.

A change in behaviour comes with a test, and the test must fail without the change.

## What must never break

1. A front stays with its own back - pairing is by position on the glass, never by list order.
2. Refuse rather than guess: every guard stops the run before anything is written.
3. True scale: cards are rotated and cropped, never resized to a nominal box.
4. Thresholds are in millimetres, converted through the measured dpi.
5. A user's own edits (spreadsheet, extra CSV columns) survive every run.
6. Nothing in the scans folder is ever changed or deleted.

`docs/how-it-works.md` explains why each step is built the way it is.

## Commits and pull requests

- One change per commit, [Conventional Commits](https://www.conventionalcommits.org/):
  `feat: …`, `fix: …`, `docs: …`, `refactor: …`, `test: …`, `chore: …`.
- Keep `docs/` and `CHANGELOG.md` (under *Unreleased*) true with the change.
- CI must be green: ruff and the tests on Linux, macOS and Windows.
