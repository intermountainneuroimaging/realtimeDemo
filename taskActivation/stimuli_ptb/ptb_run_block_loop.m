function ptb_run_block_loop(win, events, stimForFn, t0, runDuration, logPath)
%PTB_RUN_BLOCK_LOOP Render `win` continuously, driven by `events` vs a clock.
%   PTB_RUN_BLOCK_LOOP(win, events, stimForFn, t0, runDuration, logPath)
%
%   events      - table from ptb_read_events_tsv.m (onset, duration,
%                 trial_type), seconds relative to the trigger.
%   stimForFn   - function handle stimForFn(win, trialType, tInEvent,
%                 duration) that DRAWS this frame's stimulus into `win`
%                 (Screen(...) calls; do not call Screen('Flip') yourself --
%                 this loop does that once per iteration). Called with
%                 trialType="" whenever no event is active (before the
%                 first event, and in any gap between events) -- draw
%                 fixation for that case.
%   t0          - GetSecs() timestamp of the trigger, from
%                 ptb_wait_for_trigger.m. Every `now` below is GetSecs()-t0.
%   runDuration - seconds to keep running past the last scheduled event
%                 (default: the last event's own onset+duration). Pass the
%                 real scan length (nVols*TR) to also show trailing rest.
%   logPath     - if non-empty, write one row per event (expected vs actual
%                 onset, in seconds) so real presentation accuracy can be
%                 checked against the design afterward.
%
%   Press Escape at any time to abort early.

    if nargin < 5 || isempty(runDuration)
        runDuration = max(events.onset + events.duration);
    end
    escKey = KbName('ESCAPE');
    nEvents = height(events);
    logged = false(nEvents, 1);
    logRows = cell(0, 5);
    idx = 1;

    while true
        now = GetSecs() - t0;
        if now >= runDuration
            break
        end
        while idx <= nEvents && now >= events.onset(idx) + events.duration(idx)
            idx = idx + 1;
        end
        if idx <= nEvents && now >= events.onset(idx)
            trialType = char(events.trial_type(idx));
            onset = events.onset(idx);
            duration = events.duration(idx);
            if ~logged(idx)
                logged(idx) = true;
                logRows(end + 1, :) = {trialType, onset, now, now - onset, duration}; %#ok<AGROW>
            end
            tInEvent = now - onset;
        else
            trialType = '';
            duration = 0;
            tInEvent = 0;
        end

        stimForFn(win, trialType, tInEvent, duration);
        Screen('Flip', win);

        [keyDown, ~, keyCode] = KbCheck;
        if keyDown && keyCode(escKey)
            fprintf('[stimuli] Escape pressed -- aborting early.\n');
            break
        end
    end

    ptb_write_event_log(logPath, ...
        {'trial_type', 'expected_onset', 'actual_onset', 'error_s', 'duration'}, logRows);
end
