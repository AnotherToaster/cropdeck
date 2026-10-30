# Changelog

All notable changes to cropdeck are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0, minor versions may change
the command line or file formats.

## [Unreleased]

### Added

- `cropdeck run FOLDER`: crops every card out of full-platen flatbed scans at true scale and pairs
  each front with its own back by position on the glass. Odd scans are fronts, even scans the same
  tray's backs.
- Guards that stop a run before anything is written: card counts that differ between fronts and
  backs, a "backs" scan that does not look like card backs, cards that moved between the scans.
- Resume: finished scans are skipped, card numbering continues, `cards.csv` is merged, not
  replaced. `cropdeck status` shows how far along a folder is.
- A proof sheet per tray, every front beside the back it was paired with.
- Optional steps: `--names` reads Pokémon names and collector numbers by OCR (Tesseract);
  `--tracker` keeps a spreadsheet of the collection in which your own edits are never overwritten.
