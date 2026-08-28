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
    'gambling':     ('gambling.toml',      'gambling WIN (reward) vs LOSS (punishment)'),
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
    args = ap.parse_args()

    configFile, desc = TASKS[args.task]
    configPath = os.path.join(HERE, 'conf', configFile)
    print(f"[run_task] {args.task} ({desc}) -> {configPath}")

    cmd = [sys.executable, os.path.join(HERE, 'taskActivation.py'), '--config', configPath]
    if args.run is not None:
        cmd += ['--run', str(args.run)]

    # subprocess, not a direct import/exec -- taskActivation.py is a
    # top-level script (not structured as an importable module), and its
    # own sys.excepthook/os._exit() force-exit behavior (see its top-of-file
    # comment) should terminate ITS process, not this wrapper's. Relaying
    # the child's exit code here gives the same final result either way.
    sys.exit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
