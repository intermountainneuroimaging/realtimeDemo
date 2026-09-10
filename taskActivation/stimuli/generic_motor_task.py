#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
generic_motor_task.py -- simple PsychoPy presentation of this project's own
LEFT/RIGHT finger-tapping design (study_design/GenericMotorLR_events.tsv,
the same file taskActivation.py's live analysis reads via conf/motor.toml),
so this project's motor task can be run end-to-end with a real (or
self-triggered) task on the stimulus computer. The Psychtoolbox equivalent
is stimuli_ptb/motor_task.m -- both present the exact same events.tsv.

Blocks: 30s LEFT FINGER / RIGHT FINGER tapping blocks separated by 10s REST
blocks (3 reps each + a trailing rest block, 250s total) -- exactly
matching taskActivation.py's GLM design (glmCondA=left_finger,
glmCondB=right_finger). Unlike hcp_motor_task.py's original 5-condition HCP
dataset, there are no "_cue" get-ready periods here -- rest between blocks
doubles as the get-ready period.

Run (needs `pip install psychopy` and a display):
    python generic_motor_task.py                    # waits for scanner trigger '5' or 't'
    python generic_motor_task.py --windowed          # not fullscreen, for testing
    python generic_motor_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import argparse
import datetime
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design', 'GenericMotorLR_events.tsv')

FINGER_LABELS = {
    'left_finger': 'LEFT\nFINGER',
    'right_finger': 'RIGHT\nFINGER',
}


def build_stims(win):
    """One TextStim per condition, built once up front -- PsychoPy stims are
    drawn every frame, so reusing the same objects avoids rebuilding
    text/geometry each time."""
    from psychopy import visual
    stims = {}
    for key, label in FINGER_LABELS.items():
        stims[key] = visual.TextStim(win, text=label, color='lime', bold=True, height=0.14)
    fixation = visual.TextStim(win, text='+', color='white', height=0.1)
    return stims, fixation


def main():
    ap = argparse.ArgumentParser(description='Present the LEFT/RIGHT finger-tapping task (PsychoPy).')
    ap.add_argument('--events', default=DEFAULT_EVENTS, help='events.tsv to present')
    ap.add_argument('--trigger-key', default='5,t',
                    help="comma-separated key(s) that start the run (scanner sync pulse, "
                         "or press one yourself to test)")
    ap.add_argument('--duration', type=float, default=None,
                    help='total run length in seconds (default: end of the last event); '
                         'pass nVols*TR to also show trailing rest')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/generic_motor_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core

    events = common.read_events_tsv(args.events)
    print(f"[generic_motor] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"generic_motor_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    stims, fixation = build_stims(win)

    def stim_for(trial_type, t_in_event, duration):
        if trial_type is None:
            return fixation
        return stims.get(trial_type, fixation)

    clock, t0 = common.wait_for_trigger(win, trigger_keys=args.trigger_key.split(','),
                                        instructions='Waiting for scanner trigger...')
    print(f"[generic_motor] triggered at t0={t0:.3f}s -- starting task")
    common.run_events(win, events, stim_for, clock, t0,
                      run_duration=args.duration, log_path=log_path)

    done = visual.TextStim(win, text='Task complete -- thank you!', color='white', height=0.06)
    done.draw()
    win.flip()
    core.wait(2.0)
    win.close()
    core.quit()


if __name__ == '__main__':
    main()
