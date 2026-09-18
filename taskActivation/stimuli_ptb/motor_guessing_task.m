function motor_guessing_task(varargin)
%MOTOR_GUESSING_TASK Psychtoolbox presentation of the secret-hand "guess the
%   hand" movement game.
%   MOTOR_GUESSING_TASK() shows a brief task-instructions screen (dismiss with
%   1/2, or Escape to abort), waits for the scanner trigger, then presents a
%   10s baseline rest and 5 x (30s MOVE + 20s rest) blocks, the last rest cut
%   to 10s (../study_design/MotorGuessing_events.tsv: rest, move, rest, x5 -- 11
%   blocks, 250s total -- the same length as motor_task.m, so the two swap freely).
%
%   The participant SECRETLY chooses a hand -- left or right -- and does NOT
%   tell the experimenter. Whenever MOVE is on screen they move that same hand --
%   by squeezing it into a fist (like a stress ball) and relaxing it, repeatedly --
%   for as long as the cue stays up; on the + fixation cross they relax. The
%   cue never names a hand, and nothing here (including the timing log)
%   records which one was used, so the experimenter stays blind. At the end of
%   the run the group guesses the hand from the real-time brain output: a hand
%   drives the OPPOSITE motor cortex (left hand -> right hemisphere).
%
%   Analyzed live as ONE condition (glmCondA='move', vs the implicit rest
%   baseline) since the hand isn't known ahead of time -- point
%   taskActivation.toml's eventsFile at MotorGuessing_events.tsv or use
%   conf/motor_guessing.toml (python run_task.py motor_guessing).
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: MotorGuessing_events.tsv)
%     'Duration'      total run length in seconds (default: end of the last
%                     event); pass nVols*TR to also show trailing rest
%     'Windowed'      true for a windowed test window (default false)
%     'ScreenWidth'   \
%     'ScreenHeight'   } pixel resolution to open at, e.g. 1920/1080 for a
%                     known scanner-room projector (default: [], auto-detect
%                     the display's own native resolution -- see
%                     ptb_open_window.m). Ignored if 'Windowed' is true.
%     'SkipSyncTests' true to disable PTB's flip-timing sync tests, for
%                     testing on a non-research display (default false)
%     'LogPath'       timing log path (default:
%                     stimuli_ptb/logs/motor_guessing_task_<timestamp>.tsv)
%     'Win'           an already-open PTB window handle to draw into,
%                     instead of opening (and auto-closing) a new one --
%                     pass this to run several tasks back-to-back in one
%                     PTB session without flashing back to the MATLAB
%                     desktop between them (see run_battery.m). Default
%                     []: open and own the window as before.
%
%   Example:
%     motor_guessing_task('Windowed', true, 'TriggerKey', {'space'})   % self-trigger, for testing
%     motor_guessing_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run, known projector res

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', 'MotorGuessing_events.tsv'));
    addParameter(p, 'Duration', []);
    addParameter(p, 'Windowed', false);
    addParameter(p, 'ScreenWidth', []);
    addParameter(p, 'ScreenHeight', []);
    addParameter(p, 'SkipSyncTests', false);
    addParameter(p, 'LogPath', '');
    addParameter(p, 'Win', []);
    parse(p, varargin{:});
    opt = p.Results;

    logPath = opt.LogPath;
    if isempty(logPath)
        logPath = fullfile(here, 'logs', sprintf('motor_guessing_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[motor_guessing_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    if isempty(opt.Win)
        win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
        cleanupWin = onCleanup(@() sca);   % guarantees the display is released on ANY exit --
                                           % normal completion, Escape-abort, or an uncaught error
    else
        win = opt.Win;   % reusing a caller-opened window (e.g. run_battery.m) -- opening/
                         % closing it is the caller's job, not this task's
    end

    labels = struct('move', 'MOVE');   % deliberately does NOT name a hand -- it's the participant's secret

    function stimFor(win, trialType, ~, ~)
        if isfield(labels, trialType)
            DrawFormattedText(win, labels.(trialType), 'center', 'center', [0 1 0]);
        else
            DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
        end
    end

    instructions = ['HAND GUESSING GAME\n\n' ...
        'Before we start, silently choose ONE hand -- your left or your right -- and ' ...
        'keep it a secret: do not tell the experimenter or say it out loud.\n\n' ...
        'Whenever you see MOVE on the screen, move your chosen hand by squeezing it into ' ...
        'a fist, like you are squeezing a stress ball, then relaxing it. Keep squeezing ' ...
        'and relaxing repeatedly for as long as MOVE stays on the screen. Use the SAME ' ...
        'hand every time. When you see the + fixation cross, relax and stay still.\n\n' ...
        'Goal: keep squeezing and relaxing steadily for the whole block, always with the same ' ...
        'hand. At the end, everyone will try to guess which hand you used from your ' ...
        'brain activity!\n\n' ...
        'If you have any questions, ask the experimenter now (but do not say which hand ' ...
        'you chose). When you are comfortable, press any button to continue.'];
    if ptb_show_instructions(win, instructions)
        return
    end

    t0 = ptb_wait_for_trigger(win, opt.TriggerKey, 'Waiting for scanner trigger...');
    fprintf('[motor_guessing_task] triggered at t0=%.3fs -- starting task\n', t0);
    ptb_run_block_loop(win, events, @stimFor, t0, opt.Duration, logPath);

    DrawFormattedText(win, 'Task complete -- thank you!', 'center', 'center', [1 1 1]);
    Screen('Flip', win);
    WaitSecs(2.0);
end
