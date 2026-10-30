# Scanning guide

The day-to-day instructions. For what happens underneath, see [how-it-works.md](how-it-works.md).

## The one rule

**Odd scan = fronts, even scan = the same cards' backs.** Scanners number files in order, and that
order *is* the pairing. Flip each card **in its own slot** — slot 5 stays slot 5. Flipping the
whole tray over as a block works too: add `--back-order mirror`.

Never delete anything from `scans/`. It is your only original, and the tools remember what they
have already cut (`sorted/.cardsplit-state.json`), so finished scans are simply skipped.

## Scanner settings

| Setting | Value |
|---|---|
| Original size | **A4 / full platen** — never "auto scan", never "business card" |
| Resolution | **400 dpi** (600 for listings that need detail; the tools measure dpi themselves) |
| Format | JPEG, high quality (or PNG) |
| Unsharp mask, descreen, fading correction | **off** |

## Layout

- 2 × 3 cards per scan works; 3 × 3 is faster (12 + 12 passes for 100 cards instead of 17 + 17).
  Tell the tools with `cropdeck run --expect 9`.
- Cards ~5–8 mm apart, ~1 cm from the platen edges. Tilt up to ~10° is corrected, sideways cards
  are stood upright, touching cards are cut apart.
- **Backing:** the scanner's plain white lid is usually best — no dust, no creases. The tools
  measure the backing colour from the edge of the glass, so white and black both work without a
  setting. Use dark paper only for white-bordered cards (and the white lid for black-bordered ones).

## The daily loop

Either works, and they mix freely:

- scan one tray of fronts, flip, scan the backs, run → six more cards
- scan ten trays over an evening, run once → sixty more cards

```bash
cropdeck run mycards                  # mycards/ holds scans/ and receives sorted/
```

Lost track? `cropdeck status mycards` lists what has been processed, what is waiting and the next card number. It changes nothing.

Start the whole collection over from 0001: `--restart`.

## Check it in five seconds

Every tray gets a proof sheet in `sorted/_pairs/`: each front next to the back it was matched with.
A scuff or bent corner on a back confirms it belongs to its front. Look at it after every run —
machine checks can be fooled, your eye on a scuffed corner cannot.

## When it stops

Backs are identical, so a mispaired tray would be invisible. The run therefore **stops before
writing anything** — and skips every later tray too — when:

1. a front scan and its back scan hold a different number of cards;
2. the "backs" scan does not look like backs (you skipped a tray's backs, and every later tray
   would be shifted by one);
3. a card moved more than halfway towards a neighbouring slot between the two scans.

```
! STOPPED on tray_0005.jpg / tray_0006.jpg: neither scan looks like card backs -
  did you scan this tray's backs at all?
  Nothing was written for this tray, and no later tray was touched either.
```

Fix the scans and run again.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Wrong number of cards | run with `--debug` and look in `sorted/_debug/` — it shows exactly what was detected |
| Cards upside down | `--rotate 180`, or `--rotate-back 180` for the backs only |
| More backing than you like around the card | `--pad 0.5` (default 1.0 mm) |
| A name read wrong | `cropdeck name <folder> --dry-run` shows every guess and its confidence; `--min-ratio 0.9` is stricter |
| Trainer / Energy cards | they have no Pokémon name; they come out as `unknown` — fill them in via `cards.csv` |
| A card takes too long | each card gets 15 s, then it is `unknown` and the run moves on; `--timeout 25`, or `0` for no limit |

## Upload-sized copies

Full-size PNG is the archive. For listings:

```bash
cropdeck split scans -o sorted-jpg --pair --format .jpg --quality 92 --max-px 1600
```
