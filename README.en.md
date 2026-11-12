# le_f_detector — Fortnite chest counter

[Français](README.md) · **English**

Counts the chests you open in Fortnite and shows them live, on top of the game.

- **Opened chests, live**: detected on screen when the "+XP CHEST" message appears.
- **Chests in the current match**: "+N this match".
- **Sprite, rare and broken chests**: read from the replay a few seconds after each match.
- **Automatic correction**: at the end of a match, the opened-chest count is adjusted to the replay (false detection or missed chest).
- **Total and your chance of having found Pirate Shop Access** with your number of chests.

```
[chest] 1065  +11 this match
[sprite] 3  [rare] 4  [broken] 9
──────────────────────────────
TOTAL 1074   Token: 0.78%
```

## How it works (and why it's safe)

- **On-screen detection**: the program captures a small area of the screen, like OBS, and looks for the purple word of the chest message. It doesn't read the game's memory and injects nothing.
- **Replays**: after each match, a small reader (`lecteur/`) opens, read-only, the `.replay` file Fortnite saves in `%LOCALAPPDATA%\FortniteGame\Saved\Demos`.
- **Map and minimap options**: same principle, replays after the match and the game's minimap read on screen. Other players' positions are never shown during a match.
- **No data sent**: everything stays on your PC, in the `data/` folder.

## Installation

Windows 10 / 11.

1. **Python 3.10+**: <https://www.python.org/downloads/>, then in a terminal, in the project folder:
   ```
   py -m pip install -r requirements.txt
   ```
2. **.NET 10 runtime** (to read replays):
   ```
   winget install Microsoft.DotNet.Runtime.10
   ```
3. **The replay reader**, in a `lecteur/` folder next to the script:
   - either the `lecteur.zip` from the *Releases* page, unzipped in the project folder;
   - or build it yourself: install the .NET 10 SDK (`winget install Microsoft.DotNet.SDK.10`), then run `lecteur_src\build.bat`.
4. **In Fortnite**:
   - *Settings → Game → Replays → Record Replays: On*;
   - *Settings → Video → Window Mode: Windowed Fullscreen* (in exclusive fullscreen, nothing can be drawn on top of the game).

## First launch

```
py compteur_coffres.py
```

Setup starts automatically:

1. **Language**: French or English.
2. **Chests already opened**: `0` (default), `1000` (maximum of the Fortnite quest counter) or your own number.
3. **Calibration**: start Fortnite, open a chest and press **F9** while the "+XP CHEST" message is on screen. Select **the whole purple word** (CHEST, or COFFRE in French) **with a wide margin all around it**, then press Enter.
4. **Check** of what is needed to read replays.

> [!WARNING]
> **Calibration: select the whole word "CHEST" with a wide margin all around it.** That is what makes only regular chests count. A selection that is too tight on the word also matches the other chest types, which then get counted too.

Sprite, rare and broken chests are counted from this first launch on: older matches are ignored.

## Usage

| Command | Effect |
|---|---|
| `py compteur_coffres.py` | Start the counter |
| `py compteur_coffres.py calibrate` | Redo the calibration |
| `py compteur_coffres.py setup` | Redo the whole setup (resets the counter to the chosen number) |
| `py compteur_coffres.py debug` | Show the similarity of each detection, to tune `SEUIL` |
| `py compteur_coffres.py map` | Option: open the map of your chests (see below) |
| `py compteur_coffres.py minimap` | Option: add a live map with the next 3 chests to the counter (see below) |
| `py compteur_coffres.py minimap-setup` | Option: locate the game's minimap on screen (F9) |
| `py compteur_coffres.py no-overlay` | Count without showing the counter on screen |

| Key | Effect |
|---|---|
| **F8** | +1 (missed chest) |
| **F7** | −1 (false detection) |
| **F10** or **Ctrl+C** | Quit |

Manual corrections are rarely needed: at the end of a match, the replay adjusts the count anyway.

### Replay delay

Fortnite keeps writing the replay until you leave the match, even while spectating your teammates. Sprite / rare / broken numbers arrive about 6 to 10 seconds after you're back in the lobby.

## Chest map (option)

`py compteur_coffres.py map` reads your replays and opens `data/carte.html` in your browser:

- **chest spots**: every place where a chest was opened, by you or by a player near you (the replay also records nearby players), accumulated match after match (the bigger the dot, the more often it was opened);
- **your last match**: your path and the chests you opened;
- **a suggested route**: click where you land, pick a distance, and the map draws the order that opens the most chests.

Mouse wheel to zoom, drag to move around, **Vue entière** to see the whole island again.

A chest's position is where the player opening it stood (the replay doesn't give map chests' positions): it's a few metres off. Only areas where you played fill up, since the replay only records what happens near you.

The option doesn't change the counter and only runs when you start this command. The first time, reading takes less than a minute for 100 replays; after that only new replays are read. It needs the reader from this version: if you use an older `lecteur.zip`, rebuild it with `lecteur_src\build.bat`.

**Map background**: put a picture of the current game map in `data/carte.png` (or `.jpg` / `.webp`). It stays on your PC. The provided alignment (`CALAGE_CARTE`) matches the official 1920 px picture of the November 2026 season. With another picture, tick **Caler la carte** and adjust the dots (drag, mouse wheel, Pivoter, Miroir) until your paths follow the roads; that setting is only kept in your browser: for the minimap, copy it into `CALAGE_CARTE`. Each new season, replace the picture, align again, and delete `data/positions.json` to start over.

### Live minimap (option)

`py compteur_coffres.py minimap` adds a small map of 300 m around you under the counter, during the match: chest spots, the ones you opened this match (red cross) and the route to the **next 3 chests** (`1:3m  2:+6m  3:+8m`).

Before the first time:

1. `py compteur_coffres.py map` (for the spots and the background picture `data/carte.*`);
2. `py compteur_coffres.py minimap-setup`: in a match, press **F9** and select exactly the game's minimap square.

Your position is read from the game's minimap, on screen, like the "+XP CHEST" message: the script looks for that piece of map in `data/carte.*` (the same art as the game's map), twice a second. Nothing is read from the game or its memory. The replay can't be used live: Fortnite only writes its decryption key at the end of the match.

A chest counted on screen is marked opened where you are. If you change resolution or the minimap's place, run `minimap-setup` again.

## Settings

At the top of `compteur_coffres.py`:

| Setting | Default | Role |
|---|---|---|
| `SEUIL` | `0.70` | Minimum similarity. Lower it if chests are missed, raise it on false detections. |
| `OVERLAY_X`, `OVERLAY_Y` | `15`, `110` | Position of the counter on screen. |
| `ECRAN` | `1` | Watched screen (1 = main). |
| `AJOUTER_CASSES` | `True` | The total includes broken chests. |
| `CORRIGER_AVEC_REPLAY` | `True` | Adjusts opened chests to the replay at the end of each match. |
| `CHANCE_TOKEN` | `1 / 137_500` | Pirate Shop Access chance per chest. |
| `CALAGE_CARTE` | November 2026 picture | Map and minimap options: how replay positions match the map picture. |
| `MINIMAP_METRES` | `300` | Side, in metres, of the area shown by the minimap. |

## Token chance

The displayed probability is the chance of having found Pirate Shop Access **at least once** with your number of chests: `1 − (1 − 1/137,500)^chests`. The 1 in 137,500 per chest rate in normal matches comes from the Fortnite Status account (see also <https://fortnite.bot/treasure>). *Treasure Hours*, which raise this rate, are not taken into account.

## Data

Everything is in `data/` (ignored by git):

| File | Content |
|---|---|
| `reglages.json` | Language |
| `calibration.json`, `modele_coffre.png` | Calibration |
| `compteur.json` | Total and time of each counted chest |
| `compteur.txt` | Total as text, for an OBS text source |
| `replays.json` | Tracking start and result of each match |
| `positions.json`, `carte.html`, `carte.png` | Map option: positions read, generated page, background picture |
| `minicarte.json` | Minimap option: where the game's minimap is on screen |

To reset sprite / rare / broken chests, delete `data/replays.json`.

## Troubleshooting

- **The counter doesn't show on top of the game**: set Fortnite to *Windowed Fullscreen*.
- **Some chests aren't detected**: run with `debug`, check the similarity, lower `SEUIL` or calibrate again.
- **Sprite / rare / broken stay at "–" or don't change**: check the messages at launch (.NET runtime, `lecteur/` folder, replays enabled).
- **Minimap: "position not found"**: normal while the map is open or you're dead. Otherwise, run `minimap-setup` again (select the minimap square, without its frame) and check that `data/carte.*` is the current season's map.
- **"Replay unreadable"**: a Fortnite update can change the replay format; open an *issue* with the message.

## Project structure

```
compteur_coffres.py    main program
carte_modele.html      page template for the map option
assets/                counter icons
lecteur_src/           replay reader source code (C#)
lecteur/               built reader (not versioned)
data/                  user data (not versioned)
```

## Credits and license

- Replay decoding: [FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor) (Shiqan, MIT), with the patches from [Fortnite-ChestCounter](https://github.com/LED-N/Fortnite-ChestCounter) (LED-N, MIT). Details in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Map alignment: the coordinate conversion formula of the [fortnite.gg](https://fortnite.gg/) map (none of their data is included).
- Code of this project: [MIT](LICENSE) license.

Fortnite is a trademark of Epic Games, Inc. This project is not affiliated with or endorsed by Epic Games.
