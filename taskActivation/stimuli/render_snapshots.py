#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
render_snapshots.py -- save one PsychoPy SNAPSHOT of every screen a participant
sees, for each task, into templates/stimulus_snapshots/<task>/<screen>.png.

These are the stimulus thumbnails utils/make_templates.py drops into the corner
of each task's pre-data "template" current.png. They are drawn by the SAME stim
builders the real tasks use (generic_motor_task.build_stims,
checkerboard_*_task.build_checker_*, blackjack_task.build_stims), so a snapshot
can't drift from what the task actually shows -- change a task's stimuli, re-run
this, then re-run make_templates.py.

Needs PsychoPy and a display (a small windowed window opens briefly). On this
project's dev machine that's the `psychopy-env` conda env:
    source ~/opt/miniconda3/etc/profile.d/conda.sh && conda activate psychopy-env
    python stimuli/render_snapshots.py

The snapshots are committed, so make_templates.py itself does NOT need PsychoPy --
only re-run this when a task's on-screen stimuli change.
-----------------------------------------------------------------------------"""
import os
import argparse
import random
import common

DEFAULT_OUT = os.path.join(common.PROJECT_ROOT, 'templates', 'stimulus_snapshots')


def _save(win, path):
    """Flip what was just drawn, grab that frame, write it as a PNG."""
    win.flip()
    win.getMovieFrame(buffer='front')
    frame = win.movieFrames.pop()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame.save(path)
    print(f"[snapshot] {os.path.relpath(path, common.PROJECT_ROOT)}")


def snapshots_motor(win, shoot):
    import generic_motor_task
    stims, fixation = generic_motor_task.build_stims(win)
    fixation.draw(); shoot('motor', 'rest')
    stims['left_hand'].draw(); shoot('motor', 'left_hand')
    stims['right_hand'].draw(); shoot('motor', 'right_hand')


def snapshots_motor_guessing(win, shoot):
    import motor_guessing_task
    stims, fixation = motor_guessing_task.build_stims(win)
    fixation.draw(); shoot('motor_guessing', 'rest')
    stims['move'].draw(); shoot('motor_guessing', 'move')


def snapshots_checkerboard_1cond(win, shoot):
    from psychopy import visual
    import checkerboard_1cond_task as t
    tex_on, _ = t.build_checker_textures(win)
    fixation = visual.TextStim(win, text='+', color='lime', height=0.1)
    fixation.draw(); shoot('checkerboard_1cond', 'rest')
    tex_on.draw(); shoot('checkerboard_1cond', 'checkerboard')   # ON phase, pattern A


def snapshots_checkerboard_2cond(win, shoot):
    from psychopy import visual
    import checkerboard_2cond_task as t
    stims = t.build_checker_stims(win)
    fixation = visual.TextStim(win, text='+', color='lime', height=0.1)
    t._LeftRightStim(None, fixation).draw(); shoot('checkerboard_2cond', 'rest')
    for pos in ('left', 'right'):
        t._LeftRightStim(stims[pos]['A'], fixation).draw()
        shoot('checkerboard_2cond', pos)


def snapshots_checkerboard_3cond(win, shoot):
    from psychopy import visual
    import checkerboard_3cond_task as t
    stims = t.build_checker_stims(win)
    fixation = visual.TextStim(win, text='+', color='lime', height=0.1)
    t._CenterLeftRightStim(None, fixation).draw(); shoot('checkerboard_3cond', 'rest')
    for pos in ('center', 'left', 'right'):
        t._CenterLeftRightStim(stims[pos]['A'], fixation).draw()
        shoot('checkerboard_3cond', pos)


def snapshots_gambling(win, shoot):
    """blackjack_task.py's screens: ITI fixation, the hit/stay DECISION screen,
    and the WIN / LOSE / TIE outcome screens (a STAY on a fixed random hand --
    the same draw order as blackjack_task.main()'s loop)."""
    import blackjack_task as t
    random.seed(7)   # a fixed, plausible hand per outcome, so re-renders are reproducible
    stims = t.build_stims(win)

    def fit_hand(hand):
        text = t.format_hand(hand)
        stims['hand'].text = text
        common.fit_text_stim(win, stims['hand'], base_height=0.12, max_w_frac=0.8, max_h_frac=0.22)
        stims['hand_small'].text = text
        common.fit_text_stim(win, stims['hand_small'], base_height=0.06, max_w_frac=0.7, max_h_frac=0.08)

    stims['fixation'].draw(); shoot('gambling', 'rest')

    fit_hand(t.deal_initial_hand('win'))
    stims['hand'].draw(); stims['prompt'].draw(); shoot('gambling', 'decision')

    for outcome in ('win', 'lose', 'tie'):
        hand = t.deal_initial_hand(outcome)
        fit_hand(hand)
        if outcome == 'lose':
            stims['outcomes']['lose'].text = t.lose_text(hand)
            common.fit_text_stim(win, stims['outcomes']['lose'], base_height=0.14,
                                 max_w_frac=0.6, max_h_frac=0.35)
        stims['hand_small'].draw(); stims['outcomes'][outcome].draw()
        shoot('gambling', outcome)


ALL = {
    'motor': snapshots_motor,
    'motor_guessing': snapshots_motor_guessing,
    'checkerboard_1cond': snapshots_checkerboard_1cond,
    'checkerboard_2cond': snapshots_checkerboard_2cond,
    'checkerboard_3cond': snapshots_checkerboard_3cond,
    'gambling': snapshots_gambling,
}


def main():
    ap = argparse.ArgumentParser(description="Save PsychoPy stimulus snapshots for the template images.")
    ap.add_argument('tasks', nargs='*', help=f"tasks to render (default: all of {', '.join(sorted(ALL))})")
    ap.add_argument('--out-dir', default=DEFAULT_OUT)
    ap.add_argument('--size', default='960x540', help='window size WxH in px (16:9; default 960x540)')
    args = ap.parse_args()
    bad = [t for t in args.tasks if t not in ALL]
    if bad:
        ap.error(f"unknown task(s) {bad}; choose from {sorted(ALL)}")

    from psychopy import visual
    w, h = (int(v) for v in args.size.lower().split('x'))
    # useRetina=False: one framebuffer pixel per requested pixel, so the saved size is exactly --size
    win = visual.Window(size=(w, h), fullscr=False, color='black', units='height',
                        useRetina=False, allowGUI=False)
    try:
        def shoot(task, screen):
            _save(win, os.path.join(args.out_dir, task, f'{screen}.png'))
        for name in (args.tasks or sorted(ALL)):
            ALL[name](win, shoot)
    finally:
        win.close()


if __name__ == '__main__':
    main()
