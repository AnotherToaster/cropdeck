# tools

Scripts for working on cropdeck itself - not part of the installed package.

| file | what |
|---|---|
| `demo_image.py` | rebuilds `docs/assets/demo-*.png`: draws a synthetic tray, runs `cropdeck split` on it and lays out scans and result (needs `pillow` and network for the font) |
| `pwa_icons.py` | rebuilds the app window's icons (`cropdeck/ui/static/img/icon-*.png`) from `icon.svg` (needs `cairosvg`) |
| `fonts.py` | fetches Inter, the font both generators use |
| `wordmark.py` | rebuilds `cropdeck/ui/static/img/logo-*.svg` from the icon and Inter Bold (needs `fonttools` and network for the font) |
