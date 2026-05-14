# GNUTempo

A minimalist terminal metronome built in Python. No GUI, no internet connection required, no bloat.

## Why I made this

Every metronome app I tried was either locked behind a paywall, required an internet connection, limited you to certain time signatures, or just did not work the way a musician actually thinks. Physical metronomes have the same problem. I wanted something I could use however I felt, on my own terms, that respected my freedom as a user. So I built one.

Note that this program was previously reffered to as OpenTempo, for simplicity most refferences to that previous name has been unchanged.

## What it does

- Create any number of beats at any time signature and tempo, including unusual ones like 7/8 or 11/16
- Layer multiple beats on top of each other and sync them to bar boundaries
- Edit beat patterns visually in a terminal UI. split slots into any subdivision, merge them back, and build rhythms that no preset list could cover
- Apply swing at a global or per-slot level for feel and groove
- Switch between a hi-fi and lo-fi tick sound set for performance on slower hardware
- Export your beats to JSON and import them back, with version tracking so old files are never silently broken

## How to use it

**Requirements.** Python 3 and pygame.

```
pip install pygame
```

Place `OpenTempo.py`, `bartick.ogg`, and `tick.ogg` in the same folder. Optionally add `lbt.ogg` and `ltk.ogg` for the low-fi tick mode. Then run:

```
python3 OpenTempo.py
```

**Basic commands:**

```
mkbt 4/4 120          create a beat at 120 bpm in 4/4
mkbt 7/8 210          create a beat in 7/8 at 210 bpm
sync && mkbt 3/4 120  add a second beat synced to the first
p 1                   pause beat 1
r 1                   resume beat 1
rm 1                  remove beat 1
lsbt                  list all beats
patui 1               open the pattern editor for beat 1
swing 1 0.1           set global swing on beat 1
tkmod 2               switch to low-fi tick sounds
export                save all beats to a JSON file
import                load beats from a JSON file
help                  show all commands
```

**Pattern editor keys** (inside patui):

```
left / right          move between slots
s                     split a slot (enter to halve, 1/3 for ratio, =3 for equal parts)
m                     enter merge mode, expand selection with arrows, enter to confirm
w / W                 nudge slot swing +0.01 / -0.01
g / G                 nudge global swing +0.01 / -0.01
r                     reset selected slot swing
R                     reset all swing
q / ESC               close editor
```

## Licence

This project is free software. See the LICENSE file included in this repository for the full terms.
