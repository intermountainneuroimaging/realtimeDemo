#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
blackjack_task.py -- simple PsychoPy presentation of this project's own
two-card blackjack task (study_design/Blackjack_events.tsv, the same file
taskActivation.py's live analysis reads via conf/gambling.toml). The
Psychtoolbox equivalent is stimuli_ptb/blackjack_task.m -- both present the
exact same events.tsv. The original HCP card-guess task (hcp_gambling_task.py
/ gambling_task.m, HcpGambling_acq-ap_events.tsv) is untouched and still used
by tutorial/'s offline validation against the real ds000244 data.

Each trial: two cards are dealt face-up, and the subject may press '1' to
HIT (deal one more card) or '2' to STAY (freeze the hand) during a brief
decision window; then a feedback outcome is shown for the rest of the trial:
green WIN +$1.00, red LOSE -$0.50, or gray TIE $0.00. Which outcome appears
and when is entirely driven by the events.tsv -- the displayed cards and the
hit/stay choice are cosmetic only and never alter the scheduled result,
exactly matching taskActivation.py's GLM contrast (glmCondA=win,
glmCondB=lose, tie as a covariate).

THE DEALT CARDS ARE NEVER A NATURAL BLACKJACK: the initial two-card hand is
never an Ace paired with a 10-value card (10/J/Q/K) -- see
deal_initial_hand() below -- so the visible hand can never look like an
automatic win regardless of the trial's actual (pre-scripted) outcome.

NO RESPONSE = NO REWARD/LOSS: if the subject doesn't press '1' or '2' during
the decision phase, the feedback shown is gray "No response $0.00" instead
of the trial's scheduled outcome -- a display-only change; the events.tsv /
GLM design driving the real-time analysis are unaffected.

Shows a brief task-instructions screen (task description + the subject's
goal; dismiss with SPACE, or Escape to abort) before waiting for the
scanner trigger.

This script uses its OWN per-frame render loop (rather than common.py's
shared run_events()) for the same reason gambling_task.m uses its own loop
instead of the shared Psychtoolbox one: hit/stay needs per-frame key
handling and a hand of cards that can change mid-trial, plus a response log
(response_key / response_time_s) that common.run_events()'s fixed log
schema doesn't carry. It still uses common.wait_for_trigger() and
common.read_events_tsv() for everything else.

Run (needs `pip install psychopy` and a display):
    python blackjack_task.py                    # waits for scanner trigger '5' or 't'
    python blackjack_task.py --windowed          # not fullscreen, for testing
    python blackjack_task.py --trigger-key space # press space yourself to start
-----------------------------------------------------------------------------"""
import os
import csv
import random
import argparse
import datetime
import common

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_EVENTS = os.path.join(common.PROJECT_ROOT, 'study_design', 'Blackjack_events.tsv')

OUTCOME_STYLE = {
    'win':  dict(text='WIN\n+$1.00', color='lime'),
    'lose': dict(text='LOSE\n−$0.50', color='red'),
    'tie':  dict(text='TIE\n$0.00', color='gray'),
}
GUESS_MAX_S = 1.5       # cap on the hit/stay decision phase, at the start of each trial
GUESS_FRACTION = 0.4    # ...or this fraction of the trial's own duration, if shorter
MAX_HAND_SIZE = 5       # cosmetic cap on cards in a hand (a held/bouncing key can't blow past this)

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
TEN_RANKS = {'10', 'J', 'Q', 'K'}
SUITS = {'H': '♥', 'D': '♦', 'C': '♣', 'S': '♠'}


def deal_card(exclude_ranks=()):
    rank = random.choice([r for r in RANKS if r not in exclude_ranks])
    suit = random.choice(list(SUITS))
    return rank, suit


def deal_initial_hand():
    """Two cosmetic cards, never a natural blackjack (an Ace paired with a
    10-value card) -- see this file's own module docstring."""
    rank1, suit1 = deal_card()
    if rank1 == 'A':
        card2 = deal_card(exclude_ranks=TEN_RANKS)
    elif rank1 in TEN_RANKS:
        card2 = deal_card(exclude_ranks={'A'})
    else:
        card2 = deal_card()
    return [(rank1, suit1), card2]


def format_hand(hand):
    return '   '.join(f'{rank}{SUITS[suit]}' for rank, suit in hand)


def build_stims(win):
    """Stims reused across frames -- see hcp_motor_task's build_stims for why
    (PsychoPy stims are drawn every frame, so avoid rebuilding text/geometry
    each time). Card-hand text changes every trial (and mid-trial on a hit),
    so its stim's `.text` is reassigned in the main loop below rather than
    rebuilt from scratch."""
    from psychopy import visual
    hand_stim = visual.TextStim(win, text='', color='white', height=0.1, pos=(0, 0.12))
    prompt_stim = visual.TextStim(win, text='1 = HIT      2 = STAY', color='white', height=0.06,
                                  pos=(0, -0.15))
    hand_small_stim = visual.TextStim(win, text='', color=(0.6, 0.6, 0.6), height=0.06,
                                      pos=(0, 0.3))
    outcomes = {}
    for trial_type, style in OUTCOME_STYLE.items():
        outcomes[trial_type] = visual.TextStim(win, text=style['text'], color=style['color'],
                                               bold=True, height=0.14)
    no_response_stim = visual.TextStim(win, text='No response\n$0.00', color='gray', height=0.1)
    fixation = visual.TextStim(win, text='+', color='white', height=0.1)
    return dict(hand=hand_stim, prompt=prompt_stim, hand_small=hand_small_stim,
                outcomes=outcomes, no_response=no_response_stim, fixation=fixation)


def main():
    ap = argparse.ArgumentParser(description='Present the Blackjack task (PsychoPy).')
    ap.add_argument('--events', default=DEFAULT_EVENTS, help='events.tsv to present')
    ap.add_argument('--trigger-key', default='5,t',
                    help="comma-separated key(s) that start the run (scanner sync pulse, "
                         "or press one yourself to test)")
    ap.add_argument('--duration', type=float, default=None,
                    help='total run length in seconds (default: end of the last event); '
                         'pass nVols*TR to also show trailing rest')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    ap.add_argument('--log', default=None,
                    help='timing log path (default: stimuli/logs/blackjack_<timestamp>.tsv)')
    args = ap.parse_args()

    from psychopy import visual, core, event

    events = common.read_events_tsv(args.events)
    print(f"[blackjack] loaded {len(events)} events from {args.events}")

    log_path = args.log or os.path.join(
        HERE, 'logs', f"blackjack_{datetime.datetime.now():%Y%m%d_%H%M%S}.tsv")

    win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    stims = build_stims(win)

    instructions = (
        "BLACKJACK CARD TASK\n\n"
        "Each round you will be dealt two cards. Press 1 to HIT (take another "
        "card) or press 2 to STAY (keep your current hand). After your choice, "
        "you will see whether you WON (+$1.00), LOST (-$0.50), or TIED ($0.00) "
        "that round.\n\n"
        "Goal: choose HIT or STAY however you think will win you the most money. "
        "You must respond within the short decision window each round, or that "
        "round pays out nothing.\n\n"
        "Press SPACE when you are ready to begin.")
    if common.show_instructions(win, instructions):
        core.quit()

    clock, t0 = common.wait_for_trigger(win, trigger_keys=args.trigger_key.split(','),
                                        instructions='Waiting for scanner trigger...')
    print(f"[blackjack] triggered at t0={t0:.3f}s -- starting task")

    end_of_run = args.duration if args.duration is not None else (
        max(o + d for o, d, _ in events) if events else 0.0)
    log_rows = [('trial_type', 'expected_onset', 'actual_onset', 'error_s', 'duration',
                 'response_key', 'response_time_s')]

    idx, n = 0, len(events)
    logged_onset = set()
    hand = None
    frozen = False
    actions = []       # e.g. ['1', '1', '2'] for this trial
    last_action_time = float('nan')
    actual_onset = None
    aborted = False

    while True:
        now = clock.getTime() - t0
        if now >= end_of_run:
            break

        while idx < n and now >= events[idx][0] + events[idx][1]:
            log_rows.append((events[idx][2], f'{events[idx][0]:.3f}', f'{actual_onset:.3f}',
                             f'{actual_onset - events[idx][0]:+.3f}', f'{events[idx][1]:.3f}',
                             ';'.join(actions) if actions else 'none',
                             f'{last_action_time:.3f}' if actions else 'nan'))
            idx += 1
            hand, frozen, actions = None, False, []

        keys = event.getKeys(keyList=['1', '2', 'escape'], timeStamped=clock)
        if any(k[0] == 'escape' for k in keys):
            print('[stimuli] Escape pressed -- aborting early.')
            aborted = True
            break

        if idx < n and now >= events[idx][0]:
            onset, duration, trial_type = events[idx]
            if idx not in logged_onset:
                logged_onset.add(idx)
                actual_onset = now
            t_in_event = now - onset

            if trial_type in OUTCOME_STYLE:
                if hand is None:
                    hand = deal_initial_hand()
                guess_dur = min(GUESS_MAX_S, duration * GUESS_FRACTION)

                if t_in_event < guess_dur and not frozen:
                    for key_name, key_time in keys:
                        if key_name == '1' and len(hand) < MAX_HAND_SIZE:
                            hand.append(deal_card())
                        if key_name in ('1', '2'):
                            actions.append(key_name)
                            last_action_time = key_time - t0 - onset
                        if key_name == '2':
                            frozen = True

                if t_in_event < guess_dur:
                    stims['hand'].text = format_hand(hand)
                    stims['hand'].draw()
                    stims['prompt'].draw()
                elif not actions:
                    stims['no_response'].draw()
                else:
                    stims['hand_small'].text = format_hand(hand)
                    stims['hand_small'].draw()
                    stims['outcomes'][trial_type].draw()
            else:
                stims['fixation'].draw()
        else:
            stims['fixation'].draw()

        win.flip()

    # flush whichever trial was still active/unfinalized when the run ended
    if idx < n and idx in logged_onset:
        onset, duration, trial_type = events[idx]
        log_rows.append((trial_type, f'{onset:.3f}', f'{actual_onset:.3f}',
                         f'{actual_onset - onset:+.3f}', f'{duration:.3f}',
                         ';'.join(actions) if actions else 'none',
                         f'{last_action_time:.3f}' if actions else 'nan'))

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', newline='') as f:
        csv.writer(f, delimiter='\t').writerows(log_rows)
    print(f"[stimuli] wrote timing log: {log_path}")

    if not aborted:
        done = visual.TextStim(win, text='Task complete -- thank you!', color='white', height=0.06)
        done.draw()
        win.flip()
        core.wait(2.0)
    win.close()
    core.quit()


if __name__ == '__main__':
    main()
