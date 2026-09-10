# Stimuli: PsychoPy presentation for the worked-example tasks

Simple task-presentation scripts for the stimulus computer, so this project
can be exercised **end to end with a real task** — not just a mock/replayed
scanner — rather than just analyzing whatever happens to already be in
`dicomDir/`.

**PsychoPy, not Psychtoolbox:** the rest of this project (rt-cloud, the
analysis, the testing scripts) is entirely Python, so PsychoPy keeps that
consistent — these scripts directly reuse
[`../utils/rt_analysis.py`](../utils/rt_analysis.py)'s own events.tsv reader
(via `common.py`), rather than needing a second, disconnected copy of the
task timing in MATLAB.

## Why this matters: one source of truth for timing

`hcp_motor_task.py`, `generic_motor_task.py`, `hcp_gambling_task.py`, and
`blackjack_task.py` read the exact same `study_design/*_events.tsv` files
`taskActivation.py`'s real-time GLM design is built from. There's no
separate, hand-copied timing table to keep in sync — whatever the subject is
actually shown **is** what the analysis assumes happened, by construction.

| Script | Events file | Conditions |
|---|---|---|
| `hcp_motor_task.py` | `../study_design/HcpMotor_acq-ap_events.tsv` | left/right hand, left/right foot, tongue (each with a brief get-ready cue) |
| `generic_motor_task.py` | `../study_design/GenericMotorLR_events.tsv` | this project's own left/right finger-tapping design (`conf/motor.toml`) -- 30s tapping blocks separated by 10s rest, no get-ready cues; the Psychtoolbox equivalent is `../stimuli_ptb/motor_task.m` |
| `blackjack_task.py` | `../study_design/Blackjack_events.tsv` | this project's own two-card blackjack design (`conf/gambling.toml`) -- hit(1)/stay(2) on a dealt hand, then a pre-scripted win/lose/tie outcome; the Psychtoolbox equivalent is `../stimuli_ptb/blackjack_task.m` |
| `hcp_gambling_task.py` | `../study_design/HcpGambling_acq-ap_events.tsv` | the original HCP card-guess task, unchanged: reward, punishment, neutral -- kept as-is for `tutorial/`'s offline validation against the real ds000244 data; not wired to any `conf/*.toml` contrast anymore |

## Install and test PsychoPy

PsychoPy needs a real display (it won't run headless/over SSH without one)
and is a fairly heavy, sometimes finicky install — run this on the actual
stimulus computer, not inside the `brainiak/rtcloud` analysis container.

### Install

A plain `pip install` in a dedicated virtual environment is the most
reliable path and works on most systems:

```bash
python3 -m venv psychopy-env
source psychopy-env/bin/activate        # Windows: psychopy-env\Scripts\activate
pip install --upgrade pip
pip install psychopy
```

A **fresh virtual environment** (rather than installing into whatever
Python already runs the rest of this project) matters here: PsychoPy pulls
in a fairly large, specific set of dependencies (wxPython/pyglet, numpy,
etc.) that can otherwise conflict with other packages.

If `pip install psychopy` fails to build, or the window in the test below
never opens, the [official Standalone PsychoPy
installer](https://www.psychopy.org/download.html) (a self-contained
app/exe bundling a known-good Python + all dependencies) is the more
reliable fallback on macOS/Windows — use its own bundled Python to run the
scripts in this folder instead of `pip`.

**Known platform gotchas:**
- **macOS:** Xcode command-line tools are usually required to build some
  dependencies (`xcode-select --install` if `pip install` fails compiling
  something). Keypresses not registering (see the test below) almost always
  means your terminal app needs **Accessibility** and/or **Input
  Monitoring** permission — System Settings → Privacy & Security.
- **Linux:** you may need a few system packages first (Debian/Ubuntu):
  `sudo apt install libgtk-3-dev libwebkit2gtk-4.0-dev libsdl2-2.0-0`
  (package names vary by distro/PsychoPy version — if `pip install` fails on
  a specific missing library, that's usually the fastest way to find its
  system package).
- **Python version:** PsychoPy tends to lag a release or two behind the
  newest CPython — if `pip install` can't find a compatible build, create
  the virtual environment above with an older Python (e.g. `python3.10 -m
  venv psychopy-env`) rather than fighting the newest one.

### Test

Once installed, confirm it actually works — importing successfully doesn't
guarantee the display backend does — with the smoke test in this folder:

```bash
python test_psychopy_install.py             # fullscreen
python test_psychopy_install.py --windowed   # windowed, e.g. on a laptop
```

It checks three things in order, printing `[ok]`/`[FAIL]` for each so a
failure tells you exactly which layer broke: (1) `psychopy` imports, (2) a
window actually opens (this is where most real install problems show up —
almost always a display/GPU-driver issue, not a PsychoPy bug), (3) a
keypress is detected. A `[warn]` at step 3 with no `[FAIL]` just means no key
was pressed in time — harmless, but see the macOS Accessibility note above
if that keeps happening once you're actually trying to use a keyboard.

Once that passes, you're ready to run `hcp_motor_task.py` /
`generic_motor_task.py` / `blackjack_task.py` / `hcp_gambling_task.py`
below.

## Running

```bash
cd stimuli
python hcp_motor_task.py
python generic_motor_task.py
python blackjack_task.py
python hcp_gambling_task.py
```

All four:
- `generic_motor_task.py` and `blackjack_task.py` **show a task-instructions
  screen first** — a brief description of the task and the subject's goal,
  dismissed with SPACE (or Escape to abort before the run even starts) —
  see `common.show_instructions()` below.
- **Wait for a scanner trigger** before starting (`--trigger-key`, default
  `5,t` — wire the scanner's sync pulse to send one of these, or press it
  yourself on the keyboard to test without a scanner). Every event is then
  timed relative to that exact trigger moment, matching how the real-time
  analysis anchors its own timing to the first DICOM.
- **Log actual vs expected onset time** per event to
  `stimuli/logs/<task>_<timestamp>.tsv`, so you can check real presentation
  accuracy against the design afterward (`--log` to change the path).
- Run fullscreen by default (`--windowed` for testing on a laptop without
  hiding everything else).
- Default to ending at the last scheduled event; pass `--duration <seconds>`
  (e.g. `nVols * TR` from the toml) to keep showing trailing rest/fixation
  for the scanner's actual full run length instead.
- Abort cleanly at any time with **Escape**.

## What each task looks like

**`hcp_motor_task.py`** — a brief gray "get ready: LEFT HAND"-style cue,
then the same instruction in bold green for the movement block itself;
plain fixation (`+`) during rest. Matches `taskActivation.py`'s
`glmCondA=left_hand` / `glmCondB=right_hand` contrast, with the other body
parts (and every `*_cue`) becoming GLM covariates, exactly as
[README.md](../README.md#how-it-works) describes.

**`generic_motor_task.py`** — bold green "LEFT FINGER" / "RIGHT FINGER"
during the 30s tapping blocks; plain fixation (`+`) during the 10s rest
blocks between them (no get-ready cue -- rest doubles as the lead-in).
Matches `conf/motor.toml`'s `glmCondA=left_finger` / `glmCondB=right_finger`
contrast for live analysis.

**`blackjack_task.py`** — each trial deals two cards face-up (never a
natural blackjack -- an Ace paired with a 10-value card is never dealt as
the opening hand); press **1 = HIT** (deal another card) or **2 = STAY**
(freeze the hand) during a brief decision window, then the outcome is
revealed: green `WIN +$1.00`, red `LOSE −$0.50`, or gray `TIE $0.00` -- or
gray "No response `$0.00`" if nothing was pressed in time. The dealt cards
and the hit/stay choice are purely cosmetic and never change the outcome --
which outcome appears and when is entirely driven by the events.tsv, so it
matches `taskActivation.py`'s `glmCondA=win` / `glmCondB=lose` contrast with
`tie` as a covariate. Unlike the other scripts here, it uses its own
per-frame render loop instead of `common.run_events()` (needed for the
hit/stay key handling and a `response_key`/`response_time_s` log, mirroring
`stimuli_ptb/blackjack_task.m`'s own reasons for not using its shared loop
helper either) — see its own module docstring for details.

**`hcp_gambling_task.py`** — the original HCP card-guess task, unchanged:
each trial briefly shows a face-down card ("Higher or Lower? press any
button"), then reveals the outcome: green `+$1.00` (reward), red `−$0.50`
(punishment), or gray `$0.00` (neutral). As in the real HCP task, the guess
doesn't actually change the outcome. Not wired to any `conf/*.toml` contrast
anymore (see the task table above) — run it directly, or via `tutorial/`'s
offline validation.

## Files

- `common.py` — shared helpers: `show_instructions()` (shows a task
  description + goal screen, blocks for a continue keypress), `wait_for_trigger()`
  (blocks for the scanner sync pulse, returns a clock + trigger timestamp),
  `run_events()` (a single continuous render loop that shows the right
  stimulus for wherever you are in the events.tsv relative to that trigger,
  handles rest gaps, timing-error logging, and Escape-to-abort), and a
  re-export of `read_events_tsv()`. Not used by the live analysis pipeline
  itself — only by the task scripts.
- `hcp_motor_task.py`, `generic_motor_task.py`, `blackjack_task.py`,
  `hcp_gambling_task.py` — the four task scripts described above.
- `test_psychopy_install.py` — standalone smoke test (see "Install and test
  PsychoPy" above); no events.tsv or trigger involved, just confirms the
  install itself works.
- `logs/` — created on first run; one timing-accuracy log per session
  (gitignored).
