"""-----------------------------------------------------------------------------
realtime_display.py  —  live motor-activation viewer (NO PsychoPy)

Watches the analysis "live" folder and continuously shows nilearn activation
plots (ortho cut at the PEAK between-condition voxel: LEFT vs RIGHT hand) plus
the two ROI activation timecourses. File-driven (one .npz per update + a
latest.txt pointer + a one-time reference.npz), so it can run on another machine
as long as the live folder is synced.

USAGE:
    python utils/realtime_display.py /path/to/rt-cloud/outDir/live   (from taskActivation/)

Overlay: RED = LEFT > RIGHT (right motor cortex), BLUE = RIGHT > LEFT (left
motor cortex). Labels come from the data.
-----------------------------------------------------------------------------"""
import os
import sys
import time
import numpy as np
import matplotlib
try:
    matplotlib.use('TkAgg', force=True)   # require an interactive (X) backend
except Exception:
    pass
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

if len(sys.argv) > 1:
    liveDir = sys.argv[1]
else:
    here = os.path.dirname(os.path.realpath(__file__))   # utils/
    liveDir = os.path.abspath(os.path.join(here, '..', '..', '..', 'outDir', 'live'))
print(f"Watching: {liveDir}")
POLL_SEC = 0.3

# install nilearn on first run if missing (shared helper lives next to this file)
try:
    sys.path.append(os.path.dirname(os.path.realpath(__file__)))
    import rt_analysis as _mrt
    _mrt.ensure_nilearn()
except Exception:
    pass

try:
    import nibabel as nib
    from nilearn import plotting
    HAVE_NILEARN = True
except Exception:
    HAVE_NILEARN = False
    print("nilearn not found; using matplotlib montage fallback.")

_ref = {'ref': None, 'affine': None}


def load_reference():
    p = os.path.join(liveDir, 'reference.npz')
    if _ref['ref'] is None and os.path.exists(p):
        try:
            d = np.load(p)
            _ref['ref'] = d['ref']; _ref['affine'] = d['affine']
        except Exception:
            pass
    return _ref['ref'], _ref['affine']


def latest_path():
    ptr = os.path.join(liveDir, 'latest.txt')
    if not os.path.exists(ptr):
        return None
    try:
        name = open(ptr).read().strip()
        p = os.path.join(liveDir, name)
        return p if os.path.exists(p) else None
    except Exception:
        return None


def load_bundle(path):
    for _ in range(3):
        try:
            return dict(np.load(path, allow_pickle=True))
        except Exception:
            time.sleep(0.05)
    return None


def voxel_to_mm(affine, ijk):
    v = np.asarray(affine) @ np.array([ijk[0], ijk[1], ijk[2], 1.0])
    return tuple(float(x) for x in v[:3])


plt.ion()
fig = plt.figure(figsize=(14, 8))
# matplotlib silently downgrades to the headless 'agg' backend when there's no
# X display; fail fast with a clear message instead of a confusing blank run.
if 'agg' in matplotlib.get_backend().lower():
    print("[viewer] no interactive (Tk/X) backend available; can't open a window.")
    sys.exit(1)
plt.pause(0.2)


def redraw(b):
    ref, affine = load_reference()
    if affine is None:
        affine = b['affine']
    zmap = b['zmap']; peak = b['peak'].astype(int); thr = float(b['thresh'])
    A = str(b['condA']); B = str(b['condB'])
    caption = str(b['caption']) if 'caption' in b else f"red {A}>{B}, blue {B}>{A}"
    labA = str(b['traceA']) if 'traceA' in b else A
    labB = str(b['traceB']) if 'traceB' in b else B
    condLabel = str(b['condLabel']) if 'condLabel' in b else ''
    contrast = b['contrast'] if 'contrast' in b.files else None
    cthr = float(b['contrast_thresh']) if 'contrast_thresh' in b.files else 2.0
    nsl = int(b['n_slices']) if 'n_slices' in b.files else 6
    _zc = b['z_cuts'] if 'z_cuts' in b.files else None
    cuts = list(_zc) if (_zc is not None and np.size(_zc) > 0) else nsl
    at = b['A_trace']; bt = b['B_trace']; cond = b['cond_trace']
    has_con = (contrast is not None and np.isfinite(contrast).any()
               and np.nanmax(np.abs(contrast)) > 1e-6)

    fig.clf()
    if has_con:
        gs = GridSpec(3, 1, height_ratios=[2.2, 2.2, 1.6], hspace=0.5)
        ax_top = fig.add_subplot(gs[0]); ax_con = fig.add_subplot(gs[1]); ax_tc = fig.add_subplot(gs[2])
    else:
        gs = GridSpec(2, 1, height_ratios=[2.4, 1.6], hspace=0.45)
        ax_top = fig.add_subplot(gs[0]); ax_con = None; ax_tc = fig.add_subplot(gs[1])

    cond_txt = f" | NOW: {condLabel}" if condLabel else ""
    title = (f"{str(b['phase'])} | run {int(b['run'])} | vol {int(b['vol'])}{cond_txt}  |  {caption}")
    if HAVE_NILEARN and ref is not None:
        zimg = nib.Nifti1Image(np.asarray(zmap, np.float32), affine)
        bg = nib.Nifti1Image(np.asarray(ref, np.float32), affine)
        plotting.plot_stat_map(zimg, bg_img=bg, threshold=thr, display_mode='z',
                               cut_coords=cuts, colorbar=True, cmap='RdBu_r', black_bg=True,
                               figure=fig, axes=ax_top, title=title)
        # second row: cumulative LEFT vs RIGHT contrast as its own axial mosaic
        if ax_con is not None:
            cimg = nib.Nifti1Image(np.asarray(contrast, np.float32), affine)
            _clabel = str(b['contrast_label']) if 'contrast_label' in b.files else 'LEFT vs RIGHT GLM contrast'
            plotting.plot_stat_map(cimg, bg_img=bg, threshold=cthr, display_mode='z',
                                   cut_coords=cuts, colorbar=True, cmap='RdBu_r', black_bg=True,
                                   figure=fig, axes=ax_con, title=_clabel)
    else:
        k = int(peak[2])
        ax_top.imshow(np.rot90(zmap[:, :, k]), cmap='RdBu_r',
                      vmin=-np.nanmax(np.abs(zmap)), vmax=np.nanmax(np.abs(zmap)))
        ax_top.set_title(title, fontsize=9); ax_top.axis('off')
        if ax_con is not None:
            c = np.asarray(contrast); kk = int(np.unravel_index(int(np.nanargmax(np.abs(c))), c.shape)[2])
            ax_con.imshow(np.rot90(ref[:, :, kk]) if ref is not None else np.rot90(c[:, :, kk]), cmap='gray')
            ov = np.rot90(c[:, :, kk]).astype(float); ov[np.abs(ov) < cthr] = np.nan
            ax_con.imshow(ov, cmap='RdBu_r', vmin=-np.nanmax(np.abs(c)), vmax=np.nanmax(np.abs(c)), alpha=0.9)
            ax_con.set_title('LEFT vs RIGHT (cumulative)', fontsize=9); ax_con.axis('off')

    x = np.arange(len(at))
    for c, color in [(1, (1, 0, 0, 0.08)), (2, (0, 0, 1, 0.08))]:
        inblk = cond == c
        if inblk.any():
            edges = np.flatnonzero(np.diff(np.r_[0, inblk.astype(int), 0]))
            for s, e in zip(edges[0::2], edges[1::2]):
                ax_tc.axvspan(s - 0.5, e - 0.5, color=color)
    ax_tc.plot(x, at, color='crimson', lw=1.8, label=labA)
    ax_tc.plot(x, bt, color='royalblue', lw=1.2, alpha=0.7, label=labB)
    ax_tc.axhline(0, color='gray', lw=0.6)
    ax_tc.set_xlabel('volume'); ax_tc.set_ylabel('% signal change')
    ax_tc.legend(loc='upper left', fontsize=8, ncol=2)
    ax_tc.set_title('Real-time % signal change from baseline', fontsize=10)
    fig.canvas.draw_idle(); plt.pause(0.001)


last_seen = None
fig.text(0.5, 0.5, "waiting for live data...", ha='center', va='center')
plt.pause(0.001)
try:
    while plt.fignum_exists(fig.number):
        p = latest_path()
        if p and p != last_seen:
            b = load_bundle(p)
            if b is not None:
                redraw(b); last_seen = p
        plt.pause(POLL_SEC)
except KeyboardInterrupt:
    pass
print("viewer closed.")
