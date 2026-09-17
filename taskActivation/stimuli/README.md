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

`generic_motor_task.py`, `checkerboard_1cond_task.py`,
`checkerboard_2cond_task.py`, `checkerboard_3cond_task.py`, and
`blackjack_task.py` read the exact same `study_design/*_events.tsv` files
`taskActivation.py`'s real-time GLM design is built from. There's no
separate, hand-copied timing table to keep in sync — whatever the subject
is actually shown **is** what the analysis assumes happened, by
construction.

| Script | Events file | Conditions |
|---|---|---|
| `generic_motor_task.py` | `../study_design/GenericMotorLR_events.tsv` | this project's own left/right finger-tapping design (`conf/motor.toml`) -- 30s tapping blocks separated by 10s rest, no get-ready cues; the Psychtoolbox equivalent is `../stimuli_ptb/motor_task.m` |
| `checkerboard_1cond_task.py` | `../study_design/Checkerboard1Cond_events.tsv` | this project's own flickering-checkerboard ON/OFF localizer (`conf/checkerboard_1cond.toml`) -- 20s ON/OFF blocks, genuine OFF/pattern-A/OFF/pattern-B flicker (not two patterns swapped with no blank); the Psychtoolbox equivalent is `../stimuli_ptb/checkerboard_1cond_task.m` |
| `checkerboard_2cond_task.py` | `../study_design/Checkerboard2Cond_events.tsv` | the LEFT/RIGHT half of `checkerboard_3cond_task.py` (`conf/checkerboard_2cond.toml`) -- no CENTER condition, an ordinary 2-condition GLM contrast, shorter run; the Psychtoolbox equivalent is `../stimuli_ptb/checkerboard_2cond_task.m` |
| `checkerboard_3cond_task.py` | `../study_design/Checkerboard3Cond_events.tsv` | this project's own 3-position checkerboard localizer (`conf/checkerboard_3cond.toml`) -- CENTER is a small foveal square, LEFT/RIGHT are full-height bars flush to the screen edge, same OFF/A/OFF/B flicker as `checkerboard_1cond_task.py`, 3-way one-vs-rest GLM contrast; the Psychtoolbox equivalent is `../stimuli_ptb/checkerboard_3cond_task.m` |
| `blackjack_task.py` | `../study_design/Blackjack_events.tsv` | this project's own two-card blackjack design (`conf/gambling.toml`) -- hit(1)/stay(2) on a dealt hand, then a pre-scripted win/lose/tie outcome; the Psychtoolbox equivalent is `../stimuli_ptb/blackjack_task.m` |

The original HCP motor and card-guess presentation scripts
(`hcp_motor_task.py`, `hcp_gambling_task.py`) have been archived — see
[`../obsolete/README.md`](../obsolete/README.md).

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

Once that passes, you're ready to run `generic_motor_task.py` /
`checkerboard_1cond_task.py` / `checkerboard_2cond_task.py` /
`checkerboard_3cond_task.py` / `blackjack_task.py` below.

## Running

```bash
cd stimuli
python generic_motor_task.py
python checkerboard_1cond_task.py
python checkerboard_2cond_task.py
python checkerboard_3cond_task.py
python blackjack_task.py
```

All five:
- `generic_motor_task.py`, `checkerboard_1cond_task.py`,
  `checkerboard_2cond_task.py`, `checkerboard_3cond_task.py`, and
  `blackjack_task.py` **show a task-instructions screen first** — a brief
  description of the task and
  the subject's goal, dismissed with button 1 or 2 (or Escape to abort
  before the run even starts) — the same digit buttons used for real
  responses, not a keyboard-only SPACE bar the subject won't have in the
  scanner; the text itself tells them to ask the experimenter with
  questions and press any button when ready — see
  `common.show_instructions()` below. It measures the real rendered
  text (`TextStim.boundingBox`) against the real window size and shrinks
  the font until the whole block fits, so the instructions stay fully
  visible at whatever resolution the window actually opens at.
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

**`generic_motor_task.py`** — bold green "LEFT FINGER" / "RIGHT FINGER"
during the 30s tapping blocks; plain fixation (`+`) during the 10s rest
blocks between them (no get-ready cue -- rest doubles as the lead-in).
Matches `conf/motor.toml`'s `glmCondA=left_finger` / `glmCondB=right_finger`
contrast for live analysis.

**`checkerboard_1cond_task.py`** — a flickering black<->white checkerboard
patch centered on screen during 20s ON blocks: a genuine flicker
(`--flicker-hz`, default 8) that goes OFF (blank) -> ON (pattern A) -> OFF
-> ON (pattern B, the black<->white inverse of A) -> repeat, each state
lasting 1/flicker_hz -- so a given screen location truly cycles black ->
white -> black, rather than swapping directly between two checkerboards
with no blank in between (which can look like a static image). Alternates
with plain fixation (`+`) during 20s OFF/rest blocks; 6 reps + a trailing
rest block, 260s total. Matches `conf/checkerboard_1cond.toml`'s
`glmCondA=checkerboard` / `glmCondB=''` (ON vs the implicit rest baseline)
contrast for live analysis. The Psychtoolbox equivalent is
`../stimuli_ptb/checkerboard_1cond_task.m`.

**`checkerboard_2cond_task.py`** — the LEFT/RIGHT half of
`checkerboard_3cond_task.py`, with the CENTER condition (and its associated
rest block each rep) dropped entirely: same OFF/A/OFF/B flicker, same
full window-height bars flush to the screen edge, same fixation-cross
behavior, but only 2 conditions and a shorter run. 17 blocks
(rest/left/rest/right x4 + trailing rest), 204s total. Since it's an
ordinary 2-condition design, it matches `taskActivation.py`'s standard
`glmCondA=left` / `glmCondB=right` contrast (`conf/checkerboard_2cond.toml`)
— not the task-specific 3-way mode `checkerboard_3cond.toml` uses. The
Psychtoolbox equivalent is `../stimuli_ptb/checkerboard_2cond_task.m`.

**`checkerboard_3cond_task.py`** — the same OFF/A/OFF/B flicker as
`checkerboard_1cond_task.py` (`--flicker-hz`, default 8), shown in one of
three screen positions per 12s block: CENTER, LEFT, or RIGHT. CENTER is a
SQUARE (its height set equal to its own width, not the window height)
centered on screen, so it stimulates only the fovea; LEFT and RIGHT are
full window-height BARS, anchored flush against the window's left/right
edge respectively (no gap), so each reaches as far into the periphery as
the window allows. A `+` fixation cross stays visible on **every** frame
of **every** condition (including rest, and every OFF phase) so the
subject can hold central gaze while LEFT/RIGHT stimulate the visual
periphery. 25 blocks (rest/center/rest/left/rest/right x4 + trailing
rest), 300s total. Matches `conf/checkerboard_3cond.toml`'s 3-way
one-vs-rest GLM contrast (`glmCondA=center` / `glmCondB=left` /
`glmCondC=right`, each contrasted against the mean of the other two) for
live analysis. The Psychtoolbox equivalent is
`../stimuli_ptb/checkerboard_3cond_task.m`.

**`blackjack_task.py`** — each 3.0s trial deals two cards face-up, with a
value that fits the trial's own pre-scripted outcome (see
`deal_initial_hand()`): never a natural blackjack (an Ace paired with a
10-value card, value 21) on any trial; on `lose` specifically, no card is
ever an Ace at all and the value is 12-20 (never an implausible
near-certain loss, never already busted); on `win`, the value is 16-20 or
under 10 (never the awkward 10-15 middle); `tie` is otherwise
unconstrained. Press **1 = HIT** or **2 = STAY**
any time during a 2.0s decision window. Whichever comes first: the SAME
instant you respond, HIT deals one more card -- chosen so it never busts
the hand on a WIN or TIE trial, and never brings it to exactly 21 on a
LOSE trial (see `deal_hit_card()`) -- and immediately reveals the outcome;
STAY immediately reveals the outcome with your current hand -- no waiting
out the rest of
the decision window once you've answered. The outcome (shown for whatever
time is left in the trial, at least 1.0s): green `WIN +$1.00`, gray
`TIE $0.00`, or red `−$0.50` labeled `BUST` or `DEALER WON` -- `BUST` if the
cosmetic hand's own blackjack value (standard scoring: number cards at face
value, face cards worth 10, Aces worth 1 or 11) is over 21, otherwise
`DEALER WON` -- or gray "No response `$0.00`" if nothing was pressed within
the full 2.0s. The dealt cards and the hit/stay choice (and the BUST/DEALER
WON message) are purely cosmetic and never change the outcome -- which outcome
appears and when is entirely driven by the events.tsv, so it matches
`taskActivation.py`'s `glmCondA=win` / `glmCondB=lose` contrast with `tie`
as a covariate. The hand, prompt, and outcome text are each sized against
the real window (see `common.fit_text_stim()`) and given their own
non-overlapping vertical region, so nothing runs off-screen or overlaps at
any resolution. Trials are separated by a variable inter-trial interval
(jittered 1.0-3.0s, ~2s mean) of plain fixation, so the design isn't
perfectly periodic. 58 trials (24 win / 24 lose / 10 tie), ~5 minutes
total. Unlike the other scripts here, it uses its own
per-frame render loop instead of `common.run_events()` (needed for the
hit/stay key handling and a `response_key`/`response_time_s` log, mirroring
`stimuli_ptb/blackjack_task.m`'s own reasons for not using its shared loop
helper either) — see its own module docstring for details.

## Files

- `common.py` — shared helpers: `show_instructions()` (shows a task
  description + goal screen, blocks for a continue keypress), `fit_text_stim()`
  (shrinks a TextStim's height until it actually fits within a fraction of
  the real window's width/height -- used by `show_instructions()` and by
  `blackjack_task.py`'s hand/prompt/outcome text), `wait_for_trigger()`
  (blocks for the scanner sync pulse, returns a clock + trigger timestamp),
  `run_events()` (a single continuous render loop that shows the right
  stimulus for wherever you are in the events.tsv relative to that trigger,
  handles rest gaps, timing-error logging, and Escape-to-abort), and a
  re-export of `read_events_tsv()`. Not used by the live analysis pipeline
  itself — only by the task scripts.
- `generic_motor_task.py`, `checkerboard_1cond_task.py`,
  `checkerboard_2cond_task.py`, `checkerboard_3cond_task.py`,
  `blackjack_task.py` — the five task scripts described above.
- `test_psychopy_install.py` — standalone smoke test (see "Install and test
  PsychoPy" above); no events.tsv or trigger involved, just confirms the
  install itself works.
- `logs/` — created on first run; one timing-accuracy log per session
  (gitignored).
