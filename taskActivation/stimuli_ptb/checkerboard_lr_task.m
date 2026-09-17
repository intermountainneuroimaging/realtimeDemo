function checkerboard_lr_task(varargin)
%CHECKERBOARD_LR_TASK Psychtoolbox presentation of a 3-position flickering-
%   checkerboard visual localizer: a full-contrast checkerboard BAR (full
%   window height, a fraction of the window width) flickers in one of
%   three screen positions per block: CENTER, LEFT, or RIGHT -- the same
%   OFF (blank) -> ON (pattern A) -> OFF -> ON (pattern B, the
%   black<->white inverse of A) -> repeat flicker checkerboard_task.m uses,
%   at 'FlickerHz'. LEFT is anchored flush against the window's left edge
%   and RIGHT flush against its right edge (not floating with a gap), so
%   the two peripheral bars sit as far into the visual periphery as the
%   window allows. A small + fixation cross stays visible at screen center
%   THROUGHOUT every block (including LEFT/RIGHT, and every OFF phase), so
%   the subject can hold central gaze while the checkerboard stimulates
%   each position -- standard practice for a peripheral visual localizer,
%   so the resulting activation reflects retinotopic stimulus location
%   rather than eye movements.
%
%   Shows a brief task-instructions screen (dismiss with 1/2, or Escape to
%   abort), waits for the scanner trigger, then presents
%   ../study_design/CheckerboardLR_events.tsv (rest, center, rest, left,
%   rest, right, x4 + a trailing rest block; 12s blocks, 25 blocks, 300s
%   total). Matches conf/checkerboard_lr.toml's 3-way one-vs-rest GLM
%   contrast (glmCondA=center / glmCondB=left / glmCondC=right, each
%   contrasted against the mean of the other two) for live analysis.
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: CheckerboardLR_events.tsv)
%     'Duration'      total run length in seconds (default: end of the last
%                     event); pass nVols*TR to also show trailing rest
%     'FlickerHz'     how many times per second the checkerboard's state
%                     changes during a CENTER/LEFT/RIGHT block (default 8):
%                     OFF (blank) -> ON (pattern A) -> OFF -> ON (pattern
%                     B, the black<->white inverse of A) -> repeat, each
%                     state lasting 1/FlickerHz -- same semantics as
%                     checkerboard_task.m
%     'Windowed'      true for a windowed test window (default false)
%     'ScreenWidth'   \
%     'ScreenHeight'   } pixel resolution to open at, e.g. 1920/1080 for a
%                     known scanner-room projector (default: [], auto-detect
%                     the display's own native resolution -- see
%                     ptb_open_window.m). Ignored if 'Windowed' is true.
%     'SkipSyncTests' true to disable PTB's flip-timing sync tests, for
%                     testing on a non-research display (default false)
%     'LogPath'       timing log path (default:
%                     stimuli_ptb/logs/checkerboard_lr_task_<timestamp>.tsv)
%
%   Example:
%     checkerboard_lr_task('Windowed', true, 'TriggerKey', {'space'})   % test
%     checkerboard_lr_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', 'CheckerboardLR_events.tsv'));
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
            sprintf('checkerboard_lr_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[checkerboard_lr_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca);   % guarantees the display is released on ANY exit --
                                       % normal completion, Escape-abort, or an uncaught error

    % ---- build the two phase-inverted checkerboard textures up front
    %      (drawn every frame during ON flashes -- rebuilding per-frame
    %      would needlessly cost time in the render loop). The SAME square
    %      texture is reused for all 3 positions: DrawTexture stretches it
    %      into whatever destRect is passed, so in a tall/narrow bar
    %      destRect the checker cells appear as tall rectangles rather
    %      than squares -- expected for a bar shape. ----
    squareSizePx = 40;
    [screenW, screenH] = Screen('WindowSize', win);
    shortSide = min(screenW, screenH);

    centerWidthFraction = 0.36;  % fraction of the screen's shorter
                                 % dimension, used as bar WIDTH (bars span
                                 % the full screen HEIGHT -- see destRects
                                 % below)
    sideWidthFraction = 0.32;    % still smaller than centerWidthFraction
                                 % so LEFT/RIGHT stay visually distinct
                                 % from CENTER
    nSquares = max(2, round(shortSide * centerWidthFraction / squareSizePx));
    patchPx = nSquares * squareSizePx;
    [X, Y] = meshgrid(0:patchPx - 1, 0:patchPx - 1);
    checker = mod(floor(X / squareSizePx) + floor(Y / squareSizePx), 2);
    texChecker = Screen('MakeTexture', win, uint8(checker * 255));
    texCheckerInv = Screen('MakeTexture', win, uint8((1 - checker) * 255));

    barWidthCenter = shortSide * centerWidthFraction;
    barWidthSide = shortSide * sideWidthFraction;

    % Bars span the FULL window height; LEFT is anchored flush against the
    % window's left edge and RIGHT flush against its right edge (no
    % margin/gap), so each reaches as far into the periphery as the window
    % allows. CENTER stays horizontally centered.
    destRects = struct( ...
        'center', CenterRectOnPointd([0 0 barWidthCenter screenH], ...
            screenW / 2, screenH / 2), ...
        'left', [0, 0, barWidthSide, screenH], ...
        'right', [screenW - barWidthSide, 0, screenW, screenH]);
    flickerHz = opt.FlickerHz;

    function stimFor(win, trialType, tInEvent, ~)
        if isfield(destRects, trialType)
            % True flicker: fully OFF (blank -- nothing drawn, so the
            % window's black background shows through) between each ON
            % flash, and the ON flash itself alternates pattern A/B
            % (black<->white inverse) so a given screen location genuinely
            % reverses polarity from one flash to the next -- same 4-phase
            % cycle as checkerboard_task.m.
            phase = mod(floor(tInEvent * flickerHz), 4);
            if phase == 1
                Screen('DrawTexture', win, texChecker, [], destRects.(trialType));
            elseif phase == 3
                Screen('DrawTexture', win, texCheckerInv, [], destRects.(trialType));
            end
            % phase == 0 or 2: blank -- draw nothing.
        end
        % Fixation stays visible for EVERY frame of EVERY condition
        % (including rest) -- see the header comment on why: keeps gaze
        % central while LEFT/RIGHT stimulate the periphery. Green (not
        % white) so it stays clearly visible against the black-and-white
        % checkerboard squares behind it.
        DrawFormattedText(win, '+', 'center', 'center', [0 1 0]);
    end

    instructions = ['CHECKERBOARD LOCALIZER TASK\n\n' ...
        'You will see a flickering black-and-white checkerboard pattern appear in ' ...
        'different places on the screen -- sometimes in the middle, sometimes off ' ...
        'to the left, sometimes off to the right.\n\n' ...
        'Goal: keep looking at the + in the center of the screen THE WHOLE TIME, ' ...
        'even when the checkerboard appears off to one side -- just notice it out ' ...
        'of the corner of your eye rather than looking directly at it. No response ' ...
        'or button press is needed during the task.\n\n' ...
        'If you have any questions, ask the experimenter now. When you are ' ...
        'comfortable, press any button to continue.'];
    if ptb_show_instructions(win, instructions)
        return
    end

    t0 = ptb_wait_for_trigger(win, opt.TriggerKey, 'Waiting for scanner trigger...');
    fprintf('[checkerboard_lr_task] triggered at t0=%.3fs -- starting task\n', t0);
    ptb_run_block_loop(win, events, @stimFor, t0, opt.Duration, logPath);

    DrawFormattedText(win, 'Task complete -- thank you!', 'center', 'center', [1 1 1]);
    Screen('Flip', win);
    WaitSecs(2.0);
end
