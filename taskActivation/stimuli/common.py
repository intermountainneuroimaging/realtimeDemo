"""-----------------------------------------------------------------------------
stimuli/common.py -- shared PsychoPy helpers for the task scripts in this
folder (hcp_motor_task.py, hcp_gambling_task.py).

These run on the STIMULUS computer, presenting the task to the subject while
taskActivation.py (in the container, on the analysis side) analyzes the
incoming scanner DICOMs in real time. Both sides read the SAME
study_design/*_events.tsv files -- rt_analysis.py's own events reader is
reused here (imported from utils/) -- so the timing actually presented to the
subject can never drift out of sync with what the real-time analysis assumes.

Not part of the analysis pipeline itself; nothing in taskActivation.py
imports this folder.
-----------------------------------------------------------------------------"""
import os
import sys
import csv

HERE = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.append(os.path.join(PROJECT_ROOT, 'utils'))
import rt_analysis as mrt  # noqa: E402 -- import after the sys.path setup above

read_events_tsv = mrt.read_events_tsv  # re-exported for convenience


def show_instructions(win, text, continue_keys=('space', 'escape')):
    """Show a task-instructions screen (task description + the subject's
    goal) and block until a continue key is pressed -- shown before
    wait_for_trigger()'s own "Waiting for scanner..." screen, so the subject
    sees what they're about to do before the run starts. Returns True if
    Escape was pressed instead of continuing (caller should return early)."""
    from psychopy import visual, event
    msg = visual.TextStim(win, text=text, color='white', height=0.05, wrapWidth=1.6)
    msg.draw()
    win.flip()
    keys = event.waitKeys(keyList=list(continue_keys))
    return keys[0] == 'escape'


def wait_for_trigger(win, trigger_keys=('5', 't'), instructions='Waiting for scanner...'):
    """Show `instructions` and block until one of `trigger_keys` is pressed
    (wire the scanner's sync pulse to send one of these -- '5' and 't' are
    the two most common site conventions; press it yourself on the keyboard
    to test without a scanner). Returns (clock, t0): a running PsychoPy Clock
    and the precise time of the trigger keypress on it. Pass both straight
    into run_events() so every event is timed relative to the actual
    first-volume trigger, not whenever the script happened to start."""
    from psychopy import visual, core, event
    clock = core.Clock()
    msg = visual.TextStim(win, text=instructions, color='white', height=0.08, wrapWidth=1.6)
    msg.draw()
    win.flip()
    keys = event.waitKeys(keyList=list(trigger_keys), timeStamped=clock)
    t0 = keys[0][1]
    return clock, t0


def run_events(win, events, stim_for, clock, t0, run_duration=None, log_path=None):
    """Continuously render `win` for the whole run, computing what to show at
    each frame from `events` (onset, duration, trial_type triples, seconds
    relative to the trigger) as time passes on `clock` since `t0`.

    `stim_for(trial_type, t_in_event, duration)` returns the stimulus to draw
    this frame (anything with a .draw() method), or None to just blank the
    screen. Called with `trial_type=None` whenever no event is active (before
    the first event, and in any gap/rest between events) -- have it return a
    fixation stim for that case. `t_in_event` is seconds since the CURRENT
    event's own onset, so a task can show different things across one
    event's duration (e.g. a brief guess phase before a feedback phase).

    `run_duration` (seconds; default: the last event's own onset+duration)
    sets how long to keep running past the last scheduled event -- pass the
    real scan length (nVols * TR) if you want trailing rest displayed too.

    Press Escape at any time to abort early. If `log_path` is given, writes
    one row per event (expected vs actual onset time, in seconds) so real
    presentation accuracy can be checked against the design afterward."""
    from psychopy import core, event
    events = list(events)
    end_of_run = run_duration if run_duration is not None else (
        max(o + d for o, d, _ in events) if events else 0.0)
    log_rows = [('trial_type', 'expected_onset', 'actual_onset', 'error_s', 'duration')]
    logged = set()
    idx, n = 0, len(events)
    while True:
        now = clock.getTime() - t0
        if now >= end_of_run:
            break
        while idx < n and now >= events[idx][0] + events[idx][1]:
            idx += 1
        if idx < n and now >= events[idx][0]:
            onset, duration, trial_type = events[idx]
            if idx not in logged:
                logged.add(idx)
                log_rows.append((trial_type, f'{onset:.3f}', f'{now:.3f}',
                                 f'{now - onset:+.3f}', f'{duration:.3f}'))
            stim = stim_for(trial_type, now - onset, duration)
        else:
            stim = stim_for(None, 0.0, 0.0)
        if stim is not None:
            stim.draw()
        win.flip()
        if event.getKeys(keyList=['escape']):
            print('[stimuli] Escape pressed -- aborting early.')
            break
    _write_log(log_path, log_rows)


def _write_log(log_path, rows):
    if not log_path:
        return
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', newline='') as f:
        csv.writer(f, delimiter='\t').writerows(rows)
    print(f"[stimuli] wrote timing log: {log_path}")
