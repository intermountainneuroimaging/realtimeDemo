#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
blackjack_task.py -- simple PsychoPy presentation of this project's own
two-card blackjack task (study_design/Blackjack_events.tsv, the same file
taskActivation.py's live analysis reads via conf/gambling.toml). The
Psychtoolbox equivalent is stimuli_ptb/blackjack_task.m -- both present the
exact same events.tsv. The original HCP card-guess task (hcp_gambling_task.py
/ gambling_task.m, HcpGambling_acq-ap_events.tsv) is untouched and still used
by tutorial/'s offline validation against the real ds000244 data.

Each trial (a fixed 3.0s in Blackjack_events.tsv): two cards are dealt
face-up, and the subject may press '1' to HIT or '2' to STAY, any time
during a 2.0s decision window. Whichever comes first: the SAME instant the
subject responds, HIT deals one more card and immediately reveals the
outcome; STAY immediately reveals the outcome with the current hand --
there's no waiting for the rest of the decision window once an answer is
given. The outcome (shown for whatever time is left in the trial, at least
1.0s): green WIN +$1.00, gray TIE $0.00, or red -$0.50 -- labeled BUST or
DEALER WON, depending on the cosmetic hand's own blackjack value (see
hand_value() below). Which outcome appears and when is entirely driven by
the events.tsv -- the displayed
cards and the hit/stay choice are cosmetic only and never alter the
scheduled result, exactly matching taskActivation.py's GLM contrast
(glmCondA=win, glmCondB=lose, tie as a covariate). Trials are separated by
a variable inter-trial interval (jittered 1.0-3.0s, ~2s mean) of plain
fixation, so the design isn't perfectly periodic. 58 trials (24 win / 24
lose / 10 tie), ~5 minutes total.

THE DEALT CARDS ARE ALWAYS CONSISTENT WITH THE TRIAL'S OUTCOME: the initial
two-card hand is never a natural blackjack (an Ace paired with a 10-value
card, value 21) on ANY trial -- a 2-card 21 is unbeatable in real
blackjack, so it's excluded outright. Beyond that, the hand's own
(cosmetic) blackjack value is drawn from a range that actually fits the
trial's pre-scripted outcome -- see deal_initial_hand() below. On a LOSE
trial, no card is ever an Ace, and the initial value is 12-20 (never an
implausible near-certain loss, never already busted). On a WIN trial, the
initial value is 16-20 (a strong hand) or under 10 (an early hand with
room to grow) -- never the awkward 10-15 middle. TIE trials are
unconstrained beyond the universal no-natural-blackjack rule. And
whichever card a HIT deals (see deal_hit_card() below) never busts the
hand on a WIN or TIE trial, and never brings it to exactly 21 on a LOSE
trial -- a real blackjack hand
can't win/tie while busted, or lose while sitting on a clean 21.

NO RESPONSE = NO REWARD/LOSS: if the subject doesn't press '1' or '2' during
the decision phase, the feedback shown is gray "No response $0.00" instead
of the trial's scheduled outcome -- a display-only change; the events.tsv /
GLM design driving the real-time analysis are unaffected.

Shows a brief task-instructions screen (task description + the subject's
goal; dismiss with SPACE, or Escape to abort) before waiting for the
scanner trigger.

CARD/PROMPT/OUTCOME TEXT FITS THE ACTUAL WINDOW, AT ANY RESOLUTION: like the
instructions screen (see common.fit_text_stim()), the hand, "1 = HIT / 2 =
STAY" prompt, and outcome text are each sized against the real window and
given their own non-overlapping vertical region -- so nothing runs
off-screen or overlaps at any resolution, whether the hand has two cards or
three.

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
    'lose': dict(color='red'),   # text is dynamic (BUST vs DEALER WON) -- see lose_text() below
    'tie':  dict(text='TIE\n$0.00', color='gray'),
}
DECISION_S = 2.0        # max hit/stay decision phase, at the start of each trial (ends
                        # the instant the subject responds -- see the module docstring);
                        # Blackjack_events.tsv gives every trial a fixed 3.0s duration,
                        # so the outcome always gets at least 1.0s

# A hand is at most the 2 initial cards + 1 hit -- never more than 3, since
# any response (hit or stay) ends the decision phase immediately.

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
TEN_RANKS = {'10', 'J', 'Q', 'K'}
SUITS = {'H': '♥', 'D': '♦', 'C': '♣', 'S': '♠'}


def deal_card(exclude_ranks=()):
    rank = random.choice([r for r in RANKS if r not in exclude_ranks])
    suit = random.choice(list(SUITS))
    return rank, suit


INITIAL_HAND_ATTEMPTS = 300   # rejection-sampling cap -- see deal_initial_hand()


def deal_initial_hand(trial_type='tie'):
    """Two cosmetic cards, drawn so their (cosmetic) blackjack value lines
    up with how plausible the trial's pre-scripted outcome actually is.
    The opening hand is NEVER a natural blackjack (an Ace paired with a
    10-value card, value 21) on ANY trial -- a 2-card 21 is unbeatable in
    real blackjack, so it's excluded outright rather than tied to a
    specific outcome. On top of that:
      - LOSE: no Aces at all (a losing hand that could show an Ace and a
        10-value card would look like an impossible blackjack loss -- see
        the module docstring), and a value between 12 and 20 -- a hand
        that's neither an implausible near-certain loss nor obviously
        about to bust.
      - WIN: a value of 16-20 (a strong hand) or under 10 (an early hand
        with plenty of room) -- never the awkward 10-15 middle where
        staying to win would look odd.
      - TIE (or anything else): unconstrained beyond the universal
        no-natural-blackjack rule above.
    Plain rejection sampling: both target ranges above cover the majority
    of possible hands, so this converges in a couple of draws on average;
    INITIAL_HAND_ATTEMPTS is a generous cap that guarantees it terminates
    even in the unlikely worst case."""
    allow_ace = trial_type != 'lose'

    def in_target_range(value):
        if trial_type == 'lose':
            return 12 <= value <= 20
        if trial_type == 'win':
            return (16 <= value <= 20) or value < 10
        return True

    hand = None
    for _ in range(INITIAL_HAND_ATTEMPTS):
        exclude = set() if allow_ace else {'A'}
        rank1, suit1 = deal_card(exclude_ranks=exclude)
        if rank1 == 'A':
            card2 = deal_card(exclude_ranks=exclude | TEN_RANKS)
        elif rank1 in TEN_RANKS:
            card2 = deal_card(exclude_ranks=exclude | {'A'})
        else:
            card2 = deal_card(exclude_ranks=exclude)
        hand = [(rank1, suit1), card2]
        if in_target_range(hand_value(hand)):
            return hand
    return hand


def format_hand(hand):
    return '   '.join(f'{rank}{SUITS[suit]}' for rank, suit in hand)


def hand_value(hand):
    """Standard blackjack scoring of the cosmetic hand: number cards count
    at face value, face cards (J/Q/K) are worth 10, Aces are worth 11
    (downgraded to 1 one at a time to avoid busting, if possible) -- used
    only to decide whether a LOSE trial's feedback says BUST or DEALER WON
    (see lose_text() below); the real win/lose/tie outcome stays whatever
    Blackjack_events.tsv scheduled, regardless of this value."""
    total, aces = 0, 0
    for rank, _ in hand:
        if rank == 'A':
            total += 11
            aces += 1
        elif rank in ('J', 'Q', 'K'):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def lose_text(hand):
    reason = 'BUST' if hand_value(hand) > 21 else 'DEALER WON'
    return f'{reason}\n−$0.50'


def deal_hit_card(hand, trial_type):
    """Pick a HIT card that keeps the cosmetic hand's value consistent with
    the trial's pre-scripted outcome -- a real blackjack hand can never
    win/tie while busted, and can never lose while sitting on a clean 21:
    - on a WIN or TIE trial, never deal a card that would push the hand
      over 21 (bust)
    - on a LOSE trial, never deal a card that would bring the hand to
      exactly 21 (Aces are already excluded entirely on LOSE trials -- see
      deal_initial_hand() -- so this only has to watch for 10-value cards
      completing a 21)
    Falls back to any card if every rank would violate the rule (e.g. the
    hand is already at 21 before the hit, so any card busts it -- there's
    no avoiding that one)."""
    candidates = [r for r in RANKS if not (trial_type == 'lose' and r == 'A')]
    safe = []
    for rank in candidates:
        value = hand_value(hand + [(rank, 'H')])
        if trial_type in ('win', 'tie') and value > 21:
            continue
        if trial_type == 'lose' and value == 21:
            continue
        safe.append(rank)
    rank = random.choice(safe or candidates)
    suit = random.choice(list(SUITS))
    return rank, suit


def build_stims(win):
    """Stims reused across frames -- see hcp_motor_task's build_stims for why
    (PsychoPy stims are drawn every frame, so avoid rebuilding text/geometry
    each time). Card-hand text changes every trial (and once more on a hit),
    so its stim's `.text` is reassigned (and refit -- see fit_hand() in
    main() below) in the main loop rather than rebuilt from scratch.

    Each element gets its own non-overlapping vertical `pos` slot -- hand
    above center, prompt below, in the decision phase; small hand near the
    top, outcome in the middle, once the outcome is revealed -- and a
    wrapWidth clamped to this window's own aspect ratio, so wrapped lines
    can't run wider than the window actually is at any resolution."""
    from psychopy import visual
    win_w_px, win_h_px = win.size
    aspect = win_w_px / win_h_px
    wrap_width = min(1.6, 0.82 * aspect)

    hand_stim = visual.TextStim(win, text='', color='white', wrapWidth=wrap_width, pos=(0, 0.20))
    prompt_stim = visual.TextStim(win, text='1 = HIT      2 = STAY', color='white',
                                  wrapWidth=wrap_width, pos=(0, -0.22))
    hand_small_stim = visual.TextStim(win, text='', color=(0.6, 0.6, 0.6),
                                      wrapWidth=wrap_width, pos=(0, 0.32))
    outcomes = {}
    for trial_type, style in OUTCOME_STYLE.items():
        outcomes[trial_type] = visual.TextStim(win, text=style.get('text', ''), color=style['color'],
                                               bold=True, wrapWidth=wrap_width, pos=(0, -0.05))
    no_response_stim = visual.TextStim(win, text='No response\n$0.00', color='gray',
                                       wrapWidth=wrap_width)
    fixation = visual.TextStim(win, text='+', color='white', height=0.1)

    # fixed-text stims never change again after this, so fit them once up front --
    # 'lose' is dynamic (BUST vs DEALER WON depends on the hand) and gets refit
    # each trial instead, in main()'s fit_hand()/response handling below
    common.fit_text_stim(win, prompt_stim, base_height=0.06, max_w_frac=0.6, max_h_frac=0.10)
    common.fit_text_stim(win, no_response_stim, base_height=0.1, max_w_frac=0.6, max_h_frac=0.3)
    common.fit_text_stim(win, outcomes['win'], base_height=0.14, max_w_frac=0.6, max_h_frac=0.35)
    common.fit_text_stim(win, outcomes['tie'], base_height=0.14, max_w_frac=0.6, max_h_frac=0.35)

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
        "The goal of the game is to get as close to 21 points as possible, "
        "without going over. Add up the value of the cards in your hand: "
        "number cards are worth their face value, face cards (J, Q, K) are "
        "worth 10 points, and Aces are worth 1 or 11 points. Going over 21 "
        "points means you BUST. If you have more points than the dealer "
        "without busting, you WIN!\n\n"
        "Each round you will be dealt two cards. Press 1 to HIT (take another "
        "card) or press 2 to STAY (keep your current hand). You will then see "
        "whether you WON (+$1.00), LOST (-$0.50), or TIED ($0.00) that "
        "round.\n\n"
        "Goal: win money by getting the best hand without going BUST. "
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

    def fit_hand(hand):
        """Refit both hand stims to this hand's text -- called only when the
        hand's cards actually change (initial deal, or a hit), not every
        frame (see common.fit_text_stim())."""
        hand_text = format_hand(hand)
        stims['hand'].text = hand_text
        common.fit_text_stim(win, stims['hand'], base_height=0.12, max_w_frac=0.8, max_h_frac=0.22)
        stims['hand_small'].text = hand_text
        common.fit_text_stim(win, stims['hand_small'], base_height=0.06, max_w_frac=0.7, max_h_frac=0.08)

    def fit_lose_outcome(hand):
        """Refit the LOSE outcome stim's text -- BUST or DEALER WON, depending
        on the (cosmetic) hand's blackjack value -- called once, right when a
        LOSE trial's outcome is about to be revealed (its hand is already
        final by then)."""
        stims['outcomes']['lose'].text = lose_text(hand)
        common.fit_text_stim(win, stims['outcomes']['lose'], base_height=0.14,
                             max_w_frac=0.6, max_h_frac=0.35)

    idx, n = 0, len(events)
    logged_onset = set()
    hand = None
    response_time = None   # t_in_event of the hit/stay response, if any --
                           # the decision phase ends the INSTANT this is set
    action_taken = 'none'  # '1', '2', or 'none'
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
                             action_taken, f'{last_action_time:.3f}' if action_taken != 'none' else 'nan'))
            idx += 1
            hand, response_time, action_taken = None, None, 'none'
            last_action_time = float('nan')

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
                    hand = deal_initial_hand(trial_type)
                    fit_hand(hand)
                decision_deadline = min(DECISION_S, duration)   # clamp in case a trial
                                                                 # is ever shorter than DECISION_S

                # Only the FIRST hit/stay counts -- the instant either key is
                # pressed, the decision phase ends and the outcome (with the
                # extra card, if HIT) is shown right away, for whatever time
                # is left in the trial.
                if response_time is None and t_in_event < decision_deadline:
                    for key_name, key_time in keys:
                        if key_name in ('1', '2'):
                            response_time = t_in_event
                            action_taken = key_name
                            last_action_time = key_time - t0 - onset
                            if key_name == '1':
                                hand.append(deal_hit_card(hand, trial_type))
                                fit_hand(hand)
                            if trial_type == 'lose':
                                fit_lose_outcome(hand)
                            break

                if response_time is None:
                    if t_in_event < decision_deadline:
                        stims['hand'].draw()
                        stims['prompt'].draw()
                    else:
                        # decision window fully elapsed with no response -- no
                        # reward/loss for this trial, regardless of what the
                        # scheduled outcome would have been (the events.tsv /
                        # GLM design are unaffected; this only changes what's
                        # shown to the subject)
                        stims['no_response'].draw()
                else:
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
                         action_taken, f'{last_action_time:.3f}' if action_taken != 'none' else 'nan'))

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
