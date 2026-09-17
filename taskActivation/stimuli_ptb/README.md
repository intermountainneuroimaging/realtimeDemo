# Stimuli: Psychtoolbox-3 presentation (MATLAB)

A Psychtoolbox-3 (MATLAB) version of the [`../stimuli/`](../stimuli/)
PsychoPy task scripts, for sites already standardized on MATLAB/PTB for
stimulus presentation. Same role: run on the **stimulus computer**,
presenting a real task to the subject while `taskActivation.py` (in the
container, on the analysis side) analyzes the incoming scanner DICOMs in
real time. This folder is independent of `../stimuli/` — pick whichever
toolkit your site already uses; both read the same `study_design/*_events.tsv`
files so the real-time analysis assumes exactly what's actually presented.

## Tasks

| Script | Events file | Design |
|---|---|---|
| `motor_task.m` | `../study_design/GenericMotorLR_events.tsv` | 30s LEFT FINGER / RIGHT FINGER tapping blocks separated by 10s REST blocks (3 reps each + trailing rest, 13 blocks / 250s) |
| `blackjack_task.m` | `../study_design/Blackjack_events.tsv` | this project's own two-card blackjack design: hit(1) or stay(2), any time in a 2.0s decision window, immediately reveals a pre-scripted win / lose / tie outcome (3.0s/trial), separated by a jittered 1.0-3.0s inter-trial interval -- 58 trials (24 win / 24 lose / 10 tie), ~5 minutes total |
| `checkerboard_1cond_task.m` | `../study_design/Checkerboard1Cond_events.tsv` | 20s ON/OFF blocks: full-contrast checkerboard (genuine OFF/A/OFF/B flicker, not two patterns swapped with no blank) vs fixation (6 reps + trailing rest, 13 blocks / 260s) |
| `checkerboard_2cond_task.m` | `../study_design/Checkerboard2Cond_events.tsv` | the LEFT/RIGHT half of `checkerboard_3cond_task.m` with CENTER dropped entirely -- an ordinary 2-condition design, not the 3-way one-vs-rest -- 12s blocks, 4 reps of each + rest between every block, 204s total |
| `checkerboard_3cond_task.m` | `../study_design/Checkerboard3Cond_events.tsv` | a 3-position visual localizer flickering OFF/A/OFF/B (same reversal-with-blank flicker as `checkerboard_1cond_task.m`) in CENTER, LEFT, or RIGHT screen position per block -- CENTER is a small foveal square, LEFT/RIGHT are full window-height bars flush to the screen edge -- with a central fixation cross visible throughout -- 12s blocks, 4 reps of each + rest between every block, 300s total |

All events.tsv files live in the top-level `study_design/` (not
`tutorial/study_design/`) — the exact folder `taskActivation.py` itself
reads `eventsFile` from — so what MATLAB presents and what the live
analysis assumes can never point at different copies of the same design.

Each task has its own ready-to-use config — `../conf/motor.toml`,
`../conf/checkerboard_1cond.toml`, `../conf/checkerboard_2cond.toml`,
`../conf/checkerboard_3cond.toml`, `../conf/gambling.toml` — with the
matching `eventsFile` and GLM contrast already set:

| Task | `conf/*.toml` | `eventsFile` | `glmCondA` | `glmCondB` | `glmCondC` |
|---|---|---|---|---|---|
| Motor | `motor.toml` | `GenericMotorLR_events.tsv` | `left_finger` | `right_finger` | — |
| Checkerboard (1-condition) | `checkerboard_1cond.toml` | `Checkerboard1Cond_events.tsv` | `checkerboard` | *(empty — single-condition beta map, i.e. ON vs the implicit rest/OFF baseline)* | — |
| Checkerboard (2-condition) | `checkerboard_2cond.toml` | `Checkerboard2Cond_events.tsv` | `left` | `right` | — |
| Checkerboard (3-condition) | `checkerboard_3cond.toml` | `Checkerboard3Cond_events.tsv` | `center` | `left` | `right` |
| Gambling (blackjack) | `gambling.toml` | `Blackjack_events.tsv` | `win` | `lose` | — |

`glmCondC` is **task-specific** — only `checkerboard_3cond.toml` sets it, and
only `taskActivation.py`'s pipeline for that one task understands it (see
"3-way (one-vs-rest) contrast" below). Every other task's toml leaves it
unset, with no change to how those are analyzed.

Run any of the five end to end with `../run_task.py` (see
[README.md](../README.md#running-with-live-scanner-data) / `quickstart.sh
<task>` in the main project) — e.g. `python ../run_task.py motor`. The
original HCP motor and card-guess presentation scripts
(`../obsolete/stimuli_ptb/gambling_task.m` and its PsychoPy/events-file
counterparts) have been archived — see
[`../obsolete/README.md`](../obsolete/README.md).

## Responses are recorded via KbQueue, not KbCheck

**Why this matters:** an MRI-compatible response button box typically
presents itself to the OS as a keyboard sending one very brief keydown
pulse per press — not a key held down the way a real keypress usually is.
A plain per-frame `KbCheck` only reports whatever is down at the *exact
instant* you call it, so in a realtime presentation loop (busy drawing and
waiting on `Screen('Flip')`) that pulse can easily land entirely between
two checks and simply never be seen.

`blackjack_task.m` starts a `KbQueue` once for the **whole run**
(`ptb_kbqueue_setup.m`), which hands keyboard buffering off to PTB's own
background collection — every press is timestamped and stored the instant
it happens, regardless of what the main loop is doing at that moment.
`ptb_kbqueue_check_any.m` is then polled once per frame and always sees
whatever was buffered since the last check, no matter how the loop's own
timing lined up with the actual press. The **same** per-frame check also
catches Escape (rather than a second, separately-fallible `KbCheck` call),
so an abort can't be missed for the same reason a response can't.

Each trial's response is written into the timing log's `response_key` /
`response_time_s` columns (`'none'` / `NaN` if the subject didn't respond in
time) -- `blackjack_task.m`'s single hit/stay press (whichever comes first
ends that trial's decision phase immediately -- see "What each task looks
like" below) never changes the outcome — which outcome appears and when is
entirely driven by the events.tsv.

`motor_task.m` and the three checkerboard tasks don't collect responses at
all (pure block presentation), so they don't use a `KbQueue` — Escape is
checked with a plain `KbCheck` each frame in `ptb_run_block_loop.m`, which
is fine for an experimenter manually aborting (unlike a scanner button
pulse, nothing is lost if a keypress held for a moment is seen a frame
later).

## Task instructions screen

`motor_task.m`, `checkerboard_1cond_task.m`, `checkerboard_2cond_task.m`,
`checkerboard_3cond_task.m`, and `blackjack_task.m` each show a brief
task-instructions screen — what the
task is and what the subject's
goal is — right after the window opens, **before** the "Waiting for scanner
trigger..." screen. `ptb_show_instructions.m` draws the text and blocks
until button 1 or 2 is pressed (via the same `KbQueue` mechanism as
everything else here — see above), or returns early if Escape is pressed
so the caller can abort before the run even starts. Using the same 1/2
buttons as the MRI response box (rather than a keyboard-only SPACE bar the
subject won't have in the scanner) means the subject dismisses the
instructions with the same button(s) they'll use for real responses; the
instructions text itself tells them to "ask the experimenter" if they have
questions and "press any button" when ready, matching this listening
window. The instructions text itself is a fixed string in each task
script, not a configurable option — edit it directly there if you want
different wording for your site.

**Fits the real window, at any resolution:** rather than a fixed font size
that only happens to fit at whatever resolution it was eyeballed on,
`ptb_show_instructions.m` uses the shared `ptb_fit_text_size.m` to measure
the real window (`Screen('Rect')`) and the real rendered text
(`DrawFormattedText`'s `DoDraw=0` "measure only" mode) and shrink the font
until the whole block fits, before actually drawing it — so the full
instructions stay visible whether this is fullscreen on a scanner-room
projector or the small 1024×768 `'Windowed'` test window. `blackjack_task.m`
uses the same helper for its card hand, "1 = HIT / 2 = STAY" prompt, and
outcome text — see its own entry in "What each task looks like" below.

## Screen / display setup

`ptb_open_window.m` (used by every script here) takes:
- **`'Windowed'`** — `true` opens a small 1024×768 test window instead of
  filling the stimulus display; use this for testing on a laptop.
- **`'ScreenWidth'` / `'ScreenHeight'`** — an explicit pixel resolution to
  open at (e.g. `1920`/`1080` for a known scanner-room projector), instead
  of trusting the display's auto-detected native resolution. Pass both to
  keep stimulus sizing in pixels reproducible across rooms/monitors, or
  when a projector reports an unreliable resolution. Default `[]`:
  auto-detect.
- **Display selection**: with more than one screen attached, opens on the
  **second** one (`Screen('Screens')` index 2) — the projector/stimulus
  display in a typical two-monitor scanner-room setup (control-room monitor
  = screen 1) — falling back to the only screen available otherwise.
- **`'SkipSyncTests'`** — `true` disables PTB's flip-timing sync tests, only
  for testing on a non-research display (laptop, VM, remote desktop) that
  can't pass them. Leave `false` for a real session so real timing problems
  aren't silently hidden.

## Clean exit on every path

Every task script wraps its window (and, for `blackjack_task.m`, its
`KbQueue`) in MATLAB's `onCleanup`, e.g.:
```matlab
win = ptb_open_window(...);
cleanupWin = onCleanup(@() sca);   % Screen('CloseAll') + ShowCursor + Priority(0)
```
`onCleanup` fires when the function exits **for any reason** — normal
completion, an Escape-triggered abort, or an uncaught error partway through
— so the display and keyboard queue are always released and the subject is
never left staring at a frozen/black screen because of a bug or a MATLAB
error dialog. `blackjack_task.m` also always writes its timing log
(including whatever responses were recorded) before returning, even on an
Escape abort.

The one exception: pass `'Win', <handle>` (see "Running several tasks in one
session" below) and a task BORROWS that window instead of opening/owning
one — it skips `ptb_open_window`/the `sca` cleanup entirely, since closing a
window it didn't open would pull the display out from under whatever opened
it (`run_battery.m`, in practice). The window still always gets released
eventually — `run_battery.m` owns that cleanup instead, with the exact same
`onCleanup(@() sca)` pattern, just once for the whole session rather than
once per task.

## Install and test Psychtoolbox

Psychtoolbox-3 needs MATLAB and a real display; it won't run headless. Use
the [official installer](http://psychtoolbox.org/download) (`DownloadPsychtoolbox.m`,
run once from MATLAB) rather than any generic package manager — this is the
supported path and handles the platform-specific pieces (kernel driver on
macOS, GStreamer on Linux, etc.) that a plain file copy would miss. See
psychtoolbox.org's own OS-specific prerequisites (macOS: Xcode command-line
tools; Linux: GStreamer plugins; Windows: specific driver requirements)
before running it.

### Test

Once installed, confirm it actually works — a successful install doesn't
guarantee the display/keyboard backend does — with the smoke test in this
folder (run from MATLAB, with this folder on the path or as the current
folder):

```matlab
test_ptb_install
test_ptb_install('Windowed', true)                          % windowed, e.g. on a laptop
test_ptb_install('ScreenWidth', 1920, 'ScreenHeight', 1080)  % a known projector resolution
```

It checks three things in order, printing `[ok]`/`[FAIL]` for each so a
failure tells you exactly which layer broke: (1) `Screen()` (the core PTB
mex file) is on the path and runs, (2) a window actually opens (this is
where most real install problems show up — almost always a display/GPU
driver issue, not a Psychtoolbox bug), (3) a keypress is detected via
`KbQueue`, **printing the exact PTB key name for whatever you press**.

**Use step 3 to find your trigger/button-box's real key names.** MRI sync
pulses and response boxes often present as the *shifted-symbol* name PTB
gives a number key rather than the plain digit — e.g. `'5%'` instead of
`'5'`, `'1!'`/`'2@'` instead of `'1'`/`'2'` — depending on the interface
hardware. The task scripts' defaults already include both forms
(`{'5','5%','t'}` for triggers, `{'1','1!','2','2@'}` for
`blackjack_task.m`'s hit/stay), but if your site's box reports something
else entirely, run `test_ptb_install`, press the actual trigger or button
once, and pass whatever it prints via `'TriggerKey'` / `'ResponseKeys'`.

**Known platform gotchas:**
- **`Screen.mex... seems to be missing or inaccessible` / `AssertOpenGL`
  fails, even on a real, working Psychtoolbox install:** `ptb_open_window.m`
  deliberately does NOT call `PsychDefaultSetup` for this reason —
  `PsychDefaultSetup(2)` wraps an `AssertOpenGL` check that has been
  observed to fail this way on some installs where `Screen`/`PsychImaging`
  work completely fine when called directly (this matches a known-working
  MATLAB/PTB script from this lab, which never calls `PsychDefaultSetup`
  either — see `ptb_open_window.m`'s comments). If you hit this from your
  *own* code (not this project's scripts), try calling `Screen`/
  `PsychImaging` directly instead of through `PsychDefaultSetup`.
- If Psychtoolbox itself is installed inside a cloud-synced folder
  (OneDrive, Dropbox, iCloud Drive, Google Drive), that's a second possible
  contributor to the same symptom: the sync client's placeholder/
  on-demand-download behavior can prevent a compiled `.mex` binary from
  being read as a real local executable, even though it's right there in a
  folder listing. Installing Psychtoolbox itself (`DownloadPsychtoolbox`'s
  target folder) to a plain local path like `~/Psychtoolbox` rules this out
  — this project's own folder living under a cloud-synced Documents is fine
  (it's just `.m` source), the concern is specifically Psychtoolbox's own
  compiled binaries.
- **Apple Silicon Macs (M1/M2/M3+):** `SetupPsychtoolbox` itself can refuse
  to finish — `Tried to setup on native Matlab or Octave for Apple Silicon
  64-Bit ARM. This is not supported` (and, just before that, a harmless
  `FAILED!` trying to strip the macOS quarantine flag from files that don't
  exist yet because setup never got that far). This isn't a bug in this
  project's scripts — Psychtoolbox ships no native arm64 `.mex` files at
  all, only Intel/x86_64 ones, so it flatly refuses to install on a native
  arm64 MATLAB or Octave. Fix by installing an **Intel (x86_64) build of
  MATLAB** (download that variant directly from MathWorks, not the
  Apple-Silicon/Universal one — it runs automatically under Rosetta 2) or
  an Intel build of Octave (`arch -x86_64 /usr/local/bin/brew install
  octave`, using an Intel Homebrew prefix), then re-run
  `SetupPsychtoolbox` from **inside that Intel session**. Once it's
  actually running under Rosetta 2, a *second*, different message —
  `PTB-ERROR: SYNCHRONIZATION FAILURE` when opening a window — is expected,
  not a sign anything is broken: Psychtoolbox's own startup warning says
  its timing/timestamping mechanisms are unreliable on Apple's own GPU and
  that sync tests should be expected to fail there. Pass `'SkipSyncTests',
  true` to every task script to get past that for local testing. **This is
  fine for testing the task logic, but PTB's own docs call visual timing on
  these Macs untrustworthy either way** — don't use an Apple Silicon Mac as
  the actual stimulus computer for a real scanner session; use an Intel
  Mac, Windows, or Linux machine there instead, with `SkipSyncTests` left
  `false` so real timing problems on that machine aren't hidden. If you
  just want to try out the task logic without fighting Rosetta/Intel-MATLAB
  setup, the PsychoPy scripts in [`../stimuli/`](../stimuli/) are pure
  Python and run natively on Apple Silicon with no such restriction.
- **macOS:** keypresses not registering almost always means MATLAB needs
  **Accessibility** and/or **Input Monitoring** permission — System
  Settings → Privacy & Security.
- **Linux:** missing GStreamer plugins are the most common install failure;
  the Psychtoolbox installer's own output names the exact package.
- **All platforms:** run `Screen('Preference', 'SkipSyncTests', ...)`
  troubleshooting (PTB prints a detailed report) rather than just leaving
  `SkipSyncTests` on — a real scanner-room display should pass cleanly.

Once that passes, you're ready to run `motor_task.m` / `blackjack_task.m` /
`checkerboard_1cond_task.m` / `checkerboard_2cond_task.m` /
`checkerboard_3cond_task.m` below.

## Running

```matlab
motor_task
blackjack_task
checkerboard_1cond_task
checkerboard_2cond_task
checkerboard_3cond_task
```

All five:
- **Show a task-instructions screen first** — a brief description of the
  task and the subject's goal, dismissed with button 1 or 2 (or Escape to
  abort before the run even starts). See "Task instructions screen" below.
- **Wait for a scanner trigger** before starting (`'TriggerKey'`, default
  `{'5','5%','t'}` — wire the scanner's sync pulse to send one of these, or
  pass `'TriggerKey', {'space'}` to press it yourself on the keyboard to
  test without a scanner). Every event is then timed relative to that exact
  trigger moment (`GetSecs()`), matching how the real-time analysis anchors
  its own timing to the first DICOM.
- **Log actual vs expected onset time** per event to
  `stimuli_ptb/logs/<task>_<timestamp>.tsv` (`blackjack_task.m`'s logs also
  have `response_key` / `response_time_s` columns — see above), so you can
  check real presentation accuracy against the design afterward
  (`'LogPath'` to change the path).
- Fill the stimulus display by default (`'Windowed', true` for testing on a
  laptop without hiding everything else; `'ScreenWidth'`/`'ScreenHeight'`
  for a known projector resolution — see "Screen / display setup" above).
- Default to ending at the last scheduled event; pass `'Duration', <seconds>`
  (e.g. `nVols * TR` from the toml) to keep showing trailing rest/fixation
  for the scanner's actual full run length instead.
- Abort cleanly at any time with **Escape** — see "Clean exit on every path"
  above.

## Running several tasks in one session

Calling task scripts directly, one after another, closes the display and
dumps back to the MATLAB desktop/workspace between EVERY one — each opens
its own window and closes it (`sca`) on exit (see "Clean exit on every path"
above). For a real scanning session running several tasks back-to-back,
that's a jarring flash to the desktop (and back) between every run.
`run_battery.m` opens the window ONCE, runs each task in sequence sharing
it, and closes it ONCE at the end:

```matlab
run_battery({ ...
    {@motor_task,               {}}, ...
    {@checkerboard_3cond_task,  {}}, ...
    {@blackjack_task,           {}}, ...
})
```

Each entry is `{taskFunctionHandle, argsCell}` — `argsCell` is that task's
own name-value args exactly as you'd pass them directly (`{}` for defaults);
`'Win'` is added automatically, so don't pass it yourself. Window-level
options (`'Windowed'`, `'ScreenWidth'`/`'ScreenHeight'`, `'SkipSyncTests'`)
go on the `run_battery` call itself, since they apply to the one shared
window, not to an individual task:

```matlab
run_battery({{@motor_task, {'TriggerKey', {'space'}}}}, 'Windowed', true)   % quick test
```

Before EVERY task (including the first), a plain "staging" screen shows,
reading `Up next: <task> (i of N) — Experimenter: press SPACE to continue.`
— a deliberate, controlled breakpoint so the experimenter decides exactly
when each task starts, rather than it auto-starting the instant
`run_battery` is called or the moment the previous task ends. Escape at a
staging screen stops the whole battery there (the window still closes
cleanly). See `ptb_show_staging_screen.m`.

This works because every task script already takes `win` as a parameter
everywhere it matters (`ptb_wait_for_trigger`, `ptb_run_block_loop`, etc.)
— only the window's own open/close was ever hardwired to "this task owns
it," so passing `'Win'` just opts a task out of that ownership. Nothing else
about how a task runs changes.

## What each task looks like

**`motor_task.m`** — bold green "LEFT FINGER" / "RIGHT FINGER" during the
movement blocks; plain fixation (`+`) during rest. Matches
`taskActivation.py`'s `glmCondA=left_finger` / `glmCondB=right_finger`
contrast when the toml is pointed at `GenericMotorLR_events.tsv`.

**`blackjack_task.m`** — each 3.0s trial deals two cards face-up, with a
value that fits the trial's own pre-scripted outcome (see
`deal_initial_hand()`): never a natural blackjack (an Ace paired with a
10-value card, value 21) on any trial; on `lose` specifically, no card is
ever an Ace at all and the value is 12-20 (never an implausible
near-certain loss, never already busted); on `win`, the value is 16-20 or
under 10 (never the awkward 10-15 middle); `tie` is otherwise
unconstrained. The subject may press **1 = HIT**
or **2 = STAY** any time during a 2.0s decision window. Whichever comes
first: the SAME instant the subject responds, HIT deals one more card --
chosen so it never busts the hand on a WIN or TIE trial, and never brings
it to exactly 21 on a LOSE trial (see `deal_hit_card()`) -- and immediately
reveals the outcome; STAY immediately reveals the outcome with the current
hand — no
waiting out the rest of the decision window once an answer is given. The
outcome (shown for whatever time is left in the trial, at least 1.0s):
green `WIN +$1.00`, gray `TIE $0.00`, or red `−$0.50` labeled `BUST` or
`DEALER WON` — `BUST` if the cosmetic hand's own blackjack value (standard
scoring: number cards at face value, face cards worth 10, Aces worth 1 or
11) is over 21, otherwise `DEALER WON` — or gray "No response `$0.00`" if nothing
was pressed within the full 2.0s, regardless of what the trial was
scheduled to pay out (an incentive to actually respond; the events.tsv /
GLM design are unaffected). The dealt cards and the hit/stay choice (and
the BUST/DEALER WON message) are purely cosmetic and never change the
outcome —
matches `taskActivation.py`'s `glmCondA=win` / `glmCondB=lose` contrast
with `tie` as a covariate. The hand, prompt, and outcome text are each
sized against the real window (see `ptb_fit_text_size.m`) and given their
own non-overlapping vertical region, so nothing runs off-screen or overlaps
at any resolution, whether the hand has two cards or three. Trials are
separated by a variable inter-trial interval (jittered 1.0-3.0s, ~2s mean)
of plain fixation, so the design isn't perfectly periodic. 58 trials (24
win / 24 lose / 10 tie), ~5 minutes total.

**`checkerboard_1cond_task.m`** — a full-contrast checkerboard patch centered
on screen during ON blocks, with a genuine flicker: OFF (blank) -> ON
(pattern A) -> OFF -> ON (pattern B, the black<->white inverse of A) ->
repeat, each state lasting `1/'FlickerHz'` (default 8) -- so a given screen
location truly cycles black -> white -> black, rather than swapping
directly between two checkerboards with no blank in between (which can
look like a static image). Plain fixation during OFF blocks. Matches
`taskActivation.py`'s `glmCondA=checkerboard` beta-weight map (no second
condition — set `glmCondB=""` in the toml) when pointed at
`Checkerboard1Cond_events.tsv`.

**`checkerboard_2cond_task.m`** — the LEFT/RIGHT half of
`checkerboard_3cond_task.m`, with the CENTER condition (and its associated
rest block each rep) dropped entirely: same OFF/A/OFF/B flicker, same
full window-height bars flush to the screen edge, same fixation-cross
behavior, but only 2 conditions and a shorter run (204s vs 300s). Since
it's an ordinary 2-condition design, it does NOT use the task-specific
3-way mode below — it matches `taskActivation.py`'s standard
`glmCondA=left` / `glmCondB=right` contrast, the same as every other
task's toml.

**`checkerboard_3cond_task.m`** — the same OFF/A/OFF/B flicker as
`checkerboard_1cond_task.m`, shown in the CENTER, LEFT, or RIGHT of the
screen depending on the block. CENTER is a SQUARE (`centerWidthFraction` of
the screen wide AND tall, not the full window height) centered on screen,
so it stimulates only the fovea; LEFT and RIGHT are full window-height
BARS (`sideWidthFraction` wide) anchored flush against the window's
left/right edge respectively (no gap), reaching as far into the periphery
as the window allows. A small `+` fixation cross stays visible at screen
center through every block (including every OFF phase) so the subject can
hold central gaze while the periphery is stimulated. Matches
`taskActivation.py`'s task-specific 3-way one-vs-rest mode (`glmCondA=center`
/ `glmCondB=left` / `glmCondC=right`) — see "3-way (one-vs-rest) contrast:
checkerboard_3cond only" below.

The original HCP card-guessing task (`gambling_task.m` — face-down card,
"Higher or Lower?", reward/punishment/neutral, the guess never changes the
outcome) has been archived — see
[`../obsolete/README.md`](../obsolete/README.md).

## 3-way (one-vs-rest) contrast: checkerboard_3cond only

Every other task/toml in this project contrasts exactly two conditions
(`glmCondA` minus `glmCondB`, or just `glmCondA`'s own beta weight). Setting
`glmCondC` — a config key ONLY `conf/checkerboard_3cond.toml` uses — switches
`taskActivation.py`'s live mosaic to three separate contrasts instead:
`glmCondA` vs the mean of `glmCondB`+`glmCondC`, `glmCondB` vs the mean of
`glmCondA`+`glmCondC`, and `glmCondC` vs the mean of `glmCondA`+`glmCondB` —
each thresholded and overlaid on the SAME brain slices in its own solid
color: **blue** (`glmCondA`/center), **red** (`glmCondB`/left), **green**
(`glmCondC`/right). The peak-voxel HRF-fit trace rows below the mosaic
follow the same blue/red/green convention (`taskActivation.py` passes a
matching `colors` list to `glm_voxel_traces()` for this case).

This is a **task-specific** addition, not a generic feature every
`conf/*.toml` can opt into — `glmCondC` and the 3-way rendering path
(`glm_beta_contrast_one_vs_rest()`, `nilearn_stat_png_3way()`,
`write_live_update_3way()` in `utils/rt_analysis.py`) exist alongside, not
instead of, the normal 2-condition machinery every other task keeps using
unchanged. Two things the normal path has that this one doesn't:
- **The web Data Plots tab** — untouched; it still shows a single ROI
  %-signal-change line from the first condition of interest (`center`),
  same mechanism as every other task, not a 3-way view.
- **The end-of-run activation GIF** — a no-op here even with `--save-gif`
  passed. `build_activation_gif()` only knows how to replay the standard
  single-contrast bundle format; `write_live_update_3way()` deliberately
  skips writing that bundle at all (see its own docstring) rather than
  produce a broken replay.

## Files

- `ptb_read_events_tsv.m` — reads a BIDS-style `events.tsv` into a table
  (onset, duration, trial_type).
- `ptb_open_window.m` — shared window setup (see "Screen / display setup").
- `ptb_kbqueue_setup.m` / `ptb_kbqueue_check_any.m` / `ptb_kbqueue_teardown.m`
  — the KbQueue mechanism described above (create+start once, poll per
  frame, stop+release at the end).
- `ptb_wait_for_trigger.m` — blocks until the scanner trigger (or a test
  keypress), via the same KbQueue mechanism, returning the trigger's
  `GetSecs()` timestamp.
- `ptb_show_instructions.m` — shows the task-instructions screen (see
  above) and blocks until a continue key (or Escape) is pressed, via the
  same KbQueue mechanism.
- `ptb_fit_text_size.m` — finds a font size + wrap-at that makes a piece of
  text actually fit within a fraction of the real window's width/height
  (see "Fits the real window, at any resolution" above); shared by
  `ptb_show_instructions.m` and `blackjack_task.m`.
- `ptb_run_block_loop.m` — the render loop `motor_task.m` and all three
  checkerboard tasks share: draws whatever the caller's `stimFor` callback
  returns for the current time, handles rest gaps, writes the
  timing-accuracy log, and checks Escape.
- `ptb_write_event_log.m` — writes a tab-delimited log from a header +
  row cell array.
- `ptb_show_staging_screen.m` — the harmless between-tasks breakpoint screen
  (see "Running several tasks in one session" above), via the same KbQueue
  mechanism, dismissed with SPACE (Escape stops the whole battery).
- `run_battery.m` — runs several task scripts back-to-back sharing ONE
  window instead of one per task (see "Running several tasks in one session"
  above).
- `motor_task.m`, `blackjack_task.m`, `checkerboard_1cond_task.m`,
  `checkerboard_2cond_task.m`, `checkerboard_3cond_task.m` — the five task
  scripts described above.
- `test_ptb_install.m` — standalone smoke test (see "Install and test
  Psychtoolbox" above); also the fastest way to discover your trigger/
  button box's real PTB key names.
- `logs/` — created on first run; one timing-accuracy log per session
  (gitignored).

## A note on testing

Psychtoolbox needs MATLAB and a real display, neither of which is available
in the environment these scripts were written in — they were built by
reading Psychtoolbox's documented API and cross-checked against a real,
working MATLAB/PTB experiment script from this lab (confirming the KbQueue
response pattern, screen-size/display-selection conventions, and clean-exit
structure above), and checked for structural/syntax correctness, but they
have **not** been run end-to-end in MATLAB (`blackjack_task.m`,
`checkerboard_2cond_task.m`, and `checkerboard_3cond_task.m` included — no
Octave/MATLAB was available to execute any of them in this environment;
their underlying designs were instead validated indirectly, by confirming
`Blackjack_events.tsv`/`gambling.toml`, `Checkerboard3Cond_events.tsv`/
`checkerboard_3cond.toml`, and `Checkerboard2Cond_events.tsv`/
`checkerboard_2cond.toml` each produce the expected GLM classification,
and a real end-to-end run against the mock scanner in Docker -- for
checkerboard_3cond, including the 3-way one-vs-rest mosaic rendering itself,
which was additionally verified directly with synthetic data on this
machine's own Python/nilearn install before the Docker run;
checkerboard_2cond's geometry/flicker logic was additionally verified
directly against its own PsychoPy port, which was rendered and visually
confirmed on this machine). Run `test_ptb_install.m` first, then a short
test run of
each task (`'Windowed', true`, `'TriggerKey', {'space'}`) before a real
session. `run_battery.m` and `ptb_show_staging_screen.m` are newer and in
the same boat -- never executed in MATLAB, checked for structural/syntax
correctness only; the `'Win'` option each task script gained for them
reuses code paths (`ptb_wait_for_trigger`, `ptb_run_block_loop`, etc.) that
were already exercised as described above, so the main untested surface is
`run_battery.m`'s own sequencing/staging-screen loop. Try
`run_battery({{@motor_task, {'TriggerKey', {'space'}}}}, 'Windowed', true)`
(a one-task battery) before trusting a real multi-task session with it.
