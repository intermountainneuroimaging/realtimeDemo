"""-----------------------------------------------------------------------------
test_recap.py — offline test of the end-of-run recap image (--recap).

Builds a synthetic run on the MNI152 template (real event timing from a task's
own events file, HRF-convolved activation injected at known voxels), then runs
the same steps taskActivation.py's --recap path runs at the end of a run:
  * the participant's screens come from rt_analysis.stim_panels_for(),
  * the recap is rendered by nilearn_stat_png() / write_live_update_3way()
    with a `header` -- the SAME functions current.png uses, so the overlay and
    trace rows can't drift apart from the live view.
and confirms:
  * every task with a stimulus strip has all its snapshots on disk,
  * the recap is the live plot's layout plus exactly the header band (the
    brain/trace block keeps its proportions), for both the single-contrast and
    the 3-way (checkerboard_3cond) renderers,
  * the header only changes the top band -- the plot region below it is
    pixel-identical to the same plot rendered without a header,
  * write_live_update(bundle=False) writes just the PNG (no .npz / latest.txt,
    which --recap must not leave behind), and bundle=True still writes them,
  * copy_png_atomic() copies and reports failure instead of raising,
  * read_mcflirt_par_all() reads every row of a whole-series mcflirt .par, and those rows
    give the single motion.tsv / motion.png that --recap's batch mode writes.
(The batch pass itself -- 4D mcflirt, smoothing, mask, GLM -- needs FSL, so it is exercised
by running --recap in the container; see README.)
Needs nilearn/matplotlib (no FSL, DICOMs, Docker or scanner).

Run:  python testing/test_recap.py
-----------------------------------------------------------------------------"""
import os
import sys
import shutil
import tempfile
import warnings
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.realpath(__file__))           # testing/
PROJECT_ROOT = os.path.dirname(HERE)                          # taskActivation/
sys.path.append(os.path.join(PROJECT_ROOT, 'utils'))
import rt_analysis as mrt
warnings.filterwarnings('ignore')
mrt.ensure_nilearn()

SNAP_ROOT = os.path.join(PROJECT_ROOT, 'templates', 'stimulus_snapshots')
DPI, HDR_IN = 110, 1.2
TR = 2.0
tmp = tempfile.mkdtemp(prefix='recap_')

# ---- a small synthetic brain: the MNI152 template at 4 mm, brain-masked
from nilearn import datasets
tpl = datasets.load_mni152_template(resolution=4)
ref3d = np.asarray(tpl.get_fdata(), np.float32)
affine = tpl.affine
shape = ref3d.shape
mask3d = ref3d > 0.35 * ref3d.max()
mask_idx = np.where(mask3d.ravel())[0]
ijk = np.array(np.unravel_index(mask_idx, shape)).T
rng = np.random.default_rng(0)


def embed(m):
    flat = np.zeros(mask3d.size, np.float32)
    flat[mask_idx] = m
    return flat.reshape(shape)


def synth(events_file, conds, centers):
    events = mrt.read_events_tsv(os.path.join(PROJECT_ROOT, 'study_design', events_file))
    nvols = int(np.ceil(max(o + d for o, d, _ in events) / TR))
    X, names = mrt.make_glm_design(events, nvols, TR, drift_order=1)
    Y = 1000 + rng.normal(0, 8, (nvols, mask_idx.size)).astype(np.float32)
    for cond, c in zip(conds, centers):
        d = np.linalg.norm(ijk - np.array(c), axis=1)
        Y += np.outer(X[:, names.index(cond)], 60 * np.exp(-(d / 4.0) ** 2))
    return events, nvols, X, names, Y


def image_size(path):
    with Image.open(path) as im:
        return im.size


checks = {}

# ---- stimulus strips: every task has one, and every snapshot exists
missing = []
for task in mrt.STIM_PANELS:
    got = mrt.stim_panels_for(task, SNAP_ROOT, strict=True)      # raises if a snapshot is missing
    if len(got) != len(mrt.STIM_PANELS[task]):
        missing.append(task)
checks['all_tasks_have_their_snapshots'] = not missing
checks['unknown_task_has_no_strip'] = mrt.stim_panels_for('taskActivation', SNAP_ROOT) == []
cc = mrt.stim_panels_for('checkerboard_2cond', SNAP_ROOT, {'left': 'tab:red', 'right': 'tab:blue'})
checks['condition_screens_take_trace_colours'] = (
    [p['color'] for p in cc] == ['#aaaaaa', 'tab:red', 'tab:blue'])
# a task whose snapshots are missing degrades to a shorter strip instead of failing the run
checks['missing_snapshot_is_skipped_not_fatal'] = mrt.stim_panels_for('motor', tmp) == []
try:
    mrt.stim_panels_for('motor', tmp, strict=True)
    checks['strict_raises_on_missing_snapshot'] = False
except FileNotFoundError:
    checks['strict_raises_on_missing_snapshot'] = True

# ---- single-contrast recap (checkerboard_2cond)
events, nvols, X, names, Y = synth('Checkerboard2Cond_events.tsv', ['left', 'right'],
                                   [(28, 14, 12), (18, 14, 12)])
traces = mrt.glm_voxel_traces(X, Y, names, mask_idx, shape, TR, ['left', 'right'], events)
contrast = embed(mrt.glm_beta_contrast(X, Y, names, condA='left', condB='right', zscore=True))
zcuts = mrt.parse_float_list('-36,-22.75,-9.5,3.75,17')
psc3d = np.zeros(shape, np.float32)
header = dict(badge='RUN RECAP -- run 9', title='checkerboard LEFT vs RIGHT',
              subtitle=f'{nvols} volumes at TR {TR:g} s',
              stim_panels=cc, stim_caption='Shown to the participant')
kw = dict(peak=(20, 20, 20), contrast3d=contrast, contrast_thresh=2.0, z_cuts=zcuts,
          voxel_traces=traces, full_xlim=(0, (nvols - 1) * TR))
live_png, recap_png = os.path.join(tmp, 'live.png'), os.path.join(tmp, 'recap.png')
ok_live = mrt.nilearn_stat_png(live_png, psc3d, ref3d, affine, 0.5, 't', **kw)   # no frame stamp: recaps have none
ok_recap = mrt.nilearn_stat_png(recap_png, psc3d, ref3d, affine, 0.5, 't', header=header, **kw)
lw, lh = image_size(live_png)
rw, rh = image_size(recap_png)
checks['recap_rendered'] = bool(ok_live and ok_recap)
checks['recap_is_live_plus_header_band'] = (rw == lw) and (rh - lh == round(HDR_IN * DPI))

# the plot below the header band is the same picture as the header-less one. Skip the top
# STRIP_OVERHANG_PX rows of it: the participant-screen thumbnails (and their labels) are taller
# than the band and overhang into the empty space above the brain slices -- by design, as in the
# pre-data templates.
STRIP_OVERHANG_PX = 80
band = round(HDR_IN * DPI)
a = np.asarray(Image.open(live_png).convert('RGB')).astype(int)
b = np.asarray(Image.open(recap_png).convert('RGB')).astype(int)[band:]
diff = np.abs(a - b).max(axis=2)[STRIP_OVERHANG_PX:]
checks['plot_region_unchanged_by_header'] = int((diff > 8).sum()) == 0
top = np.asarray(Image.open(recap_png).convert('RGB'))[:band]
checks['header_band_has_content'] = int((top.max(axis=2) > 60).sum()) > 2000

# ---- 3-way recap (checkerboard_3cond)
c3 = ['center', 'left', 'right']
events3, nvols3, X3, names3, Y3 = synth('Checkerboard3Cond_events.tsv', c3,
                                        [(23, 8, 12), (28, 14, 12), (18, 14, 12)])
traces3 = mrt.glm_voxel_traces(X3, Y3, names3, mask_idx, shape, TR, c3, events3,
                               colors=['tab:blue', 'tab:red', 'tab:green'])
maps = tuple(embed(mrt.glm_beta_contrast_one_vs_rest(
    X3, Y3, names3, c, [o for o in c3 if o != c], zscore=True)) for c in c3)
h3 = dict(header, stim_panels=mrt.stim_panels_for('checkerboard_3cond', SNAP_ROOT))
d3 = os.path.join(tmp, 'three')
kw3 = dict(maps=maps, labels=tuple(c3), colors=('Blues', 'Reds', 'Greens'), thresh=2.0,
           z_cuts=zcuts, voxel_traces=traces3, full_xlim=(0, (nvols3 - 1) * TR))
mrt.write_live_update_3way(d3, 11, nvols3, 'task', ref3d, affine, **kw3)
w0, h0 = image_size(os.path.join(d3, 'current.png'))
mrt.write_live_update_3way(d3, 11, nvols3, 'task', ref3d, affine, header=h3, **kw3)
w1, h1 = image_size(os.path.join(d3, 'current.png'))
checks['recap_3way_is_live_plus_header_band'] = (w1 == w0) and (h1 - h0 == round(HDR_IN * DPI))

# ---- bundle=False writes the PNG only; the default still writes the replay bundle
d_nb, d_b = os.path.join(tmp, 'nobundle'), os.path.join(tmp, 'bundle')
common = dict(zmap3d=psc3d, ref3d=ref3d, affine=affine, peak=(20, 20, 20), thresh=0.5,
              A_trace=[0.0], B_trace=[0.0], cond_trace=[0], contrast3d=contrast,
              z_cuts=zcuts, voxel_traces=traces, full_xlim=(0, 100))
mrt.write_live_update(d_nb, 9, 1, 'task', header=header, bundle=False, **common)
mrt.write_live_update(d_b, 9, 1, 'task', **common)
checks['bundle_false_writes_png_only'] = sorted(os.listdir(d_nb)) == ['current.png']
checks['bundle_true_still_writes_bundle'] = sorted(os.listdir(d_b)) == [
    'current.png', 'latest.txt', 'live_run9_vol001.npz']

# ---- copy_png_atomic
dest = os.path.join(tmp, 'recaps', 'recap_x_run9.png')
checks['copy_png_creates_folder_and_copies'] = (
    mrt.copy_png_atomic(recap_png, dest) and open(dest, 'rb').read() == open(recap_png, 'rb').read())
checks['copy_png_reports_failure_not_raise'] = (
    mrt.copy_png_atomic(os.path.join(tmp, 'nope.png'), os.path.join(tmp, 'x.png')) is False)

# ---- --recap's one-shot motion output: a whole-series mcflirt .par -> motion rows -> motion.tsv/.png
par = os.path.join(tmp, 'series.par')
rng2 = np.random.default_rng(1)
par_rows = rng2.normal(0, 0.01, (40, 6))
np.savetxt(par, par_rows)
allrows = mrt.read_mcflirt_par_all(par)
checks['par_all_reads_every_volume'] = (len(allrows) == 40 and np.allclose(allrows, par_rows, atol=1e-6))
checks['par_all_matches_last_row_reader'] = np.allclose(mrt.read_mcflirt_par(par), allrows[-1], atol=1e-9)
np.savetxt(os.path.join(tmp, 'one.par'), par_rows[:1])
checks['par_all_single_volume'] = len(mrt.read_mcflirt_par_all(os.path.join(tmp, 'one.par'))) == 1
checks['par_all_missing_file_is_empty'] = mrt.read_mcflirt_par_all(os.path.join(tmp, 'nope.par')) == []
mrows = [[v + 1] + row for v, row in enumerate(allrows)]
mdir = os.path.join(tmp, 'motion')
mrt.write_motion(mdir, mrows, TR=TR)
ok_png = mrt.write_motion_png(mdir, mrows, TR=TR, nVols=40)
checks['motion_outputs_written_once'] = bool(ok_png) and sorted(os.listdir(mdir)) == ['motion.png', 'motion.tsv']
with open(os.path.join(mdir, 'motion.tsv')) as f:
    checks['motion_tsv_has_a_row_per_volume'] = len(f.read().strip().splitlines()) == 41   # header + 40

print("\n==== recap image ====")
print(f"live {lw}x{lh}px -> recap {rw}x{rh}px (+{rh - lh}px header)   3-way {w0}x{h0} -> {w1}x{h1}")
print()
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
ok = all(bool(v) for v in checks.values())
print("\nRESULT:", "ALL PASS" if ok else "SEE FAILURES")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)
