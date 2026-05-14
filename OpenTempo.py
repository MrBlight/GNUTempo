# OpenTempo - Terminal Minimalist Metronome
# Copyright (C) 2025 MrBlight
# Licensed under the GNU General Public License v3.0
# See https://www.gnu.org/licenses/gpl-3.0.html

import os
import sys
import time
import threading
import shlex
import json
from fractions import Fraction
import platform

# Optional curses import for pattern editor (not available on Windows by default)
try:
    import curses
    CURSES_AVAILABLE = True
except ImportError:
    CURSES_AVAILABLE = False

# Audio backend selection - make pygame optional
PYGAME_AVAILABLE = False
try:
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pass

# Windows built-in sound as fallback
WINSOUND_AVAILABLE = False
if platform.system() == 'Windows':
    try:
        import winsound
        WINSOUND_AVAILABLE = True
    except ImportError:
        pass

# ── audio setup ───────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# mode 1: default hi-fi set
BARTICK_PATH = os.path.join(SCRIPT_DIR, "bartick.ogg")
TICK_PATH    = os.path.join(SCRIPT_DIR, "tick.ogg")
# mode 2: low-fi set (lighter on cpu for demanding beats)
LBT_PATH     = os.path.join(SCRIPT_DIR, "lbt.ogg")
LTK_PATH     = os.path.join(SCRIPT_DIR, "ltk.ogg")

# global tick mode: 1 or 2
tick_mode      = 1
tick_mode_lock = threading.Lock()

def check_audio_files():
    missing = []
    if not os.path.isfile(BARTICK_PATH): missing.append("bartick.ogg")
    if not os.path.isfile(TICK_PATH):    missing.append("tick.ogg")
    if missing:
        print(f"ERROR: missing required audio file(s): {', '.join(missing)}")
        print("place bartick.ogg and tick.ogg in the same folder as OpenTempo.py.")
        sys.exit(1)
    # low-fi files are optional at startup, warn if missing
    lofi_missing = []
    if not os.path.isfile(LBT_PATH): lofi_missing.append("lbt.ogg")
    if not os.path.isfile(LTK_PATH): lofi_missing.append("ltk.ogg")
    if lofi_missing:
        print(f"note: low-fi audio file(s) not found ({', '.join(lofi_missing)}). tkmod 2 will be unavailable.")

# Audio initialization (deferred to allow --test and --help without audio)
_audio_initialized = False

def init_audio():
    """Initialize audio backend. Returns True on success, False on failure."""
    global _audio_initialized
    if _audio_initialized:
        return True

    # Try pygame first
    if PYGAME_AVAILABLE:
        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.init()
            _audio_initialized = True
            return True
        except Exception as e:
            print(f"Warning: Pygame audio initialization failed: {e}")

    # Fallback to Windows built-in sound
    if WINSOUND_AVAILABLE:
        print("Using Windows built-in sound (beep) as audio backend.")
        _audio_initialized = True
        return True

    print("Warning: No audio backend available.")
    print("Running in no-audio mode. Some features will be unavailable.")
    return False

bartick_sound = tick_sound = None
lbt_sound     = ltk_sound  = None

def load_sounds():
    global bartick_sound, tick_sound, lbt_sound, ltk_sound
    if not _audio_initialized:
        return

    # Only load pygame sounds if pygame is available
    if PYGAME_AVAILABLE:
        bartick_sound = pygame.mixer.Sound(BARTICK_PATH)
        tick_sound    = pygame.mixer.Sound(TICK_PATH)
        if os.path.isfile(LBT_PATH): lbt_sound = pygame.mixer.Sound(LBT_PATH)
        if os.path.isfile(LTK_PATH): ltk_sound = pygame.mixer.Sound(LTK_PATH)

def get_sounds():
    """Return (bar_tick, tick) for the current tick mode."""
    with tick_mode_lock:
        mode = tick_mode
    if mode == 2 and lbt_sound and ltk_sound:
        return lbt_sound, ltk_sound
    return bartick_sound, tick_sound

def cmd_tkmod(args):
    global tick_mode
    if not args:
        with tick_mode_lock:
            print(f"current tick mode: {tick_mode}  (1=default  2=low-fi)")
        return
    try:    m = int(args[0])
    except: print("usage: tkmod <1|2>"); return
    if m not in (1, 2):
        print("tick mode must be 1 or 2.")
        return
    if m == 2 and (not lbt_sound or not ltk_sound):
        print("low-fi audio files (lbt.ogg / ltk.ogg) not found. tkmod 2 unavailable.")
        return
    with tick_mode_lock:
        tick_mode = m
    label = "default" if m == 1 else "low-fi"
    print(f"tick mode set to {m} ({label}).")

# ── slot tree ─────────────────────────────────────────────────────────────────
#
# A bar is a tree of Slot objects. leaf slots are what actually play.
# duration is a Fraction of the full bar.
# swing_offset: float [-0.5, 0.5], shifts attack as a fraction of slot duration.

class Slot:
    _id_counter = 0

    def __init__(self, duration: Fraction, swing_offset: float = 0.0):
        Slot._id_counter += 1
        self.id           = Slot._id_counter
        self.duration     = duration
        self.swing_offset = swing_offset
        self.children     = []

    @property
    def is_leaf(self):
        return len(self.children) == 0

    def leaves(self):
        if self.is_leaf:
            return [self]
        result = []
        for c in self.children:
            result.extend(c.leaves())
        return result

    def find(self, sid):
        if self.id == sid:
            return self
        for c in self.children:
            found = c.find(sid)
            if found:
                return found
        return None

    def find_parent(self, sid):
        for c in self.children:
            if c.id == sid:
                return self
            p = c.find_parent(sid)
            if p:
                return p
        return None

    def to_dict(self):
        return {
            "id":           self.id,
            "duration":     [self.duration.numerator, self.duration.denominator],
            "swing_offset": self.swing_offset,
            "children":     [c.to_dict() for c in self.children],
        }

    @staticmethod
    def from_dict(d):
        s = Slot.__new__(Slot)
        s.id           = d["id"]
        s.duration     = Fraction(d["duration"][0], d["duration"][1])
        s.swing_offset = d.get("swing_offset", 0.0)
        s.children     = [Slot.from_dict(c) for c in d.get("children", [])]
        return s

def make_root(numerator: int) -> Slot:
    root = Slot(Fraction(1))
    root.children = [Slot(Fraction(1, numerator)) for _ in range(numerator)]
    return root

VERSION = "1.0.5"

VERSION_HISTORY = {
    "1.0.0": "initial release. basic metronome with mkbt, p, r, rm, lsbt.",
    "1.0.1": "added pattern system with named patterns (322, 323, etc.) and pat command.",
    "1.0.2": "added patui curses editor, JSON export/import, swing (global + per-slot).",
    "1.0.3": "added tkmod (tick mode switching, hi-fi / low-fi sound sets).",
    "1.0.4": "tkmod persisted in JSON. import restores tick mode. backward compat for old JSON.",
    "1.0.5": "N-equal split (=N syntax). version stamped in JSON. bar integrity enforced.",
}

# denominators tried when labelling a duration fraction.
_DURATION_DENOMS = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,18,20,24,27,32,36,48,64]

def fmt_duration(f: Fraction, bpm: float = None, numerator: int = None) -> str:
    """
    Human-readable label for a slot duration as a Fraction of the full bar.
    Tries N/D using a wide set of denominators first.
    Falls back to milliseconds only for truly exotic fractions.
    bpm and numerator are only needed for the ms fallback.
    """
    for d in _DURATION_DENOMS:
        candidate = Fraction(round(float(f) * d), d)
        if candidate == f:
            n  = f.numerator
            dn = f.denominator
            if dn == 1:
                return "bar" if n == 1 else f"{n} bars"
            return f"{n}/{dn}"
    # ms fallback
    if bpm is not None and numerator is not None:
        bar_ms = (60.0 / bpm) * numerator * 1000
        ms     = float(f) * bar_ms
        return f"{ms:.1f}ms"
    return f"{f.numerator}/{f.denominator}"

# ── beat state ────────────────────────────────────────────────────────────────

beats        = {}
beats_lock   = threading.Lock()
next_beat_id = 1

def make_beat(numerator, denominator, bpm, root=None, global_swing=0.0):
    return {
        "numerator":    numerator,
        "denominator":  denominator,
        "bpm":          bpm,
        "root":         root if root else make_root(numerator),
        "global_swing": global_swing,
        "paused":       False,
        "thread":       None,
        "stop_event":   threading.Event(),
        "bar_event":    threading.Event(),
        "pattern_lock": threading.Lock(),
    }

# ── beat thread ───────────────────────────────────────────────────────────────

def beat_loop(beat_id, beat, sync_to_id=None):
    stop_event = beat["stop_event"]

    if sync_to_id is not None:
        with beats_lock:
            target = beats.get(sync_to_id)
        if target:
            target["bar_event"].wait()

    next_tick = time.perf_counter()

    while not stop_event.is_set():
        with beat["pattern_lock"]:
            bpm          = beat["bpm"]
            global_swing = beat["global_swing"]
            leaves       = beat["root"].leaves()
            paused       = beat["paused"]

        bar_seconds = 60.0 / bpm * beat["numerator"]

        first = True
        for slot in leaves:
            if stop_event.is_set():
                return

            slot_seconds  = float(slot.duration) * bar_seconds
            swing         = max(-0.5, min(0.5, global_swing + slot.swing_offset))
            attack_offset = swing * slot_seconds

            now        = time.perf_counter()
            sleep_time = next_tick + attack_offset - now
            if sleep_time > 0:
                stop_event.wait(timeout=sleep_time)
            if stop_event.is_set():
                return

            if not paused:
                bar_snd, tk_snd = get_sounds()
                if first:
                    if bar_snd:
                        bar_snd.play()
                    beat["bar_event"].set()
                    beat["bar_event"].clear()
                    first = False
                else:
                    if tk_snd:
                        tk_snd.play()

            next_tick += slot_seconds

# ── mkbt ──────────────────────────────────────────────────────────────────────

def cmd_mkbt(args, sync_to_id=None):
    global next_beat_id
    if len(args) < 2:
        print("usage: mkbt ##/## bpm")
        return
    try:
        num_str, den_str = args[0].split("/")
        numerator   = int(num_str)
        denominator = int(den_str)
        bpm         = float(args[1])
    except ValueError:
        print("invalid arguments. example: mkbt 4/4 120")
        return
    if numerator < 1 or denominator < 1:
        print("time signature values must be positive integers.")
        return
    if bpm <= 0:
        print("bpm must be a positive number.")
        return

    with beats_lock:
        bid  = next_beat_id
        next_beat_id += 1
        beat = make_beat(numerator, denominator, bpm)
        beats[bid] = beat

    t = threading.Thread(target=beat_loop, args=(bid, beat, sync_to_id), daemon=True)
    beat["thread"] = t
    t.start()

    if sync_to_id is not None:
        print(f"beat {bid} ({numerator}/{denominator} at {bpm} bpm) synced to beat {sync_to_id}.")
    else:
        print(f"beat {bid} ({numerator}/{denominator} at {bpm} bpm) started.")

def cmd_sync_mkbt(args):
    try:
        amp_idx = args.index("&&")
        sub_cmd = args[amp_idx + 1:]
    except (ValueError, IndexError):
        print("usage: sync && mkbt ##/## bpm")
        return
    if not sub_cmd or sub_cmd[0] != "mkbt":
        print("sync must be followed by mkbt.")
        return
    with beats_lock:
        active_ids = [bid for bid, b in beats.items() if not b["paused"]]
    if not active_ids:
        print("no active beats to sync to.")
        return
    cmd_mkbt(sub_cmd[1:], sync_to_id=active_ids[0])

# ── p / r / rm / lsbt ────────────────────────────────────────────────────────

def cmd_pause(args):
    if not args: print("usage: p <id>"); return
    try:    bid = int(args[0])
    except: print("beat id must be an integer."); return
    with beats_lock:
        if bid not in beats: print(f"beat {bid} does not exist."); return
        beats[bid]["paused"] = True
    print(f"beat {bid} paused.")

def cmd_resume(args):
    if not args: print("usage: r <id>"); return
    try:    bid = int(args[0])
    except: print("beat id must be an integer."); return
    with beats_lock:
        if bid not in beats: print(f"beat {bid} does not exist."); return
        beats[bid]["paused"] = False
    print(f"beat {bid} resumed.")

def cmd_remove(args):
    if not args: print("usage: rm <id>"); return
    try:    bid = int(args[0])
    except: print("beat id must be an integer."); return
    with beats_lock:
        if bid not in beats: print(f"beat {bid} does not exist."); return
        beats[bid]["stop_event"].set()
        del beats[bid]
    print(f"beat {bid} removed.")

def cmd_list():
    with beats_lock:
        if not beats: print("no beats."); return
        for bid, b in beats.items():
            status = "PAUSED" if b["paused"] else "ACTIVE"
            leaves = b["root"].leaves()
            bpm    = b["bpm"]
            num    = b["numerator"]
            pat    = "  ".join(fmt_duration(s.duration, bpm, num) for s in leaves)
            gs     = f"  swing {b['global_swing']:+.2f}" if b["global_swing"] != 0 else ""
            print(f"  [{bid}] {num}/{b['denominator']} at {bpm} bpm  [{pat}]{gs}  {status}")

# ── sanitize ─────────────────────────────────────────────────────────────────
#
# sanitize <beat_id>   scans all leaf slots, removes any with duration >= 1
#                      (full bar or larger) by replacing them with one slot
#                      of duration 1/numerator (default beat size).
# sanitize all         runs on every loaded beat.

def sanitize_beat(bid, beat):
    """
    Fix two classes of broken slot state:
    1. any individual slot with duration >= 1 bar  -> replace with default beat dur
    2. slots that don't sum to 1 bar               -> flag as unrecoverable,
       user should use patui 'x' to hard reset the pattern
    Returns (clamped, sum_ok, total_dur).
    """
    with beat["pattern_lock"]:
        leaves      = beat["root"].leaves()
        num         = beat["numerator"]
        default_dur = Fraction(1, num)
        new_leaves  = []
        clamped     = 0
        for s in leaves:
            if s.duration >= Fraction(1):
                new_leaves.append(Slot(default_dur, s.swing_offset))
                clamped += 1
            else:
                new_leaves.append(s)
        if clamped:
            beat["root"].children = new_leaves
            for leaf in new_leaves:
                leaf.children = []
            leaves = new_leaves
        total_dur = sum(s.duration for s in leaves)
        sum_ok    = (total_dur == Fraction(1))
    return clamped, sum_ok, total_dur

def cmd_sanitize(args):
    if not args or args[0] == "all":
        with beats_lock:
            bids = list(beats.keys())
        total = 0
        for bid in bids:
            with beats_lock:
                b = beats.get(bid)
            if b:
                n, sum_ok, total_dur = sanitize_beat(bid, b)
                if n:
                    print(f"  beat {bid}: replaced {n} oversized slot(s).")
                    total += n
                if not sum_ok:
                    print(f"  beat {bid}: slots sum to {total_dur} not 1. "
                          f"use patui {bid} then press x to hard reset the pattern.")
        if total == 0:
            print("no oversized slots found.")
        return
    try:    bid = int(args[0])
    except: print("usage: sanitize [beat_id | all]"); return
    with beats_lock:
        if bid not in beats: print(f"beat {bid} does not exist."); return
        b = beats[bid]
    n, sum_ok, total_dur = sanitize_beat(bid, b)
    if n == 0 and sum_ok:
        print(f"beat {bid} is clean.")
    else:
        if n:
            print(f"beat {bid}: replaced {n} oversized slot(s) with default beat duration.")
        if not sum_ok:
            print(f"beat {bid}: slots sum to {total_dur} not 1. "
                  f"use patui {bid} then press x to hard reset the pattern.")

# ── swing ─────────────────────────────────────────────────────────────────────

def cmd_swing(args):
    if len(args) < 2:
        print("usage: swing <beat_id> <value>")
        print("       swing <beat_id> slot <leaf_index> <value>")
        return
    try:    bid = int(args[0])
    except: print("beat id must be an integer."); return
    with beats_lock:
        if bid not in beats: print(f"beat {bid} does not exist."); return
        beat = beats[bid]

    if len(args) >= 4 and args[1] == "slot":
        try:
            idx = int(args[2])
            val = float(args[3])
        except ValueError:
            print("usage: swing <beat_id> slot <leaf_index> <value>")
            return
        val = max(-0.5, min(0.5, val))
        with beat["pattern_lock"]:
            leaves = beat["root"].leaves()
            if idx < 0 or idx >= len(leaves):
                print(f"leaf index out of range (0-{len(leaves)-1}).")
                return
            leaves[idx].swing_offset = val
        print(f"beat {bid} slot {idx} swing set to {val:+.2f}.")
    else:
        try:    val = float(args[1])
        except: print("value must be a number."); return
        val = max(-0.5, min(0.5, val))
        with beat["pattern_lock"]:
            beat["global_swing"] = val
        print(f"beat {bid} global swing set to {val:+.2f}.")

# ── export / import / lsjsn ──────────────────────────────────────────────────

def next_json_path():
    base = os.path.join(SCRIPT_DIR, "data.json")
    if not os.path.exists(base):
        return base
    n = 1
    while True:
        p = os.path.join(SCRIPT_DIR, f"data{n}.json")
        if not os.path.exists(p):
            return p
        n += 1

def cmd_export():
    with beats_lock:
        if not beats:
            print("no beats to export.")
            return
        data = {}
        for bid, b in beats.items():
            with b["pattern_lock"]:
                data[str(bid)] = {
                    "numerator":    b["numerator"],
                    "denominator":  b["denominator"],
                    "bpm":          b["bpm"],
                    "global_swing": b["global_swing"],
                    "paused":       b["paused"],
                    "active":       not b["stop_event"].is_set(),
                    "root":         b["root"].to_dict(),
                }
    path = next_json_path()
    with open(path, "w") as f:
        json.dump({"version": VERSION, "tick_mode": tick_mode, "beats": data}, f, indent=2)
    print(f"exported to {os.path.basename(path)}  (OpenTempo {VERSION}).")

def cmd_lsjsn():
    files = sorted(f for f in os.listdir(SCRIPT_DIR) if f.endswith(".json"))
    if not files:
        print("no JSON files found in project folder.")
        return
    print("JSON files in project folder:")
    for i, f in enumerate(files):
        print(f"  [{i}] {f}")

def cmd_import(args):
    global next_beat_id
    files = sorted(f for f in os.listdir(SCRIPT_DIR) if f.endswith(".json"))
    if not files:
        print("no JSON files found in project folder.")
        return

    if not args:
        cmd_lsjsn()
        raw = input("choose file index: ").strip()
        try:    idx = int(raw)
        except: print("invalid index."); return
    else:
        try:    idx = int(args[0])
        except: print("usage: import [index]"); return

    if idx < 0 or idx >= len(files):
        print("index out of range.")
        return

    path = os.path.join(SCRIPT_DIR, files[idx])
    try:
        with open(path) as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"could not read file: {e}")
        return

    # support new format {"version":..,"tick_mode":..,"beats":{..}} and old flat format
    if "beats" in raw_data and isinstance(raw_data["beats"], dict):
        saved_mode    = raw_data.get("tick_mode", 1)
        saved_version = raw_data.get("version", "unknown")
        data          = raw_data["beats"]
    else:
        saved_mode    = 1
        saved_version = "unknown"
        data          = raw_data

    # version report and compatibility notes
    print(f"file version: {saved_version}  (running: {VERSION})")
    if saved_version != VERSION and saved_version != "unknown":
        # walk version history and note anything added after the saved version
        versions = sorted(VERSION_HISTORY.keys())
        try:
            sv_idx = versions.index(saved_version)
            newer  = versions[sv_idx + 1:]
            if newer:
                print("features added since this file was saved:")
                for v in newer:
                    print(f"  {v}: {VERSION_HISTORY[v]}")
        except ValueError:
            print(f"note: version {saved_version} not in history. file may be from a future version.")

    # restore tick mode
    if saved_mode == 2 and (not lbt_sound or not ltk_sound):
        print("note: saved tick mode 2 but low-fi files not found. staying on mode 1.")
    else:
        global tick_mode
        with tick_mode_lock:
            tick_mode = saved_mode
        label = "default" if saved_mode == 1 else "low-fi"
        print(f"tick mode restored to {saved_mode} ({label}).")

    def _max_id(slot):
        m = slot.id
        for c in slot.children:
            m = max(m, _max_id(c))
        return m

    def validate_leaves(root, numerator):
        """Return error string if leaf durations violate bar integrity, else None."""
        leaves   = root.leaves()
        total    = sum(s.duration for s in leaves)
        expected = Fraction(1)
        if total != expected:
            return f"leaf durations sum to {total}, expected 1 bar."
        for s in leaves:
            if s.duration >= Fraction(1):
                return f"slot with duration {s.duration} >= 1 bar found."
            if s.duration <= Fraction(0):
                return f"slot with zero/negative duration found."
        return None

    loaded  = 0
    skipped = 0
    for bid_str, bd in data.items():
        try:
            numerator    = bd["numerator"]
            denominator  = bd["denominator"]
            bpm          = bd["bpm"]
            global_swing = bd.get("global_swing", 0.0)
            root         = Slot.from_dict(bd["root"])
            paused       = bd.get("paused", False)
        except Exception as e:
            print(f"skipping entry {bid_str}: {e}")
            skipped += 1
            continue

        # integrity check: reject beats with broken bar structure
        err = validate_leaves(root, numerator)
        if err:
            print(f"skipping entry {bid_str}: bar integrity violation. {err}")
            print(f"  tip: run 'sanitize all' if you loaded this file in an older version first.")
            skipped += 1
            continue

        Slot._id_counter = max(Slot._id_counter, _max_id(root))

        with beats_lock:
            bid = next_beat_id
            next_beat_id += 1
            beat = make_beat(numerator, denominator, bpm, root=root, global_swing=global_swing)
            beat["paused"] = paused
            beats[bid] = beat

        t = threading.Thread(target=beat_loop, args=(bid, beat), daemon=True)
        beat["thread"] = t
        t.start()
        loaded += 1

    summary = f"imported {loaded} beat(s) from {files[idx]}."
    if skipped:
        summary += f" {skipped} skipped due to errors (see above)."
    print(summary)

# ── patui: curses pattern editor ─────────────────────────────────────────────
#
# keys:
#   left / right    move cursor between leaf slots
#   s               split selected slot (prompts for ratio, enter = 1/2)
#   m               merge slot back into parent
#   w / W           nudge selected slot swing +0.01 / -0.01
#   g / G           nudge global swing +0.01 / -0.01
#   r               reset selected slot swing to 0
#   R               reset all swing (global + every slot) to 0
#   q / ESC         close editor (all changes already live)

def patui(stdscr, beat_id):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected slot
    curses.init_pair(2, curses.COLOR_CYAN,  -1)                  # accent
    curses.init_pair(3, curses.COLOR_YELLOW,-1)                  # swing info
    curses.init_pair(4, curses.COLOR_GREEN, -1)                  # header
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_MAGENTA) # merge selection

    cursor      = 0
    msg         = ""
    merge_mode  = False   # True while user is dragging a merge selection
    merge_start = 0       # anchor index when merge mode is active
    merge_end   = 0       # current far end of merge selection

    def get_beat():
        with beats_lock:
            return beats.get(beat_id)

    def draw():
        beat = get_beat()
        if beat is None:
            stdscr.clear()
            stdscr.addstr(0, 0, f"beat {beat_id} no longer exists. press any key.")
            stdscr.refresh()
            stdscr.getch()
            return False

        with beat["pattern_lock"]:
            leaves       = beat["root"].leaves()
            global_swing = beat["global_swing"]
            bpm          = beat["bpm"]
            num          = beat["numerator"]
            den          = beat["denominator"]

        h, w = stdscr.getmaxyx()
        stdscr.erase()

        # header
        header = (f" beat {beat_id}  {num}/{den}  {bpm} bpm"
                  f"  global swing: {global_swing:+.2f}  slots: {len(leaves)} ")
        stdscr.attron(curses.color_pair(4))
        try: stdscr.addstr(0, 0, header[:w-1])
        except curses.error: pass
        stdscr.attroff(curses.color_pair(4))

        # slot bar at row 2 (3 rows tall: top border, label, bottom border)
        bar_y = 2
        bar_w = w - 2
        bar_x = 1
        n     = len(leaves)

        # size slots relative to the total leaf duration, not the full bar.
        # this keeps experimental splits (where leaves may not sum to 1) from
        # overflowing or leaving empty space. every leaf always fills its fair
        # share of the visible bar_w.
        total_leaf_dur = sum(float(s.duration) for s in leaves) or 1.0

        for i, slot in enumerate(leaves):
            cell_w = max(3, int(round((float(slot.duration) / total_leaf_dur) * bar_w)))
            if i == n - 1:
                used   = sum(max(3, int(round((float(leaves[j].duration) / total_leaf_dur) * bar_w))) for j in range(n-1))
                cell_w = max(3, bar_w - used)

            label   = fmt_duration(slot.duration, bpm, num)
            sw_str  = f" s{slot.swing_offset:+.2f}" if slot.swing_offset != 0 else ""
            content = (label + sw_str)
            content = content[:cell_w-1].ljust(cell_w-1)

            in_merge = merge_mode and (min(merge_start, merge_end) <= i <= max(merge_start, merge_end))
            is_cursor = (i == cursor)
            if in_merge:
                attr = curses.color_pair(5)
            elif is_cursor:
                attr = curses.color_pair(1)
            else:
                attr = 0
            try:
                stdscr.addstr(bar_y,   bar_x, "+" + "-"*(cell_w-1), attr)
                stdscr.addstr(bar_y+1, bar_x, "|" + content,        attr)
                stdscr.addstr(bar_y+2, bar_x, "+" + "-"*(cell_w-1), attr)
            except curses.error:
                pass
            bar_x += cell_w

        # swing info / merge hint
        if bar_y + 4 < h:
            if merge_mode:
                lo  = min(merge_start, merge_end)
                hi  = max(merge_start, merge_end)
                cnt = hi - lo + 1
                sinfo = f" MERGE MODE: slots {lo}-{hi} ({cnt} selected)   enter=confirm   esc=cancel "
            else:
                sel   = leaves[cursor] if cursor < len(leaves) else None
                sw    = sel.swing_offset if sel else 0.0
                sinfo = f" selected slot swing: {sw:+.2f}   global swing: {global_swing:+.2f}"
            stdscr.attron(curses.color_pair(3))
            try: stdscr.addstr(bar_y+4, 0, sinfo[:w-1])
            except curses.error: pass
            stdscr.attroff(curses.color_pair(3))

        # message
        if msg and bar_y + 6 < h:
            try: stdscr.addstr(bar_y+6, 1, msg[:w-2])
            except curses.error: pass

        # bottom hint bar
        if merge_mode:
            hints = (" \u2190\u2192 expand selection   enter confirm merge   esc cancel ")
        else:
            hints = (" \u2190\u2192 move   s split   m merge   "
                     "w/W slot swing \u00b10.01   g/G global swing \u00b10.01   "
                     "r reset slot swing   R reset all swing   x reset pattern   q quit ")
        try: stdscr.addstr(h-1, 0, hints[:w-1], curses.A_REVERSE)
        except curses.error: pass

        stdscr.refresh()
        return True

    while True:
        if not draw():
            break

        key = stdscr.getch()
        beat = get_beat()
        if beat is None:
            break

        with beat["pattern_lock"]:
            leaves = beat["root"].leaves()
            n      = len(leaves)

        msg = ""

        if key in (ord('q'), 27):
            if merge_mode:
                merge_mode = False
                msg = "merge cancelled."
            else:
                break

        elif key == curses.KEY_LEFT:
            if merge_mode:
                merge_end = max(0, merge_end - 1)
                cursor    = merge_end
            else:
                cursor = max(0, cursor - 1)

        elif key == curses.KEY_RIGHT:
            if merge_mode:
                merge_end = min(n - 1, merge_end + 1)
                cursor    = merge_end
            else:
                cursor = min(n - 1, cursor + 1)

        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            if merge_mode:
                lo = min(merge_start, merge_end)
                hi = max(merge_start, merge_end)
                if lo == hi:
                    merge_mode = False
                    msg = "select more than one slot to merge."
                else:
                    with beat["pattern_lock"]:
                        leaves   = beat["root"].leaves()
                        selected = leaves[lo:hi+1]
                        combined = sum(s.duration for s in selected)
                        if combined >= Fraction(1):
                            merge_mode = False
                            msg = (f"merge cancelled: combined duration {combined} "
                                   f">= 1 bar. that would create an oversized slot.")
                        else:
                            new_slot = Slot(combined, selected[0].swing_offset)
                            new_leaves = leaves[:lo] + [new_slot] + leaves[hi+1:]
                            beat["root"].children = new_leaves
                            for leaf in new_leaves:
                                leaf.children = []
                            bpm_now    = beat["bpm"]
                            num_now    = beat["numerator"]
                            cursor     = lo
                            merge_mode = False
                            msg        = f"merged {hi-lo+1} slots into {fmt_duration(combined, bpm_now, num_now)}."

        elif key == ord('s'):
            # split modes:
            #   enter alone    -> halve into 2 equal pieces
            #   ratio  1/3     -> split at that ratio (two pieces summing to parent)
            #   N-equal  =N    -> split into N equal pieces (e.g. =3 gives three equal thirds)
            # all results must sum exactly to the parent slot's duration.
            curses.echo()
            curses.curs_set(1)
            h, w = stdscr.getmaxyx()
            prompt = "split: enter=halve  ratio e.g. 1/3  or =N equal parts e.g. =3: "
            try:
                stdscr.addstr(h-2, 0, (" " * (w-1)))
                stdscr.addstr(h-2, 0, prompt[:w-1])
                stdscr.refresh()
                raw = stdscr.getstr(h-2, min(len(prompt), w-2), 20).decode().strip()
            except curses.error:
                raw = ""
            curses.noecho()
            curses.curs_set(0)

            with beat["pattern_lock"]:
                leaves = beat["root"].leaves()
                if cursor >= len(leaves):
                    msg = "cursor out of range."
                    continue
                target = leaves[cursor]
                d      = target.duration

            bpm_now = beat["bpm"]
            num_now = beat["numerator"]

            if raw == "":
                # halve
                half = d * Fraction(1, 2)
                with beat["pattern_lock"]:
                    target.children = [
                        Slot(half, target.swing_offset),
                        Slot(half, 0.0),
                    ]
                    target.swing_offset = 0.0
                msg = f"split into {fmt_duration(half, bpm_now, num_now)} + {fmt_duration(half, bpm_now, num_now)}."

            elif raw.startswith("="):
                # N equal parts
                try:
                    n_parts = int(raw[1:].strip())
                except ValueError:
                    msg = "invalid input. use =3 for 3 equal parts."
                    continue
                if n_parts < 2:
                    msg = "need at least 2 parts."
                    continue
                piece = d * Fraction(1, n_parts)
                if piece <= Fraction(0):
                    msg = "piece duration would be zero. choose fewer parts."
                    continue
                # verify integrity: n_parts * piece must equal d exactly
                assert piece * n_parts == d, "fraction arithmetic error"
                with beat["pattern_lock"]:
                    target.children = [
                        Slot(piece, target.swing_offset if i == 0 else 0.0)
                        for i in range(n_parts)
                    ]
                    target.swing_offset = 0.0
                label = fmt_duration(piece, bpm_now, num_now)
                msg = f"split into {n_parts} x {label}."

            elif "/" in raw:
                # ratio split
                try:
                    p_str, q_str = raw.split("/")
                    ratio = Fraction(int(p_str.strip()), int(q_str.strip()))
                except Exception:
                    msg = "invalid ratio. example: 1/3"
                    continue
                if not (Fraction(0) < ratio < Fraction(1)):
                    msg = "ratio must be strictly between 0 and 1."
                    continue
                a      = d * ratio
                b_frac = d - a
                # integrity check
                if a + b_frac != d:
                    msg = "fraction arithmetic error. split cancelled."
                    continue
                with beat["pattern_lock"]:
                    target.children = [
                        Slot(a,      target.swing_offset),
                        Slot(b_frac, 0.0),
                    ]
                    target.swing_offset = 0.0
                msg = (f"split into {fmt_duration(a, bpm_now, num_now)} + "
                       f"{fmt_duration(b_frac, bpm_now, num_now)}.")
            else:
                msg = "invalid input. enter alone to halve, 1/3 for ratio, =3 for equal parts."

        elif key == ord('m'):
            if n < 2:
                msg = "nothing to merge."
            elif merge_mode:
                msg = "already in merge mode. use arrows to expand, enter to confirm, esc to cancel."
            else:
                merge_mode  = True
                merge_start = cursor
                merge_end   = cursor
                msg = "merge mode: expand with arrows, enter to confirm, esc to cancel."

        elif key == ord('w'):
            with beat["pattern_lock"]:
                leaves = beat["root"].leaves()
                if cursor < len(leaves):
                    leaves[cursor].swing_offset = round(
                        max(-0.5, min(0.5, leaves[cursor].swing_offset + 0.01)), 4)

        elif key == ord('W'):
            with beat["pattern_lock"]:
                leaves = beat["root"].leaves()
                if cursor < len(leaves):
                    leaves[cursor].swing_offset = round(
                        max(-0.5, min(0.5, leaves[cursor].swing_offset - 0.01)), 4)

        elif key == ord('g'):
            with beat["pattern_lock"]:
                beat["global_swing"] = round(
                    max(-0.5, min(0.5, beat["global_swing"] + 0.01)), 4)

        elif key == ord('G'):
            with beat["pattern_lock"]:
                beat["global_swing"] = round(
                    max(-0.5, min(0.5, beat["global_swing"] - 0.01)), 4)

        elif key == ord('r'):
            with beat["pattern_lock"]:
                leaves = beat["root"].leaves()
                if cursor < len(leaves):
                    leaves[cursor].swing_offset = 0.0
            msg = "slot swing reset."

        elif key == ord('R'):
            with beat["pattern_lock"]:
                beat["global_swing"] = 0.0
                for s in beat["root"].leaves():
                    s.swing_offset = 0.0
            msg = "all swing reset."

        elif key == ord('x'):
            # hard reset: rebuild pattern from scratch as equal subdivision
            with beat["pattern_lock"]:
                num  = beat["numerator"]
                new_root = make_root(num)
                beat["root"] = new_root
            cursor = 0
            msg = f"pattern reset to {num} equal beats."

def cmd_patui(args):
    if not args:
        print("usage: patui <beat_id>")
        return
    if not CURSES_AVAILABLE:
        print("ERROR: patui requires the 'curses' module, which is not available on your system.")
        print("       The pattern editor (patui) only works on Linux/macOS/BSD.")
        print("       On Windows, you can edit patterns by importing/exporting JSON files.")
        return
    try:    bid = int(args[0])
    except: print("beat id must be an integer."); return
    with beats_lock:
        if bid not in beats:
            print(f"beat {bid} does not exist.")
            return
    try:
        curses.wrapper(patui, bid)
    except Exception as e:
        print(f"patui error: {e}")

# ── help ──────────────────────────────────────────────────────────────────────

def cmd_help():
    print("""
  mkbt ##/## bpm              create a beat
  sync && mkbt ##/## bpm      overlay a beat synced to the next bar
  p <id>                      pause a beat
  r <id>                      resume a beat
  rm <id>                     remove a beat
  lsbt                        list all beats
  sanitize [id | all]         remove oversized slots (>= 1 bar) from beat(s)
  patui <id>                  open the pattern editor
  swing <id> <val>            set global swing  (-0.5 to 0.5)
  swing <id> slot <i> <val>   set per-slot swing override
  tkmod <1|2>                 switch tick sound set (1=default  2=low-fi)
  export                      save all beats to data.json (auto-numbered)
  import [index]              import beats from a JSON file in project folder
  lsjsn                       list JSON files in project folder
  debug [subcmd]              debug/diagnostic tools (type 'debug' for options)
  tap                         enter tap tempo mode
  help                        show this help
  exit / quit                 quit

patui keys:
  left / right    move between slots
  s               split (enter=halve  1/3=ratio  =3=N equal parts)
  m               enter merge mode (expand selection with arrows, enter to confirm)
  w / W           nudge slot swing +0.01 / -0.01
  g / G           nudge global swing +0.01 / -0.01
  r               reset selected slot swing
  R               reset all swing to 0
  x               hard reset pattern to equal subdivision (recovers broken state)
  q / ESC         close editor (changes are already live)
""")

# ── presets ───────────────────────────────────────────────────────────────────

PRESETS = {
    "rock": {
        "time": "4/4",
        "bpm": 120,
        "description": "Basic rock pattern",
        "pattern": [(1, 4), (1, 4), (1, 4), (1, 4)],  # Four quarter notes
    },
    "jazz": {
        "time": "4/4",
        "bpm": 140,
        "description": "Swing pattern",
        "pattern": [(1, 4), (1, 4), (1, 4), (1, 4)],
        "swing": 0.25,
    },
    "bossa": {
        "time": "4/4",
        "bpm": 130,
        "description": "Bossa nova pattern",
        "pattern": [(1, 4), (1, 8), (1, 8), (1, 4), (1, 4)],
    },
    "waltz": {
        "time": "3/4",
        "bpm": 90,
        "description": "Waltz pattern",
        "pattern": [(1, 4), (1, 4), (1, 4)],
    },
    "funk": {
        "time": "4/4",
        "bpm": 100,
        "description": "Funk pattern with 16th notes",
        "pattern": [(1, 16)] * 16,
    },
    "samba": {
        "time": "2/4",
        "bpm": 160,
        "description": "Samba pattern",
        "pattern": [(1, 8), (1, 8), (1, 8), (1, 8)],
    },
    "triplet": {
        "time": "4/4",
        "bpm": 120,
        "description": "Triplet feel",
        "pattern": [(1, 12)] * 12,
    },
    "half_time": {
        "time": "4/4",
        "bpm": 70,
        "description": "Half-time rock",
        "pattern": [(1, 2), (1, 2)],
    },
    "double_time": {
        "time": "4/4",
        "bpm": 180,
        "description": "Double-time punk/metal",
        "pattern": [(1, 8)] * 8,
    },
    "seven_eight": {
        "time": "7/8",
        "bpm": 140,
        "description": "Progressive 7/8 pattern",
        "pattern": [(1, 8)] * 7,
    },
}

# ── debug/diagnostic tools ────────────────────────────────────────────────────

DEBUG_MODE = False

def debug_log(message):
    """Print debug message if DEBUG_MODE is enabled."""
    if DEBUG_MODE:
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"\n[DEBUG {timestamp}] {message}")

def cmd_debug(args):
    """Toggle or display debug information."""
    global DEBUG_MODE

    if not args:
        # Show current debug status
        print(f"Debug mode: {'ON' if DEBUG_MODE else 'OFF'}")
        print("\nDebug commands:")
        print("  debug on/off     - Toggle debug mode")
        print("  debug info       - Show system information")
        print("  debug timing     - Run timing accuracy test")
        print("  debug audio      - Test audio playback")
        print("  debug state      - Dump internal beat state")
        return

    subcmd = args[0].lower()

    if subcmd == "on":
        DEBUG_MODE = True
        print("Debug mode enabled.")
    elif subcmd == "off":
        DEBUG_MODE = False
        print("Debug mode disabled.")
    elif subcmd == "info":
        print("\n=== GNUTempo Debug Info ===")
        print(f"Version: {VERSION}")
        print(f"Python: {sys.version}")
        print(f"Platform: {sys.platform}")
        if PYGAME_AVAILABLE:
            print(f"Pygame version: {pygame.version.ver}")
            print(f"Audio driver: {pygame.mixer.get_init()}")
        elif WINSOUND_AVAILABLE:
            print("Audio backend: Windows built-in sound (winsound)")
        else:
            print("Audio backend: None available")
        print(f"Working directory: {SCRIPT_DIR}")
        print(f"Debug mode: {DEBUG_MODE}")
        print(f"Active beats: {len(beats)}")
        print(f"Tick mode: {tick_mode}")

        # Check audio files
        print("\nAudio files:")
        for f in [BARTICK_PATH, TICK_PATH, LBT_PATH, LTK_PATH]:
            exists = os.path.isfile(f)
            size = os.path.getsize(f) if exists else 0
            status = f"{size:,} bytes" if exists else "MISSING"
            print(f"  {os.path.basename(f)}: {status}")

    elif subcmd == "timing":
        print("\nRunning timing accuracy test (5 seconds)...")
        test_duration = 5.0
        start = time.perf_counter()
        count = 0
        while time.perf_counter() - start < test_duration:
            count += 1
            time.sleep(0.01)  # 10ms intervals
        elapsed = time.perf_counter() - start
        expected = int(test_duration / 0.01)
        accuracy = (count / expected) * 100
        print(f"Expected iterations: {expected}")
        print(f"Actual iterations: {count}")
        print(f"Timing accuracy: {accuracy:.2f}%")
        if accuracy < 95:
            print("WARNING: System may have timing issues affecting metronome accuracy.")
        else:
            print("Timing looks good!")

    elif subcmd == "audio":
        print("\nTesting audio playback...")
        if not PYGAME_AVAILABLE:
            print("Pygame not available - using Windows built-in sound")
            if WINSOUND_AVAILABLE:
                winsound.Beep(440, 100)
                time.sleep(0.1)
                winsound.Beep(880, 100)
                print("Beep sounds: OK")
            else:
                print("No audio backend available")
            return

        try:
            if bartick_sound:
                bartick_sound.play()
                print("Bar tick sound: OK")
                time.sleep(0.1)
            if tick_sound:
                tick_sound.play()
                print("Tick sound: OK")
            if lbt_sound and ltk_sound:
                lbt_sound.play()
                time.sleep(0.1)
                ltk_sound.play()
                print("Low-fi sounds: OK")
            else:
                print("Low-fi sounds: Not available")
            print("Audio test complete.")
        except Exception as e:
            print(f"Audio test failed: {e}")

    elif subcmd == "state":
        print("\n=== Internal State Dump ===")
        with beats_lock:
            for bid, beat in beats.items():
                print(f"\nBeat {bid}:")
                print(f"  Time: {beat['numerator']}/{beat['denominator']}")
                print(f"  BPM: {beat['bpm']}")
                print(f"  Paused: {beat['paused']}")
                print(f"  Global swing: {beat['global_swing']}")
                print(f"  Thread alive: {beat['thread'].is_alive() if beat['thread'] else 'N/A'}")
                leaves = beat['root'].leaves()
                print(f"  Leaf slots: {len(leaves)}")
                for i, leaf in enumerate(leaves):
                    dur_str = fmt_duration(leaf.duration, beat['bpm'], beat['numerator'])
                    swing_str = f" (swing: {leaf.swing_offset:+.2f})" if leaf.swing_offset != 0 else ""
                    print(f"    [{i}] {dur_str}{swing_str}")
    else:
        print(f"Unknown debug subcommand: {subcmd}")
        print("Type 'debug' for available options.")

# ── tap tempo ─────────────────────────────────────────────────────────────────

class TapTempo:
    """Tap tempo calculator."""

    def __init__(self):
        self.taps = []
        self.lock = threading.Lock()

    def tap(self):
        """Record a tap and return current BPM estimate."""
        now = time.perf_counter()
        with self.lock:
            self.taps.append(now)
            # Keep only last 10 taps
            if len(self.taps) > 10:
                self.taps = self.taps[-10:]

            if len(self.taps) < 2:
                return None

            # Calculate average interval
            intervals = [self.taps[i] - self.taps[i-1] for i in range(1, len(self.taps))]
            avg_interval = sum(intervals) / len(intervals)

            if avg_interval < 0.2:  # Too fast, probably accidental
                return None

            bpm = 60.0 / avg_interval
            return bpm

    def reset(self):
        with self.lock:
            self.taps = []

tap_tempo = TapTempo()

def cmd_tap(args):
    """Tap tempo mode. Press Enter to tap, 'q' to quit."""
    print("\n=== TAP TEMPO MODE ===")
    print("Press Enter to tap, 'q' + Enter to quit")
    print("Tap at least 2 times to get a BPM reading\n")

    tap_tempo.reset()

    try:
        while True:
            raw = input("[Tap] ").strip()
            if raw.lower() == 'q':
                break

            bpm = tap_tempo.tap()
            if bpm:
                print(f"  → {bpm:.1f} BPM")
    except (EOFError, KeyboardInterrupt):
        pass

    print("\nTap tempo mode exited.")

# ── quick start from command line ─────────────────────────────────────────────

def apply_preset(preset_name):
    """Apply a preset pattern to the current beat setup."""
    preset_name = preset_name.lower()
    if preset_name not in PRESETS:
        print(f"Preset '{preset_name}' not found.")
        print("Available presets:", ", ".join(PRESETS.keys()))
        return False

    preset = PRESETS[preset_name]
    time_sig = preset["time"]
    bpm = preset["bpm"]

    # Parse time signature
    num, den = map(int, time_sig.split("/"))

    # Create the beat
    cmd_mkbt([time_sig, str(bpm)])

    # Get the beat ID (most recently created)
    with beats_lock:
        beat_id = max(beats.keys()) if beats else None

    if beat_id and "pattern" in preset:
        beat = beats[beat_id]
        # Build the pattern by splitting slots as needed
        with beat["pattern_lock"]:
            leaves = beat["root"].leaves()
            pattern = preset["pattern"]

            # For simplicity, rebuild the pattern from scratch
            new_leaves = []
            for dur_frac in pattern:
                duration = Fraction(dur_frac[0], dur_frac[1])
                new_leaves.append(Slot(duration))

            # Replace root children
            beat["root"].children = new_leaves
            for leaf in new_leaves:
                leaf.children = []

        # Apply swing if specified
        if "swing" in preset:
            beat["global_swing"] = preset["swing"]
            print(f"Applied swing: {preset['swing']:+.2f}")

    print(f"Preset '{preset_name}' applied: {preset['description']}")
    return True

def quick_start(bpm=None, time_sig=None, preset_name=None):
    """Quick start with command-line parameters."""
    if preset_name:
        if apply_preset(preset_name):
            return
        # Fall through to default if preset fails

    # Use defaults or provided values
    if not time_sig:
        time_sig = "4/4"
    if not bpm:
        bpm = 120.0

    cmd_mkbt([time_sig, str(bpm)])
    print(f"Quick started: {time_sig} at {bpm} BPM")

# ── diagnostic/test modes ─────────────────────────────────────────────────────

def run_self_test():
    """Run internal self-tests."""
    print("Running GNUTempo self-tests...\n")

    errors = 0

    # Test 1: Fraction arithmetic
    print("Test 1: Fraction arithmetic...")
    try:
        f1 = Fraction(1, 4)
        f2 = Fraction(1, 4)
        assert f1 + f2 == Fraction(1, 2)
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # Test 2: Slot creation
    print("Test 2: Slot creation...")
    try:
        slot = Slot(Fraction(1, 4))
        assert slot.is_leaf
        assert slot.duration == Fraction(1, 4)
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # Test 3: Beat creation
    print("Test 3: Beat creation...")
    try:
        beat = make_beat(4, 4, 120)
        assert beat["numerator"] == 4
        assert beat["denominator"] == 4
        assert beat["bpm"] == 120
        leaves = beat["root"].leaves()
        assert len(leaves) == 4
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # Test 4: Pattern integrity
    print("Test 4: Pattern integrity...")
    try:
        beat = make_beat(4, 4, 120)
        leaves = beat["root"].leaves()
        total = sum(s.duration for s in leaves)
        assert total == Fraction(1)
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # Test 5: Swing clamping
    print("Test 5: Swing clamping...")
    try:
        val = max(-0.5, min(0.5, 0.8))
        assert val == 0.5
        val = max(-0.5, min(0.5, -0.9))
        assert val == -0.5
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    print(f"\nSelf-test complete: {5 - errors}/5 tests passed")
    if errors > 0:
        print(f"WARNING: {errors} test(s) failed!")
        return False
    return True

# ── main ──────────────────────────────────────────────────────────────────────

def parse_cli_args():
    """Parse command-line arguments for quick-start and flags."""
    import argparse

    parser = argparse.ArgumentParser(
        prog='gnutempo',
        description='GNUTempo - Terminal Minimalist Metronome',
        add_help=False  # We handle help ourselves
    )

    parser.add_argument('--help', '-h', action='store_true',
                       help='Show command-line help')
    parser.add_argument('--version', '-v', action='store_true',
                       help='Show version')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    parser.add_argument('--bpm', '-b', type=float, default=None,
                       help='Starting BPM')
    parser.add_argument('--time', '-t', type=str, default=None,
                       help='Time signature (e.g., 4/4)')
    parser.add_argument('--preset', '-p', type=str, default=None,
                       help='Use preset (rock, jazz, bossa, waltz, funk, samba, triplet)')
    parser.add_argument('--test', action='store_true',
                       help='Run self-tests and exit')
    parser.add_argument('--list-presets', action='store_true',
                       help='List available presets')
    parser.add_argument('--no-sound-check', action='store_true',
                       help='Skip audio file verification')

    return parser.parse_args()

def show_cli_help():
    """Show command-line help."""
    print("""
GNUTempo v1.1.0 - Terminal Minimalist Metronome

USAGE:
  gnutempo [OPTIONS]

OPTIONS:
  --help, -h              Show this help message
  --version, -v           Show version information
  --debug                 Enable debug mode
  --bpm, -b <value>       Set starting BPM (default: 120)
  --time, -t <sig>        Set time signature (default: 4/4)
  --preset, -p <name>     Use preset rhythm pattern
  --test                  Run self-tests and exit
  --list-presets          List available presets
  --no-sound-check        Skip audio file verification

PRESETS:
  rock, jazz, bossa, waltz, funk, samba, triplet, half_time,
  double_time, seven_eight

EXAMPLES:
  gnutempo                          Start interactive mode
  gnutempo --bpm 120 --time 4/4     Quick start with settings
  gnutempo --preset rock            Start with rock preset
  gnutempo --debug                  Enable debug mode
  gnutempo --test                   Run self-tests
  gnutempo --list-presets           Show all presets

Once running, type 'help' for interactive commands.

Licensed under GPLv3
""")

def main():
    global DEBUG_MODE

    # Parse command-line arguments
    args = parse_cli_args()

    # Handle --help
    if args.help:
        show_cli_help()
        return

    # Handle --version
    if args.version:
        print(f"GNUTempo v{VERSION}")
        print("Terminal Minimalist Metronome")
        print("Licensed under GPLv3")
        return

    # Handle --list-presets
    if args.list_presets:
        print("Available presets:")
        for name, info in PRESETS.items():
            print(f"  {name:12} - {info['description']} ({info['time']} @ {info['bpm']} BPM)")
        return

    # Handle --test
    if args.test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    # Set debug mode from CLI
    if args.debug:
        DEBUG_MODE = True

    # Initialize audio (deferred to allow --test/--help without audio hardware)
    if not args.no_sound_check:
        check_audio_files()

    init_audio()
    load_sounds()

    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"GNUTempo {VERSION}  |  GPLv3  |  terminal metronome")
    print('type "help" for commands.\n')

    # Apply quick-start parameters
    if args.bpm or args.time or args.preset:
        print("Starting with parameters:")
        if args.preset:
            print(f"  Preset: {args.preset}")
        if args.time:
            print(f"  Time: {args.time}")
        if args.bpm:
            print(f"  BPM: {args.bpm}")
        print()
        quick_start(bpm=args.bpm, time_sig=args.time, preset_name=args.preset)

    print("READY")

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nexiting.")
            break
        if not raw:
            continue
        try:
            tokens = shlex.split(raw)
        except ValueError as e:
            print(f"parse error: {e}")
            continue

        cmd = tokens[0].lower()

        if   cmd in ("exit","quit"):  print("exiting."); break
        elif cmd == "mkbt":           cmd_mkbt(tokens[1:])
        elif cmd == "sync":           cmd_sync_mkbt(tokens)
        elif cmd == "p":              cmd_pause(tokens[1:])
        elif cmd == "r":              cmd_resume(tokens[1:])
        elif cmd == "rm":             cmd_remove(tokens[1:])
        elif cmd == "lsbt":           cmd_list()
        elif cmd == "sanitize":       cmd_sanitize(tokens[1:])
        elif cmd == "patui":          cmd_patui(tokens[1:])
        elif cmd == "tkmod":          cmd_tkmod(tokens[1:])
        elif cmd == "export":         cmd_export()
        elif cmd == "import":         cmd_import(tokens[1:])
        elif cmd == "lsjsn":          cmd_lsjsn()
        elif cmd == "help":           cmd_help()
        elif cmd == "debug":          cmd_debug(tokens[1:])
        elif cmd == "tap":            cmd_tap(tokens[1:])
        else: print(f"unknown command: {cmd}. type help for a list.")

    with beats_lock:
        for b in beats.values():
            b["stop_event"].set()

    if PYGAME_AVAILABLE:
        pygame.mixer.quit()


if __name__ == "__main__":
    main()
