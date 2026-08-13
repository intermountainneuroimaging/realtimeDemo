"""-----------------------------------------------------------------------------
motion_display.py  —  live head-motion plot in its own window.

Watches outDir/live/motion.tsv (written by taskActivation.py from mcflirt's
-plots output) and shows all six rigid-body parameters on one axes:
x-axis = time (s), y-axis = head motion (mm). Translations (tx, ty, tz) are in
mm; rotations (rx, ry, rz) are converted to mm-equivalent at a 50 mm head radius
so they share the same axis. Refreshes as each new volume arrives.

Run manually, on any machine that can see the live folder:
    python motion_display.py /rt-cloud/outDir/live
-----------------------------------------------------------------------------"""
import os
import sys
import time
import numpy as np
import matplotlib
try:
    matplotlib.use('TkAgg', force=True)        # require an interactive (X) backend
except Exception:
    pass
import matplotlib.pyplot as plt

liveDir = sys.argv[1] if len(sys.argv) > 1 else '/rt-cloud/outDir/live'
motion_tsv = os.path.join(liveDir, 'motion.tsv')
HEAD_RADIUS_MM = 50.0      # convert rotations (rad) to mm-equivalent arc length

PARAMS = [('trans_x', 'tx'), ('trans_y', 'ty'), ('trans_z', 'tz'),
          ('rot_x', 'rx'), ('rot_y', 'ry'), ('rot_z', 'rz')]
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

plt.ion()
fig, (ax, ax_fd) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
fig.suptitle('Real-time head motion (mcflirt)')
if 'agg' in matplotlib.get_backend().lower():
    print("[motion] no interactive (Tk/X) backend available; can't open a window.")
    sys.exit(1)
plt.pause(0.2)


def load_motion():
    try:
        d = np.genfromtxt(motion_tsv, names=True, delimiter='\t')
        return np.atleast_1d(d) if d.size else None
    except Exception:
        return None


def redraw(d):
    t = d['time_s'] if 'time_s' in d.dtype.names else d['vol']
    rot = np.column_stack([d['rot_x'], d['rot_y'], d['rot_z']])
    tr = np.column_stack([d['trans_x'], d['trans_y'], d['trans_z']])
    if len(t) > 1:
        dfd = (np.abs(np.diff(tr, axis=0)).sum(1)
               + np.abs(np.diff(rot, axis=0)).sum(1) * HEAD_RADIUS_MM)
        fd = np.concatenate([[0.0], dfd])
    else:
        fd = np.zeros(len(t))
    ax.clear(); ax_fd.clear()
    for (col, lab), color in zip(PARAMS, COLORS):
        y = np.asarray(d[col], float)
        if col.startswith('rot'):
            y = y * HEAD_RADIUS_MM          # rad -> mm-equivalent
        ax.plot(t, y, label=lab, color=color, lw=1.5)
    ax.axhline(0, color='gray', lw=0.5)
    ax.set_ylabel('head motion (mm)')
    ax.legend(loc='upper left', ncol=6, fontsize=8)
    ax.set_title('translations (tx,ty,tz) + rotations (rx,ry,rz @ 50 mm) in mm', fontsize=9)
    ax_fd.plot(t, fd, color='crimson', lw=1.5, label='FD')
    ax_fd.axhline(0.5, color='orange', ls='--', lw=0.8, label='0.5 mm')
    ax_fd.set_ylabel('FD (mm)'); ax_fd.set_xlabel('time (s)')
    ax_fd.legend(loc='upper left', fontsize=8)
    ax_fd.set_title(f'Framewise displacement  (max {fd.max():.2f} mm, mean {fd.mean():.2f} mm)',
                    fontsize=9)
    fig.canvas.draw_idle(); plt.pause(0.001)


print(f"[motion] watching {motion_tsv}")
last_n = -1
while True:
    if not plt.fignum_exists(fig.number):
        break
    d = load_motion()
    if d is not None and len(d) != last_n:
        last_n = len(d)
        try:
            redraw(d)
        except Exception as e:
            print('[motion] redraw error:', e)
    plt.pause(0.5)
    time.sleep(0.3)
