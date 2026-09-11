function aborted = ptb_show_instructions(win, instructionsText, continueKeys)
%PTB_SHOW_INSTRUCTIONS Show a task-instructions screen and block until a
%   continue key is pressed, before the "waiting for scanner trigger"
%   screen -- so the subject sees the task description and their goal
%   before the run starts, not just the raw stimuli.
%
%   aborted = PTB_SHOW_INSTRUCTIONS(win, instructionsText, continueKeys)
%
%   instructionsText - the text to show.
%   continueKeys     - cellstr of PTB key names that dismiss the screen
%                       (default {'space'}).
%
%   Returns true if Escape was pressed instead (caller should return early
%   -- its own onCleanup still releases the window/KbQueue as usual).
%
%   FITS THE ACTUAL WINDOW, AT ANY RESOLUTION: rather than a fixed font size
%   and a fixed wrap-at character count (which only happens to fit at
%   whatever resolution they were eyeballed on), this uses
%   ptb_fit_text_size.m to measure the real window and the real rendered
%   text, then shrinks the font until the whole block fits within it -- so
%   the full instructions are visible whether this is fullscreen on a
%   scanner-room projector or the small 1024x768 'Windowed' test window.
%
%   Uses the same KbQueue mechanism as ptb_wait_for_trigger.m / response
%   collection (see ptb_kbqueue_setup.m), for the same reason: a single
%   per-frame KbCheck could miss a brief keydown pulse.

    if nargin < 3 || isempty(continueKeys)
        continueKeys = {'space'};
    end

    % 0.82/0.85 leave an 18%-of-width, 15%-of-height margin so lines don't
    % touch the edges.
    [textSize, wrapat] = ptb_fit_text_size(win, instructionsText, 0.82, 0.85, 32, 14);

    Screen('TextSize', win, textSize);
    DrawFormattedText(win, instructionsText, 'center', 'center', [1 1 1], wrapat);
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
