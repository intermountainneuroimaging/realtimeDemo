function checkerboard_task(varargin)
%CHECKERBOARD_TASK Psychtoolbox presentation of a flickering-checkerboard
%   visual localizer: alternating ON (flickering full-contrast checkerboard)
%   / OFF (fixation only) blocks. Shows a brief task-instructions screen
%   (dismiss with SPACE, or Escape to abort), waits for the scanner trigger,
%   then presents ../study_design/Checkerboard_events.tsv (rest, checkerboard,
%   x6, + a trailing rest block; 20s blocks, 13 blocks, 260s total). Matches
%   this project's real-time GLM convention: point taskActivation.toml's
%   eventsFile at Checkerboard_events.tsv and set glmCondA='checkerboard',
%   glmCondB='' (a single-condition beta map -- there's no second condition
%   to contrast against) to analyze it live.
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: Checkerboard_events.tsv)
%     'Duration'      total run length in seconds (default: end of the last
%                     event); pass nVols*TR to also show trailing rest
%     'FlickerHz'     pattern-reversal rate during ON blocks, i.e. how many
%                     times per second the checkerboard flips black<->white
%                     (default 8 -- standard for a visual localizer)
%     'Windowed'      true for a windowed test window (default false)
%     'ScreenWidth'   \
%     'ScreenHeight'   } pixel resolution to open at, e.g. 1920/1080 for a
%                     known scanner-room projector (default: [], auto-detect
%                     the display's own native resolution -- see
%                     ptb_open_window.m). Ignored if 'Windowed' is true.
%     'SkipSyncTests' true to disable PTB's flip-timing sync tests, for
%                     testing on a non-research display (default false)
%     'LogPath'       timing log path (default:
%                     stimuli_ptb/logs/checkerboard_task_<timestamp>.tsv)
%
%   Example:
%     checkerboard_task('Windowed', true, 'TriggerKey', {'space'})   % test
%     checkerboard_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', 'Checkerboard_events.tsv'));
    addParameter(p, 'Duration', []);
    addParameter(p, 'FlickerHz', 8);
    addParameter(p, 'Windowed', false);
    addParameter(p, 'ScreenWidth', []);
    addParameter(p, 'ScreenHeight', []);
    addParameter(p, 'SkipSyncTests', false);
    addParameter(p, 'LogPath', '');
    parse(p, varargin{:});
    opt = p.Results;

    logPath = opt.LogPath;
    if isempty(logPath)
        logPath = fullfile(here, 'logs', ...
            sprintf('checkerboard_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[checkerboard_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca);   % guarantees the display is released on ANY exit --
                                       % normal completion, Escape-abort, or an uncaught error

    % ---- build the two phase-inverted checkerboard textures once up front
    %      (drawn every frame during ON blocks -- rebuilding per-frame would
    %      needlessly cost time in the render loop) ----
    squareSizePx = 40;
    patchFraction = 0.8;   % fraction of the screen's shorter dimension
    [screenW, screenH] = Screen('WindowSize', win);
    nSquares = max(2, round(min(screenW, screenH) * patchFraction / squareSizePx));
    patchSize = nSquares * squareSizePx;
    [X, Y] = meshgrid(0:patchSize - 1, 0:patchSize - 1);
    checker = mod(floor(X / squareSizePx) + floor(Y / squareSizePx), 2);
    texOn = Screen('MakeTexture', win, uint8(checker * 255));
    texOff = Screen('MakeTexture', win, uint8((1 - checker) * 255));
    destRect = CenterRectOnPointd([0 0 patchSize patchSize], screenW / 2, screenH / 2);
    flickerHz = opt.FlickerHz;

    function stimFor(win, trialType, tInEvent, ~)
        if strcmp(trialType, 'checkerboard')
            if mod(floor(tInEvent * flickerHz), 2) == 0
                Screen('DrawTexture', win, texOn, [], destRect);
            else
                Screen('DrawTexture', win, texOff, [], destRect);
            end
        else
            DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
        end
    end

    instructions = ['CHECKERBOARD VIEWING TASK\n\n' ...
        'You will see a flickering black-and-white checkerboard pattern, alternating ' ...
        'with a plain + fixation cross.\n\n' ...
        'Goal: simply keep your eyes open and look at the checkerboard while it is ' ...
        'on screen, and rest your eyes on the + cross in between. No response or ' ...
        'button press is needed -- just watch and stay still.\n\n' ...
        'Press SPACE when you are ready to begin.'];
    if ptb_show_instructions(win, instructions)
        return
    end

    t0 = ptb_wait_for_trigger(win, opt.TriggerKey, 'Waiting for scanner trigger...');
    fprintf('[checkerboard_task] triggered at t0=%.3fs -- starting task\n', t0);
    ptb_run_block_loop(win, events, @stimFor, t0, opt.Duration, logPath);

    DrawFormattedText(win, 'Task complete -- thank you!', 'center', 'center', [1 1 1]);
    Screen('Flip', win);
    WaitSecs(2.0);
end
