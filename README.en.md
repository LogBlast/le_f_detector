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
| `py compteur_coffres.py no-overlay` | Count without showing the counter on screen |

| Key | Effect |
|---|---|
| **F8** | +1 (missed chest) |
| **F7** | −1 (false detection) |
| **F10** or **Ctrl+C** | Quit |

Manual corrections are rarely needed: at the end of a match, the replay adjusts the count anyway.

### Replay delay

Fortnite keeps writing the replay until you leave the match, even while spectating your teammates. Sprite / rare / broken numbers arrive about 6 to 10 seconds after you're back in the lobby.

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

To reset sprite / rare / broken chests, delete `data/replays.json`.

## Troubleshooting

- **The counter doesn't show on top of the game**: set Fortnite to *Windowed Fullscreen*.
- **Some chests aren't detected**: run with `debug`, check the similarity, lower `SEUIL` or calibrate again.
- **Sprite / rare / broken stay at "–" or don't change**: check the messages at launch (.NET runtime, `lecteur/` folder, replays enabled).
- **"Replay unreadable"**: a Fortnite update can change the replay format; open an *issue* with the message.

## Project structure

```
compteur_coffres.py    main program
assets/                counter icons
lecteur_src/           replay reader source code (C#)
lecteur/               built reader (not versioned)
data/                  user data (not versioned)
```

## Credits and license

- Replay decoding: [FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor) (Shiqan, MIT), with the patches from [Fortnite-ChestCounter](https://github.com/LED-N/Fortnite-ChestCounter) (LED-N, MIT). Details in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Code of this project: [MIT](LICENSE) license.

Fortnite is a trademark of Epic Games, Inc. This project is not affiliated with or endorsed by Epic Games.
