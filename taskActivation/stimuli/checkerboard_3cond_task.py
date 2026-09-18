#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
checkerboard_3cond_task.py -- simple PsychoPy presentation of this project's
own 3-position flickering-checkerboard visual localizer
(study_design/Checkerboard3Cond_events.tsv, the same file taskActivation.py's
live analysis reads via conf/checkerboard_3cond.toml). The Psychtoolbox
equivalent is stimuli_ptb/checkerboard_3cond_task.m -- both present the exact
same events.tsv.

A full-contrast checkerboard flickers in one of three screen positions per
block: CENTER, LEFT, or RIGHT -- the same OFF (blank) -> ON (pattern A) ->
OFF -> ON (pattern B, the black<->white inverse of A) -> repeat flicker
checkerboard_1cond_task.py uses, at --flicker-hz. CENTER is a SQUARE (its height
set equal to its own width, not the window height) centered on screen, so
it stimulates only the fovea; LEFT and RIGHT are full window-height BARS,
anchored flush against the window's left/right edge respectively (not
floating with a gap), so they reach as far into the visual periphery as the
window allows. A small + fixation cross stays visible at screen center
THROUGHOUT every block (including LEFT/RIGHT, and every OFF phase), so the
subject can hold central gaze while the checkerboard stimulates each
position -- standard practice for a peripheral visual localizer, so the
resulting activation reflects retinotopic stimulus location rather than eye
movements.

Blocks: rest / center / rest / left / rest / right, x4 reps + a trailing
rest block, 12s blocks, 300s total -- matches conf/checkerboard_3cond.toml's
3-way one-vs-rest GLM contrast (glmCondA=center / glmCondB=left /
glmCondC=right, each contrasted against the mean of the other two) for
live analysis.

Shows a brief task-instructions screen (task description + the subject's
goal; dismiss with 1/2, or Escape to abort) before waiting for the scanner
trigger.

Run (needs `pip install psychopy` and a display):
    python checkerboard_3cond_task.py                    # waits for scanner trigger '5' or 't'
    python checkerboard_3cond_task.py --windowed          # not fullscreen, for testing
    python checkerboard_3cond_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import argparse
import datetime
import numpy as np
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design', 'Checkerboard3Cond_events.tsv')


class _CenterLeftRightStim:
    """Draws the (possibly None) checker bar for this frame, THEN the
    fixation cross on top -- fixation must stay visible on EVERY frame of
    EVERY condition (see the module docstring), so a single stim_for()
    return value has to combine both rather than picking one or the other
    like the plain checkerboard_1cond_task.py / generic_motor_task.py do."""
    def __init__(self, checker, fixation):
        self.checker = checker
        self.fixation = fixation

    def draw(self):
        if self.checker is not None:
            self.checker.draw()
        self.fixation.draw()


def build_checker_stims(win, cells_across=8, center_width_frac=0.288, side_width_frac=0.32):
    """Build the two phase-inverted checkerboard GratingStims (pattern A /
    pattern B -- see the module docstring's OFF/A/OFF/B flicker) for each
    position (center/left/right), sized and placed as fractions of the
    window -- mirrors checkerboard_3cond_task.m's pixel-level destRects, but
    in PsychoPy 'height' units (window height = 1.0, width = aspect) so it
    scales to any window size the same way the rest of this project's
    PsychoPy stims do.

    CENTER is a SQUARE (height == center_width_frac, not the window height)
    centered on screen, so it stimulates only the fovea. LEFT and RIGHT
    span the FULL window height (vertical bars) and are only
    side_width_frac of the window wide; LEFT sits flush against the
    window's left edge and RIGHT flush against its right edge (no
    gap/margin) so each reaches as far into the periphery as the window
    allows. side_width_frac is still smaller than center_width_frac,
    matching the .m version.

    Returns {'center': {'A': stim, 'B': stim}, 'left': {...}, 'right': {...}}.

    THE CHECKER CELLS STAY SQUARE even though LEFT/RIGHT are tall, narrow
    rectangles. PsychoPy's GratingStim texture upload requires a SQUARE
    power-of-two array on some OpenGL backends (older/software renderers
    without the GL_ARB_texture_non_power_of_two extension) -- a non-square
    array like (n_rows, n_cols) with n_rows != n_cols logs a "Requiring a
    square power of two texture" error, and simply stretching a square
    array via size=(width, height) elongates the cells whenever
    width != height. So instead the texture stays a minimal 2x2 checker
    tile (still square, still power of two), and GratingStim's own
    spatial-frequency tiling (`sf`) repeats it `cells_across / 2` cycles
    horizontally and a DIFFERENT number of cycles vertically -- scaled by
    that stim's own height/width ratio -- so each repeated cell ends up
    the same physical height as width regardless of the stim's own aspect
    ratio (a no-op correction for CENTER, since it's already square)."""
    from psychopy import visual
    win_w_px, win_h_px = win.size
    aspect = win_w_px / win_h_px   # window width in 'height' units

    tile = np.array([[1.0, -1.0], [-1.0, 1.0]])   # minimal 2x2 checker tile
    tile_inv = -tile
    bar_height = 1.0   # full window height, for LEFT/RIGHT only
    sf_x = cells_across / 2.0   # cycles across the width (2 cells/cycle)

    def make(pos, width, height, arr):
        sf = (sf_x, sf_x * height / width)   # compensate for this stim's own aspect ratio
        return visual.GratingStim(win, tex=arr, mask=None, size=(width, height),
                                  pos=pos, units='height', interpolate=False, sf=sf)

    positions = {
        'center': (0.0, center_width_frac, center_width_frac),
        'left': (-aspect / 2 + side_width_frac / 2, side_width_frac, bar_height),
        'right': (aspect / 2 - side_width_frac / 2, side_width_frac, bar_height),
    }
    return {
        key: {'A': make((x, 0), width, height, tile), 'B': make((x, 0), width, height, tile_inv)}
        for key, (x, width, height) in positions.items()
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
    ap.add_argument('--flicker-hz', type=float, default=2.0,
                    help='how many times per second the checkerboard changes state during a '
                         'CENTER/LEFT/RIGHT block (default 2): OFF (blank) -> ON (pattern A) -> '
                         'OFF -> ON (pattern B, the black<->white inverse of A) -> repeat, each '
                         'state lasting 1/flicker_hz -- same semantics as checkerboard_1cond_task.py')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/checkerboard_3cond_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core

    events = common.read_events_tsv(args.events)
    print(f"[checkerboard_3cond] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"checkerboard_3cond_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    checker_stims = build_checker_stims(win)
    # Green (not white) so it stays clearly visible against the
    # black-and-white checkerboard squares behind it.
    fixation = visual.TextStim(win, text='+', color='lime', height=0.1)
    flicker_hz = args.flicker_hz

    def stim_for(trial_type, t_in_event, duration):
        # True flicker: fully OFF (blank) between each ON flash, and the
        # flash itself alternates pattern A/B (black<->white inverse) so a
        # given screen location genuinely reverses polarity from one flash
        # to the next -- same 4-phase cycle as checkerboard_1cond_task.py.
        entry = checker_stims.get(trial_type)
        stim = None
        if entry is not None:
            phase = int(t_in_event * flicker_hz) % 4
            if phase == 1:
                stim = entry['A']
            elif phase == 3:
                stim = entry['B']
        return _CenterLeftRightStim(stim, fixation)

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
    print(f"[checkerboard_3cond] triggered at t0={t0:.3f}s -- starting task")
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
