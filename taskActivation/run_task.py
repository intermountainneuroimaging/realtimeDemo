#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
run_task.py -- quick task selector for taskActivation.py.

This project ships three ready-to-run task configs (conf/motor.toml,
conf/checkerboard.toml, conf/gambling.toml), each paired with a
study_design/*_events.tsv and (for a real task on the stimulus computer) a
matching script in stimuli_ptb/ or stimuli/. Rather than remembering each
config's exact filename, run one by its short name:

    python run_task.py motor
    python run_task.py checkerboard
    python run_task.py gambling

This is a thin dispatcher -- it does no analysis itself, just maps the name
to its conf/<task>.toml and runs taskActivation.py with that --config as a
subprocess, so it's exactly equivalent to (and stays in sync with any future
change to) running taskActivation.py directly:

    python taskActivation.py --config conf/motor.toml

Pass --run to override the toml's runNum, exactly as taskActivation.py's own
--run does (see its --help): e.g. `python run_task.py gambling --run 2`.

Pass --plot-every-frame to disable taskActivation.py's default behavior of
skipping current.png's render on volumes where the run has fallen too far
behind real scanner time (see its --help) -- use this for a replay/offline
run where keeping every frame matters more than staying caught up.

Pass --skip-motion-correction to skip mcflirt entirely (testing/demo only --
see taskActivation.py's --help for the real accuracy tradeoff this makes).

Whichever task is chosen, taskActivation.py writes outDir/live/viewer.html
(current.png, the activation view) and viewer-motion.html (motion.png) as
two separate auto-refreshing pages -- same as running taskActivation.py
directly, since this is just a subprocess wrapper around it.

motor and checkerboard each also get a hard-coded --z-cuts (see Z_CUTS
below), so current.png's axial mosaic lands on that task's actual activation
instead of generic auto-selected slice levels.
-----------------------------------------------------------------------------"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))

# name -> (config file, one-line description)
TASKS = {
    'motor':        ('motor.toml',        'LEFT vs RIGHT finger tapping'),
    'checkerboard': ('checkerboard.toml',  'flickering checkerboard ON vs OFF'),
    'gambling':     ('gambling.toml',      'blackjack WIN vs LOSE (tie as covariate)'),
}

# task -> 5 axial slice positions (mm), hard-coded to where each task's
# activation actually falls rather than the generic auto-selected levels --
# forwarded to taskActivation.py's --z-cuts, overriding the toml's zCuts for
# that run. Motor cortex sits near the vertex (high z); visual cortex is
# posterior/inferior (low z). gambling has no fixed region picked yet, so
# it's absent here and keeps using its toml's own zCuts (currently auto).
Z_CUTS = {
    'motor':        '0,16.25,32.5,48.75,65',
    'checkerboard': '-36,-22.75,-9.5,3.75,17',
}


def main():
    ap = argparse.ArgumentParser(
        description='Run one of this project\'s ready-made task configs.',
        epilog='Tasks:\n' + '\n'.join(f'  {name:<13s} {desc}' for name, (_, desc) in TASKS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('task', choices=sorted(TASKS), help='which task to run')
    ap.add_argument('--run', '-r', type=int, default=None,
                     help="run number to use (overrides the toml's runNum) -- "
                          "forwarded straight to taskActivation.py's own --run")
    ap.add_argument('--plot-every-frame', action='store_true',
                     help="never skip current.png's render for falling behind real scanner "
                          "time -- forwarded straight to taskActivation.py's own "
                          "--plot-every-frame; see its --help for what the default skips")
    ap.add_argument('--skip-motion-correction', action='store_true',
                     help="OPT-IN, testing/demo only -- skip mcflirt (real accuracy tradeoff, "
                          "see taskActivation.py's --help) -- forwarded straight to its own "
                          "--skip-motion-correction")
    args = ap.parse_args()

    configFile, desc = TASKS[args.task]
    configPath = os.path.join(HERE, 'conf', configFile)
    print(f"[run_task] {args.task} ({desc}) -> {configPath}")

    cmd = [sys.executable, os.path.join(HERE, 'taskActivation.py'), '--config', configPath]
    if args.run is not None:
        cmd += ['--run', str(args.run)]
    if args.plot_every_frame:
        cmd += ['--plot-every-frame']
    if args.skip_motion_correction:
        cmd += ['--skip-motion-correction']
    z_cuts = Z_CUTS.get(args.task)
    if z_cuts:
        # --z-cuts=value (one token), not ['--z-cuts', value] -- a value
        # starting with '-' (e.g. checkerboard's '-36,...') otherwise looks
        # like an unrecognized flag to argparse rather than this option's
        # value, since it doesn't match argparse's plain-negative-number
        # pattern (a comma-separated list isn't a single number).
        cmd += [f'--z-cuts={z_cuts}']

    # subprocess, not a direct import/exec -- taskActivation.py is a
    # top-level script (not structured as an importable module), and its
    # own sys.excepthook/os._exit() force-exit behavior (see its top-of-file
    # comment) should terminate ITS process, not this wrapper's. Relaying
    # the child's exit code here gives the same final result either way.
    sys.exit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
