# tools

Scripts for working on cropdeck itself - not part of the installed package.

| file | what |
|---|---|
| `demo_image.py` | rebuilds `docs/assets/demo-*.png`: draws a synthetic tray, runs `cropdeck split` on it and lays out scans and result (needs `pillow` and network for the font) |
| `fonts.py` | fetches Inter, the font both generators use |
| `wordmark.py` | rebuilds `docs/assets/logo-*.svg` from the icon and Inter Bold (needs `fonttools` and network for the font) |
