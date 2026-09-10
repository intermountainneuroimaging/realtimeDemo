function aborted = ptb_show_instructions(win, instructionsText, continueKeys)
%PTB_SHOW_INSTRUCTIONS Show a task-instructions screen and block until a
%   continue key is pressed, before the "waiting for scanner trigger"
%   screen -- so the subject sees the task description and their goal
%   before the run starts, not just the raw stimuli.
%
%   aborted = PTB_SHOW_INSTRUCTIONS(win, instructionsText, continueKeys)
%
%   instructionsText - the text to show (wrapped to the window width).
%   continueKeys     - cellstr of PTB key names that dismiss the screen
%                       (default {'space'}).
%
%   Returns true if Escape was pressed instead (caller should return early
%   -- its own onCleanup still releases the window/KbQueue as usual).
%
%   Uses the same KbQueue mechanism as ptb_wait_for_trigger.m / response
%   collection (see ptb_kbqueue_setup.m), for the same reason: a single
%   per-frame KbCheck could miss a brief keydown pulse.

    if nargin < 3 || isempty(continueKeys)
        continueKeys = {'space'};
    end

    Screen('TextSize', win, 28);
    DrawFormattedText(win, instructionsText, 'center', 'center', [1 1 1], 60);
    Screen('Flip', win);

    ptb_kbqueue_setup([continueKeys, {'ESCAPE'}]);
    pressed = '';
    while isempty(pressed)
        [found, keyName] = ptb_kbqueue_check_any();
        if found
            pressed = keyName;
        end
        WaitSecs(0.001);
    end
    ptb_kbqueue_teardown();

    aborted = strcmpi(pressed, 'ESCAPE');
    if aborted
        fprintf('[stimuli] Escape pressed during instructions -- aborting.\n');
    end
end
