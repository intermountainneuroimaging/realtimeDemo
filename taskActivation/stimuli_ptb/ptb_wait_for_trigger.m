function t0 = ptb_wait_for_trigger(win, triggerKeys, instructions)
%PTB_WAIT_FOR_TRIGGER Block until the scanner sync pulse (or a test keypress).
%   t0 = PTB_WAIT_FOR_TRIGGER(win, triggerKeys, instructions)
%
%   triggerKeys  - cellstr of PTB key names that count as the trigger, e.g.
%                  {'5','t'} (the two most common scanner sync-pulse
%                  conventions -- wire the scanner to send one of these, or
%                  press it yourself on the keyboard to test without one).
%   instructions - text shown while waiting (default: 'Waiting for
%                  scanner...').
%
%   Returns t0, the GetSecs() timestamp of the trigger keypress -- pass this
%   into ptb_run_block_loop.m (or use directly, as gambling_task.m does) so
%   every event is timed relative to the actual first-volume trigger, not
%   whenever the script happened to start.
%
%   Uses the same KbQueue mechanism as response collection (see
%   ptb_kbqueue_setup.m) rather than KbWait, for the same reason: some
%   scanner sync boxes present the pulse as a single very brief keypress,
%   which a queue catches reliably regardless of what's being drawn at that
%   instant.

    if nargin < 3 || isempty(instructions)
        instructions = 'Waiting for scanner...';
    end

    Screen('TextSize', win, 36);
    DrawFormattedText(win, instructions, 'center', 'center', [1 1 1]);
    Screen('Flip', win);

    ptb_kbqueue_setup(triggerKeys);
    triggerKeys = lower(triggerKeys);
    t0 = [];
    while isempty(t0)
        [found, keyName, tStamp] = ptb_kbqueue_check_any();
        if found && any(strcmpi(keyName, triggerKeys))
            t0 = tStamp;
        end
        WaitSecs(0.001);
    end
    ptb_kbqueue_teardown();
end
