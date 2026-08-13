"""-----------------------------------------------------------------------------
test_pipeline.py  —  offline end-to-end test of the NEW baseline / %-change /
first-block-ROI pipeline on the REAL ds000244 HcpMotor design.

Synthesizes a 4D series with the dataset's real event timing (from the shipped
events.tsv) and HRF-convolved activation in simulated left/right M1, then runs
the same analysis used live (rt_analysis helpers + the new logic):
  * baseline = first frames before the first event
  * % signal change from that baseline
  * ROI = peak %-change voxel of the FIRST event block
and checks the ROI lands on the first effector's region and its %-change trace
tracks that effector. Also covers the NIfTI replay source and the nilearn plot.

Run:  python test_pipeline.py
-----------------------------------------------------------------------------"""
import os
import numpy as np
import nibabel as nib
from scipy.ndimage import gaussian_filter
import rt_analysis as mrt
mrt.ensure_nilearn()

currPath = os.path.dirname(os.path.realpath(__file__))
liveDir = os.path.join(currPath, '_test_live')
os.makedirs(liveDir, exist_ok=True)

TR = 2.0; hrf_delay = 2; roiRadius = 4; mapThreshPct = 0.5
events = mrt.read_events_tsv(os.path.join(currPath, 'study_design', 'HcpMotor_acq-ap_events.tsv'))
last = max(o + d for o, d, _ in events)
nVols = int(np.ceil((last + 10) / TR))
design = mrt.build_design_from_events(events, nVols, TR, hrf_delay)

# first event block + baseline length (effector-agnostic)
firstOnset, firstOffset, firstLabel = mrt.first_event_window(events)
baselineN = max(1, int(firstOnset // TR))
firstBlockVols = set(v for v in range(1, nVols + 1)
                     if firstOnset <= ((v - 1) - hrf_delay) * TR < firstOffset)
print(f"nVols={nVols}  first block='{firstLabel}' {firstOnset:.1f}-{firstOffset:.1f}s  baselineN={baselineN}")
assert firstLabel == 'left_hand', firstLabel   # HcpMotor starts with left hand

# ---- synthetic geometry: +x = right hemisphere ----
shape = (48, 56, 40); vox = 2.5
affine = np.diag([vox, vox, vox, 1.0]); affine[:3, 3] = [-vox*shape[0]/2, -vox*shape[1]/2, -vox*shape[2]/2]
cx = shape[0] // 2
brain = np.zeros(shape, bool); brain[6:42, 6:50, 4:36] = True
rM1 = np.zeros(shape, bool); rM1[cx+8:cx+12, 30:34, 22:26] = True   # LEFT hand -> right hemi
lM1 = np.zeros(shape, bool); lM1[cx-12:cx-8, 30:34, 22:26] = True   # RIGHT hand -> left hemi

def boxcar(types):
    b = np.zeros(nVols)
    for v in range(nVols):
        t = v * TR
        for o, d, tt in events:
            if tt in types and o <= t < o + d:
                b[v] = 1; break
    return b

from math import gamma
tk = np.arange(0, 32, TR)
hrf = ((1**6)*(tk**5)*np.exp(-tk)/gamma(6)) - 0.35*((1**16)*(tk**15)*np.exp(-tk)/gamma(16))
hrf /= hrf.max()
bl = np.convolve(boxcar(('left_hand',)), hrf)[:nVols]; bl /= bl.max()+1e-9
br = np.convolve(boxcar(('right_hand',)), hrf)[:nVols]; br /= br.max()+1e-9
rng = np.random.default_rng(0); BASE = 1000.0

def make_volume(v):
    vol = BASE + rng.normal(0, 8, shape) + 0.04*BASE*bl[v]*rM1 + 0.04*BASE*br[v]*lM1
    return gaussian_filter(vol*brain, 1.2) * brain

# ---- run the NEW analysis loop (mirrors taskActivation.py) ----
# sbref mask: write a synthetic sbref next to a fake bold and mask from it
sbref3d = make_volume(0)
boldP = os.path.join(liveDir, 'sub-01_ses-03_task-HcpMotor_acq-ap_bold.nii.gz')
sbrefP = mrt.sbref_path_for(boldP)
nib.save(nib.Nifti1Image(sbref3d.astype(np.float32), affine), sbrefP)
sb_mask, sb_img = mrt.mask_from_sbref(sbrefP)
bmask = (sb_mask.flatten() if sb_mask is not None else mrt.compute_brain_mask(make_volume(0)).flatten())
ref3d = sbref3d; mrt.write_reference(liveDir, ref3d, affine)
baseline_sum = None; baseline_mean = None
fb_sum = None; fb_n = 0; roi = None; roi_peak = None
Xglm, glm_names = mrt.make_glm_design(events, nVols, TR, drift_order=1)
mask_idx = np.where(bmask)[0]; Yglm = np.zeros((nVols, mask_idx.size), np.float32)
motion_rows = []
roi_tr = []; glob_tr = []; cond_tr = []
last_contrast = None; last_condlabel = None
for vol in range(1, nVols + 1):
    cond = int(design[(vol-1)-hrf_delay]) if (vol-1-hrf_delay) >= 0 else 3
    img = make_volume(vol-1).flatten() * bmask
    Yglm[vol-1] = img[mask_idx]
    motion_rows.append([vol, 0.001*vol, 0.0, 0.0, 0.02*np.sin(vol/5.0), 0.0, 0.0])  # synthetic motion
    if vol <= baselineN:
        baseline_sum = img.copy() if baseline_sum is None else baseline_sum + img
        if vol == baselineN: baseline_mean = baseline_sum / baselineN
    if baseline_mean is not None:
        psc = mrt.percent_change(img, baseline_mean, bmask); psc3d = psc.reshape(shape)
        if vol in firstBlockVols:
            fb_sum = psc.copy() if fb_sum is None else fb_sum + psc; fb_n += 1
        if roi is None and fb_n > 0 and vol >= max(firstBlockVols):
            roi_peak = mrt.peak_voxel((fb_sum/fb_n).reshape(shape), bmask.reshape(shape))
            roi = mrt.sphere_roi(shape, roi_peak, roiRadius).flatten() & bmask
        roi_psc = float(psc[roi].mean()) if (roi is not None and roi.sum() > 0) else 0.0
        glob = float(psc[bmask].max())
        if roi_peak is not None:
            rp = mrt.peak_voxel(psc3d, bmask.reshape(shape))
            center = roi_peak if psc3d[rp] < mapThreshPct else rp
            contrast3d = None
            cpct = mrt.glm_beta_contrast(Xglm[:vol], Yglm[:vol], glm_names)
            if cpct is not None:
                flat = np.zeros(bmask.size, np.float32); flat[mask_idx] = cpct
                contrast3d = flat.reshape(shape); last_contrast = contrast3d
            last_condlabel = mrt.active_condition_label(events, ((vol-1)-hrf_delay)*TR)
            if vol % 15 == 0 or vol == nVols:     # render PNG sparsely to keep the test fast
                mrt.write_live_update(liveDir, 1, vol, 'task', psc3d, ref3d, affine, center,
                                      mapThreshPct, roi_tr+[roi_psc], glob_tr+[glob], cond_tr+[cond],
                                      caption='% change from baseline', condLabel=last_condlabel,
                                      contrast3d=contrast3d, contrast_thresh=0.4,
                                      traceALabel=f'ROI ({firstLabel})', traceBLabel='peak')
    else:
        roi_psc = 0.0; glob = 0.0
    roi_tr.append(roi_psc); glob_tr.append(glob); cond_tr.append(cond)
mrt.write_motion(liveDir, motion_rows)
mrt.write_motion_png(liveDir, motion_rows, TR=TR)
mrt.write_motion_png(liveDir, motion_rows, TR=TR)

roi_tr = np.array(roi_tr); cond_tr = np.array(cond_tr)

# ---- checks ----
checks = {}
checks['first_block_is_left_hand'] = (firstLabel == 'left_hand')
checks['baseline_before_first_event'] = baselineN >= 1 and baselineN*TR <= firstOnset
checks['baseline_frozen'] = baseline_mean is not None
checks['roi_localized'] = roi_peak is not None
# first block = left hand -> ROI should sit in the RIGHT-hemisphere cluster
checks['roi_in_first_effector_region'] = roi_peak is not None and rM1[roi_peak]
checks['roi_right_hemisphere'] = roi_peak is not None and roi_peak[0] > cx
# ROI %change should be high during left_hand blocks (cond==1), ~0 in rest (cond==0)
checks['roi_psc_tracks_first_effector'] = (
    roi_tr[cond_tr == 1].mean() > max(0.2, 3 * abs(roi_tr[cond_tr == 0].mean())))
checks['roi_psc_low_in_rest'] = abs(roi_tr[cond_tr == 0].mean()) < 0.3
checks['sbref_mask_used'] = sb_mask is not None and int(bmask.sum()) > 100
checks['sbref_path_builder'] = mrt.sbref_path_for('/x/sub-01_task-X_bold.nii.gz') == '/x/sub-01_task-X_sbref.nii.gz'
# mask dispatcher: BET requested but absent in sandbox -> must fall back gracefully
_mflat, _msrc = mrt.make_brain_mask(sbrefP, sbref3d, affine, shape, method='bet')
checks['mask_dispatch_falls_back'] = _msrc in ('bet', 'epi', 'threshold') and 0.02 < _mflat.mean() < 0.8
checks['condition_label_left_hand'] = ('left hand' in [
    mrt.active_condition_label(events, t) for t in np.arange(0, last, 1.0)])
checks['condition_label_rest'] = mrt.active_condition_label(events, 0.0) == 'REST'
# cumulative L vs R contrast: left-hand region (right hemi) should be the positive peak
checks['glm_design_has_hand_regressors'] = ('left_hand' in glm_names and 'right_hand' in glm_names
                                            and 'intercept' in glm_names)
checks['glm_contrast_computed'] = last_contrast is not None
if last_contrast is not None:
    cpk = np.unravel_index(int(np.nanargmax(last_contrast)), last_contrast.shape)  # most LEFT>RIGHT
    checks['glm_contrast_left_gt_right_in_right_hemi'] = cpk[0] > cx and rM1[cpk]
else:
    checks['glm_contrast_left_gt_right_in_right_hemi'] = False
# z-scored output: full-run contrast over brain voxels ~ mean 0, std 1
_zc = mrt.glm_beta_contrast(Xglm, Yglm, glm_names, condA='left_hand', condB='right_hand', zscore=True)
checks['glm_output_zscored'] = (_zc is not None and abs(float(_zc.mean())) < 0.05
                                and abs(float(_zc.std()) - 1.0) < 0.05)
# single-condition beta weight (condB empty) -> still a map, peaks in right hemi for left_hand
_bw = mrt.glm_beta_contrast(Xglm, Yglm, glm_names, condA='left_hand', condB=None, zscore=True)
_bwmap = np.zeros(bmask.size, np.float32); _bwmap[mask_idx] = _bw; _bwmap = _bwmap.reshape(shape)
checks['glm_betaweight_single_condition'] = (_bw is not None
        and rM1[np.unravel_index(int(np.nanargmax(_bwmap)), shape)])
# end-of-run peak-voxel measured-vs-HRF-predicted traces
_vt = mrt.glm_voxel_traces(Xglm, Yglm, glm_names, mask_idx, shape, TR,
                           ['left_hand', 'right_hand'], events)
checks['voxel_traces_built'] = (len(_vt) == 2 and all(len(t['measured']) == nVols for t in _vt)
                                and all(len(t['blocks']) > 0 for t in _vt))
checks['voxel_trace_fits_hrf'] = all(
    np.corrcoef(t['measured'], t['predicted'])[0, 1] > 0.8 for t in _vt)
# motion: par reader + motion.tsv written with all volumes
np.savetxt('/tmp/_t.par', np.array([[0.01, 0.0, 0.0, 0.5, 0.0, 0.0]]))
checks['motion_par_read'] = mrt.read_mcflirt_par('/tmp/_t.par') == [0.01, 0.0, 0.0, 0.5, 0.0, 0.0]
_mt = os.path.join(liveDir, 'motion.tsv')
checks['motion_tsv_written'] = os.path.exists(_mt) and sum(1 for _ in open(_mt)) == nVols + 1
_md = np.genfromtxt(_mt, names=True, delimiter='\t')
checks['motion_tsv_has_time'] = ('time_s' in _md.dtype.names
                                 and abs(float(_md['time_s'][1]) - 2 * TR) < 1e-6)
checks['motion_png_written'] = os.path.exists(os.path.join(liveDir, 'motion.png'))
checks['motion_png_written'] = os.path.exists(os.path.join(liveDir, 'motion.png'))
checks['contrast_in_bundle'] = False
checks['condlabel_in_bundle'] = False
try:
    _latest = open(os.path.join(liveDir, 'latest.txt')).read().strip()
    _b = np.load(os.path.join(liveDir, _latest))
    checks['contrast_in_bundle'] = 'contrast' in _b.files
    checks['condlabel_in_bundle'] = str(_b['condLabel']) != ''
except Exception as e:
    print('bundle check error:', e)

checks['percent_change_sign'] = mrt.percent_change(np.array([110.0]), np.array([100.0]),
                                                   np.array([True]))[0] == 10.0
checks['nilearn_png_written'] = os.path.exists(os.path.join(liveDir, 'current.png')) and \
    os.path.getsize(os.path.join(liveDir, 'current.png')) > 5000
checks['live_bundles_written'] = len([f for f in os.listdir(liveDir) if f.startswith('live_')]) > 0

# NIfTI replay source
_v4 = np.stack([make_volume(v) for v in range(8)], axis=-1)
_p = os.path.join(liveDir, '_synthetic_bold.nii.gz'); nib.save(nib.Nifti1Image(_v4.astype(np.float32), affine), _p)
_src = mrt.NiftiReplaySource(_p)
checks['nifti_replay_numvols'] = _src.numVolumes == 8
checks['nifti_replay_volume_matches'] = np.allclose(np.asarray(_src.get_volume(3).dataobj), _v4[..., 3], atol=1e-3)

print("\n==== CHECKS ====")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
print(f"\nROI peak {roi_peak} (right-hemi i>{cx}); ROI %ΔS  left-blocks={roi_tr[cond_tr==1].mean():+.2f}  "
      f"rest={roi_tr[cond_tr==0].mean():+.2f}")
allpass = all(checks.values())
print("\nRESULT:", "ALL PASS" if allpass else "SEE FAILURES ABOVE")
import sys; sys.exit(0 if allpass else 1)
