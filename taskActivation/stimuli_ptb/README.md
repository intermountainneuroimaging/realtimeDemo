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
| `gambling_task.m` | `../study_design/HcpGambling_acq-ap_events.tsv` | the HCP project's own card-guessing design, unchanged: reward / punishment / neutral |
| `checkerboard_task.m` | `../study_design/Checkerboard_events.tsv` | 20s ON/OFF blocks: flickering full-contrast checkerboard vs fixation (6 reps + trailing rest, 13 blocks / 260s) |

All three events.tsv files live in the top-level `study_design/` (not
`tutorial/study_design/`) — the exact folder `taskActivation.py` itself
reads `eventsFile` from — so what MATLAB presents and what the live
analysis assumes can never point at different copies of the same design.

Each task has its own ready-to-use config — `../conf/motor.toml`,
`../conf/checkerboard.toml`, `../conf/gambling.toml` — with the matching
`eventsFile` and GLM contrast already set:

| Task | `conf/*.toml` | `eventsFile` | `glmCondA` | `glmCondB` |
|---|---|---|---|---|
| Motor | `motor.toml` | `GenericMotorLR_events.tsv` | `left_finger` | `right_finger` |
| Checkerboard | `checkerboard.toml` | `Checkerboard_events.tsv` | `checkerboard` | *(empty — single-condition beta map, i.e. ON vs the implicit rest/OFF baseline)* |
| Gambling | `gambling.toml` | `HcpGambling_acq-ap_events.tsv` | `reward` | `punishment` |

Run any of the three end to end with `../run_task.py` (see
[README.md](../README.md#running-with-live-scanner-data) / `quickstart.sh
<task>` in the main project) — e.g. `python ../run_task.py motor`.

## Responses are recorded via KbQueue, not KbCheck

**Why this matters:** an MRI-compatible response button box typically
presents itself to the OS as a keyboard sending one very brief keydown
pulse per press — not a key held down the way a real keypress usually is.
A plain per-frame `KbCheck` only reports whatever is down at the *exact
instant* you call it, so in a realtime presentation loop (busy drawing and
waiting on `Screen('Flip')`) that pulse can easily land entirely between
two checks and simply never be seen.

`gambling_task.m` starts a `KbQueue` once for the **whole run**
(`ptb_kbqueue_setup.m`), which hands keyboard buffering off to PTB's own
background collection — every press is timestamped and stored the instant
it happens, regardless of what the main loop is doing at that moment.
`ptb_kbqueue_check_any.m` is then polled once per frame and always sees
whatever was buffered since the last check, no matter how the loop's own
timing lined up with the actual press. The **same** per-frame check also
catches Escape (rather than a second, separately-fallible `KbCheck` call),
so an abort can't be missed for the same reason a response can't.

Each trial's response — the key pressed and its reaction time relative to
the guess-phase onset — is written into the timing log's `response_key` /
`response_time_s` columns (`'none'` / `NaN` if the subject didn't respond in
time). As in the real HCP task, the guess doesn't change the outcome; which
outcome appears and when is entirely driven by the events.tsv.

`motor_task.m` and `checkerboard_task.m` don't collect responses at all (pure
block presentation), so they don't use a `KbQueue` — Escape is checked with a
plain `KbCheck` each frame in `ptb_run_block_loop.m`, which is fine for an
experimenter manually aborting (unlike a scanner button pulse, nothing is
lost if a keypress held for a moment is seen a frame later).

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

Every task script wraps its window (and, for `gambling_task.m`, its
`KbQueue`) in MATLAB's `onCleanup`, e.g.:
```matlab
win = ptb_open_window(...);
cleanupWin = onCleanup(@() sca);   % Screen('CloseAll') + ShowCursor + Priority(0)
```
`onCleanup` fires when the function exits **for any reason** — normal
completion, an Escape-triggered abort, or an uncaught error partway through
— so the display and keyboard queue are always released and the subject is
never left staring at a frozen/black screen because of a bug or a MATLAB
error dialog. `gambling_task.m` also always writes its timing log (including
whatever responses were recorded) before returning, even on an Escape abort.

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
(`{'5','5%','t'}` for triggers, `{'1','1!','2','2@','3','3#','4','4$'}` for
gambling responses), but if your site's box reports something else
entirely, run `test_ptb_install`, press the actual trigger or button once,
and pass whatever it prints via `'TriggerKey'` / `'ResponseKeys'`.

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
- **Apple Silicon Macs (M1/M2/M3+):** `PTB-ERROR: SYNCHRONIZATION FAILURE`
  when opening a window is expected, not a sign anything is broken —
  Psychtoolbox's own startup warning says its timing/timestamping
  mechanisms are unreliable on Apple's own GPU and that sync tests should
  be expected to fail. Pass `'SkipSyncTests', true` to every task script to
  get past it for local testing on a machine like this. **This is fine for
  testing the task logic, but PTB's own docs call visual timing on these
  Macs untrustworthy** — don't use an Apple Silicon Mac as the actual
  stimulus computer for a real scanner session; use an Intel Mac, Windows,
  or Linux machine there instead, with `SkipSyncTests` left `false` so real
  timing problems on that machine aren't hidden.
- **macOS:** keypresses not registering almost always means MATLAB needs
  **Accessibility** and/or **Input Monitoring** permission — System
  Settings → Privacy & Security.
- **Linux:** missing GStreamer plugins are the most common install failure;
  the Psychtoolbox installer's own output names the exact package.
- **All platforms:** run `Screen('Preference', 'SkipSyncTests', ...)`
  troubleshooting (PTB prints a detailed report) rather than just leaving
  `SkipSyncTests` on — a real scanner-room display should pass cleanly.

Once that passes, you're ready to run `motor_task.m` / `gambling_task.m` /
`checkerboard_task.m` below.

## Running

```matlab
motor_task
gambling_task
checkerboard_task
```

All three:
- **Wait for a scanner trigger** before starting (`'TriggerKey'`, default
  `{'5','5%','t'}` — wire the scanner's sync pulse to send one of these, or
  pass `'TriggerKey', {'space'}` to press it yourself on the keyboard to
  test without a scanner). Every event is then timed relative to that exact
  trigger moment (`GetSecs()`), matching how the real-time analysis anchors
  its own timing to the first DICOM.
- **Log actual vs expected onset time** per event to
  `stimuli_ptb/logs/<task>_<timestamp>.tsv` (`gambling_task.m`'s log also
  has `response_key` / `response_time_s` columns — see above), so you can
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

## What each task looks like

**`motor_task.m`** — bold green "LEFT FINGER" / "RIGHT FINGER" during the
movement blocks; plain fixation (`+`) during rest. Matches
`taskActivation.py`'s `glmCondA=left_finger` / `glmCondB=right_finger`
contrast when the toml is pointed at `GenericMotorLR_events.tsv`.

**`gambling_task.m`** — each trial briefly shows a face-down card ("Higher
or Lower? press any button"), then reveals the outcome: green `+$1.00`
(reward), red `−$0.50` (punishment), or gray `$0.00` (neutral) — or gray
"No response `$0.00`" if the subject didn't press anything during the guess
phase, regardless of what the trial was scheduled to pay out (an incentive
to actually respond; the events.tsv / GLM design are unaffected). As in the
real HCP task, the guess doesn't actually change which outcome a responded
trial gets. Matches `taskActivation.py`'s `glmCondA=reward` /
`glmCondB=punishment` contrast with `neutral` as a covariate.

**`checkerboard_task.m`** — a full-contrast checkerboard patch reversing
black/white at `'FlickerHz'` (default 8) times per second during ON blocks;
plain fixation during OFF blocks. Matches `taskActivation.py`'s
`glmCondA=checkerboard` beta-weight map (no second condition — set
`glmCondB=""` in the toml) when pointed at `Checkerboard_events.tsv`.

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
- `ptb_run_block_loop.m` — the render loop `motor_task.m` /
  `checkerboard_task.m` share: draws whatever the caller's `stimFor`
  callback returns for the current time, handles rest gaps, writes the
  timing-accuracy log, and checks Escape.
- `ptb_write_event_log.m` — writes a tab-delimited log from a header +
  row cell array.
- `motor_task.m`, `gambling_task.m`, `checkerboard_task.m` — the three task
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
have **not** been run end-to-end in MATLAB. Run `test_ptb_install.m` first,
then a short test run of each task (`'Windowed', true`, `'TriggerKey',
{'space'}`) before a real session.
