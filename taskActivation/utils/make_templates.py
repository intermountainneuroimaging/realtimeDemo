#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
make_templates.py -- render each task's pre-data "template" current.png into
templates/current_<task>.png, for display before any real data has arrived.

Each template is the live current.png's layout with everything data-dependent
left out:
  * brain mosaic -- the standard MNI152 template as the underlay (nilearn ships
    it, no download), at the SAME axial slices the live run will show (run_task.py's
    Z_CUTS), with no statistical overlay;
  * one % signal change row per GLM condition -- ONLY the event timing (shaded
    blocks) and the predicted HRF response (dashed); no measured trace;
  * top-right corner -- PsychoPy snapshots of what the participant sees (made by
    stimuli/render_snapshots.py, committed under templates/stimulus_snapshots/),
    bordered in the matching condition's trace colour.
Everything else (events, conditions, contrast label) is read from the same
conf/<task>.toml + study_design/ events file the live run uses, so a template
can't disagree with its task.

The run's TR is only known once the first DICOM arrives, so --tr (default 1.0,
this project's scanner protocol) sets the sampling of the predicted curve; the
shape is essentially unaffected.

Usage (from the taskActivation/ project root; no PsychoPy needed):
    python utils/make_templates.py                 # all tasks
    python utils/make_templates.py gambling motor  # just these
-----------------------------------------------------------------------------"""
import os
import sys
import ast
import math
import argparse
import numpy as np

HERE = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)   # run_task.py (TASKS / Z_CUTS)
sys.path.insert(0, HERE)
import rt_analysis as mrt          # noqa: E402
import mock_scanner as mock        # noqa: E402 -- only for load_cfg (works without tomllib)
import run_task                    # noqa: E402

SNAP_DIR = os.path.join(PROJECT_ROOT, 'templates', 'stimulus_snapshots')
OUT_DIR = os.path.join(PROJECT_ROOT, 'templates')

# Screens shown to the participant per task live in rt_analysis.STIM_PANELS (shared with
# the end-of-run recap, taskActivation.py --recap).
PANELS = mrt.STIM_PANELS


def _as_list(v):
    """A toml list, or (when mock.load_cfg fell back to its naive parser) its string form."""
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, str) and v.strip().startswith('['):
        try:
            return list(ast.literal_eval(v))
        except (ValueError, SyntaxError):
            return []
    return []


def mni_underlay():
    from nilearn import datasets
    img = datasets.load_mni152_template(resolution=2)
    return np.asarray(img.get_fdata(), np.float32), img.affine


def build_task(name, tr):
    """Everything template_png() needs for one task, from its own config/events."""
    conf_file, _desc = run_task.TASKS[name]
    cfg = mock.load_cfg(os.path.join(PROJECT_ROOT, 'conf', conf_file))
    events = mrt.read_events_tsv(os.path.join(PROJECT_ROOT, 'study_design', cfg['eventsFile']))

    cond_a = str(cfg.get('glmCondA', '')).strip()
    cond_b = str(cfg.get('glmCondB', '')).strip()
    cond_c = str(cfg.get('glmCondC', '')).strip()
    conds = [c for c in (cond_a, cond_b, cond_c) if c]
    # same trace colours taskActivation.py uses (3-way case matches its blue/red/green mosaic)
    colors = ['tab:blue', 'tab:red', 'tab:green'] if cond_c else ['tab:red', 'tab:blue', 'tab:green', 'tab:orange']

    end = max(o + d for o, d, _ in events)
    n_vols = int(math.ceil(end / tr))
    X, names = mrt.make_glm_design(events, n_vols, tr, drift_order=int(cfg.get('driftOrder', 1)),
                                   rest_types=_as_list(cfg.get('restTypes')) or None)
    t = np.arange(n_vols) * tr
    traces = []
    for k, cond in enumerate(conds):
        reg = X[:, names.index(cond)]
        traces.append({
            't': t,
            'predicted': reg / reg.max(),   # peak 1: a SHAPE, not a magnitude -- no data yet to scale it
            'blocks': [(o, o + d) for o, d, tt in events if tt == cond],
            'color': colors[k % len(colors)],
            'title': f"{cond} -- event timing (shaded) and HRF-predicted response (dashed)",
            'ylabel': 'predicted % ΔS\n(arbitrary scale)',
            'ylim': (-0.25, 1.2),
        })

    # the live run's mosaic caption, minus its z-scoring suffix (no data to z-score yet)
    if cond_c:
        label = f"{cond_a}/{cond_b}/{cond_c} one-vs-rest: blue {cond_a} / red {cond_b} / green {cond_c}"
    elif cond_b:
        label = f"{cond_a} vs {cond_b} GLM contrast: red {cond_a}>{cond_b} / blue {cond_b}>{cond_a}"
    else:
        label = f"{cond_a} GLM β-weight: red positive / blue negative"

    color_of = {c: colors[k % len(colors)] for k, c in enumerate(conds)}
    panels = mrt.stim_panels_for(name, SNAP_DIR, color_of, strict=True)

    z_cuts = mrt.parse_float_list(run_task.Z_CUTS.get(name))
    return dict(traces=traces, z_cuts=z_cuts, panels=panels, full_xlim=(0.0, max((n_vols - 1) * tr, tr)),
                title=str(cfg.get('title', name)),
                caption=f"{label}  --  awaiting data (MNI152 template underlay)")


def main():
    ap = argparse.ArgumentParser(description="Render the pre-data template current.png for each task.")
    ap.add_argument('tasks', nargs='*', help=f"tasks to render (default: all of {', '.join(sorted(run_task.TASKS))})")
    ap.add_argument('--tr', type=float, default=1.0, help='TR (s) used to sample the predicted curve (default 1.0)')
    ap.add_argument('--out-dir', default=OUT_DIR)
    args = ap.parse_args()
    bad = [t for t in args.tasks if t not in PANELS]
    if bad:
        ap.error(f"unknown task(s) {bad}; choose from {sorted(PANELS)}")

    ref3d, affine = mni_underlay()
    os.makedirs(args.out_dir, exist_ok=True)
    for name in (args.tasks or sorted(PANELS)):
        spec = build_task(name, args.tr)
        out = os.path.join(args.out_dir, f'current_{name}.png')
        ok = mrt.template_png(
            out, ref3d, affine, spec['traces'], spec['z_cuts'], spec['title'], spec['caption'],
            stim_panels=spec['panels'], full_xlim=spec['full_xlim'],
            subtitle="The brain map and measured traces replace this once data arrive.")
        if not ok:
            sys.exit("nilearn/matplotlib unavailable -- can't render templates here")
        print(f"[template] {os.path.relpath(out, PROJECT_ROOT)}")


if __name__ == '__main__':
    main()
