#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
checkerboard_lr_task.py -- simple PsychoPy presentation of this project's
own 3-position flickering-checkerboard visual localizer
(study_design/CheckerboardLR_events.tsv, the same file taskActivation.py's
live analysis reads via conf/checkerboard_lr.toml). The Psychtoolbox
equivalent is stimuli_ptb/checkerboard_lr_task.m -- both present the exact
same events.tsv.

A full-contrast checkerboard patch flickers ON/OFF (fully visible, then
fully blank -- NOT the phase-reversal black<->white flip checkerboard_task.py
uses) at --flicker-hz, shown in one of three screen positions per block:
CENTER, LEFT, or RIGHT. A small + fixation cross stays visible at screen
center THROUGHOUT every block (including LEFT/RIGHT, and the OFF half of
every flicker cycle), so the subject can hold central gaze while the
checkerboard stimulates each position -- standard practice for a peripheral
visual localizer, so the resulting activation reflects retinotopic stimulus
location rather than eye movements.

Blocks: rest / center / rest / left / rest / right, x4 reps + a trailing
rest block, 12s blocks, 300s total -- matches conf/checkerboard_lr.toml's
3-way one-vs-rest GLM contrast (glmCondA=center / glmCondB=left /
glmCondC=right, each contrasted against the mean of the other two) for
live analysis.

Shows a brief task-instructions screen (task description + the subject's
goal; dismiss with 1/2, or Escape to abort) before waiting for the scanner
trigger.

Run (needs `pip install psychopy` and a display):
    python checkerboard_lr_task.py                    # waits for scanner trigger '5' or 't'
    python checkerboard_lr_task.py --windowed          # not fullscreen, for testing
    python checkerboard_lr_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import argparse
import datetime
import numpy as np
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design', 'CheckerboardLR_events.tsv')


class _CenterLeftRightStim:
    """Draws the (possibly None) checker patch for this frame, THEN the
    fixation cross on top -- fixation must stay visible on EVERY frame of
    EVERY condition (see the module docstring), so a single stim_for()
    return value has to combine both rather than picking one or the other
    like the plain checkerboard_task.py / generic_motor_task.py do."""
    def __init__(self, checker, show_checker, fixation):
        self.checker = checker
        self.show_checker = show_checker
        self.fixation = fixation

    def draw(self):
        if self.checker is not None and self.show_checker:
            self.checker.draw()
        self.fixation.draw()


def build_checker_stims(win, n_squares=8, center_fraction=0.45, side_fraction=0.40, margin_frac=0.04):
    """Build one checkerboard GratingStim per position (center/left/right),
    sized and placed as fractions of the window -- mirrors
    checkerboard_lr_task.m's pixel-level destRects, but in PsychoPy
    'height' units (window height = 1.0, width = aspect) so it scales to
    any window size the same way the rest of this project's PsychoPy stims
    do. side_fraction is still smaller than center_fraction so a LEFT/RIGHT
    patch fits inside the outer screen thirds without clipping, matching
    the .m version.

    n_squares MUST be a power of two (default 8): PsychoPy's GratingStim
    texture upload requires a square power-of-two array on some OpenGL
    backends (older/software renderers without the
    GL_ARB_texture_non_power_of_two extension) -- an arbitrary size like 6
    logs a "Requiring a square power of two texture" error and silently
    fails to render correctly."""
    from psychopy import visual
    win_w_px, win_h_px = win.size
    aspect = win_w_px / win_h_px
    short_side = min(1.0, aspect)

    checker = np.indices((n_squares, n_squares)).sum(axis=0) % 2
    checker = checker.astype(float) * 2 - 1

    patch_size_center = center_fraction * short_side
    patch_size_side = side_fraction * short_side
    margin = margin_frac * aspect   # aspect == window width in 'height' units

    def make(pos, size):
        return visual.GratingStim(win, tex=checker, mask=None, size=(size, size),
                                  pos=pos, units='height', interpolate=False)

    return {
        'center': make((0, 0), patch_size_center),
        'left': make((-aspect / 2 + margin + patch_size_side / 2, 0), patch_size_side),
        'right': make((aspect / 2 - margin - patch_size_side / 2, 0), patch_size_side),
    }


def main():
    ap = argparse.ArgumentParser(
        description='Present the CENTER/LEFT/RIGHT checkerboard localizer (PsychoPy).')
    ap.add_argument('--events', default=DEFAULT_EVENTS, help='events.tsv to present')
    ap.add_argument('--trigger-key', default='5,t',
                    help="comma-separated key(s) that start the run (scanner sync pulse, "
                         "or press one yourself to test)")
    ap.add_argument('--duration', type=float, default=None,
                    help='total run length in seconds (default: end of the last event); '
                         'pass nVols*TR to also show trailing rest')
    ap.add_argument('--flicker-hz', type=float, default=4.0,
                    help='ON/OFF flicker rate, i.e. how many times per second the checkerboard '
                         'toggles fully visible <-> fully blank (default 4 -- half the '
                         'pattern-reversal rate checkerboard_task.py uses, since a full on/off '
                         'cycle here is twice as long as one reversal there for the same '
                         'perceived flicker rate)')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/checkerboard_lr_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core

    events = common.read_events_tsv(args.events)
    print(f"[checkerboard_lr] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"checkerboard_lr_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    checker_stims = build_checker_stims(win)
    # Green (not white) so it stays clearly visible against the
    # black-and-white checkerboard squares behind it.
    fixation = visual.TextStim(win, text='+', color='lime', height=0.1)
    flicker_hz = args.flicker_hz

    def stim_for(trial_type, t_in_event, duration):
        checker = checker_stims.get(trial_type)
        # ON/OFF: show the checkerboard for the first half of each flicker
        # cycle, nothing (just the fixation cross) for the second half --
        # a true on/off flicker, not a black<->white pattern reversal.
        show = checker is not None and int(t_in_event * flicker_hz * 2) % 2 == 0
        return _CenterLeftRightStim(checker, show, fixation)

    instructions = (
        "CHECKERBOARD LOCALIZER TASK\n\n"
        "You will see a flickering black-and-white checkerboard pattern appear in "
        "different places on the screen -- sometimes in the middle, sometimes off "
        "to the left, sometimes off to the right.\n\n"
        "Goal: keep looking at the + in the center of the screen THE WHOLE TIME, "
        "even when the checkerboard appears off to one side -- just notice it out "
        "of the corner of your eye rather than looking directly at it. No response "
        "or button press is needed during the task.\n\n"
        "If you have any questions, ask the experimenter now. When you are "
        "comfortable, press any button to continue.")
    if common.show_instructions(win, instructions):
        core.quit()

    clock, t0 = common.wait_for_trigger(win, trigger_keys=args.trigger_key.split(','),
                                        instructions='Waiting for scanner trigger...')
    print(f"[checkerboard_lr] triggered at t0={t0:.3f}s -- starting task")
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
