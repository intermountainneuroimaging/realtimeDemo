#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
motor_guessing_task.py -- PsychoPy presentation of this project's "guess the
hand" motor game (study_design/MotorGuessing_events.tsv, the same file
taskActivation.py's live analysis reads via conf/motor_guessing.toml). The
Psychtoolbox equivalent is stimuli_ptb/motor_guessing_task.m -- both present
the exact same events.tsv.

The participant SECRETLY chooses a hand -- left or right -- and does NOT tell
the experimenter. Whenever MOVE is on screen they move that same hand -- by
squeezing it into a fist (like a stress ball) and relaxing it, repeatedly -- for as
long as the cue stays up; on the + fixation cross they relax. The cue never
names a hand, and nothing in this script (or its timing log) records which
one was used, so the experimenter stays blind. At the end of the run the group
guesses the hand from the real-time brain output: a hand drives the OPPOSITE
motor cortex (left hand -> right hemisphere).

Blocks: a 10s baseline rest, then 5 x (30s MOVE + 20s rest), the last rest cut to 10s --
250s total, the same length as generic_motor_task.py so the two can be swapped freely.
Analyzed live as ONE condition (glmCondA='move', vs the implicit rest
baseline), since the hand isn't known ahead of time -- see conf/motor_guessing.toml.

Shows a brief task-instructions screen (dismiss with 1/2, or Escape to abort)
before waiting for the scanner trigger.

Run (needs `pip install psychopy` and a display):
    python motor_guessing_task.py                    # waits for scanner trigger '5' or 't'
    python motor_guessing_task.py --windowed          # not fullscreen, for testing
    python motor_guessing_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import argparse
import datetime
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design', 'MotorGuessing_events.tsv')

CUE_LABELS = {
    'move': 'MOVE',   # deliberately does NOT name a hand -- the hand is the participant's secret
}


def build_stims(win):
    """One TextStim per condition, built once up front -- PsychoPy stims are
    drawn every frame, so reusing the same objects avoids rebuilding
    text/geometry each time."""
    from psychopy import visual
    stims = {}
    for key, label in CUE_LABELS.items():
        stims[key] = visual.TextStim(win, text=label, color='lime', bold=True, height=0.14)
    fixation = visual.TextStim(win, text='+', color='white', height=0.1)
    return stims, fixation


def main():
    ap = argparse.ArgumentParser(description='Present the secret-hand movement "guess the hand" task (PsychoPy).')
    ap.add_argument('--events', default=DEFAULT_EVENTS, help='events.tsv to present')
    ap.add_argument('--trigger-key', default='5,t',
                    help="comma-separated key(s) that start the run (scanner sync pulse, "
                         "or press one yourself to test)")
    ap.add_argument('--duration', type=float, default=None,
                    help='total run length in seconds (default: end of the last event); '
                         'pass nVols*TR to also show trailing rest')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/motor_guessing_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core

    events = common.read_events_tsv(args.events)
    print(f"[motor_guessing] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"motor_guessing_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    stims, fixation = build_stims(win)

    def stim_for(trial_type, t_in_event, duration):
        if trial_type is None:
            return fixation
        return stims.get(trial_type, fixation)

    instructions = (
        "HAND GUESSING GAME\n\n"
        "Before we start, silently choose ONE hand -- your left or your right -- and "
        "keep it a secret: do not tell the experimenter or say it out loud.\n\n"
        "Whenever you see MOVE on the screen, move your chosen hand by squeezing it into "
        "a fist, like you are squeezing a stress ball, then relaxing it. Keep squeezing "
        "and relaxing repeatedly for as long as MOVE stays on the screen. Use the SAME "
        "hand every time. When you see the + fixation cross, relax and stay still.\n\n"
        "Goal: keep squeezing and relaxing steadily for the whole block, always with the same "
        "hand. At the end, everyone will try to guess which hand you used from your "
        "brain activity!\n\n"
        "If you have any questions, ask the experimenter now (but do not say which hand "
        "you chose). When you are comfortable, press any button to continue.")
    if common.show_instructions(win, instructions):
        core.quit()

    clock, t0 = common.wait_for_trigger(win, trigger_keys=args.trigger_key.split(','),
                                        instructions='Waiting for scanner trigger...')
    print(f"[motor_guessing] triggered at t0={t0:.3f}s -- starting task")
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
