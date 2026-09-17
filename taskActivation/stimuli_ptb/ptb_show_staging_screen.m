function aborted = ptb_show_staging_screen(win, message)
%PTB_SHOW_STAGING_SCREEN Show a between-tasks "staging" screen and block
%   until the EXPERIMENTER presses SPACE -- used by run_battery.m to give a
%   clear, harmless breakpoint between tasks that share one PTB window (see
%   motor_task.m's/etc.'s 'Win' option), instead of either auto-starting the
%   next task with no warning or closing/reopening the display between
%   tasks (which is what this whole mechanism exists to avoid).
%
%   aborted = PTB_SHOW_STAGING_SCREEN(win, message)
%
%   win     - an already-open PTB window (see ptb_open_window.m).
%   message - text to show (default: 'Waiting for next task...\n\nExperimenter:
%             press SPACE to continue.').
%
%   Returns true if Escape was pressed instead of SPACE -- run_battery.m
%   stops the whole battery there rather than starting the next task.
%
%   Uses the SAME KbQueue mechanism as ptb_wait_for_trigger.m/
%   ptb_show_instructions.m (see ptb_kbqueue_setup.m) for the same reason: a
%   single per-frame KbCheck could miss a brief keydown pulse. SPACE (not
%   the response-box digit keys ptb_show_instructions.m uses) because this
%   screen is dismissed by the EXPERIMENTER at the console, not the subject.

    if nargin < 2 || isempty(message)
        message = 'Waiting for next task...\n\nExperimenter: press SPACE to continue.';
    end

    [textSize, wrapat] = ptb_fit_text_size(win, message, 0.82, 0.85, 32, 14);
    Screen('TextSize', win, textSize);
    DrawFormattedText(win, message, 'center', 'center', [1 1 1], wrapat);
    Screen('Flip', win);

    ptb_kbqueue_setup({'SPACE', 'ESCAPE'});
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
        fprintf('[stimuli] Escape pressed at the staging screen -- stopping the battery.\n');
    end
end
