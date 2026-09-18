#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
checkerboard_1cond_task.py -- simple PsychoPy presentation of this project's own
flickering-checkerboard visual localizer (study_design/Checkerboard1Cond_events.tsv,
the same file taskActivation.py's live analysis reads via conf/checkerboard.toml).
The Psychtoolbox equivalent is stimuli_ptb/checkerboard_1cond_task.m -- both present
the exact same events.tsv and the same flicker: OFF (blank) -> ON (pattern A)
-> OFF -> ON (pattern B, the black<->white inverse of A) -> repeat, each
state lasting 1/flicker_hz, so a given screen location genuinely goes
black, then white, then black -- not two checkerboards swapped directly
with no blank in between (which can look like a static image if the two
patterns aren't visually distinct at a glance). See checkerboard_3cond_task.py
for the 3-position on/off (single-pattern) variant.

Blocks: alternating 20s rest (fixation only) / 20s checkerboard (flickering)
blocks, 6 reps + a trailing rest block, 260s total -- exactly matching
taskActivation.py's GLM design (glmCondA=checkerboard, glmCondB='' -- ON vs
the implicit rest baseline).

Shows a brief task-instructions screen (task description + the subject's
goal; dismiss with 1/2, or Escape to abort) before waiting for the scanner
trigger.

Run (needs `pip install psychopy` and a display):
    python checkerboard_1cond_task.py                    # waits for scanner trigger '5' or 't'
    python checkerboard_1cond_task.py --windowed          # not fullscreen, for testing
    python checkerboard_1cond_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import argparse
import datetime
import numpy as np
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design', 'Checkerboard1Cond_events.tsv')


def build_checker_textures(win, n_squares=16, patch_fraction=0.8):
    """Build the two phase-inverted checkerboard patches (ON: black<->white
    reversal) as GratingStims with a custom numpy texture, sized as a
    fraction of the window's shorter dimension -- mirrors
    checkerboard_1cond_task.m's pixel-level texOn/texOff construction, but in
    PsychoPy 'height' units so it scales to any window size the same way
    the rest of this project's PsychoPy stims do.

    n_squares MUST be a power of two (default 16): PsychoPy's GratingStim
    texture upload requires a square power-of-two array on some OpenGL
    backends (older/software renderers without the
    GL_ARB_texture_non_power_of_two extension) -- an arbitrary size like 20
    logs a "Requiring a square power of two texture" error and silently
    fails to render correctly."""
    from psychopy import visual
    win_w_px, win_h_px = win.size
    aspect = win_w_px / win_h_px
    short_side = min(1.0, aspect)   # 'height' units: window height is always 1.0

    checker = np.indices((n_squares, n_squares)).sum(axis=0) % 2
    checker = checker.astype(float) * 2 - 1   # -1/+1 for GratingStim's luminance texture

    patch_size = patch_fraction * short_side
    tex_on = visual.GratingStim(win, tex=checker, mask=None, size=(patch_size, patch_size),
                                pos=(0, 0), units='height', interpolate=False)
    tex_off = visual.GratingStim(win, tex=-checker, mask=None, size=(patch_size, patch_size),
                                 pos=(0, 0), units='height', interpolate=False)
    return tex_on, tex_off


def main():
    ap = argparse.ArgumentParser(description='Present the flickering-checkerboard localizer (PsychoPy).')
    ap.add_argument('--events', default=DEFAULT_EVENTS, help='events.tsv to present')
    ap.add_argument('--trigger-key', default='5,t',
                    help="comma-separated key(s) that start the run (scanner sync pulse, "
                         "or press one yourself to test)")
    ap.add_argument('--duration', type=float, default=None,
                    help='total run length in seconds (default: end of the last event); '
                         'pass nVols*TR to also show trailing rest')
    ap.add_argument('--flicker-hz', type=float, default=2.0,
                    help='how many times per second the checkerboard changes state during ON '
                         'blocks (default 2): OFF (blank) -> ON (pattern A) -> OFF -> ON '
                         '(pattern B, the black<->white inverse of A) -> repeat, each state '
                         'lasting 1/flicker_hz -- so the same screen location genuinely goes '
                         'black, then white, then black, rather than swapping directly between '
                         'two checkerboards with no blank in between')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/checkerboard_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core

    events = common.read_events_tsv(args.events)
    print(f"[checkerboard_1cond] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"checkerboard_1cond_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    tex_on, tex_off = build_checker_textures(win)
    fixation = visual.TextStim(win, text='+', color='lime', height=0.1)
    flicker_hz = args.flicker_hz

    def stim_for(trial_type, t_in_event, duration):
        if trial_type == 'checkerboard':
            # True flicker: fully OFF (blank -- nothing drawn, so the
            # window's black background shows through) between each ON
            # flash, and the ON flash itself alternates which squares are
            # black vs white (tex_on/tex_off) so a given screen location
            # genuinely reverses polarity from one flash to the next,
            # rather than looking like a static image with two very
            # similar-looking patterns swapped underneath it.
            phase = int(t_in_event * flicker_hz) % 4
            if phase == 1:
                return tex_on
            elif phase == 3:
                return tex_off
            return None   # phase 0 or 2: blank
        return fixation

    instructions = (
        "CHECKERBOARD VIEWING TASK\n\n"
        "You will see a flickering black-and-white checkerboard pattern, alternating "
        "with a plain + fixation cross.\n\n"
        "Goal: keep your eyes fixed on the CENTER of the screen THE WHOLE TIME -- on "
        "the + cross when it is showing, and on the center of the checkerboard while "
        "it is on screen. Do not let your eyes wander around the checkerboard or look "
        "away from the center, even though the pattern is flickering. No response or "
        "button press is needed during the task -- just keep your eyes on the center "
        "and stay still.\n\n"
        "If you have any questions, ask the experimenter now. When you are "
        "comfortable, press any button to continue.")
    if common.show_instructions(win, instructions):
        core.quit()

    clock, t0 = common.wait_for_trigger(win, trigger_keys=args.trigger_key.split(','),
                                        instructions='Waiting for scanner trigger...')
    print(f"[checkerboard_1cond] triggered at t0={t0:.3f}s -- starting task")
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
