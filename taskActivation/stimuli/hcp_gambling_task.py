#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
hcp_gambling_task.py -- simple PsychoPy presentation of the HcpGambling task
(ds000244 timing, the same study_design/HcpGambling_acq-ap_events.tsv
taskActivation.py's live pipeline reads via conf/gambling.toml -- also a copy
of the one tutorial/'s offline validation uses), so this project's second
worked example (reward vs punishment, neutral as a covariate) can also be
run with a real task on the stimulus computer.

Each trial: the subject briefly guesses whether a hidden card is higher or
lower (any button press -- as in the real HCP task, the guess doesn't
actually change the outcome), then a feedback outcome is shown for the rest
of the trial. Which outcome (reward/punishment/neutral) and when is entirely
driven by the events.tsv, matching exactly what taskActivation.py's GLM
contrast (glmCondA=reward, glmCondB=punishment, neutral as a covariate)
expects -- rest is implicit in the gaps between trials.

Run (needs `pip install psychopy` and a display):
    python hcp_gambling_task.py                    # waits for scanner trigger '5' or 't'
    python hcp_gambling_task.py --windowed          # not fullscreen, for testing
    python hcp_gambling_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import argparse
import datetime
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design',
                              'HcpGambling_acq-ap_events.tsv')

OUTCOME_STYLE = {
    'reward':     dict(text='+$1.00', color='lime'),
    'punishment': dict(text='−$0.50', color='red'),
    'neutral':    dict(text='$0.00', color='gray'),
}
GUESS_MAX_S = 1.5       # cap on the guess phase, at the start of each trial
GUESS_FRACTION = 0.4    # ...or this fraction of the trial's own duration, if shorter


def build_stims(win):
    """Guess-phase + outcome stims, built once up front (see hcp_motor_task's
    build_stims for why: PsychoPy stims are drawn every frame, so reusing the
    same objects avoids rebuilding text/geometry each time)."""
    from psychopy import visual
    guess = visual.TextStim(win, text='?\n\nHigher or Lower?\n(press any button)',
                            color='white', height=0.08)
    outcomes = {}
    for trial_type, style in OUTCOME_STYLE.items():
        outcomes[trial_type] = visual.TextStim(win, text=style['text'], color=style['color'],
                                               bold=True, height=0.18)
    fixation = visual.TextStim(win, text='+', color='white', height=0.1)
    return guess, outcomes, fixation


def main():
    ap = argparse.ArgumentParser(description='Present the HcpGambling task (PsychoPy).')
    ap.add_argument('--events', default=DEFAULT_EVENTS, help='events.tsv to present')
    ap.add_argument('--trigger-key', default='5,t',
                    help="comma-separated key(s) that start the run (scanner sync pulse, "
                         "or press one yourself to test)")
    ap.add_argument('--duration', type=float, default=None,
                    help='total run length in seconds (default: end of the last event); '
                         'pass nVols*TR to also show trailing rest')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/hcp_gambling_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core, event

    events = common.read_events_tsv(args.events)
    print(f"[hcp_gambling] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"hcp_gambling_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    guess_stim, outcome_stims, fixation = build_stims(win)

    def stim_for(trial_type, t_in_event, duration):
        if trial_type not in OUTCOME_STYLE:
            return fixation
        event.getKeys()   # let the subject "answer" during the guess phase; not scored --
                          # the real HCP task's feedback is predetermined, not contingent
                          # on the guess, and neither is this one
        guess_dur = min(GUESS_MAX_S, duration * GUESS_FRACTION)
        if t_in_event < guess_dur:
            return guess_stim
        return outcome_stims[trial_type]

    clock, t0 = common.wait_for_trigger(win, trigger_keys=args.trigger_key.split(','),
                                        instructions='Waiting for scanner trigger...')
    print(f"[hcp_gambling] triggered at t0={t0:.3f}s -- starting task")
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
