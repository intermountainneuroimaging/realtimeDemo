# Real-Time fMRI Task Activation (registration-free)

A generic RT-Cloud project that shows **task activation in real time** for any
block/event fMRI design, with **no anatomical registration**. The brain mask
and ROIs are derived from the functional data itself, and the realtime
activation maps are plotted with **nilearn**. The design is read from a BIDS
`events.tsv`, so it adapts to any task: rest is implicit, the conditions of
interest are set by `glmCondA`/`glmCondB`, and every other `trial_type`
becomes a GLM covariate. The shipped `conf/taskActivation.toml` uses the
ds000244 "HcpMotor" task design (LEFT vs RIGHT hand) as a worked example of
the event timing / GLM contrast a real scanner run needs.

Data comes from a real (or mock) scanner's DICOM stream — see
[tutorial/](tutorial/) for an offline, no-scanner-needed way to validate this
same analysis against real HCP task data (HcpMotor + HcpGambling) before you
ever point it at a scanner, and [stimuli/](stimuli/) (PsychoPy) or
[stimuli_ptb/](stimuli_ptb/) (Psychtoolbox/MATLAB) for simple task-presentation
scripts, so the whole thing can be run end to end with a real task rather than
just a mock/replayed scan. Three tasks are ready to go out of the box — see
[Quick start](#quick-start-direct-testing-no-web-interface) below for
`motor`/`checkerboard`/`gambling`.

**Setup:** see **[INSTALLATION.md](INSTALLATION.md)** for one-time setup
(Docker image, host-side Python deps, prefetching demo data, and installing
`dicom_bridge.py` as a background service).
**Testing:** see **[TESTING.md](TESTING.md)** to verify each component works
in isolation before connecting to a real scanner.
**Before every live session:** see **[PREFLIGHT.md](PREFLIGHT.md)** for the
short pre-flight checklist (share still up, bridge still running, `dicomDir`
clean, config matches this session).

This file focuses on the **main way to run the project — against live
scanner data — and what the outputs actually look like.**

## How it works

The analysis is task-agnostic — it reads the design straight from the events
file and classifies `trial_type`s automatically:

- **Rest** is implicit: any period with no event (or an event whose name
  looks like rest/fixation/baseline/iti/blank…) is the GLM baseline — no rest
  regressor is added. Override detection with `restTypes` in the toml.
- **Conditions of interest** are whatever you put in `glmCondA` / `glmCondB`.
- **Every other `trial_type`** in the events file is added as its own GLM
  covariate regressor, so its variance is modeled out of the contrast.

To point it at a different task, set `taskName` + `eventsFile` and the
conditions — e.g. `task-HcpGambling`, `reward` vs `punishment`, with `neutral`
automatically becoming a covariate (see [tutorial/](tutorial/) for that
example validated offline against real HcpGambling data).

It always streams DICOMs from a real (or mock) scanner via `dicomDir/` — see
below for how to point that at a real scanner, or
[TESTING.md](TESTING.md#4-mock-scanner-dicom-streaming--the-full-pipeline-docker--live-path-no-real-scanner)
to exercise the same path with `mock_scanner.py` instead. TR is always
inferred from the first real DICOM's `RepetitionTime` (waits up to 30s for it
to appear) rather than hand-copied into a config — correct by construction
for whatever protocol is actually running.

## Quick start: direct testing (no web interface)

This mirrors rt-cloud's ["Testing Your Project
Directly"](https://github.com/brainiak/rt-cloud) pattern: it runs
`taskActivation.py` straight inside the container for rapid iteration,
without spinning up the projectInterface/projectServer, certs, or a browser.
See [TESTING.md](TESTING.md) for how to exercise this with `mock_scanner.py`
before pointing it at a real scanner; for a real scanner, see
[Running with live scanner data](#running-with-live-scanner-data) below.

**Fastest path:** `./quickstart.sh` does everything below in one command —
exports these same variables (sensible defaults, or export your own first to
override), runs the container, and opens `outDir/live/viewer.html` in your
browser automatically as soon as it exists. It also has an *optional* section
for `dicom_bridge.py`/its systemd/launchd background service (see
[Running with live scanner data](#running-with-live-scanner-data)) — skipped
by default, since it's only relevant for a real scanner. It also auto-answers
the `continue using localfiles?` prompt below, so the whole thing runs
unattended.

**Three ready-made tasks, one command each:** pass a task name to
`quickstart.sh` (or to `run_task.py` directly — see below) to run that task's
own `conf/*.toml` instead of the default:

```bash
./quickstart.sh motor          # LEFT vs RIGHT finger tapping
./quickstart.sh checkerboard   # flickering checkerboard ON vs OFF
./quickstart.sh gambling       # gambling WIN (reward) vs LOSS (punishment)
```

Add `--run`/`-r <N>` (either before or after the task name, or on its own with
the default config) to override the toml's `runNum` without editing it —
handy for bridging/streaming a different run each session:

```bash
./quickstart.sh motor --run 2  # motor.toml, but run number 2
./quickstart.sh --run 2        # default config, run number 2
```

| Task | `conf/*.toml` | `eventsFile` | `glmCondA` vs `glmCondB` | Present it with |
|---|---|---|---|---|
| Motor | `motor.toml` | `GenericMotorLR_events.tsv` | `left_finger` vs `right_finger` | `stimuli_ptb/motor_task.m` |
| Checkerboard | `checkerboard.toml` | `Checkerboard_events.tsv` | `checkerboard` vs *(empty — beta map, i.e. vs the implicit rest/OFF baseline)* | `stimuli_ptb/checkerboard_task.m` |
| Gambling | `gambling.toml` | `HcpGambling_acq-ap_events.tsv` | `reward` vs `punishment` | `stimuli_ptb/gambling_task.m` |

`run_task.py` is the thing actually doing the selection (`quickstart.sh
<task>` just forwards to it inside the container) — it's a thin wrapper
around `taskActivation.py --config conf/<task>.toml`, so running it directly
(e.g. for the [direct-testing command](#quick-start-direct-testing-no-web-interface)
below, or inside `scripts/run-projectInterface.sh`) works identically:

```bash
python projects/$PROJ_NAME/run_task.py motor          # instead of $PROJ_NAME.py
python projects/$PROJ_NAME/run_task.py motor --run 2   # --run forwards through, same as taskActivation.py's own
```

See [stimuli_ptb/README.md](stimuli_ptb/README.md) (or
[stimuli/README.md](stimuli/README.md) for the PsychoPy equivalents of motor
and gambling) for what each task actually looks like to the subject.

The rest of this section is the same thing spelled out by hand, for anyone
who wants to see or customize each step individually:

```bash
PROJ_NAME=taskActivation
PROJ_DIR=/full/path/to/taskActivation
DICOM_DIR=/full/path/to/dicomDir
OUT_DIR=/full/path/to/outDir          # where current.png / motion.png / the GIF land

docker run -it --rm \
  -v $PROJ_DIR:/rt-cloud/projects/$PROJ_NAME \
  -v $DICOM_DIR:/rt-cloud/projects/$PROJ_NAME/dicomDir \
  -v $OUT_DIR:/rt-cloud/outDir \
  brainiak/rtcloud:latest python projects/$PROJ_NAME/$PROJ_NAME.py
```

`PROJ_DIR` must point at *this* folder (`taskActivation/`, containing
`taskActivation.py`), since `PROJ_NAME` is used both as the mount point and as
the script filename. `DICOM_DIR` needs volumes waiting in it before/while the
run starts — either a real scanner's export folder (via `dicom_bridge.py`,
below) or `mock_scanner.py` (see [TESTING.md](TESTING.md)). Once volumes are
flowing, open `$OUT_DIR/live/viewer.html` in a browser for an auto-refreshing
view of `current.png`/`motion.png` (this is what `quickstart.sh` opens for
you automatically).

Running this way (rather than through rt-cloud's own
`run-projectInterface.sh` / web interface launcher) bypasses whatever sets the
run number there, so pass `--run` to override the toml's `runNum` without
editing it — handy for bridging/streaming a different run each session:

```bash
python projects/$PROJ_NAME/$PROJ_NAME.py --run 2
```

On startup `ClientInterface()` can't reach a project server inside this
single-container run, and will ask:
`Unable to connect to projectServer, continue using localfiles? (y/n):` —
answer **y** (the `-it` flag keeps the container interactive so you can type
it). This runs `webInterface`/`subjInterface`/`dataInterface` locally in the
same process instead of over RPC.

`OUT_DIR` is mounted by default here specifically so you can actually see the
outputs: without it, `outDir/live/current.png`, `motion.png`, the end-of-run
GIF, etc. are written *inside* the `--rm` container and vanish the moment it
exits — you'd never see them on the host at all. With it mounted, they appear
in `$OUT_DIR/live` as the run progresses (see
[Data outputs to expect](#data-outputs-to-expect)).

**Full project interface (browser dashboard):** if you'd rather use rt-cloud's
web UI (login `test`/`test`, a **Data Plots** tab for the live ROI trace), run
`scripts/run-projectInterface.sh` instead — see the
[run-in-docker docs](https://github.com/brainiak/rt-cloud/blob/master/docs/run-in-docker.md).
The brain-image plot still isn't shown in the browser either way; you always
need `realtime_display.py` (below) for that.

## Running with live scanner data

Pointing `dicomDir/` at a **real** scanner's DICOM output (rather than
`mock_scanner.py`) means dealing with two things a mock run doesn't have to:

**1. rt-cloud can't match your scanner's real filenames.** rt-cloud's DICOM
watcher builds one exact, predictable filename per volume with plain
`str.format()` — it has no wildcard/glob support. If your site's real-time
export appends an unpredictable SOPInstanceUID (a common convention, e.g.
`002_000003_000001_1.3.12.2.1107....dcm`), no `dicomNamePattern` can match it.
`dicom_bridge.py` solves this: it watches the real drop folder (`--source`),
reads each file's actual `SeriesNumber`/`InstanceNumber` from its DICOM
header (not its filename — conventions vary by site), and copies it into a
destination folder (`--dest`) renamed to match `dicomNamePattern` exactly. It
only renames — dcm2niix already handles Enhanced multi-frame DICOM natively,
so no pixel data is touched. It also has to patch one metadata field:
rt-cloud's own metadata reader only looks at top-level DICOM tags, so a
nested `RepetitionTime` (where Enhanced multi-frame DICOM stores it) has to
be promoted to the top level, or every volume fails with
`MissingMetadataError`.

It also auto-cleans `--dest`: files older than `--max-age-hours` (default
24) are deleted at startup and every `--clean-interval-hours` while running,
so a long-running background service doesn't quietly accumulate every past
session's DICOMs — and so old leftovers can't mix with a new session's and
crash the run the way described in
[PREFLIGHT.md](PREFLIGHT.md#3-dicomdir-is-empty-or-only-has-files-you-expect).
`--source` (the scanner's own export) is left alone by default — pass
`--source-max-age-hours` to also age those out, but that's opt-in since it
may be the only copy of that data.

**`--source` and `--dest` are two different folders, and both matter:**
`--source` is the real scanner's raw export location (anywhere readable —
often a network share). `--dest` is **the same `$DICOM_DIR` you bind-mounted
into the container** in the [direct-testing command](#quick-start-direct-testing-no-web-interface)
above (`-v $DICOM_DIR:/rt-cloud/projects/taskActivation/dicomDir`) — that's
how the bridged files actually reach the container. `--dest` isn't required
(it falls back to this project's own `dicomDir/` folder on disk if omitted),
but for a real scan you should pass it explicitly so it's unambiguous which
folder is being fed into the container:

`--source` is searched recursively, so it's fine to point it at a parent
directory the scanner organizes into per-session subfolders (e.g.
`<source>/20260812.some_study.some_study/*.dcm`) rather than requiring a
single flat folder — every `.dcm` anywhere underneath is a candidate, and two
sessions reusing the same instance filenames (both starting at `IM001.dcm`)
won't collide, since files are tracked by full path rather than basename.
Auto-cleanup (below) recurses the same way and removes any per-session
subfolder it leaves empty.

By default `RUN` in the output filename is each file's own real
`SeriesNumber` — not a fixed value — so bridging everything in the drop
folder is collision-safe (an SBRef series and a bold series land in
`$DICOM_DIR` under distinct `RUN` labels, never overwriting each other):

```bash
DICOM_DIR=/full/path/to/dicomDir   # same folder as -v $DICOM_DIR:.../dicomDir in the docker command

# bridge every series found, each kept separate by its own SeriesNumber:
python utils/dicom_bridge.py --config conf/taskActivation.toml \
  --source /path/to/real/scanner/drop/folder --dest $DICOM_DIR

# one-shot backfill (bridge what's there now, then exit):
python utils/dicom_bridge.py --config conf/taskActivation.toml \
  --source /path/to/real/scanner/drop/folder --dest $DICOM_DIR --once
```

Pass `--series` to bridge only one run, and/or `--run` to relabel it to a
fixed value instead of using the real `SeriesNumber` (useful when the toml's
`runNum` needs to stay the same across sessions whose real series numbers
change — `--run` requires `--series`, since forcing one `RUN` value while
bridging multiple series would collide):

```bash
# only series 3, relabeled as RUN 1 (matches a toml with runNum = [1]):
python utils/dicom_bridge.py --config conf/taskActivation.toml \
  --source /path/to/real/scanner/drop/folder --dest $DICOM_DIR --series 3 --run 1
```

Run this in a second host terminal (it has no `rtCommon` dependency, so it
doesn't run inside the container) — or install it as a background service so
you don't have to; see [INSTALLATION.md](INSTALLATION.md#4-setting-up-dicom_bridgepy-as-a-background-service-systemd--launchd)
(the systemd unit example there also shows `--source`/`--dest` set explicitly).

> Real scanner files carry real `PatientName`/`PatientID`/etc. until
> rt-cloud's own `anonymize=True` (already set in `taskActivation.py`'s
> `initDicomBidsStream` call) strips them on read — same as a real scanner's
> raw feed always has. `dicom_bridge.py` doesn't change that; it's expected,
> not a new exposure.

**2. Don't let a normal startup gap crash the run.** Each volume fetch waits
up to `dicomTimeout` seconds (default 30) for its DICOM to appear before
raising — rtCommon's own default is only 5s, which is routinely too short
for the real gap before a scan starts (or an occasional slow volume
mid-scan). If nothing arrives within `dicomTimeout`, you get a clear
`RuntimeError` telling you to check that the scanner / `dicom_bridge.py` /
`mock_scanner.py` is actually running and pointed at this `dicomDir` — not a
raw rtCommon traceback. Raise `dicomTimeout` further if your site's startup
delay routinely runs longer.

**Other subjects/runs/tasks:** point `taskName` + `eventsFile` at your own
design (see [How it works](#how-it-works)), and set `dicomNamePattern` +
`runNum` to match what `dicom_bridge.py` / your scanner actually writes.

## Data outputs to expect

The nilearn brain plot is not automatic — nothing renders it for you:

| Output | Where it shows |
|---|---|
| ROI % signal change from baseline (at the ROI's center/peak voxel), one value per volume | rt-cloud web interface **Data Plots** tab (`webInterface.plotDataPoint` — numbers only) |
| nilearn % -change activation plot (ortho cut at the ROI / active peak), stamped with the current frame/volume number | written to `outDir/live/current.png` every volume |
| Full interactive ortho + ROI %-change timecourse | the `realtime_display.py` window, run manually against `outDir/live` |
| Head motion (6 rigid-body params + framewise displacement) | `outDir/live/motion.tsv` / `motion.png` every volume; `motion_display.py` for a live window |
| Browser view of `current.png` + `motion.png`, auto-refreshing every 0.5s | `outDir/live/viewer.html` — open directly in any browser, no Python needed |
| Replay of the whole run's activation maps | `outDir/live/activation_run<N>.gif`, written once at the end of the run |

The **Data Plots** tab can only render numeric line plots, so the brain image
cannot go there. Easiest way to see it live: open `outDir/live/viewer.html`
in any browser (auto-refreshes both images every half second, no setup
needed). For the full interactive interface instead, run `realtime_display.py`
on a machine that can see the `outDir/live/` folder:

```bash
python utils/realtime_display.py /path/to/rt-cloud/outDir/live
```

### The live figure

- **Top row** — the per-frame % difference from baseline as a single-row
  axial mosaic, updated every volume and labeled with the current condition
  (e.g. `left hand`, `REST`, `tongue`), with the frame/volume number stamped
  in the top-left corner. Slice positions: set `zCuts` in the toml to a fixed
  list of z-coordinates in mm, or leave it empty (`[]`) to auto-pick 6 levels.
- **Second row** — a separate axial mosaic of a GLM map. An HRF-convolved
  design matrix (one regressor per effector + polynomial drift + intercept)
  is re-fit by OLS on every volume seen so far as data streams in. `glmCondA`
  / `glmCondB` choose the contrast; leave `glmCondB = ""` to plot the condA
  β-weight alone. `glmZscore` z-scores the map across voxels; `driftOrder`
  sets the drift terms.
- **Bottom rows** — one per condition (condA, condB): at that condition's
  peak-beta voxel, the measured % signal change timecourse plotted against
  the HRF-predicted signal from the fitted GLM, with the condition's stimulus
  blocks shaded. These update live too, starting as soon as the incremental
  GLM has enough volumes to be estimable (not just once at the end) — so
  `current.png` gains these rows partway through the run and keeps refitting
  them every frame after that. Their x-axis is fixed to the run's whole
  expected duration (`nVols` × TR) from the start, so it doesn't grow or
  rescale frame to frame — `motion.png`'s x-axis is fixed the same way.

### Replaying a whole run (`activation_run<N>.gif`)

At the end of the run, every frame that was ever written to `current.png`
(one saved bundle per live update) gets re-rendered and assembled into an
animated GIF at `outDir/live/activation_run<N>.gif` — a single, standalone
file you can reopen and replay anytime afterward, without rerunning the
analysis or needing rt-cloud running at all. Controlled by two toml keys:
`saveGif = true` (set `false` to skip it entirely) and `gifFps` (playback
speed; default 8 frames/sec). Building it takes a little while for a long run
(nilearn re-renders every saved frame), so it happens once, after the last
volume, and won't interfere with the live 'while it's running' outputs above.

### Sample output

`current.png` from a full HcpMotor run (LEFT vs RIGHT hand — LEFT hand drives
the right motor cortex, RIGHT hand the left, the two peak-voxel rows at the
bottom showing that lateralized, HRF-shaped response recovered live volume by
volume) and a full HcpGambling run (reward vs punishment, `neutral` regressed
out as a covariate) are in [tutorial/README.md](tutorial/README.md#sample-output) —
both were produced by replaying real ds000244 data through this same analysis
pipeline, offline.

## Project structure

```
taskActivation/
├── README.md                 # this file — running + outputs
├── INSTALLATION.md           # one-time setup
├── TESTING.md                # verifying each component
├── PREFLIGHT.md              # short checklist to run before every live session
├── quickstart.sh              # one-command direct-testing run (see Quick start below)
│                              # -- quickstart.sh motor/checkerboard/gambling picks a task
├── taskActivation.py         # main RT-Cloud analysis (registration-free, task-agnostic,
│                              # dicom streaming) -- takes any conf/*.toml via --config
├── run_task.py                # quick task selector: run_task.py {motor,checkerboard,gambling}
│                              # -- just picks the matching conf/*.toml and runs taskActivation.py
├── conf/
│   ├── taskActivation.toml   # default/example config: HcpMotor (left_hand vs right_hand)
│   ├── motor.toml            # LEFT vs RIGHT finger tapping (GenericMotorLR_events.tsv)
│   ├── checkerboard.toml     # flickering checkerboard ON vs OFF (Checkerboard_events.tsv)
│   └── gambling.toml         # gambling WIN (reward) vs LOSS (punishment) (HcpGambling_acq-ap_events.tsv)
├── study_design/
│   ├── HcpMotor_acq-ap_events.tsv     # real ds000244 HcpMotor events (drives conf/taskActivation.toml)
│   ├── GenericMotorLR_events.tsv      # this project's own LEFT/RIGHT-finger design (conf/motor.toml)
│   ├── Checkerboard_events.tsv        # this project's own ON/OFF checkerboard design (conf/checkerboard.toml)
│   └── HcpGambling_acq-ap_events.tsv  # real ds000244 HcpGambling events (conf/gambling.toml)
├── templates/                 # anonymized Enhanced multi-frame DICOM header for mock_scanner
├── dicomDir/                  # scanner DICOMs
├── utils/                     # everything taskActivation.py imports or that supports a live deployment
│   ├── rt_analysis.py             # shared helpers: design-from-events, masks, nilearn plots
│   ├── mock_scanner.py            # simulate a scanner: stream Enhanced multi-frame DICOMs to dicomDir/
│   ├── dicom_bridge.py            # bridge a real scanner's raw filenames into rt-cloud's expected pattern
│   ├── com.rtcloud.dicombridge.plist  # macOS launchd template for running dicom_bridge.py persistently
│   ├── realtime_display.py        # standalone nilearn/matplotlib viewer (no PsychoPy); run manually
│   ├── motion_display.py          # standalone head-motion window (also writes motion.png); run manually
│   └── make_design.py             # (optional) write static design files for inspection
├── testing/
│   └── test_mock_scanner.py   # tests the mock DICOM scanner (frame pack/unpack + recovery)
├── stimuli/                   # PsychoPy presentation of the two worked-example tasks
│   ├── README.md                   # install/test PsychoPy, setup, running
│   ├── common.py                    # shared trigger-wait / event-loop / timing-log helpers
│   ├── hcp_motor_task.py            # presents the HcpMotor task (left/right hand, foot, tongue)
│   ├── hcp_gambling_task.py         # presents the HcpGambling task (reward/punishment/neutral)
│   ├── test_psychopy_install.py     # standalone smoke test for the PsychoPy install itself
│   └── logs/                        # per-session timing-accuracy logs (gitignored)
├── stimuli_ptb/                # Psychtoolbox (MATLAB) presentation of all three ready-made tasks
│   ├── README.md                    # install/test Psychtoolbox, setup, running
│   ├── motor_task.m, checkerboard_task.m, gambling_task.m   # the three task scripts
│   ├── ptb_*.m                      # shared helpers (window setup, KbQueue, event-loop, logging)
│   ├── test_ptb_install.m           # standalone smoke test for the Psychtoolbox install itself
│   └── logs/                        # per-session timing-accuracy logs (gitignored)
└── tutorial/                  # offline HCP-data validation of this analysis, no scanner needed
    ├── README.md                        # what it is + sample outputs
    ├── test_pipeline.py                 # offline end-to-end test on the REAL HcpMotor timing
    ├── test_generalize.py               # generalization test on HcpGambling (reward/punishment)
    ├── replay_real_data.py              # runs the real pipeline against an actual downloaded BOLD run
    ├── hcp_replay.py                    # OpenNeuro download + NIfTI replay helpers (tutorial-only)
    ├── download_data.sh                 # prefetch an OpenNeuro demo BOLD run
    ├── conf/taskActivation_gambling.toml  # reference config for the HcpGambling nifti-replay demo
    ├── study_design/HcpGambling_acq-ap_events.tsv
    ├── docs/images/                     # sample current.png outputs
    ├── openneuro_cache/                 # downloaded demo BOLD runs (gitignored)
    └── _real_data_live/                 # replay_real_data.py's output (gitignored)
```

## Per-volume pipeline (registration-free)

1. DICOM → Nifti via the BIDS incremental
2. Motion correction to volume 1 as the functional reference (`mcflirt`) —
   realignment only
3. 5 mm FWHM Gaussian smoothing (`fslmaths`)
4. Brain mask from the **average of the `baselineN` pre-task volumes** (BET
   skull-strip, nilearn EPI mask, or intensity threshold) — no atlas/warp, no
   separate sbref/reference scan needed. Built once `baselineN` volumes have
   arrived; every volume up to that point is buffered and retroactively fed
   into the GLM once the mask exists.
5. Accumulate the volume into the running per-condition averages
6. Update ROI traces, the % signal change map, and the incremental GLM map

## Notes & caveats

- The per-frame activation map is a running % signal change from baseline;
  the GLM map (second row) is a proper incremental OLS fit — not the same
  contrast, by design (the first is fast/transparent for live viewing, the
  second is the statistically real one).
- The functional brain mask degrades gracefully: `bet` → nilearn
  `compute_epi_mask` → intensity threshold. Tune `maskMethod`/`maskFrac`/
  `maskFraction`/`maskPercentile` for your EPI if coverage looks off (printed
  every run, and saved to `outDir/live/brain_mask.nii.gz`).
- The base `brainiak/rtcloud` image has FSL (`mcflirt`/`fslmaths`) and
  numpy/nibabel; `nilearn` installs itself on first run if missing (a
  matplotlib montage is used instead if that install fails).
