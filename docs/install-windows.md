# Installing on Windows

About ten minutes, once. Nothing here needs WSL or a terminal you have used before.

## 1. Python

1. Download Python 3.10 or newer from <https://www.python.org/downloads/windows/>.
2. Run the installer and tick **"Add python.exe to PATH"** on the first screen, then
   *Install Now*.
3. Open **PowerShell** (Start menu → type `powershell`) and check:

   ```powershell
   py --version
   ```

   It prints `Python 3.x.y`. If it says the command is unknown, restart PowerShell or reinstall
   with the PATH box ticked.

## 2. cropdeck

```powershell
py -m pip install "cropdeck[all] @ https://github.com/AnotherToaster/cropdeck/archive/refs/heads/main.zip"
```

`[all]` brings the optional parts too: reading names, the spreadsheet and the browser interface.
Without it you get cropping and pairing only.

## 3. Tesseract - only for reading names

Cropping and pairing work without it. For `--names`:

1. Download the Windows installer from <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Install it with the defaults. cropdeck finds it in `C:\Program Files\Tesseract-OCR` (or, if
   you installed it for your user only, under `%LOCALAPPDATA%\Programs`) without any PATH setting.

If cropdeck cannot find it, it says so and tells you where to get it.

## 4. First run

```powershell
py -m cropdeck ui
```

The browser opens on setup: choose or make a folder for your cards (for example
`Documents\cards`), pick how the cards lie on the glass, and set the scans path it shows as your
scanner's save folder (see [scanning.md](scanning.md) for the settings). From then on the page
shows the next step. Folder names with spaces or umlauts are fine.

Or on the command line, with a `scans` folder inside your cards folder:

```powershell
py -m cropdeck run "$HOME\Documents\cards"
py -m cropdeck run "$HOME\Documents\cards" --names --tracker
```

The first line crops and pairs; the second also reads names and keeps the spreadsheet
`card-tracker.xlsx` next to the `scans` folder.

`py -m cropdeck` always works. The shorter `cropdeck ui` and `cropdeck run …` work too if pip's script folder is on
your PATH - pip prints a warning naming that folder when it is not.

## Updating

```powershell
py -m pip install --upgrade "cropdeck[all] @ https://github.com/AnotherToaster/cropdeck/archive/refs/heads/main.zip"
```

Your scans, cards and spreadsheet are never touched by an update.
