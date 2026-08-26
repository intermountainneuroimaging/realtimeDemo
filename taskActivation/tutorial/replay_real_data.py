#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
replay_real_data.py -- runs the SAME analysis taskActivation.py does live
(baseline-average brain masking, mcflirt motion correction, fslmaths
smoothing, incremental GLM, ROI localization, live plotting) against a REAL
downloaded OpenNeuro ds000244 BOLD run, offline -- no scanner, no Docker, no
rt-cloud.

Unlike test_pipeline.py / test_generalize.py (synthetic activation injected
into simulated geometry, for a fast no-download correctness check), this
downloads (once, then cached) and processes an ACTUAL real fMRI run, so
outDir/live/current.png shows real recovered brain activation, not synthetic.

Needs:
  - FSL (mcflirt/fslmaths) on PATH -- the same tools taskActivation.py calls,
    normally present in the brainiak/rtcloud image; install locally otherwise.
  - awscli + network access for the first download (see
    tutorial/README.md / INSTALLATION.md) -- cached after that.
  - nilearn (installed automatically on first run, like taskActivation.py).

Run:
    python replay_real_data.py                    # HcpMotor (default)
    python replay_real_data.py --task HcpGambling
-----------------------------------------------------------------------------"""
import os
import sys
import shutil
import argparse
import tempfile
from subprocess import call
import numpy as np
import nibabel as nib

HERE = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.append(os.path.join(PROJECT_ROOT, 'utils'))
sys.path.append(HERE)
import rt_analysis as mrt
import hcp_replay as hcp
mrt.ensure_nilearn()

TASKS = {
    'HcpMotor': dict(events_path=os.path.join(PROJECT_ROOT, 'study_design',
                                              'HcpMotor_acq-ap_events.tsv'),
                     condA='left_hand', condB='right_hand'),
    'HcpGambling': dict(events_path=os.path.join(HERE, 'study_design',
                                                 'HcpGambling_acq-ap_events.tsv'),
                        condA='reward', condB='punishment'),
}


def main():
    ap = argparse.ArgumentParser(
        description='Replay a real OpenNeuro ds000244 BOLD run through the live analysis '
                    'pipeline, offline (no scanner/Docker/rt-cloud).')
    ap.add_argument('--task', choices=sorted(TASKS), default='HcpMotor')
    ap.add_argument('--subject', default='01')
    ap.add_argument('--session', default='03')
    ap.add_argument('--acquisition', default='ap')
    ap.add_argument('--ds', default='ds000244')
    ap.add_argument('--cache-dir', default=os.path.join(HERE, 'openneuro_cache'))
    ap.add_argument('--out-dir', default=os.path.join(HERE, '_real_data_live'))
    ap.add_argument('--fwhm', type=float, default=5.0, help='smoothing FWHM (mm)')
    ap.add_argument('--hrf-delay', type=int, default=2, help='hemodynamic lag, in volumes')
    ap.add_argument('--mask-method', default='bet', choices=['bet', 'epi', 'threshold'])
    ap.add_argument('--mask-frac', type=float, default=0.35)
    ap.add_argument('--mask-fraction', type=float, default=0.12)
    ap.add_argument('--mask-percentile', type=float, default=98)
    ap.add_argument('--map-thresh-pct', type=float, default=0.5)
    ap.add_argument('--contrast-thresh', type=float, default=2.0)
    ap.add_argument('--live-every', type=int, default=5, help='write current.png every N volumes')
    ap.add_argument('--save-gif', action='store_true', help='also build activation_run1.gif at the end')
    args = ap.parse_args()

    cfg = TASKS[args.task]
    events = mrt.read_events_tsv(cfg['events_path'])
    glmCondA, glmCondB = cfg['condA'], cfg['condB']

    print(f"[replay] downloading/locating real {args.task} BOLD (first run downloads ~600MB "
          "-- cached after that)...")
    boldPath = hcp.ensure_openneuro_bold(args.cache_dir, args.ds, args.subject, args.session,
                                         args.task, args.acquisition)
    src = hcp.NiftiReplaySource(boldPath)
    nVols = src.numVolumes
    TR = float(nib.load(boldPath).header.get_zooms()[3])   # real TR, from the NIfTI header itself
    print(f"[replay] {boldPath}\n[replay] {nVols} volumes, TR={TR:g}s")

    hrf_delay = args.hrf_delay
    liveDir = args.out_dir
    os.makedirs(liveDir, exist_ok=True)
    tmpPath = tempfile.mkdtemp(prefix='replay_real_')

    design = mrt.build_design_from_events(events, nVols, TR, hrf_delay,
                                          condA_types=[glmCondA], condB_types=[glmCondB])
    cls = mrt.classify_conditions(events, condA=glmCondA, condB=glmCondB)
    print(f"[replay] Conditions -> interest: {cls['interest']} | covariates: {cls['covariates']} "
          f"| rest(implicit): {cls['rest'] or 'gaps only'}")
    Xglm, glm_names = mrt.make_glm_design(events, nVols, TR, drift_order=1)
    print(f"[replay] GLM regressors: {glm_names}")
    conds = [glmCondA, glmCondB]

    interest_set = set(cls['interest']) or None
    fe = mrt.first_event_window(events, include_types=interest_set)
    if fe is None:
        raise RuntimeError("No conditions of interest found to define the first block.")
    firstOnset, firstOffset, firstLabel = fe
    non_rest_onsets = [o for o, _, tt in events if not mrt.is_rest_type(tt)]
    first_any_onset = min(non_rest_onsets) if non_rest_onsets else min(o for o, _, _ in events)
    baselineN = max(1, int(first_any_onset // TR))
    firstBlockVols = set(v for v in range(1, nVols + 1)
                         if firstOnset <= ((v - 1) - hrf_delay) * TR < firstOffset)
    lastFirstBlockVol = max(firstBlockVols) if firstBlockVols else baselineN + 6
    print(f"[replay] baseline={baselineN} volumes; first block '{firstLabel}' "
          f"{firstOnset:.1f}-{firstOffset:.1f}s")

    glmLabel = (f"{glmCondA} vs {glmCondB} GLM contrast (z): red {glmCondA}>{glmCondB} / "
               f"blue {glmCondB}>{glmCondA}")
    fullXlim = (0.0, max((nVols - 1) * TR, TR))

    # ---- running state (mirrors taskActivation.py's own loop exactly) ----
    brain_mask_flat = None; vol_shape = None; ref3d = None; affine = None
    pre_baseline_imgs = []; baseline_mean = None
    fb_sum = None; fb_n = 0; Yglm = None; mask_idx = None
    motion_rows = []; roi_peak = None
    roi_trace, glob_trace, cond_trace = [], [], []
    center = None; contrast3d = None; condLabel = ''; psc3d = None
    point_idx = -1

    try:
        for vol in range(1, nVols + 1):
            cond = int(design[(vol - 1) - hrf_delay]) if (vol - 1 - hrf_delay) >= 0 else mrt.IGNORE
            print(f'--- {args.task} | vol {vol}/{nVols} | cond {cond} ---')
            niftiObject = src.get_volume(vol - 1)

            if vol == 1:
                nib.save(niftiObject, tmpPath + "/funcRef.nii")
                ref_img = nib.load(tmpPath + "/funcRef.nii")
                affine = ref_img.affine; vol_shape = ref_img.shape

            # ---- preprocess: motion correct -> smooth (identical to taskActivation.py) ----
            nib.save(niftiObject, tmpPath + "/temp.nii")
            call(f"mcflirt -in {tmpPath}/temp.nii -reffile {tmpPath}/funcRef.nii "
                f"-out {tmpPath}/temp_mc -plots", shell=True)
            par = mrt.read_mcflirt_par(tmpPath + "/temp_mc.par")
            motion_rows.append([vol] + par)
            mrt.write_motion(liveDir, motion_rows, TR=TR)
            mrt.write_motion_png(liveDir, motion_rows, TR=TR, nVols=nVols)
            call(f'fslmaths {tmpPath}/temp_mc -kernel gauss {args.fwhm/2.3548} -fmean {tmpPath}/temp_sm',
                shell=True)
            img_flat_raw = nib.load(tmpPath + '/temp_sm.nii.gz').get_fdata().astype(np.float32).flatten()

            # ---- brain mask from the baseline average (same as taskActivation.py) ----
            if vol <= baselineN:
                pre_baseline_imgs.append(img_flat_raw)
            if vol == baselineN:
                baseline_mean_full = np.mean(pre_baseline_imgs, axis=0)
                baselineP = tmpPath + "/baselineRef.nii"
                nib.save(nib.Nifti1Image(baseline_mean_full.reshape(vol_shape).astype(np.float32), affine),
                        baselineP)
                brain_mask_flat, mask_method = mrt.make_brain_mask(
                    baselineP, baseline_mean_full.reshape(vol_shape), affine, vol_shape,
                    method=args.mask_method, frac=args.mask_frac, maskFraction=args.mask_fraction,
                    maskPercentile=args.mask_percentile, work_dir=tmpPath)
                frac = 100.0 * brain_mask_flat.mean()
                print(f"[replay] Brain mask: {mask_method} -> {int(brain_mask_flat.sum())} voxels "
                    f"({frac:.1f}% of FOV)")
                ref3d = (baseline_mean_full * brain_mask_flat).reshape(vol_shape)
                mrt.write_reference(liveDir, ref3d, affine)
                mask_idx = np.where(brain_mask_flat)[0]
                Yglm = np.zeros((nVols, mask_idx.size), np.float32)
                for i, raw in enumerate(pre_baseline_imgs):
                    Yglm[i] = (raw * brain_mask_flat)[mask_idx]
                baseline_mean = baseline_mean_full * brain_mask_flat
                print(f"[replay] Baseline image frozen from the first {baselineN} volumes.")

            if brain_mask_flat is not None:
                img_flat = img_flat_raw * brain_mask_flat
                if vol > baselineN:
                    Yglm[vol - 1] = img_flat[mask_idx]

            # ---- % signal change, ROI, incremental GLM, live plot ----
            if baseline_mean is not None:
                psc = mrt.percent_change(img_flat, baseline_mean, brain_mask_flat)
                psc3d = psc.reshape(vol_shape)
                if vol in firstBlockVols:
                    fb_sum = psc.copy() if fb_sum is None else fb_sum + psc
                    fb_n += 1
                if roi_peak is None and fb_n > 0 and vol >= lastFirstBlockVol:
                    fb_mean = (fb_sum / fb_n).reshape(vol_shape)
                    roi_peak = mrt.peak_voxel(fb_mean, brain_mask_flat.reshape(vol_shape))
                    print(f"[replay] ROI = peak %change voxel of first '{firstLabel}' block @ {roi_peak}")
                roi_psc = float(psc3d[roi_peak]) if roi_peak is not None else 0.0
                glob_psc = float(psc[brain_mask_flat].max()) if brain_mask_flat.any() else 0.0
            else:
                psc3d = None; roi_psc = 0.0; glob_psc = 0.0

            roi_trace.append(roi_psc); glob_trace.append(glob_psc); cond_trace.append(cond)
            point_idx += 1

            if psc3d is not None and (point_idx % args.live_every) == 0 and ref3d is not None:
                running_peak = mrt.peak_voxel(psc3d, brain_mask_flat.reshape(vol_shape))
                center = roi_peak if (roi_peak is not None and psc3d[running_peak] < args.map_thresh_pct) \
                    else running_peak
                contrast3d = None
                if Yglm is not None:
                    cpct = mrt.glm_beta_contrast(Xglm[:vol], Yglm[:vol], glm_names,
                                                condA=glmCondA, condB=glmCondB, zscore=True)
                    if cpct is not None:
                        flat = np.zeros(brain_mask_flat.size, np.float32)
                        flat[mask_idx] = cpct
                        contrast3d = flat.reshape(vol_shape)
                condLabel = mrt.active_condition_label(events, ((vol - 1) - hrf_delay) * TR)
                vtraces = []
                if Yglm is not None and vol >= Xglm.shape[1] + 2:
                    vtraces = mrt.glm_voxel_traces(Xglm[:vol], Yglm[:vol], glm_names, mask_idx,
                                                   vol_shape, TR, conds, events)
                mrt.write_live_update(
                    liveDir, 1, vol, args.task, psc3d, ref3d, affine, center, args.map_thresh_pct,
                    roi_trace, glob_trace, cond_trace,
                    condAName='ROI %ΔS', condBName='peak %ΔS',
                    caption='% change from baseline (red: increase, blue: decrease)',
                    traceALabel=f'ROI ({firstLabel}) %ΔS', traceBLabel='whole-brain peak %ΔS',
                    contrast3d=contrast3d, contrast_thresh=args.contrast_thresh, condLabel=condLabel,
                    n_slices=6, contrast_label=glmLabel, voxel_traces=vtraces, full_xlim=fullXlim)
    finally:
        shutil.rmtree(tmpPath, ignore_errors=True)

    # ---- guaranteed final peak-voxel plot using the complete series ----
    try:
        vtraces = mrt.glm_voxel_traces(Xglm, Yglm, glm_names, mask_idx, vol_shape, TR, conds, events)
        if vtraces and psc3d is not None and center is not None:
            mrt.write_live_update(
                liveDir, 1, nVols, args.task, psc3d, ref3d, affine, center, args.map_thresh_pct,
                roi_trace, glob_trace, cond_trace,
                condAName='ROI %ΔS', condBName='peak %ΔS',
                caption='% change from baseline (red: increase, blue: decrease)',
                traceALabel=f'ROI ({firstLabel}) %ΔS', traceBLabel='whole-brain peak %ΔS',
                contrast3d=contrast3d, contrast_thresh=args.contrast_thresh, condLabel=condLabel,
                n_slices=6, contrast_label=glmLabel, voxel_traces=vtraces, full_xlim=fullXlim)
    except Exception as e:
        print(f"[replay] final trace plot skipped: {e}")

    if args.save_gif:
        try:
            gifPath = mrt.build_activation_gif(liveDir, 1)
            if gifPath:
                print(f"[replay] activation GIF saved to {gifPath}")
        except Exception as e:
            print(f"[replay] activation GIF skipped: {e}")

    print(f"\n[replay] done -- see {liveDir}/current.png (+ motion.png)")


if __name__ == '__main__':
    main()
