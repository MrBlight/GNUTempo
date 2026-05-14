# GNUTempo

A minimalist terminal metronome built in Python. No GUI, no internet connection required, no bloat.

## Why I made this

Every metronome app I tried was either locked behind a paywall, required an internet connection, limited you to certain time signatures, or just did not work the way a musician actually thinks. Physical metronomes have the same problem. I wanted something I could use however I felt, on my own terms, that respected my freedom as a user. So I built one.

Note that this program was previously referred to as OpenTempo, for simplicity most references to that previous name has been unchanged.

## What it does

- Create any number of beats at any time signature and tempo, including unusual ones like 7/8 or 11/16
- Layer multiple beats on top of each other and sync them to bar boundaries
- Edit beat patterns visually in a terminal UI: split slots into any subdivision, merge them back, and build rhythms that no preset list could cover
- Apply swing at a global or per-slot level for feel and groove
- Switch between a hi-fi and lo-fi tick sound set for performance on slower hardware
- Export your beats to JSON and import them back, with version tracking so old files are never silently broken
- **NEW**: 10 musical presets (rock, jazz, bossa, waltz, funk, samba, triplet, half-time, double-time, 7/8)
- **NEW**: Tap tempo mode to find BPM by tapping
- **NEW**: Debug/diagnostic tools for timing accuracy and system info
- **NEW**: Command-line flags for quick start without interactive setup
- **NEW**: Self-test mode to verify installation


## Installation

### Quick Install (Linux/macOS/BSD)

```bash
./install.sh
```

This script will:
- Detect your operating system
- Check and install dependencies (Python 3, pygame)
- Install `gnutempo` as a system-wide command
- Optionally install man pages and shared files

For system-wide installation:
```bash
sudo ./install.sh
```

### Manual Installation

**Requirements:** Python 3 and pygame.

```bash
pip install pygame
```

Place `OpenTempo.py`, `bartick.ogg`, and `tick.ogg` in the same folder. Optionally add `lbt.ogg` and `ltk.ogg` for the low-fi tick mode. Then run:

```bash
python3 OpenTempo.py
```

Or after running the install script:

```bash
gnutempo
```

## Usage

### Command-Line Options

```bash
gnutempo                          # Start interactive mode
gnutempo --bpm 120 --time 4/4     # Quick start with settings
gnutempo --preset rock            # Start with rock preset
gnutempo --debug                  # Enable debug mode
gnutempo --test                   # Run self-tests
gnutempo --list-presets           # Show all presets
gnutempo --version                # Show version
gnutempo --help                   # Show help
```

### Basic Commands (Interactive Mode)

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
debug info            show system information
debug timing          test timing accuracy
tap                   enter tap tempo mode
help                  show all commands
```

### Presets

Quick-start with common rhythm patterns:

```
rock         - Basic rock pattern (4/4 @ 120 BPM)
jazz         - Swing pattern (4/4 @ 140 BPM)
bossa        - Bossa nova pattern (4/4 @ 130 BPM)
waltz        - Waltz pattern (3/4 @ 90 BPM)
funk         - Funk pattern with 16th notes (4/4 @ 100 BPM)
samba        - Samba pattern (2/4 @ 160 BPM)
triplet      - Triplet feel (4/4 @ 120 BPM)
half_time    - Half-time rock (4/4 @ 70 BPM)
double_time  - Double-time punk/metal (4/4 @ 180 BPM)
seven_eight  - Progressive 7/8 pattern (7/8 @ 140 BPM)
```

### Pattern Editor Keys (inside patui)

```
left / right          move between slots
s                     split a slot (enter to halve, 1/3 for ratio, =3 for N equal parts)
m                     enter merge mode, expand selection with arrows, enter to confirm
w / W                 nudge slot swing +0.01 / -0.01
g / G                 nudge global swing +0.01 / -0.01
r                     reset selected slot swing
R                     reset all swing
x                     hard reset pattern to equal subdivision (recovers broken state)
q / ESC               close editor (changes are already live)
```

### Debug Tools

The new `debug` command provides diagnostic capabilities:

```
debug              show debug options
debug on/off       toggle debug mode
debug info         show system information (Python version, pygame, audio files)
debug timing       run timing accuracy test
debug audio        test audio playback
debug state        dump internal beat state
```

### Tap Tempo

Use the `tap` command to enter tap tempo mode. Press Enter to tap out a rhythm, and GNUTempo will calculate the BPM for you.

```
tap                enter tap tempo mode
```

## Examples

### Start a simple 4/4 beat
```bash
gnutempo
> mkbt 4/4 120
```

### Use a preset
```bash
gnutempo --preset jazz
```

### Layer complex polyrhythms
```bash
gnutempo
> mkbt 5/4 140
> sync && mkbt 7/8 140
> lsbt
```

### Create a custom pattern
```bash
gnutempo
> mkbt 4/4 120
> patui 1
# Then use s to split, m to merge, w/W for swing
```

### Save and load patterns
```bash
gnutempo
> mkbt 7/8 200
> export
# Later...
> import
```

### Test your system
```bash
gnutempo --test
gnutempo
> debug timing
> debug audio
```

## Files

- `bartick.ogg` - Bar tick sound (required)
- `tick.ogg` - Regular tick sound (required)
- `lbt.ogg` - Low-fi bar tick (optional)
- `ltk.ogg` - Low-fi tick (optional)
- `*.json` - Saved beat patterns

## License

This project is free software licensed under the GNU General Public License v3.0. See the LICENSE file for the full terms.

## Version History

- **1.1.0** - Added presets, tap tempo, debug tools, CLI flags, self-test, man page, install script
- **1.0.5** - N-equal split (=N syntax), version stamped in JSON, bar integrity enforced
- **1.0.4** - tkmod persisted in JSON, import restores tick mode, backward compat
- **1.0.3** - Added tkmod (tick mode switching, hi-fi / low-fi sound sets)
- **1.0.2** - Added patui curses editor, JSON export/import, swing (global + per-slot)
- **1.0.1** - Added pattern system with named patterns (322, 323, etc.) and pat command
- **1.0.0** - Initial release with basic metronome functionality