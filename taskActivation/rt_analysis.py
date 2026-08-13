"""-----------------------------------------------------------------------------
rt_analysis.py  —  registration-free real-time fMRI task-activation helpers
                   (numpy / nibabel / nilearn)

Shared by:
  - taskActivation.py  (live RT-Cloud analysis)
  - test_pipeline.py  (offline harness that tests the pipeline on the real
                       ds000244 HcpMotor design/geometry without rtCommon)

Nothing here imports rtCommon, so it is unit-testable anywhere. nilearn is used
to render the realtime activation plots; if nilearn is unavailable a matplotlib
montage is used instead.
-----------------------------------------------------------------------------"""
import os
import sys
import csv
import re
import subprocess
import importlib
import numpy as np


def ensure_nilearn(verbose=True):
    """Make nilearn importable, installing it into the current interpreter if
    needed. rt-cloud runs in Docker where nilearn may not be preinstalled, so we
    pip-install on first run (requires the container to have network access).
    Returns True if nilearn is usable, False if we fell back to matplotlib."""
    try:
        import nilearn  # noqa: F401
        return True
    except Exception:
        pass
    if verbose:
        print("[setup] nilearn not found - installing it (one-time)...")
    attempts = (
        [sys.executable, "-m", "pip", "install", "-q", "nilearn"],
        [sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "nilearn"],
        [sys.executable, "-m", "pip", "install", "-q", "--user", "nilearn"],
    )
    for args in attempts:
        try:
            subprocess.check_call(args)
            importlib.invalidate_caches()
            import nilearn  # noqa: F401
            if verbose:
                print("[setup] nilearn installed.")
            return True
        except Exception as e:
            if verbose:
                print(f"[setup] '{' '.join(args[3:])}' failed: {e}")
    if verbose:
        print("[setup] could not install nilearn; using matplotlib fallback for plots.")
    return False


# condition codes
def pack_frames(vol):
    """Pack a 3D volume (rows, cols, slices) into an Enhanced-multi-frame-style
    frame stack: shape (slices, rows, cols), frame i = slice i (ascending,
    matching InStackPositionNumber 1..N in the DICOM's PerFrameFunctionalGroups).
    This is what a multi-frame DICOM's PixelData holds (pydicom's .pixel_array
    returns this same shape automatically for Enhanced multi-frame files)."""
    return np.ascontiguousarray(np.moveaxis(vol, 2, 0))


def unpack_frames(frames):
    """Inverse of pack_frames: (slices, rows, cols) -> (rows, cols, slices)."""
    return np.ascontiguousarray(np.moveaxis(frames, 0, 2))


def dicom_header_info(path):
    """Read the handful of geometry/timing tags a mock-scanner or live-TR-inference
    caller needs from a real DICOM, checking both classic single-frame top-level
    tags and Enhanced multi-frame's nested Shared/PerFrame Functional Groups
    (Siemens Enhanced MR, e.g. MAGNETOM Prisma/Vida XA-line reconstructions store
    RepetitionTime/PixelSpacing/SliceThickness there instead of top-level).
    Returns a dict with whichever of TR/pixelSpacing/sliceThickness/rows/cols/
    nFrames were found (missing ones are simply absent, not defaulted here)."""
    import pydicom
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    info = {}
    if hasattr(ds, 'Rows'):
        info['rows'] = int(ds.Rows)
    if hasattr(ds, 'Columns'):
        info['cols'] = int(ds.Columns)
    if hasattr(ds, 'NumberOfFrames'):
        info['nFrames'] = int(ds.NumberOfFrames)

    tr = getattr(ds, 'RepetitionTime', None)
    px = getattr(ds, 'PixelSpacing', None)
    st = getattr(ds, 'SliceThickness', None)
    shared = getattr(ds, 'SharedFunctionalGroupsSequence', None)
    if shared:
        grp = shared[0]
        if tr is None:
            try:
                tr = grp.MRTimingAndRelatedParametersSequence[0].RepetitionTime
            except Exception:
                pass
        try:
            pm = grp.PixelMeasuresSequence[0]
            if px is None:
                px = pm.PixelSpacing
            if st is None:
                st = pm.SliceThickness
        except Exception:
            pass
    if tr is not None:
        info['TR'] = float(tr) / 1000.0   # DICOM RepetitionTime is in ms
    if px is not None:
        info['pixelSpacing'] = [float(v) for v in px]
    if st is not None:
        info['sliceThickness'] = float(st)
    return info


def promote_repetition_time_to_top_level(ds):
    """rt-cloud's own metadata reader (rtCommon.bidsCommon.getDicomMetadata)
    only iterates TOP-LEVEL DICOM elements -- it never looks inside
    SharedFunctionalGroupsSequence. So a real Enhanced-multi-frame DICOM whose
    RepetitionTime lives only in that nested location (the normal place for
    it, per the Enhanced MR IOD) will make rt-cloud's live pipeline raise
    MissingMetadataError, even though the file is perfectly valid and dcm2niix
    parses it fine. This copies RepetitionTime up to a top-level element
    (mutates `ds` in place; does not touch pixel data or anything else) so
    rt-cloud can see it. Returns True if a value was found and set."""
    if getattr(ds, 'RepetitionTime', None) is not None:
        return True
    try:
        tr = ds.SharedFunctionalGroupsSequence[0].MRTimingAndRelatedParametersSequence[0].RepetitionTime
    except Exception:
        return False
    ds.RepetitionTime = tr
    return True


def wait_for_first_dicom(dicomDir, namePattern, run, timeout=10.0, poll=0.25):
    """Poll dicomDir for the first volume's file (TR=1) of `run`, matching the
    same filename rt-cloud's own DicomToBidsStream will look for. Returns the
    path once it appears, or None on timeout (caller decides the fallback)."""
    import os as _os
    import time as _time
    fname = namePattern.format(RUN=run, SCAN=run, TR=1)
    path = _os.path.join(dicomDir, fname)
    end = _time.time() + timeout
    while _time.time() < end:
        if _os.path.exists(path) and _os.path.getsize(path) > 0:
            return path
        _time.sleep(poll)
    return None


def parse_float_list(val):
    """Robustly parse a list of floats from either a TOML array (list/tuple) or a
    string such as '[-20, -5, 10]', '-20,-5,10', or '-20 -5 10'. Some config / web
    layers deliver list-valued settings as strings; without this, list(str) would
    explode into characters. Empty / None / 'none' -> []."""
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        items = val
    else:
        s = str(val).strip().strip('[]()')
        if not s or s.lower() == 'none':
            return []
        items = re.split(r'[,\s]+', s)
    out = []
    for x in items:
        try:
            out.append(float(str(x).strip()))
        except (TypeError, ValueError):
            pass
    return out


REST = 0
COND_A = 1     # condition-of-interest A  (e.g. left_hand / reward)
COND_B = 2     # condition-of-interest B  (e.g. right_hand / punishment)
IGNORE = 3     # other modeled conditions (covariates / cues): not contrasted, not baseline

# trial_type names that denote implicit baseline rather than a modeled condition
REST_PATTERNS = ('rest', 'fixation', 'fixate', 'fixcross', 'crosshair', 'baseline',
                 'iti', 'blank', 'null', 'inter_trial', 'intertrial')


def is_rest_type(name):
    """True if a trial_type denotes rest/baseline (and so is modeled implicitly,
    not as a GLM regressor)."""
    n = str(name).strip().lower()
    if n in ('', 'n/a', 'na', '+', 'fix'):
        return True
    return any(p in n for p in REST_PATTERNS)


def classify_conditions(rows, condA=None, condB=None, rest_types=None):
    """Split the events' trial_types into rest (implicit baseline), the
    conditions of interest (condA/condB), and additional covariates (everything
    else). Returns a dict with keys: rest, interest, covariates, modeled."""
    all_types = sorted(set(tt for _, _, tt in rows))
    rest = set(rest_types) if rest_types is not None else {t for t in all_types if is_rest_type(t)}
    interest = [c for c in (condA, condB) if c]
    modeled = [t for t in all_types if t not in rest]
    covariates = [t for t in modeled if t not in interest]
    return {'rest': sorted(rest), 'interest': interest,
            'covariates': covariates, 'modeled': modeled}


# ======================= design from a BIDS events.tsv =======================
def read_events_tsv(path):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f, delimiter='\t'):
            rows.append((float(row['onset']), float(row['duration']),
                         row['trial_type'].strip()))
    return rows


def build_design_from_events(rows, nVols, TR, hrf_delay,
                             condA_types=('left_hand',), condB_types=('right_hand',),
                             rest_types=None):
    """Per-VOLUME condition codes (length nVols), hrf-aligned, for the timecourse
    shading / first-block ROI. condA_types -> 1, condB_types -> 2, any other
    modeled condition -> 3 (IGNORE); rest-like or no event -> 0 (REST)."""
    rest = set(rest_types) if rest_types is not None else None
    condA_types, condB_types = set(condA_types), set(condB_types)

    def active(t):
        for o, d, tt in rows:
            if o <= t < o + d:
                return tt
        return None

    codes = np.zeros(nVols, int)
    for v in range(nVols):
        tt = active(v * TR - hrf_delay * TR)   # brain volume reflects earlier neural event
        is_rest = (tt is None) or (is_rest_type(tt) if rest is None else (tt in rest))
        if is_rest:
            codes[v] = REST
        elif tt in condA_types:
            codes[v] = COND_A
        elif tt in condB_types:
            codes[v] = COND_B
        else:
            codes[v] = IGNORE
    return codes


# ======================= registration-free analysis ==========================
def _threshold_mask(ref3d, maskFraction=0.12, maskPercentile=98):
    ref3d = np.asarray(ref3d, np.float32)
    pos = ref3d[ref3d > 0]
    if pos.size == 0:
        return np.zeros(ref3d.shape, bool)
    return ref3d > maskFraction * np.percentile(pos, maskPercentile)


def _epi_mask(ref3d, affine):
    """nilearn data-driven EPI mask (or None on failure / implausible coverage)."""
    try:
        import nibabel as nib
        from nilearn.masking import compute_epi_mask
        img = nib.Nifti1Image(np.asarray(ref3d, np.float32), affine)
        m = np.asarray(compute_epi_mask(img, exclude_zeros=True).get_fdata()).astype(bool)
        return m if 0.03 < m.mean() < 0.75 else None
    except Exception:
        return None


def bet_brain_mask(in_path, work_dir, frac=0.35, robust=True):
    """Skull/neck-stripped brain mask via FSL BET (present in the rtcloud image).
    BET is built to remove non-brain tissue (skull, neck, eyes), which intensity
    thresholds keep. Returns a 3D bool mask, or None if BET is unavailable."""
    import shutil
    import subprocess
    if not in_path or not os.path.exists(in_path) or shutil.which('bet') is None:
        return None
    out = os.path.join(work_dir, '_bet_brain')
    cmd = ['bet', in_path, out, '-f', str(frac), '-n', '-m']
    if robust:
        cmd.append('-R')                  # robust centre estimation (good for EPI/neck)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return None
    import nibabel as nib
    for mf in (out + '_mask.nii.gz', out + '_mask.nii'):
        if os.path.exists(mf):
            return np.asarray(nib.load(mf).get_fdata()).astype(bool)
    return None


def make_brain_mask(image_path, ref3d, affine, vol_shape, method='bet', frac=0.35,
                    maskFraction=0.12, maskPercentile=98, work_dir='/tmp'):
    """Build a brain mask, preferring `method` and degrading gracefully:
    bet -> nilearn EPI -> intensity threshold. Returns (mask_flat_bool, source)."""
    import nibabel as nib
    vol_shape = tuple(vol_shape)
    # source image data (sbref or func volume) for the epi/threshold methods
    if image_path and os.path.exists(image_path):
        im = nib.load(image_path); d = im.get_fdata(); aff = im.affine
        if d.ndim == 4:
            d = d.mean(axis=3)
    else:
        d, aff = np.asarray(ref3d), affine
    order = {'bet': ['bet', 'epi', 'threshold'],
             'epi': ['epi', 'threshold'],
             'threshold': ['threshold']}.get(method, ['bet', 'epi', 'threshold'])
    for m in order:
        try:
            if m == 'bet':
                mask = bet_brain_mask(image_path, work_dir, frac)
            elif m == 'epi':
                mask = _epi_mask(d, aff)
            else:
                mask = _threshold_mask(d, maskFraction, maskPercentile)
        except Exception:
            mask = None
        if mask is not None and mask.shape == vol_shape and 0.02 < mask.mean() < 0.8:
            return mask.flatten(), m
    # last resort: threshold on the functional reference itself
    return _threshold_mask(ref3d, maskFraction, maskPercentile).flatten(), 'threshold(ref)'


def compute_brain_mask(ref3d, maskFraction=0.12, maskPercentile=98, affine=None):
    """Brain mask for a single EPI/sbref volume. nilearn EPI mask when an affine
    is given (adaptive), else an intensity threshold. (Kept for compatibility;
    `make_brain_mask` is the fuller dispatcher that also tries FSL BET.)"""
    if affine is not None:
        m = _epi_mask(ref3d, affine)
        if m is not None:
            return m
    return _threshold_mask(ref3d, maskFraction, maskPercentile)


def sbref_path_for(boldPath):
    """Path of the single-band reference (sbref) that sits next to a bold file."""
    if boldPath.endswith('_bold.nii.gz'):
        return boldPath[:-len('_bold.nii.gz')] + '_sbref.nii.gz'
    if boldPath.endswith('_bold.nii'):
        return boldPath[:-len('_bold.nii')] + '_sbref.nii'
    return None


def mask_from_sbref(sbrefPath, maskFraction=0.12, maskPercentile=98):
    """Brain mask computed from the sbref image (higher SNR than a single EPI vol).
    Returns (mask3d, sbref3d) or (None, None) if unavailable."""
    import nibabel as nib
    if not sbrefPath or not os.path.exists(sbrefPath):
        return None, None
    img = nib.load(sbrefPath)
    data = img.get_fdata()
    if data.ndim == 4:                 # average over time if the sbref is 4D
        data = data.mean(axis=3)
    mask = compute_brain_mask(data, maskFraction, maskPercentile, affine=img.affine)
    return mask, data


def active_condition_label(rows, t):
    """Human-readable label of the event active at time `t` (s); 'REST' if none."""
    for o, d, tt in rows:
        if o <= t < o + d:
            return tt.replace('_', ' ')
    return 'REST'


def zmap_from_diff(diff_flat, mask_flat):
    z = np.zeros_like(diff_flat, dtype=np.float32)
    if mask_flat.sum() > 0:
        d = diff_flat[mask_flat]
        z[mask_flat] = (d - d.mean()) / (d.std() + 1e-9)
    return z


def peak_voxel(zmap3d, mask3d):
    masked = np.where(mask3d, zmap3d, -np.inf)
    return tuple(int(c) for c in np.unravel_index(int(np.argmax(masked)), masked.shape))


def sphere_roi(shape, center, radius):
    ii, jj, kk = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return ((ii - center[0])**2 + (jj - center[1])**2 + (kk - center[2])**2) <= radius**2


def voxel_to_mm(affine, ijk):
    v = np.asarray(affine) @ np.array([ijk[0], ijk[1], ijk[2], 1.0])
    return tuple(float(x) for x in v[:3])


# ======================= local NIfTI replay source ===========================
def bids_bold_relpath(subject, session, task, acquisition):
    """Relative BIDS path of a bold file from subject/session/task/acquisition."""
    name = f"sub-{subject}"
    sub = f"sub-{subject}"
    parts = [sub]
    if session:
        parts.append(f"ses-{session}")
        name += f"_ses-{session}"
    parts.append("func")
    name += f"_task-{task}"
    if acquisition:
        name += f"_acq-{acquisition}"
    name += "_bold.nii.gz"
    return os.path.join(*parts, name)


def ensure_openneuro_bold(cacheDir, dsAccession, subject, session, task, acquisition,
                          verbose=True):
    """Download a single bold (+ its events/json) from OpenNeuro's public S3 mirror
    using the same `aws s3 sync --no-sign-request` rt-cloud uses. Returns the local
    path to the 4D bold .nii.gz (downloading only if missing)."""
    rel = bids_bold_relpath(subject, session, task, acquisition)
    local_bold = os.path.join(cacheDir, dsAccession, rel)
    if os.path.exists(local_bold):
        if verbose:
            print(f"[data] using cached bold: {local_bold}")
        return local_bold
    func_dir = os.path.dirname(local_bold)
    os.makedirs(func_dir, exist_ok=True)
    # S3 source = the func/ folder for this subject/session
    s3sub = f"sub-{subject}/" + (f"ses-{session}/" if session else "") + "func/"
    s3 = f"s3://openneuro.org/{dsAccession}/{s3sub}"
    inc = f"*task-{task}*" + (f"acq-{acquisition}*" if acquisition else "")
    cmd = (f'aws s3 sync --no-sign-request "{s3}" "{func_dir}" '
           f'--exclude "*" --include "{inc}"')
    if verbose:
        print(f"[data] downloading: {cmd}")
    os.system(cmd)
    if not os.path.exists(local_bold):
        raise FileNotFoundError(
            f"Could not download {local_bold}. Check the accession/entities and that "
            f"awscli is installed and the container has network access.")
    return local_bold


class NiftiReplaySource:
    """Replays volumes from a local 4D NIfTI, mimicking a realtime stream.
    Avoids rt-cloud's initOpenNeuroStream run-entity requirement and works for
    any dataset/file. Volumes are read lazily (no full 4D load)."""
    def __init__(self, path):
        import nibabel as nib
        self.img = nib.load(path)
        if self.img.ndim != 4:
            raise ValueError(f"Expected a 4D bold, got shape {self.img.shape}")
        self.numVolumes = int(self.img.shape[3])
        self.affine = self.img.affine
        self.header = self.img.header

    def get_volume(self, volIdx):
        """Return a 3D nibabel image for 0-based volume volIdx."""
        import nibabel as nib
        vol = np.asarray(self.img.dataobj[..., volIdx])
        return nib.Nifti1Image(vol, self.affine, self.header)


# ======================= realtime activation plots ===========================
def nilearn_stat_png(out_png, zmap3d, ref3d, affine, thresh, title,
                     peak=None, condAName='A', condBName='B', caption=None, cmap='RdBu_r',
                     contrast3d=None, contrast_thresh=2.0,
                     contrast_label='LEFT vs RIGHT (cumulative)', n_slices=6, z_cuts=None,
                     voxel_traces=None):
    """Realtime plot via nilearn.plot_stat_map as a single-row AXIAL MOSAIC.
    Slice positions: `z_cuts` (a list of z-coords in mm) if given, else `n_slices`
    auto-selected levels. Top row = per-frame map; when `contrast3d` is given a
    SECOND mosaic row below shows the GLM contrast. `voxel_traces` (optional, used
    at end of run) adds one line-plot row per entry below the brain rows, each
    showing a peak voxel's measured signal vs its HRF-predicted signal."""
    try:
        import nibabel as nib
        from nilearn import plotting
        import matplotlib.pyplot as plt
    except Exception:
        return False
    cuts = list(z_cuts) if z_cuts else n_slices      # explicit mm levels, or auto count
    cap = caption if caption is not None else f"red {condAName}>{condBName} / blue {condBName}>{condAName}"
    zimg = nib.Nifti1Image(np.asarray(zmap3d, np.float32), affine)
    bg = nib.Nifti1Image(np.asarray(ref3d, np.float32), affine)
    has_con = (contrast3d is not None and np.isfinite(contrast3d).any()
               and np.nanmax(np.abs(contrast3d)) > 1e-6)
    traces = voxel_traces or []
    n_brain = 2 if has_con else 1
    nrows = n_brain + len(traces)
    height_ratios = [3.0] * n_brain + [1.5] * len(traces)
    fig_h = 2.9 * n_brain + 2.0 * len(traces)
    fig = plt.figure(figsize=(13, fig_h), facecolor='black')
    gs = fig.add_gridspec(nrows, 1, height_ratios=height_ratios, hspace=0.45)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1]) if has_con else None
    plotting.plot_stat_map(zimg, bg_img=bg, threshold=thresh, display_mode='z',
                           cut_coords=cuts, colorbar=True, cmap=cmap, black_bg=True,
                           figure=fig, axes=ax_top, title=f"{title}  ({cap})")
    if has_con:
        cimg = nib.Nifti1Image(np.asarray(contrast3d, np.float32), affine)
        plotting.plot_stat_map(cimg, bg_img=bg, threshold=contrast_thresh,
                               display_mode='z', cut_coords=cuts, colorbar=True,
                               cmap='RdBu_r', black_bg=True, figure=fig, axes=ax_bot,
                               title=contrast_label)
    # end-of-run: measured vs HRF-predicted timecourse at each condition's peak voxel
    for i, tr in enumerate(traces):
        ax = fig.add_subplot(gs[n_brain + i], facecolor='black')
        t = np.asarray(tr['t'])
        for (b0, b1) in tr.get('blocks', []):
            ax.axvspan(b0, b1, color=tr.get('color', 'tab:red'), alpha=0.12)
        ax.plot(t, tr['measured'], color='white', lw=1.4, label='measured %\u0394S')
        ax.plot(t, tr['predicted'], color=tr.get('color', 'tab:red'), lw=1.8,
                ls='--', label='HRF-predicted')
        ax.axhline(0, color='gray', lw=0.5)
        ax.set_title(tr['title'], color='white', fontsize=9)
        ax.set_xlabel('time (s)', color='white'); ax.set_ylabel('% \u0394S', color='white')
        ax.tick_params(colors='white', labelsize=7)
        for s in ax.spines.values():
            s.set_color('white')
        ax.legend(loc='upper right', fontsize=7, facecolor='black', labelcolor='white')
    fig.savefig(out_png, dpi=110, facecolor='black')
    plt.close(fig)
    return True


def _matplotlib_montage_png(out_png, zmap3d, ref3d, peak, thresh, title,
                            condAName='A', condBName='B'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    i, j, k = peak
    bgs = [ref3d[i, :, :], ref3d[:, j, :], ref3d[:, :, k]]
    ovs = [zmap3d[i, :, :], zmap3d[:, j, :], zmap3d[:, :, k]]
    vmax = max(float(np.nanmax(np.abs(zmap3d))), thresh + 1e-3)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for ax, bg, ov, t in zip(axes, bgs, ovs, ['Sagittal', 'Coronal', 'Axial']):
        ax.imshow(np.rot90(bg), cmap='gray')
        o = np.rot90(ov).astype(float).copy()
        o[np.abs(o) < thresh] = np.nan
        ax.imshow(o, cmap='RdBu_r', vmin=-vmax, vmax=vmax, alpha=0.85)
        ax.set_title(t, fontsize=10); ax.axis('off')
    fig.suptitle(f"{title}  (red {condAName}>{condBName} / blue {condBName}>{condAName})", fontsize=11)
    fig.tight_layout(); fig.savefig(out_png, dpi=110); plt.close(fig)


def write_reference(liveDir, ref3d, affine):
    """Write the functional reference once (the viewer loads it once)."""
    os.makedirs(liveDir, exist_ok=True)
    np.savez_compressed(os.path.join(liveDir, 'reference.npz'),
                        ref=np.asarray(ref3d, np.float32), affine=np.asarray(affine, np.float32))


def write_live_update(liveDir, run, vol, runLabel, zmap3d, ref3d, affine, peak, thresh,
                      A_trace, B_trace, cond_trace, condAName='A', condBName='B',
                      caption=None, traceALabel=None, traceBLabel=None,
                      contrast3d=None, contrast_thresh=2.0, condLabel=None, n_slices=6,
                      z_cuts=None, contrast_label='LEFT vs RIGHT GLM contrast',
                      voxel_traces=None):
    """Write the per-update bundle (full 3D map for nilearn) + a nilearn PNG, and
    atomically update the latest.txt pointer."""
    os.makedirs(liveDir, exist_ok=True)
    fn = os.path.join(liveDir, f'live_run{run}_vol{vol:03d}.npz')
    bundle = dict(
        run=run, vol=vol, phase=runLabel, peak=np.array(peak), thresh=thresh,
        condA=condAName, condB=condBName,
        traceA=(traceALabel or condAName), traceB=(traceBLabel or condBName),
        caption=(caption or ''), condLabel=(condLabel or ''),
        contrast_label=(contrast_label or ''),
        contrast_thresh=float(contrast_thresh), n_slices=int(n_slices),
        z_cuts=np.asarray(z_cuts if z_cuts else [], dtype=np.float32),
        affine=np.asarray(affine, np.float32),
        zmap=np.asarray(zmap3d, np.float32),
        A_trace=np.array(A_trace, np.float32), B_trace=np.array(B_trace, np.float32),
        cond_trace=np.array(cond_trace, np.int16))
    if contrast3d is not None:
        bundle['contrast'] = np.asarray(contrast3d, np.float32)
    np.savez_compressed(fn, **bundle)
    tmp = os.path.join(liveDir, 'latest.tmp')
    with open(tmp, 'w') as f:
        f.write(os.path.basename(fn))
    os.replace(tmp, os.path.join(liveDir, 'latest.txt'))
    out_png = os.path.join(liveDir, 'current.png')
    cond_txt = f" | {condLabel}" if condLabel else ""
    title = f"{runLabel} | run {run} | vol {vol}{cond_txt}"
    try:
        ok = nilearn_stat_png(out_png, zmap3d, ref3d, affine, thresh, title,
                              peak=peak, condAName=condAName, condBName=condBName,
                              caption=caption, contrast3d=contrast3d,
                              contrast_thresh=contrast_thresh, n_slices=n_slices,
                              z_cuts=z_cuts, contrast_label=contrast_label,
                              voxel_traces=voxel_traces)
        if not ok:
            _matplotlib_montage_png(out_png, zmap3d, ref3d, peak, thresh, title,
                                    condAName, condBName)
    except Exception as e:
        print(f"[live] activation plot skipped: {e}")
    return fn


def first_event_window(rows, exclude_cues=True, gap=3.0, include_types=None,
                       rest_types=None):
    """(onset, offset, label) of the FIRST event block. If `include_types` is
    given (the conditions of interest), only those are considered; otherwise the
    first non-rest (and, by default, non-cue) event is used. The block extends
    over immediately-following events of the same type (gaps < `gap` s)."""
    rest = set(rest_types) if rest_types is not None else None

    def keep(tt):
        if include_types is not None:
            return tt in include_types
        if rest_types is None:
            if is_rest_type(tt):
                return False
        elif tt in rest:
            return False
        return not (exclude_cues and tt.endswith('_cue'))

    evs = sorted([(o, d, tt) for (o, d, tt) in rows if keep(tt)], key=lambda x: x[0])
    if not evs:
        return None
    onset, dur, label = evs[0]
    offset = onset + dur
    for o, d, tt in evs[1:]:
        if tt == label and o <= offset + gap:
            offset = max(offset, o + d)
        else:
            break
    return onset, offset, label


def percent_change(img_flat, baseline_flat, mask_flat):
    """Per-voxel % signal change from a fixed baseline, zeroed outside the mask."""
    psc = np.zeros_like(img_flat, dtype=np.float32)
    valid = mask_flat & (baseline_flat > 0)
    psc[valid] = 100.0 * (img_flat[valid] - baseline_flat[valid]) / baseline_flat[valid]
    return psc


# ============================ incremental GLM ================================
def canonical_hrf(TR, length=32.0):
    """SPM-style double-gamma HRF sampled at TR, normalized to peak 1 (so a GLM
    beta on a unit boxcar regressor is ~ the peak response amplitude)."""
    from math import gamma
    t = np.arange(0, length, TR)
    hrf = (t**5) * np.exp(-t) / gamma(6) - ((t**15) * np.exp(-t) / gamma(16)) / 6.0
    m = np.max(hrf)
    return hrf / (m if m > 0 else 1.0)


def make_glm_design(rows, nVols, TR, drift_order=1, rest_types=None):
    """Design matrix X (nVols x K) for any task: ONE HRF-convolved regressor for
    every non-rest trial_type in the events (conditions of interest AND all other
    conditions, which become additional covariates), plus polynomial drift and an
    intercept. Rest is modeled implicitly by the intercept (no rest regressor).
    `rest_types` overrides the automatic rest detection. Returns (X, names)."""
    all_types = sorted(set(tt for _, _, tt in rows))
    rest = set(rest_types) if rest_types is not None else {t for t in all_types if is_rest_type(t)}
    conditions = [t for t in all_types if t not in rest]
    hrf = canonical_hrf(TR)
    ft = np.arange(nVols) * TR
    cols, names = [], []
    for cond in conditions:
        box = np.zeros(nVols)
        for o, d, tt in rows:
            if tt == cond:
                box[(ft >= o) & (ft < o + d)] = 1.0
        cols.append(np.convolve(box, hrf)[:nVols]); names.append(cond)
    denom = max(ft[-1], 1.0)
    for k in range(1, drift_order + 1):
        cols.append((ft / denom) ** k); names.append(f'drift{k}')
    cols.append(np.ones(nVols)); names.append('intercept')
    return np.column_stack(cols).astype(np.float32), names


def glm_voxel_traces(X, Y, names, mask_idx, vol_shape, TR, conds, events_rows, colors=None):
    """For each condition in `conds`, fit the full GLM, find the voxel with the
    largest beta for that condition, and return a trace dict: the measured
    %-signal-change timecourse at that voxel, the full-model HRF prediction (also
    in %), and the condition's stimulus blocks (for shading). Used at end of run."""
    try:
        beta, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)   # K x nVox
    except Exception:
        return []
    iI = names.index('intercept')
    t = np.arange(X.shape[0]) * TR
    palette = colors or ['tab:red', 'tab:blue', 'tab:green', 'tab:orange']
    traces = []
    for k, cond in enumerate(conds):
        if not cond or cond not in names:
            continue
        ic = names.index(cond)
        col = int(np.argmax(beta[ic]))                      # peak voxel for this condition
        vox = tuple(int(c) for c in np.unravel_index(int(mask_idx[col]), vol_shape))
        mean = abs(float(beta[iI, col])) + 1e-6
        measured = 100.0 * (Y[:, col] - mean) / mean
        predicted = 100.0 * (X @ beta[:, col] - mean) / mean
        blocks = [(o, o + d) for (o, d, tt) in events_rows if tt == cond]
        traces.append({'title': f"{cond} peak voxel {vox}  (\u03b2={beta[ic, col]:.0f})",
                       't': t, 'measured': np.asarray(measured), 'predicted': np.asarray(predicted),
                       'blocks': blocks, 'color': palette[k % len(palette)]})
    return traces


def glm_beta_contrast(X, Y, names, condA='left_hand', condB='right_hand', min_on=4,
                      zscore=True):
    """Fit OLS beta = pinv(X) Y for every voxel and return a map over voxels:
      * if `condB` is given -> the condA-minus-condB beta contrast
      * if `condB` is None/'' -> the condA beta weight
    The map is z-scored across voxels when `zscore` (else expressed as % signal
    change, contrast/intercept*100). Returns None until the model is estimable."""
    if condA not in names:
        return None
    iA = names.index(condA); iI = names.index('intercept')
    if X.shape[0] < X.shape[1] + 2:                       # need more rows than params
        return None
    if int((X[:, iA] > 0.1).sum()) < min_on:
        return None
    use_contrast = bool(condB) and condB in names
    if use_contrast:
        iB = names.index(condB)
        if int((X[:, iB] > 0.1).sum()) < min_on:
            return None
    try:
        beta, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)   # K x nVox
    except Exception:
        return None
    out = (beta[iA] - beta[iB]) if use_contrast else beta[iA]
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    if zscore:
        s = out.std()
        out = (out - out.mean()) / (s + 1e-9)
    else:
        out = 100.0 * out / (np.abs(beta[iI]) + 1e-6)
    return out.astype(np.float32)


# ============================ head motion ===================================
def read_mcflirt_par(par_path):
    """Read mcflirt -plots output: 6 params per volume (rot x/y/z [rad],
    trans x/y/z [mm]). Returns the last row as a list of 6 floats."""
    try:
        arr = np.loadtxt(par_path)
        row = arr if arr.ndim == 1 else arr[-1]
        return [float(v) for v in row[:6]]
    except Exception:
        return [0.0] * 6


def write_motion_png(liveDir, motion_rows, TR=2.0, head_radius_mm=50.0):
    """Render the live head-motion plot to liveDir/motion.png with a headless
    (Agg) backend, so a motion image always exists in outDir/live even when no
    interactive window is available. One line per parameter (tx,ty,tz,rx,ry,rz),
    x = time (s), y = mm (rotations converted to mm at `head_radius_mm`)."""
    if not motion_rows:
        return False
    try:
        import matplotlib
        if 'agg' not in matplotlib.get_backend().lower():
            matplotlib.use('Agg', force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return False
    m = np.asarray(motion_rows, float)              # cols: vol, rx, ry, rz, tx, ty, tz
    t = m[:, 0] * TR
    series = [('tx', m[:, 4]), ('ty', m[:, 5]), ('tz', m[:, 6]),
              ('rx', m[:, 1] * head_radius_mm), ('ry', m[:, 2] * head_radius_mm),
              ('rz', m[:, 3] * head_radius_mm)]
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    os.makedirs(liveDir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    for (lab, y), c in zip(series, colors):
        ax.plot(t, y, label=lab, color=c, lw=1.5)
    ax.axhline(0, color='gray', lw=0.5)
    ax.set_xlabel('time (s)'); ax.set_ylabel('head motion (mm)')
    ax.legend(loc='upper left', ncol=6, fontsize=8)
    ax.set_title('Real-time head motion (mcflirt): tx,ty,tz + rx,ry,rz @ 50 mm', fontsize=10)
    tmp = os.path.join(liveDir, 'motion.png.tmp')
    fig.tight_layout(); fig.savefig(tmp, dpi=110, format='png'); plt.close(fig)
    os.replace(tmp, os.path.join(liveDir, 'motion.png'))
    return True


def write_motion(liveDir, motion_rows, TR=2.0):
    """Atomically (re)write motion.tsv with all rows seen so far. Each input row is
    [vol, rot_x, rot_y, rot_z, trans_x, trans_y, trans_z]; a time_s column
    (vol*TR) is added so viewers can use seconds on the x-axis."""
    os.makedirs(liveDir, exist_ok=True)
    p = os.path.join(liveDir, 'motion.tsv')
    tmp = p + '.tmp'
    with open(tmp, 'w') as f:
        f.write('vol\ttime_s\trot_x\trot_y\trot_z\ttrans_x\ttrans_y\ttrans_z\n')
        for r in motion_rows:
            vol = r[0]
            f.write(f'{vol:g}\t{vol*TR:.3f}\t' + '\t'.join(f'{v:.6f}' for v in r[1:]) + '\n')
    os.replace(tmp, p)


def write_motion_png(liveDir, motion_rows, TR=2.0, head_radius_mm=50.0, fd_thresh=0.5):
    """Render the live head-motion plot to outDir/live/motion.png with TWO rows:
    (1) one line per parameter, x = time [s], y = head motion [mm] (rotations
    converted to mm-equivalent at `head_radius_mm`); (2) framewise displacement
    (FD, Power et al.) per volume on the same image. Headless-safe (Agg canvas)."""
    if not motion_rows:
        return False
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
    except Exception:
        return False
    m = np.asarray(motion_rows, dtype=float)            # cols: vol, rx, ry, rz, tx, ty, tz
    t = m[:, 0] * TR
    series = [('tx', m[:, 4], '#1f77b4'), ('ty', m[:, 5], '#ff7f0e'),
              ('tz', m[:, 6], '#2ca02c'), ('rx', m[:, 1]*head_radius_mm, '#d62728'),
              ('ry', m[:, 2]*head_radius_mm, '#9467bd'), ('rz', m[:, 3]*head_radius_mm, '#8c564b')]
    # framewise displacement: sum of |Δtrans| + radius*|Δrot| (rotations in rad)
    rot, trans = m[:, 1:4], m[:, 4:7]
    if len(m) > 1:
        dfd = np.abs(np.diff(trans, axis=0)).sum(1) + np.abs(np.diff(rot, axis=0)).sum(1)*head_radius_mm
        fd = np.concatenate([[0.0], dfd])
    else:
        fd = np.zeros(len(m))

    fig = Figure(figsize=(10, 7), facecolor='white')
    FigureCanvasAgg(fig)
    ax1 = fig.add_subplot(2, 1, 1)
    ax2 = fig.add_subplot(2, 1, 2, sharex=ax1)
    for lab, y, color in series:
        ax1.plot(t, y, label=lab, color=color, lw=1.5)
    ax1.axhline(0, color='gray', lw=0.5)
    ax1.set_ylabel('head motion (mm)')
    ax1.legend(loc='upper left', ncol=6, fontsize=8)
    ax1.set_title('Real-time head motion (mcflirt): translations + rotations '
                  f'(rx,ry,rz @ {head_radius_mm:g} mm) in mm', fontsize=9)
    ax2.plot(t, fd, color='crimson', lw=1.5, label='FD')
    ax2.axhline(fd_thresh, color='orange', ls='--', lw=0.8, label=f'{fd_thresh:g} mm')
    ax2.set_ylabel('FD (mm)'); ax2.set_xlabel('time (s)')
    ax2.legend(loc='upper left', fontsize=8)
    ax2.set_title(f'Framewise displacement  (max {fd.max():.2f} mm, mean {fd.mean():.2f} mm)',
                  fontsize=9)
    fig.tight_layout()
    out = os.path.join(liveDir, 'motion.png')
    tmp = out + '.tmp.png'
    fig.savefig(tmp, dpi=110); os.replace(tmp, out)
    return True


