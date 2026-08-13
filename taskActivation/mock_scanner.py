#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
mock_scanner.py  —  simulate an MRI scanner for dataSource = "dicom".

Writes one Enhanced-multi-frame DICOM per volume into the watched dicomDir at
TR cadence, exactly matching the project's dicomNamePattern, so you can test
the full real-time DICOM streaming path (file-watch -> getIncremental ->
analysis) without a real scanner. RT-Cloud converts each file to a NIfTI with
dcm2niix and feeds it to the analysis exactly as a real scanner would.

Geometry (Rows/Columns/NumberOfFrames, PixelSpacing, SliceThickness) and TR
are READ FROM A REFERENCE DICOM at runtime (--reference-dicom; defaults to
the bundled, fully anonymized templates/enhanced_bold_template.dcm, itself
derived from a real Siemens Prisma Fit Enhanced-MR acquisition) rather than
hardcoded, so the synthetic data matches whatever scanner/protocol produced
the reference file. Point --reference-dicom at a different real DICOM to
match a different scanner/protocol.

Volume source:
  --source synthetic   (default) build a series with task activation driven
                       by the events file (condA / condB regions).
  --source <nifti>     replay a real 4D NIfTI, resampling each volume to the
                       reference DICOM's (rows, cols, nSlices) grid.

Usage (run in a second terminal, alongside the taskActivation run):
  python mock_scanner.py --config conf/taskActivation.toml            # synthetic
  python mock_scanner.py --config conf/taskActivation.toml --source bold.nii.gz
  python mock_scanner.py --config conf/... --no-delay --clean         # fast test
-----------------------------------------------------------------------------"""
import os
import sys
import time
import copy
import argparse
import numpy as np

import rt_analysis as mrt

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_REFERENCE = os.path.join(HERE, 'templates', 'enhanced_bold_template.dcm')


def load_cfg(path):
    """Read the handful of keys we need from the toml (no rtCommon dependency)."""
    try:
        import tomllib
        with open(path, 'rb') as f:
            return tomllib.load(f)
    except Exception:
        cfg = {}
        for line in open(path):
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
        return cfg


def ellipsoid_brain(shape):
    R, C, S = shape
    ii, jj, kk = np.indices(shape)          # row, col, slice coordinates
    e = (((ii - R/2)/(R*0.45))**2 + ((jj - C/2)/(C*0.45))**2 + ((kk - S/2)/(S*0.48))**2)
    return e <= 1.0


def synthetic_series(events, nVols, TR, condA, condB, shape,
                     seed=0, base=1200.0, resp=0.05):
    """4D (rows, cols, slices, time) with two task-driven regions (condA/condB),
    HRF-convolved from the real events, on an ellipsoid brain + noise. `shape`
    is the reference DICOM's (rows, cols, nSlices)."""
    rng = np.random.default_rng(seed)
    X, names = mrt.make_glm_design(events, nVols, TR, drift_order=1)
    R, C, S = shape
    brain = ellipsoid_brain(shape)
    anat = base * (0.8 + 0.2 * np.sin(np.indices(shape)[0] / 5.0))
    regA = X[:, names.index(condA)] if condA in names else np.zeros(nVols)
    regB = X[:, names.index(condB)] if condB in names else np.zeros(nVols)
    A = np.zeros(shape, bool); A[R//2+6:R//2+11, C//2-3:C//2+2, S//2-2:S//2+3] = True
    B = np.zeros(shape, bool); B[R//2-11:R//2-6, C//2-3:C//2+2, S//2-2:S//2+3] = True
    A &= brain; B &= brain
    series = np.zeros((R, C, S, nVols), np.float32)
    for t in range(nVols):
        v = anat + rng.normal(0, base*0.012, shape)
        v += base*resp*regA[t]*A + base*resp*regB[t]*B
        series[..., t] = v * brain
    return series, (A, B)


def nifti_series(path, shape, nVols_hint=None):
    """Load a 4D NIfTI and resample each volume to `shape` (the reference
    DICOM's rows, cols, nSlices)."""
    import nibabel as nib
    from scipy.ndimage import zoom
    img = nib.load(path)
    data = img.get_fdata()
    if data.ndim == 3:
        data = data[..., None]
    nVols = data.shape[3]
    factors = [shape[i] / data.shape[i] for i in range(3)]
    out = np.zeros(shape + (nVols,), np.float32)
    for t in range(nVols):
        out[..., t] = zoom(data[..., t], factors, order=1)
    # rescale to a sane uint16 range
    out = out - out.min()
    if out.max() > 0:
        out = out / out.max() * 2000.0
    return out, None


def write_dicom(template, vol3d, out_path, instance, run, TR):
    """Write one Enhanced-multi-frame DICOM: deepcopy the reference template,
    pack vol3d's slices into PixelData (frame i = slice i, matching the
    template's InStackPositionNumber order), and stamp per-volume identifiers
    (InstanceNumber/AcquisitionNumber/SeriesNumber/SOPInstanceUID, and each
    frame's TemporalPositionIndex) so the file is a faithful one-volume
    Enhanced MR instance, not a re-used copy of the reference volume's frame
    metadata. RepetitionTime is stamped at BOTH the top level and the nested
    Enhanced-multi-frame location, and to the TR actually used to generate/pace
    this series (not just copied from the reference) -- otherwise every file
    would keep silently claiming the reference DICOM's original TR regardless
    of --tr/demoStep. The top-level tag matters even though Enhanced MR IOD
    formally stores it nested: rt-cloud's own getDicomMetadata() (bidsCommon.py)
    only iterates top-level DICOM elements, so RepetitionTime is invisible to
    the live pipeline (MissingMetadataError) unless it's also present there."""
    import pydicom
    frames = mrt.pack_frames(np.clip(vol3d, 0, 65535).astype(np.uint16))
    ds = copy.deepcopy(template)
    ds.PixelData = frames.astype('<u2').tobytes()
    ds.InstanceNumber = int(instance)
    ds.AcquisitionNumber = int(instance)
    ds.SeriesNumber = int(run)
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.RepetitionTime = TR * 1000.0   # top-level: rt-cloud's getDicomMetadata() only reads this
    try:
        ds.SharedFunctionalGroupsSequence[0].MRTimingAndRelatedParametersSequence[0].RepetitionTime = TR * 1000.0
    except Exception:
        pass
    for grp in ds.PerFrameFunctionalGroupsSequence:
        fc = grp.FrameContentSequence[0]
        if hasattr(fc, 'TemporalPositionIndex'):
            fc.TemporalPositionIndex = int(instance)
        if hasattr(fc, 'DimensionIndexValues'):
            div = list(fc.DimensionIndexValues)
            div[-1] = int(instance)
            fc.DimensionIndexValues = div
    tmp = out_path + '.part'
    ds.save_as(tmp, write_like_original=False)             # write fully, then rename
    os.replace(tmp, out_path)                               # atomic -> watcher sees complete file


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mock DICOM scanner for RT-Cloud dataSource='dicom'.")
    ap.add_argument('--config', default=os.path.join(HERE, 'conf', 'taskActivation.toml'))
    ap.add_argument('--reference-dicom', default=DEFAULT_REFERENCE,
                    help='real (or template) DICOM to source geometry/TR from; '
                         'default is the bundled anonymized Enhanced multi-frame template')
    ap.add_argument('--source', default='synthetic',
                    help="'synthetic' (default) or a path to a 4D NIfTI")
    ap.add_argument('--out', default=None, help='output dicomDir (default: <cfg>/dicomDir or project dicomDir)')
    ap.add_argument('--run', type=int, default=None, help='run number (default from config runNum)')
    ap.add_argument('--tr', type=float, default=None,
                    help='seconds between volumes (default: reference DICOM TR, '
                         'or config demoStep if not "auto")')
    ap.add_argument('--nvols', type=int, default=None, help='override number of volumes')
    ap.add_argument('--start-index', type=int, default=1, help='first TR file index (project reads 1-based)')
    ap.add_argument('--no-delay', action='store_true', help='write all volumes immediately (for tests)')
    ap.add_argument('--clean', action='store_true', help='remove existing *.dcm in the output dir first')
    args = ap.parse_args(argv)

    cfg = load_cfg(args.config)

    try:
        import pydicom
    except Exception:
        print("[mock] pydicom is required (pip install pydicom)"); return 1
    template = pydicom.dcmread(args.reference_dicom)
    ref_info = mrt.dicom_header_info(args.reference_dicom)
    if not all(k in ref_info for k in ('rows', 'cols', 'nFrames')):
        print(f"[mock] {args.reference_dicom} is missing Rows/Columns/NumberOfFrames "
              "-> not a usable multi-frame reference"); return 1
    shape = (ref_info['rows'], ref_info['cols'], ref_info['nFrames'])

    demoStepCfg = str(cfg.get('demoStep', 'auto')).strip().lower()
    if args.tr is not None:
        TR = args.tr
    elif demoStepCfg != 'auto':
        TR = float(cfg.get('demoStep'))
    elif 'TR' in ref_info:
        TR = ref_info['TR']
    else:
        TR = 2.0
        print("[mock][warn] no --tr, no numeric demoStep, and the reference DICOM has "
              "no RepetitionTime -> falling back to TR=2.0s")

    run = args.run if args.run is not None else int(np.ravel(cfg.get('runNum', [1]))[0]) \
        if not isinstance(cfg.get('runNum', [1]), str) else 1
    pattern = str(cfg.get('dicomNamePattern', '001_{RUN:06d}_{TR:06d}.dcm'))
    min_size = int(cfg.get('minExpectedDicomSize', 300000))
    task = str(cfg.get('taskName', 'HcpMotor'))
    condA = str(cfg.get('glmCondA', 'left_hand'))
    condB = str(cfg.get('glmCondB', 'right_hand'))
    events_file = str(cfg.get('eventsFile', f'{task}_acq-ap_events.tsv'))
    out_dir = args.out or os.path.join(HERE, 'dicomDir')
    os.makedirs(out_dir, exist_ok=True)

    if args.clean:
        for f in os.listdir(out_dir):
            if f.endswith('.dcm') or f.endswith('.dcm.part'):
                os.remove(os.path.join(out_dir, f))

    print(f"[mock] reference: {os.path.basename(args.reference_dicom)}  "
          f"shape={shape} (rows,cols,slices)  TR={TR}s")

    # ---- build the volume series ----
    if args.source == 'synthetic':
        events = mrt.read_events_tsv(os.path.join(HERE, 'study_design', events_file))
        last = max(o + d for o, d, _ in events)
        nVols = args.nvols or int(np.ceil((last + 10) / TR))
        series, _ = synthetic_series(events, nVols, TR, condA, condB, shape)
        print(f"[mock] synthetic {task}: {nVols} vols, condA={condA} condB={condB}")
    else:
        series, _ = nifti_series(args.source, shape)
        nVols = args.nvols or series.shape[3]
        print(f"[mock] NIfTI replay: {args.source} -> {nVols} vols (resampled to {shape})")

    print(f"[mock] writing to {out_dir}  pattern={pattern}  run={run}  TR={TR}s"
          + ("  (no delay)" if args.no_delay else ""))
    for k in range(nVols):
        idx = args.start_index + k
        fname = pattern.format(RUN=run, SCAN=run, TR=idx)
        out_path = os.path.join(out_dir, fname)
        write_dicom(template, series[..., k], out_path, instance=idx, run=run, TR=TR)
        sz = os.path.getsize(out_path)
        if sz < min_size:
            print(f"[mock][warn] {fname} is {sz} B < minExpectedDicomSize {min_size}")
        print(f"[mock] vol {idx:3d}/{nVols}  ->  {fname} ({sz} B)")
        if not args.no_delay and k < nVols - 1:
            time.sleep(TR)
    print(f"[mock] done: {nVols} DICOMs in {out_dir}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
