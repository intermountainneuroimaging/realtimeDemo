"""-----------------------------------------------------------------------------
--- REAL-TIME fMRI TASK ACTIVATION (registration-free) ---
A generic real-time task-activation demo for RT-Cloud. Streams DICOMs from a
real (or mock) scanner via dicomDir/, and for every volume shows task activation
WITHOUT anatomical registration: the brain mask and ROIs come from the functional
data itself (rt_analysis.py), and activation is plotted with nilearn.

The design is read at runtime from study_design/<events_tsv> so it always matches
the dataset's real timing and the stream's actual volume count. It is task-agnostic:
  * REST is implicit (any gap / rest-like event) -> the GLM baseline,
  * the conditions of interest are whatever you set in glmCondA / glmCondB,
  * every other trial_type becomes its own GLM covariate regressor.

Each volume writes outDir/live/current.png with:
  * an axial mosaic of the per-frame % signal change from baseline,
  * an axial mosaic of the incremental GLM condA-vs-condB (or condA beta) map,
and at the END of the run two more rows are added: the measured vs HRF-predicted
timecourse at the peak voxel for condA and condB. A live head-motion plot
(motion.png + motion_display.py) and a web Data Plots ROI trace are also produced.

Defaults to the ds000244 (Individual Brain Charting) "HcpMotor" task design
(LEFT/RIGHT hand blocks, TR = 2.0 s) as the event timing template; see
tutorial/ for an offline, no-scanner-needed demonstration of this same
analysis validated against real HCP task data.
-----------------------------------------------------------------------------"""
import os
import sys
import warnings
import argparse
from subprocess import call
import tempfile
from pathlib import Path
import numpy as np
import nibabel as nib
import pdb
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=UserWarning)

tmpPath = tempfile.gettempdir()
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
dicomPath = currPath + '/dicomDir'
outPath = rootPath + '/outDir'
os.makedirs(outPath, exist_ok=True)
sys.path.append(rootPath)
sys.path.append(os.path.join(currPath, 'utils'))

import rt_analysis as mrt
mrt.ensure_nilearn()   # install nilearn on first run if the container lacks it
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface
from rtCommon.imageHandling import readRetryDicomFromDataInterface, convertDicomImgToNifti, saveAsNiftiImage
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsRun import BidsRun

# ---- config ----
defaultConfig = os.path.join(currPath, f'conf/{Path(__file__).stem}.toml')
ap = argparse.ArgumentParser()
ap.add_argument('--config', '-c', default=defaultConfig, type=str)
ap.add_argument('--run', '-r', default=None, type=int,
                help="run number to use (overrides the toml's runNum). Only needed when "
                     "running taskActivation.py directly (e.g. the 'Quick start: direct "
                     "testing' docker command) rather than through rt-cloud's own "
                     "run-projectInterface.sh / web interface launcher.")
args = ap.parse_args(None)
cfg = loadConfigFile(args.config)


def _cfg_opt(key, default, cast=str):
    """Like getattr(cfg, key, default), but also falls back to `default` when
    the attribute exists but is None. rt-cloud's own config object can
    pre-populate some field names it recognizes as standard across projects
    (e.g. demoStep) as None rather than leaving them absent -- a plain
    getattr default only kicks in when the attribute is missing entirely, so
    it doesn't catch that case and cast(None) blows up downstream."""
    val = getattr(cfg, key, None)
    return cast(val) if val is not None else default


taskName = str(getattr(cfg, 'taskName', None) or getattr(cfg, 'title', None) or 'task')
curRun = args.run if args.run is not None else (
    int(cfg.runNum[0]) if isinstance(cfg.runNum, (list, tuple)) else int(cfg.runNum))
if args.run is not None:
    print(f"[run] using run number {curRun} from --run (overrides toml runNum={cfg.runNum})")

# ---- constants (not deployment-specific -- no need to expose these in the toml) ----
AUTO_TR_TIMEOUT = 30.0     # seconds to wait for the first real DICOM to infer TR from
HRF_DELAY_SECONDS = 4.0    # canonical hemodynamic peak lag; hrf_delay (in volumes) = this / TR
NVOLS_FALLBACK_PADDING = 10  # extra volumes of headroom if nVols has to be estimated from events
SUBJECT_NUM = 1            # BIDS 'subject' entity tag for the stream/archive (bookkeeping only)
DEFAULT_N_SLICES = 6       # axial mosaic slice count when zCuts is empty

# TR is always inferred from the first real DICOM's RepetitionTime (rather than
# hand-copying it into a config) -- correct by construction for whatever
# scanner/protocol is actually running, no per-site TR to keep in sync.
_peekPattern = stringPartialFormat(cfg.dicomNamePattern, 'RUN', curRun)
print(f"[auto-TR] waiting up to {AUTO_TR_TIMEOUT:g}s for the first DICOM in {dicomPath} "
      "to infer TR (start mock_scanner.py / dicom_bridge.py / the scanner now if it "
      "isn't running yet)...")
_firstDicom = mrt.wait_for_first_dicom(dicomPath, _peekPattern, curRun, timeout=AUTO_TR_TIMEOUT)
if _firstDicom is None:
    raise RuntimeError(
        f"No DICOM matching {_peekPattern!r} appeared in {dicomPath} within "
        f"{AUTO_TR_TIMEOUT:g}s. Start the DICOM source (scanner / dicom_bridge.py / "
        "mock_scanner.py) first.")
_info = mrt.dicom_header_info(_firstDicom)
if 'TR' not in _info:
    raise RuntimeError(f"{_firstDicom} has no RepetitionTime tag; TR cannot be inferred.")
TR = _info['TR']
print(f"[auto-TR] inferred TR={TR:g}s from {os.path.basename(_firstDicom)}")
hrf_delay = max(1, round(HRF_DELAY_SECONDS / TR))
fwhm = float(cfg.fwhm)
mapThreshPct = _cfg_opt('mapThreshPct', 0.5, float)    # % signal change overlay threshold
contrastThresh = _cfg_opt('contrastThresh', 2.0, float)  # GLM map threshold (z if zscored)
driftOrder = _cfg_opt('driftOrder', 1, int)             # polynomial drift terms in the GLM
glmCondA = _cfg_opt('glmCondA', 'left_hand', str)       # GLM contrast: condA [- condB]
glmCondB = _cfg_opt('glmCondB', 'right_hand', str)      # empty -> plot condA beta weight only
glmZscore = _cfg_opt('glmZscore', True, bool)           # z-score the GLM map across voxels
_rt = _cfg_opt('restTypes', [], list) or []             # explicit rest trial_types; [] = auto-detect
restTypes = _rt if _rt else None
nSlices = DEFAULT_N_SLICES
zCuts = mrt.parse_float_list(getattr(cfg, 'zCuts', None))  # fixed axial levels in mm; [] = auto
baselineFramesCfg = _cfg_opt('baselineFrames', -1, int)  # -1 = auto (frames before 1st event)
saveGif = _cfg_opt('saveGif', True, bool)               # replay-able activation GIF at end of run
gifFps = _cfg_opt('gifFps', 8, int)                     # GIF playback speed (frames/sec)
dicomTimeout = _cfg_opt('dicomTimeout', 30.0, float)    # seconds to wait per volume before raising
                                                         # -- rtCommon's own default is only 5s, too
                                                         # short for real scanner gaps
demoStep = _cfg_opt('demoStep', 0.0, float)  # TESTING ONLY: artificial delay (s) rtCommon inserts
                                              # per volume in getIncremental, e.g. to pace replay of
                                              # a dicomDir that's already fully written (mock_scanner.py
                                              # --no-delay). 0 (default) = no artificial delay, deliver
                                              # as soon as the DICOM is there. Does NOT affect TR -- TR
                                              # always comes from the DICOM header and is never used
                                              # for plot step size/timing.
maskFraction = float(cfg.maskFraction)
maskPercentile = float(cfg.maskPercentile)
liveEveryTR = int(cfg.liveEveryTR)
condAName = glmCondA                       # display label = the condition itself
condBName = glmCondB
liveDir = os.path.join(outPath, str(cfg.liveDirName))
os.makedirs(liveDir, exist_ok=True)
viewerPath = mrt.write_live_viewer_html(liveDir)
print(f"Live viewer: open {viewerPath} in a browser for an auto-refreshing "
      f"view of current.png + motion.png (updates every 0.5s).")
eventsPath = os.path.join(currPath, 'study_design', str(cfg.eventsFile))

print(f"\n----{cfg.title}  [task={taskName}]  A={condAName} B={condBName}  run={curRun}----\n")
events_rows = mrt.read_events_tsv(eventsPath)

# ---- client interfaces ----
clientInterfaces = ClientInterface()
dataInterface = clientInterfaces.dataInterface
subjInterface = clientInterfaces.subjInterface
webInterface = clientInterfaces.webInterface
bidsInterface = clientInterfaces.bidsInterface
archive = BidsArchive(tmpPath + '/bidsDataset')
try:
    webInterface.clearAllPlots()
except Exception:
    pass

# ---- start the DICOM stream ----
maskMethod = _cfg_opt('maskMethod', 'bet', str)   # 'bet' (skull-strip) | 'epi' | 'threshold'
maskFrac = _cfg_opt('maskFrac', 0.35, float)      # BET fractional-intensity threshold

dicomScanNamePattern = stringPartialFormat(cfg.dicomNamePattern, 'RUN', curRun)
streamId = bidsInterface.initDicomBidsStream(dicomPath, dicomScanNamePattern,
                                             cfg.minExpectedDicomSize, anonymize=True,
                                             **{'subject': SUBJECT_NUM, 'run': curRun,
                                                'task': cfg.taskName})
try:
    nVols = int(bidsInterface.getNumVolumes(streamId))
except Exception:
    # the stream couldn't report its own length -- estimate from the events
    # file itself (whatever task/design is actually loaded) plus headroom
    lastEventEnd = max(o + d for o, d, _ in events_rows)
    nVols = int(np.ceil(lastEventEnd / TR)) + NVOLS_FALLBACK_PADDING
    print(f"[warn] stream did not report its volume count; estimated nVols={nVols} "
          f"from the events file (last event ends {lastEventEnd:.1f}s) + "
          f"{NVOLS_FALLBACK_PADDING} volumes headroom.")

print(f"Data source: dicom | volumes: {nVols}")
# fixed (0, expected-run-duration) x-axis for the trace/motion plots, so they
# don't grow/rescale frame to frame -- based on nVols, the expected number of
# TRs, not however much data has arrived so far.
fullXlim = (0.0, max((nVols - 1) * TR, TR))
# label for the GLM mosaic row, from the configured contrast
_zsfx = ' (z)' if glmZscore else ' (%)'
if glmCondB:
    glmLabel = f"{glmCondA} vs {glmCondB} GLM contrast{_zsfx}: red {glmCondA}>{glmCondB} / blue {glmCondB}>{glmCondA}"
else:
    glmLabel = f"{glmCondA} GLM \u03b2-weight{_zsfx}: red positive / blue negative"
design = mrt.build_design_from_events(
    events_rows, nVols, TR, hrf_delay,
    condA_types=[glmCondA], condB_types=([glmCondB] if glmCondB else []),
    rest_types=restTypes)

# ---- generalized design: rest = implicit baseline; condA/condB = interest;
#      every other trial_type becomes its own GLM covariate regressor ----
cls = mrt.classify_conditions(events_rows, condA=glmCondA, condB=(glmCondB or None),
                              rest_types=restTypes)
print(f"Conditions -> interest: {cls['interest']} | covariates: {cls['covariates']} | "
      f"rest(implicit): {cls['rest'] or 'gaps only'}")
Xglm, glm_names = mrt.make_glm_design(events_rows, nVols, TR, drift_order=driftOrder,
                                      rest_types=restTypes)
print(f"GLM regressors: {glm_names}")
conds = [glmCondA] + ([glmCondB] if glmCondB else [])   # for the peak-voxel HRF-fit rows

# ---- baseline + first-condition-of-interest block ----
interest_set = set(cls['interest']) or None
fe = mrt.first_event_window(events_rows, include_types=interest_set, rest_types=restTypes)
if fe is None:
    raise RuntimeError("No conditions of interest found to define the first block.")
firstOnset, firstOffset, firstLabel = fe
# Baseline = average signal at the start of the run, before the FIRST non-rest event.
rest_set = set(restTypes) if restTypes is not None else set(cls['rest'])
non_rest_onsets = [o for o, _, tt in events_rows if tt not in rest_set and not mrt.is_rest_type(tt)]
first_any_onset = min(non_rest_onsets) if non_rest_onsets else min(o for o, _, _ in events_rows)
baselineN = baselineFramesCfg if baselineFramesCfg >= 0 else max(1, int(first_any_onset // TR))
# 1-based volume indices whose (hrf-shifted) signal reflects the first event block
firstBlockVols = set(
    v for v in range(1, nVols + 1)
    if firstOnset <= ((v - 1) - hrf_delay) * TR < firstOffset)
lastFirstBlockVol = max(firstBlockVols) if firstBlockVols else baselineN + 6
print(f"Baseline = first {baselineN} volumes (before first event at {firstOnset:.1f}s).")
print(f"First event block: '{firstLabel}' {firstOnset:.1f}-{firstOffset:.1f}s "
      f"-> analysis volumes {sorted(firstBlockVols)}")


def fetch_volume(vol):
    """Return a 3D nibabel image for 1-based volume index `vol`, and append it
    to the BIDS run.

    Delivery is driven by DICOM arrival, not by TR: `demoStep` (config,
    default 0) is passed straight through to rtCommon purely as a TESTING
    knob -- it tells rtCommon to insert that many seconds of artificial
    per-volume pacing (meant for replaying a dataset that's already fully on
    disk at a simulated real-time cadence; irrelevant for a real scanner,
    where initDicomBidsStream is already waiting on the file to actually
    appear). It never touches TR or anything derived from it -- TR always
    comes from the DICOM header, and is used only for the event-timing math
    (GLM design, HRF convolution, hrf_delay), never for plot step size/timing.
    With demoStep=0 (default), a volume is fetched, analyzed, and plotted the
    moment its DICOM shows up, whatever the real inter-arrival gap is.

    rtCommon's own getIncremental()/getImageData() already poll quietly for
    the file to appear -- but only for 5s by default, which is too short for
    a real scanner (there's often a real gap before the first volume, or an
    occasional slow one mid-scan). `dicomTimeout` (config, default 30s)
    extends that wait so a normal startup delay doesn't crash the run; it
    only raises once nothing has arrived for that long."""
    try:
        inc = bidsInterface.getIncremental(streamId, volIdx=vol, demoStep=demoStep, timeout=dicomTimeout)
    except Exception as e:
        raise RuntimeError(
            f"No DICOM for volume {vol} arrived within dicomTimeout={dicomTimeout:g}s. "
            "Is the scanner / dicom_bridge.py / mock_scanner.py actually running and "
            "pointed at this dicomDir? Raise dicomTimeout in the toml if the scanner "
            "just starts slowly.") from e
    try:
        currentBidsRun.appendIncremental(inc)
    except Exception as e:
        # almost always means dicomDir mixes DICOMs from two different
        # acquisitions (different slice count/geometry) matching the same
        # dicomNamePattern/runNum -- typically leftover files from an earlier
        # test run (a different --reference-dicom, or mock_scanner.py run
        # without --clean) that never got cleared before this run started.
        raise RuntimeError(
            f"Volume {vol}'s DICOM has different geometry than earlier volumes in this "
            f"run ({e}). dicomDir is likely mixing files from two different acquisitions "
            "-- check for leftovers from an earlier test (a different mock_scanner.py "
            "--reference-dicom, or a real scan with a different protocol) matching the "
            "same dicomNamePattern/runNum, and clear dicomDir (or use mock_scanner.py "
            "--clean) before starting a fresh run.") from e
    return inc.image

currentBidsRun = BidsRun()

# ---- running state ----
brain_mask_flat = None
vol_shape = None
ref3d = None
affine = None
pre_baseline_imgs = []       # raw (unmasked) smoothed volumes, buffered until the
                              # brain mask can be built from their average
baseline_mean = None         # frozen per-voxel baseline
fb_sum = None                # accumulates % change over the first event block
fb_n = 0
Yglm = None                  # (nVols x nVoxMasked) signal buffer for the incremental GLM
mask_idx = None              # flat indices of brain voxels
motion_rows = []             # accumulated mcflirt motion parameters
roi_peak = None               # ROI = peak %change voxel from the first event block
roi_trace, glob_trace, cond_trace = [], [], []
last_center = None
center = None                # set once a live update has run; guards the final HRF-fit plot
contrast3d = None
condLabel = ''
point_idx = -1
firstRefVol = 1



for vol in range(1, nVols + 1):
    cond = int(design[(vol - 1) - hrf_delay]) if (vol - 1 - hrf_delay) >= 0 else mrt.IGNORE
    print(f'--- {taskName} | vol {vol}/{nVols} | cond {cond} ---')

    niftiObject = fetch_volume(vol)

    if vol == firstRefVol:
        nib.save(niftiObject, tmpPath + "/funcRef.nii")
        ref_img = nib.load(tmpPath + "/funcRef.nii")
        affine = ref_img.affine; vol_shape = ref_img.shape

    # ---- preprocess: motion correct (with motion params) -> smooth ----
    nib.save(niftiObject, tmpPath + "/temp.nii")
    call(f"mcflirt -in {tmpPath}/temp.nii -reffile {tmpPath}/funcRef.nii "
         f"-out {tmpPath}/temp_mc -plots", shell=True)
    # head-motion parameters for this volume (rot x/y/z rad, trans x/y/z mm)
    par = mrt.read_mcflirt_par(tmpPath + "/temp_mc.par")
    motion_rows.append([vol] + par)
    mrt.write_motion(liveDir, motion_rows, TR=TR)
    mrt.write_motion_png(liveDir, motion_rows, TR=TR, nVols=nVols)   # always-available motion.png
    call(f'fslmaths {tmpPath}/temp_mc -kernel gauss {fwhm/2.3548} -fmean {tmpPath}/temp_sm', shell=True)
    img_flat_raw = nib.load(tmpPath + '/temp_sm.nii.gz').get_fdata().astype(np.float32).flatten()

    # ---- brain mask: built ONCE, from the AVERAGE of the baseline (pre-task)
    #      frames -- higher SNR than any single frame, and needs no separate
    #      sbref scan. Volumes before the mask exists are buffered raw. ----
    if vol <= baselineN:
        pre_baseline_imgs.append(img_flat_raw)
    if vol == baselineN:
        baseline_mean_full = np.mean(pre_baseline_imgs, axis=0)
        baseline_img_path = tmpPath + "/baselineRef.nii"
        nib.save(nib.Nifti1Image(baseline_mean_full.reshape(vol_shape).astype(np.float32), affine),
                 baseline_img_path)
        # ---- BET skull-strip -> nilearn EPI -> threshold, on the baseline average ----
        brain_mask_flat, mask_method = mrt.make_brain_mask(
            baseline_img_path, baseline_mean_full.reshape(vol_shape), affine, vol_shape,
            method=maskMethod, frac=maskFrac, maskFraction=maskFraction,
            maskPercentile=maskPercentile, work_dir=tmpPath)
        frac = 100.0 * brain_mask_flat.mean()
        print(f"Brain mask: {mask_method} on the {baselineN}-volume baseline average "
              f"-> {int(brain_mask_flat.sum())} voxels ({frac:.1f}% of FOV)")
        if frac < 3.0 or frac > 75.0:
            print("  [warn] mask coverage looks off — inspect outDir/live/brain_mask.nii.gz; "
                  "try maskMethod='bet'/'epi'/'threshold', or tune maskFrac.")
        try:
            nib.save(nib.Nifti1Image(brain_mask_flat.reshape(vol_shape).astype(np.uint8), affine),
                     os.path.join(liveDir, 'brain_mask.nii.gz'))
        except Exception:
            pass
        # the masked baseline average doubles as the display background (higher
        # SNR than any single frame; registration still used the un-masked funcRef.nii)
        ref3d = (baseline_mean_full * brain_mask_flat).reshape(vol_shape)
        mrt.write_reference(liveDir, ref3d, affine)
        mask_idx = np.where(brain_mask_flat)[0]
        Yglm = np.zeros((nVols, mask_idx.size), np.float32)   # GLM signal buffer
        for i, raw in enumerate(pre_baseline_imgs):
            Yglm[i] = (raw * brain_mask_flat)[mask_idx]        # backfill the buffered volumes
        baseline_mean = baseline_mean_full * brain_mask_flat
        print(f"Baseline image frozen from the first {baselineN} (rest) volumes.")

    if brain_mask_flat is not None:
        img_flat = img_flat_raw * brain_mask_flat
        if vol > baselineN:                          # baseline rows already filled above
            Yglm[vol - 1] = img_flat[mask_idx]        # feed the incremental GLM

    # ---- % signal change from baseline ----
    if baseline_mean is not None:
        psc = mrt.percent_change(img_flat, baseline_mean, brain_mask_flat)
        psc3d = psc.reshape(vol_shape)

        # accumulate the first event block, then localize the ROI on its peak %change
        if vol in firstBlockVols:
            fb_sum = psc.copy() if fb_sum is None else fb_sum + psc
            fb_n += 1
        if roi_peak is None and fb_n > 0 and vol >= lastFirstBlockVol:
            fb_mean = (fb_sum / fb_n).reshape(vol_shape)
            roi_peak = mrt.peak_voxel(fb_mean, brain_mask_flat.reshape(vol_shape))
            print(f"ROI = peak %change voxel of first '{firstLabel}' block @ {roi_peak}")

        # data-plot value: % signal change at the ROI's center (peak) voxel
        roi_psc = float(psc3d[roi_peak]) if roi_peak is not None else 0.0
        glob_psc = float(psc[brain_mask_flat].max()) if brain_mask_flat.any() else 0.0
    else:
        psc3d = None
        roi_psc = 0.0
        glob_psc = 0.0

    roi_trace.append(roi_psc); glob_trace.append(glob_psc); cond_trace.append(cond)
    point_idx += 1

    # ---- Data Plots tab: % signal change of the localized ROI ----
    webInterface.plotDataPoint(curRun, point_idx, float(round(roi_psc, 3)))
    subjInterface.setResultDict(name=f'run{curRun}_vol{vol}',
                                values={'roi_psc': str(round(roi_psc, 3)),
                                        'peak_psc': str(round(glob_psc, 3)),
                                        'condition': str(cond)})

    # ---- live brain map: per-frame % change from baseline, labeled with the
    #      current condition; small corner inset = cumulative LEFT vs RIGHT contrast ----
    if psc3d is not None and (point_idx % liveEveryTR) == 0 and ref3d is not None:
        running_peak = mrt.peak_voxel(psc3d, brain_mask_flat.reshape(vol_shape))
        if roi_peak is not None and psc3d[running_peak] < mapThreshPct:
            center = roi_peak           # sit on the ROI during rest
        else:
            center = running_peak       # follow the active region during a block
        last_center = center

        # LEFT vs RIGHT (or single-condition) map from an incremental GLM: refit
        # OLS on all rows seen so far (HRF-convolved regressors), contrast the
        # configured conditions, z-scored across voxels.
        contrast3d = None
        if Yglm is not None:
            cpct = mrt.glm_beta_contrast(Xglm[:vol], Yglm[:vol], glm_names,
                                         condA=glmCondA, condB=(glmCondB or None),
                                         zscore=glmZscore)
            if cpct is not None:
                flat = np.zeros(brain_mask_flat.size, np.float32)
                flat[mask_idx] = cpct
                contrast3d = flat.reshape(vol_shape)

        # condition label for THIS frame (hrf-aligned), e.g. 'left hand' / 'REST'
        condLabel = mrt.active_condition_label(events_rows, ((vol - 1) - hrf_delay) * TR)

        # peak-voxel measured-vs-HRF-predicted traces, refit on all rows seen so
        # far -- same incremental-refit approach as the GLM contrast map above,
        # so these rows update live every frame instead of only appearing once
        # at the very end of the run.
        vtraces = []
        if Yglm is not None and vol >= Xglm.shape[1] + 2:
            vtraces = mrt.glm_voxel_traces(Xglm[:vol], Yglm[:vol], glm_names, mask_idx,
                                           vol_shape, TR, conds, events_rows)

        mrt.write_live_update(
            liveDir, curRun, vol, taskName, psc3d, ref3d, affine, center, mapThreshPct,
            roi_trace, glob_trace, cond_trace,
            condAName='ROI %\u0394S', condBName='peak %\u0394S',
            caption='% change from baseline (red: increase, blue: decrease)',
            traceALabel=f'ROI ({firstLabel}) %\u0394S', traceBLabel='whole-brain peak %\u0394S',
            contrast3d=contrast3d, contrast_thresh=contrastThresh, condLabel=condLabel,
            n_slices=nSlices, z_cuts=(zCuts or None), contrast_label=glmLabel,
            voxel_traces=vtraces, full_xlim=fullXlim)

try:
    archive.appendBidsRun(currentBidsRun)
except Exception as e:
    print(f"[bids] archive append skipped: {e}")
bidsInterface.closeStream(streamId)

# ---- end of run: guaranteed final peak-voxel plot using the COMPLETE series
#      (the per-frame writes above already show these rows live throughout the
#      run, but liveEveryTR>1 can leave the very last frame's write a few
#      volumes stale -- this ensures the final current.png always reflects
#      every volume) ----
try:
    vtraces = mrt.glm_voxel_traces(Xglm, Yglm, glm_names, mask_idx, vol_shape, TR,
                                   conds, events_rows)
    if vtraces and psc3d is not None and center is not None:
        mrt.write_live_update(
            liveDir, curRun, nVols, taskName, psc3d, ref3d, affine, center, mapThreshPct,
            roi_trace, glob_trace, cond_trace,
            condAName='ROI %\u0394S', condBName='peak %\u0394S',
            caption='% change from baseline (red: increase, blue: decrease)',
            traceALabel=f'ROI ({firstLabel}) %\u0394S', traceBLabel='whole-brain peak %\u0394S',
            contrast3d=contrast3d, contrast_thresh=contrastThresh, condLabel=condLabel,
            n_slices=nSlices, z_cuts=(zCuts or None), contrast_label=glmLabel,
            voxel_traces=vtraces, full_xlim=fullXlim)
        print(f"Final current.png includes peak-voxel HRF fits for: "
              f"{[t['title'].split(' peak')[0] for t in vtraces]}")
    elif vtraces:
        print("[final] no live update ran during this run (baseline never froze / "
              "run too short) \u2014 skipping the peak-voxel HRF plot.")
except Exception as e:
    print(f"[final] peak-voxel HRF plot skipped: {e}")

# ---- end of run: assemble every saved live_run{curRun}_vol*.npz bundle into a
#      replay-able GIF of the whole run's activation maps (set saveGif=false
#      in the toml to skip this) ----
if saveGif:
    try:
        gifPath = mrt.build_activation_gif(liveDir, curRun, fps=gifFps)
        if gifPath:
            print(f"Activation GIF saved to {gifPath} -- reopen it anytime to replay the run.")
    except Exception as e:
        print(f"[gif] activation GIF skipped: {e}")

print(f"\n{taskName} complete. Realtime % signal-change plots + final peak-voxel HRF "
      f"fits in {liveDir}/current.png (Data Plots tab shows the ROI trace; "
      f"brain maps via realtime_display.py).")

print("-----------------------------------------------------------------------")
sys.exit(0)
