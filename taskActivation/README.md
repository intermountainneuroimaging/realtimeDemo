# Real-Time fMRI Task Activation (registration-free)

A generic RT-Cloud project that shows **task activation in real time** for any
block/event fMRI design, with **no anatomical registration**. The brain mask and
ROIs are derived from the functional data itself, and the realtime activation maps
are plotted with **nilearn**. The design is read from a BIDS `events.tsv`, so it
adapts to any task: rest is implicit, the conditions of interest are set by
`glmCondA`/`glmCondB`, and every other trial_type becomes a GLM covariate. The
default config maps the ds000244 "HcpMotor" task (LEFT vs RIGHT hand); a second
config maps "HcpGambling" (reward vs punishment).

It runs three ways, selected by `dataSource` in the toml:

- **`nifti`** *(default for ds000244)* — downloads the one HcpMotor bold from
  OpenNeuro's public S3 mirror (once) and replays its volumes with nibabel.
- **`dicom`** — streams DICOMs from the scanner (`dicomDir/`) for live scanning.
- **`openneuro`** — rt-cloud's `initOpenNeuroStream` (only for datasets that have
  a `run` entity).

> **Why `nifti` and not `openneuro` for this dataset?** rt-cloud's
> `initOpenNeuroStream` raises *"Must specify subject and run number"* — it
> hard-requires a BIDS `run` entity. The HcpMotor task has **no run** (it uses
> `acq-ap`/`acq-pa`), so that API can't address it. The `nifti` source downloads
> the file with the same `aws s3 sync --no-sign-request` rt-cloud uses
> internally, then streams its volumes directly — no run entity needed, and it
> works the same whether the analysis runs on the scanner machine or a server.
> You can also pre-fetch with `./download_data.sh ds000244 01 03 HcpMotor ap`.

## Why ds000244 / HcpMotor

The `HcpMotor` task has clean, easy-to-interpret block timing with explicit
`left_hand` and `right_hand` conditions (plus foot/tongue, which we ignore), a
TR of 2.0 s, and a proper BIDS `events.tsv`. **LEFT hand drives the right motor
cortex; RIGHT hand drives the left motor cortex** — a clean lateralized contrast.

The per-volume design is built **at runtime** from the shipped events file
(`study_design/HcpMotor_acq-ap_events.tsv`) so it always matches the dataset's
real timing and the stream's actual volume count.

## Adapting to other task designs

The analysis is task-agnostic — it reads the design straight from the events file
and classifies trial_types automatically:

- **Rest** is implicit: any period with no event (or an event whose name looks
  like rest/fixation/baseline/iti/blank…) is the GLM baseline — no rest regressor
  is added. Override detection with `restTypes` in the toml.
- **Conditions of interest** are whatever you put in `glmCondA` / `glmCondB`.
- **Every other trial_type** in the events file is added as its **own GLM
  covariate regressor**, so its variance is modeled out of the contrast.

To run a different task, point `taskName` + `eventsFile` at it and set the
conditions. A ready-made example for the gambling task ships as
`conf/taskActivation_gambling.toml` (`task-HcpGambling`, `reward` vs `punishment`,
with `neutral` automatically becoming a covariate). `test_generalize.py` verifies
on HcpGambling that reward/punishment localize and that the `neutral` covariate is
regressed out of the reward−punishment contrast.

## Testing with a mock scanner (`dataSource = "dicom"`)

To exercise the real-time DICOM streaming path without a scanner, `mock_scanner.py`
writes one **Enhanced-multi-frame DICOM per volume** (all slices as separate
frames in one file, matching modern Siemens XA-line reconstructions — not the
older single-frame "mosaic" format) into the watched `dicomDir/` at TR cadence,
matching the project's `dicomNamePattern`. RT-Cloud picks each file up, converts
it with dcm2niix, and feeds it to the analysis exactly as a real scanner would.

Geometry (rows/columns/slice count, pixel spacing) and TR are **read from a
reference DICOM at runtime** (`--reference-dicom`, default
`templates/enhanced_bold_template.dcm` — a fully anonymized real 88×88×56,
TR=1000ms acquisition), not hardcoded, so the synthetic data matches whatever
scanner/protocol produced the reference. Point `--reference-dicom` at a
different real (or anonymized) DICOM to match a different site/protocol.

Set `dataSource = "dicom"` in the toml, start the analysis, then in a **second
terminal on the host** (not inside the container) run the mock scanner pointed
at the same `dicomDir` the container has mounted:

```bash
# synthetic run built from the events file (condA/condB regions activate):
python mock_scanner.py --config conf/taskActivation.toml --out $DICOM_DIR

# or replay a real 4D NIfTI (each volume resampled to the reference's grid):
python mock_scanner.py --config conf/taskActivation.toml --out $DICOM_DIR --source bold.nii.gz

# fast, no-scanner-cadence write (for offline checks):
python mock_scanner.py --config conf/taskActivation.toml --out $DICOM_DIR --no-delay --clean

# match a different scanner/protocol's geometry+TR instead of the bundled template:
python mock_scanner.py --config conf/taskActivation.toml --out $DICOM_DIR \
  --reference-dicom /path/to/an/anonymized/real.dcm
```

TR precedence: `--tr` (explicit override) > numeric `demoStep` in the toml >
the reference DICOM's own `RepetitionTime` > a `2.0`s last-resort fallback.
Set `demoStep = "auto"` in the toml to skip straight to the reference DICOM's
TR (see [Live scanning](#live-scanning) below — the same `"auto"` value also
works for the live analysis itself).

`mock_scanner.py` only needs `numpy`, `nibabel`, and `pydicom` (`pip install
pydicom`) — it has no rtCommon dependency, so it runs directly on the host, not
in the rtcloud Docker image. If you're using the [direct-testing docker
command](#quick-start-direct-testing-no-web-interface) below, `$DICOM_DIR` is
the same host folder you bind-mounted to the container's `dicomDir/`, so files
written there appear to the container immediately. Files are written atomically
(`.part` then rename) so the watcher only sees complete volumes.
`test_mock_scanner.py` verifies (no dcm2niix/scanner needed) that the DICOMs
are named correctly, exceed `minExpectedDicomSize`, parse to the reference
DICOM's exact shape, frame-pack/unpack round-trips exactly, and the series
carries recoverable condA/condB activation.

## Live scanning

Point `dataSource = "dicom"` at a **real** scanner's DICOM output and this
project needs two things a mock/synthetic run doesn't have to deal with:

**1. rt-cloud can't match your scanner's real filenames.** rt-cloud's DICOM
watcher builds one exact, predictable filename per volume with plain
`str.format()` — it has no wildcard/glob support. If your site's real-time
export appends an unpredictable SOPInstanceUID (a common convention, e.g.
`002_000003_000001_1.3.12.2.1107....dcm`), no `dicomNamePattern` can match it.
`dicom_bridge.py` solves this: it watches the real drop folder, reads each
file's actual `SeriesNumber`/`InstanceNumber` from its DICOM header (not its
filename — conventions vary by site), and copies it into `dicomDir/` renamed
to match `dicomNamePattern` exactly. It only renames — dcm2niix already
handles Enhanced multi-frame DICOM natively, so no pixel data is touched.

```bash
# bridge whatever's already in the drop folder, then keep watching for more:
python dicom_bridge.py --config conf/taskActivation.toml \
  --source /path/to/real/scanner/drop/folder --series 3

# one-shot backfill (bridge what's there now, then exit):
python dicom_bridge.py --config conf/taskActivation.toml \
  --source /path/to/real/scanner/drop/folder --series 3 --once
```

`--series` is the DICOM `SeriesNumber` of the run you want (read the header of
one file to find it — e.g. with `pydicom`), **not** the toml's `runNum`/`RUN`
token, which is just the output filename's run label. Run this alongside the
analysis the same way you'd run `mock_scanner.py`, in a second host terminal,
pointed at the same `dicomDir` the container has mounted.

> Real scanner files carry real `PatientName`/`PatientID`/etc. until rt-cloud's
> own `anonymize=True` (already set in `taskActivation.py`'s
> `initDicomBidsStream` call) strips them on read — same as a real scanner's
> raw feed always has. `dicom_bridge.py` doesn't change that; it's expected,
> not a new exposure.

**2. Don't hand-copy the protocol's TR into the toml.** Set `demoStep = "auto"`
(instead of a number) and, in `dicom` mode, `taskActivation.py` will wait for
the first real DICOM to appear in `dicomDir/` and read its actual
`RepetitionTime` before building the GLM design — rather than requiring you to
find and hardcode it. It waits up to `demoStepAutoTimeout` seconds (default 30;
set that key in the toml to change it) and raises a clear error if nothing
arrives in time, so start the scanner / `dicom_bridge.py` / `mock_scanner.py`
first. A numeric `demoStep` always overrides auto-inference and behaves exactly
as before.



The HcpMotor run contains several effectors in one run (left/right hand, left/right
foot, tongue). Rather than contrasting conditions, the pipeline uses a simple,
effector-agnostic localizer:

1. **Brain mask** — by default the **sbref** image next to the bold
   (`..._sbref.nii.gz`) is skull-stripped with **FSL BET** (present in the rtcloud
   image), which removes skull/neck/eyes that intensity thresholds keep. It
   degrades gracefully: `bet` → nilearn `compute_epi_mask` → intensity threshold.
   Knobs: `maskSource = "sbref" | "func"`, `maskMethod = "bet" | "epi" | "threshold"`,
   and `maskFrac` (BET fractional-intensity threshold; lower = larger brain). The
   mask is saved to `outDir/live/brain_mask.nii.gz` and its source + coverage are
   printed — **inspect that file** if it looks wrong. The displayed background is
   brain-extracted so you can see the mask is applied.
2. **Baseline image** — always the **average signal at the start of the run,
   before the first event** (cue or condition). `baselineFrames = -1` auto-detects
   how many initial frames that is; set a number ≥ 0 to override.
3. **% signal change** — every volume is expressed as `100 × (signal − baseline)
   / baseline`, per voxel.
4. **ROI** — the **voxel with the highest % change during the first event block**
   (a small sphere of `roiRadius` voxels around it) becomes the region whose mean
   % signal change is plotted on the **Data Plots** tab.

### The live figure

- **Top row** — the **per-frame % difference from baseline** as a single-row
  **axial mosaic**, updated every volume and **labeled with the current condition**
  (e.g. `left hand`, `REST`, `tongue`). Slice positions: set `zCuts` in the toml
  to a fixed list of z-coordinates in mm (e.g. `[-20, -5, 10, 25, 40, 55]`), or
  leave it empty (`[]`) to auto-pick `nSlices` levels (default 6).
- **Second row** — a separate axial mosaic of a **GLM map**. An HRF-convolved
  design matrix (one regressor per effector + polynomial drift + intercept) is
  **re-fit by OLS on every volume seen so far** as data streams in. Configure the
  map in the toml: `glmCondA` / `glmCondB` choose the contrast (`condA − condB`);
  leave `glmCondB = ""` to plot the **condA β-weight** alone. `glmZscore` z-scores
  the map across voxels (threshold `contrastThresh` in z); set it false for %
  signal change. `driftOrder` sets the drift terms.

### Head-motion window

mcflirt is run with `-plots`, and the 6 motion parameters per volume are logged to
`outDir/live/motion.tsv` (with a `time_s` column), and a rendered
`outDir/live/motion.png` is written on each live update (always available, even
with no interactive window). A separate live window
(`motion_display.py`) plots all six rigid-body parameters on one axes —
**x = time (s), y = head motion (mm)**, one line each for tx, ty, tz, rx, ry, rz
(rotations converted to mm-equivalent at a 50 mm head radius). Run it yourself,
pointed at the live folder:

```bash
python projects/taskActivation/motion_display.py /rt-cloud/outDir/live
```

### End-of-run peak-voxel HRF fits

When the run finishes, two more rows are appended to `current.png`: for the
condA and condB peak voxels (the voxels with the largest GLM beta for each
condition), the **measured** % signal change timecourse is plotted against the
**HRF-predicted** signal from the fitted GLM, with the condition's stimulus blocks
shaded. This shows, voxel-by-voxel, how well the predicted hemodynamic response
matches the data.

## Where each output appears

The nilearn brain plot is not automatic — nothing renders it for you:

| Output | Where it shows |
|---|---|
| ROI mean % signal change from baseline, one value per volume | rt-cloud web interface **Data Plots** tab (`webInterface.plotDataPoint` — numbers only) |
| nilearn % -change activation plot (ortho cut at the ROI / active peak) | written to `outDir/live/current.png` every volume |
| Full interactive ortho + ROI %-change timecourse | the `realtime_display.py` window, run manually against `outDir/live` |

The **Data Plots** tab can only render numeric line plots, so the brain image
cannot go there. To see the brain plot, run `realtime_display.py` (or open
`current.png` in any image viewer) on a machine that can see the `outDir/live/`
folder — the same machine the analysis runs on, or another one synced to it:

```bash
python projects/taskActivation/realtime_display.py /rt-cloud/outDir/live
```

## The realtime display (no PsychoPy)

`realtime_display.py` is a standalone **nilearn + matplotlib** viewer (no
PsychoPy). It watches the analysis `live/` folder and continuously redraws the
nilearn ortho activation map at the current peak, with the two ROI timecourses
below (LEFT/RIGHT blocks shaded). It loads the reference once and each per-volume
z-map after, communicating purely through files so it can run on another machine.

```bash
python realtime_display.py /path/to/rt-cloud/outDir/live
```

## Project structure

```
taskActivation/
├── README.md
├── taskActivation.py          # main RT-Cloud analysis (registration-free, task-agnostic)
├── rt_analysis.py               # shared helpers: design-from-events, masks, nilearn plots
├── realtime_display.py       # standalone nilearn/matplotlib viewer (no PsychoPy); run manually
├── motion_display.py         # standalone head-motion window (also writes motion.png); run manually
├── mock_scanner.py           # simulate a scanner: stream Enhanced multi-frame DICOMs to dicomDir/
├── dicom_bridge.py           # bridge a real scanner's raw filenames into rt-cloud's expected pattern
├── templates/                # anonymized Enhanced multi-frame DICOM header for mock_scanner
├── test_pipeline.py          # offline end-to-end test on the REAL HcpMotor timing
├── test_generalize.py        # generalization test on HcpGambling (reward/punishment)
├── test_mock_scanner.py      # tests the mock DICOM scanner (frame pack/unpack + recovery)
├── make_design.py            # (optional) write static design files for inspection
├── conf/
│   └── taskActivation.toml     # data source, conditions, timing, display settings
├── study_design/
│   ├── HcpMotor_acq-ap_events.tsv   # real ds000244 events (drives the design)
│   └── HcpGambling_acq-ap_events.tsv # another task (reward vs punishment)
└── dicomDir/                  # scanner DICOMs (live mode only)
```

## Per-volume pipeline (registration-free)

1. DICOM → Nifti via the BIDS incremental
2. Motion correction to the functional reference (`mcflirt`) — realignment only
3. 5 mm FWHM Gaussian smoothing (`fslmaths`)
4. Brain mask from the functional reference (intensity threshold) — no atlas/warp
5. Accumulate the volume into the running REST / LEFT / RIGHT averages
6. Update ROI traces, the lateralization plot, and the nilearn live activation map

## How to run

There are two ways to run this project: a **direct** single-container run for
local testing/iteration (no browser, no certs, no project server), or the
**full project interface** with the rt-cloud browser dashboard. Both use the
same `taskActivation.py` entry point and `conf/taskActivation.toml`.

### Quick start: direct testing (no web interface)

This mirrors rt-cloud's ["Testing Your Project
Directly"](https://github.com/brainiak/rt-cloud) pattern: it runs
`taskActivation.py` straight inside the container for rapid iteration, without
spinning up the projectInterface/projectServer, certs, or a browser.

```bash
PROJ_NAME=taskActivation
PROJ_DIR=/full/path/to/taskActivation
DICOM_DIR=/full/path/to/dicomDir      # only needed for dataSource = "dicom"

docker run -it --rm \
  -v $PROJ_DIR:/rt-cloud/projects/$PROJ_NAME \
  -v $DICOM_DIR:/rt-cloud/projects/$PROJ_NAME/dicomDir \
  brainiak/rtcloud:latest python projects/$PROJ_NAME/$PROJ_NAME.py
```

`PROJ_DIR` must point at *this* folder (`taskActivation/`, containing
`taskActivation.py`), since `PROJ_NAME` is used both as the mount point and as
the script filename. With the default `dataSource = "nifti"` config you don't
need `DICOM_DIR` at all — drop that `-v` line and the `nVols` bold is fetched
from OpenNeuro on first run instead.

On startup `ClientInterface()` can't reach a project server inside this
single-container run, and will ask:
`Unable to connect to projectServer, continue using localfiles? (y/n):` —
answer **y** (the `-it` flag keeps the container interactive so you can type
it). This runs `webInterface`/`subjInterface`/`dataInterface` locally in the
same process instead of over RPC.

Outputs (`outDir/live/current.png`, `motion.tsv`, `motion.png`, etc.) are
written inside the container at `/rt-cloud/outDir/live`. To inspect them from
the host (e.g. with `realtime_display.py`), add `-v $OUT_DIR:/rt-cloud/outDir`
to the command above and point the viewer at `$OUT_DIR/live`.

To test the **live DICOM streaming path** without a real scanner, see
[Testing with a mock scanner](#testing-with-a-mock-scanner-datasource--dicom)
above — set `dataSource = "dicom"` in the toml, start this container, then run
`mock_scanner.py` on the host against the same `$DICOM_DIR`.

### Full project interface (browser dashboard)

Copy this folder into `rt-cloud/projects/`, then start the project interface
(Docker example; mirrors the
[run-in-docker docs](https://github.com/brainiak/rt-cloud/blob/master/docs/run-in-docker.md)):

```bash
IP=`curl https://ifconfig.co/`
PROJ_DIR=/full/path/to/taskActivation
docker run -it --rm \
  -v certs:/rt-cloud/certs \
  -v $PROJ_DIR:/rt-cloud/projects/taskActivation \
  -p 8888:8888 brainiak/rtcloud:latest \
  scripts/run-projectInterface.sh \
  -p taskActivation -c projects/taskActivation/conf/taskActivation.toml -ip $IP
```

1. Open `https://localhost:8888` (login `test`/`test`); confirm components connected.
2. Click **Run**. Activation streams to `outDir/live/current.png`; the
   head-motion plot and end-of-run peak-voxel HRF fits land there too, and the
   ROI trace appears live on the **Data Plots** tab.
3. Run `python realtime_display.py <outDir>/live` (on a machine that can see
   that folder) to watch the brain activation map live — it isn't shown in the
   browser automatically.

**Other subjects/runs:** ds000244 events differ per subject. To use a different
`subjectName`/`acquisition`, copy that run's `*_events.tsv` into `study_design/`
and point `eventsFile` at it. (`nilearn` is required for the plots:
`pip install nilearn`.)

**Live scanning:** set `dataSource = 'dicom'` and supply your own design (events
file / `glmCondA`/`glmCondB`) — see [Live scanning](#live-scanning) above for
getting a real scanner's filenames and TR into this pipeline correctly.

**Run-based OpenNeuro datasets:** set `dataSource = 'openneuro'` and `runEntity`
to the run number; this uses rt-cloud's `initOpenNeuroStream` directly.

## Testing it on the real dataset

`test_pipeline.py` validates the whole pipeline against the **real HcpMotor event
timing** without needing the (large) BOLD download: it synthesizes a 4D series
with the dataset's actual event onsets and a realistic geometry/affine, injects
HRF-convolved activation into simulated left/right M1, and runs the exact analysis
(mapping → block task) used live.

```bash
python test_pipeline.py
```

It checks that the mask is sane, that each hand localizes to the correct
contralateral hemisphere/cluster, that the ROI timecourses lateralize (LEFT-ROI
up in LEFT blocks, RIGHT-ROI up in RIGHT blocks), and that the nilearn realtime
plot and live bundles are produced — currently **all pass**. The only thing it
can't exercise locally is the S3 BOLD download, which rt-cloud performs at runtime
via `initOpenNeuroStream` on your machine.

## Notes & caveats

- The activation maps use a fast running **mean-difference / z** contrast for
  transparency and speed (great for live viewing), not a full incremental GLM.
- The functional brain mask is a simple intensity threshold; tune `maskFraction`
  / `maskPercentile` for your EPI.
- The base `brainiak/rtcloud` image has FSL (`mcflirt`/`fslmaths`) and
  numpy/nibabel; install `nilearn` for the activation plots (a matplotlib montage
  is used automatically if nilearn is missing).
