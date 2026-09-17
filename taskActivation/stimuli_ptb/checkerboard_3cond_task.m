function checkerboard_3cond_task(varargin)
%CHECKERBOARD_3COND_TASK Psychtoolbox presentation of a 3-position flickering-
%   checkerboard visual localizer, flickering in one of three screen
%   positions per block: CENTER, LEFT, or RIGHT -- OFF (blank) -> ON
%   (pattern A) -> OFF -> ON (pattern B, the black<->white inverse of A)
%   -> repeat, at 'FlickerHz'. CENTER is a SQUARE (its height set equal to
%   its own width, not the window height) centered on screen, so it
%   stimulates only the fovea; LEFT and RIGHT are full window-height BARS,
%   anchored flush against the window's left/right edge respectively (not
%   floating with a gap), so they reach as far into the visual periphery
%   as the window allows. A small + fixation cross stays visible at screen
%   center THROUGHOUT every block (including LEFT/RIGHT, and every OFF
%   phase), so the subject can hold central gaze while the checkerboard
%   stimulates each position -- standard practice for a peripheral visual
%   localizer, so the resulting activation reflects retinotopic stimulus
%   location rather than eye movements.
%
%   Shows a brief task-instructions screen (dismiss with 1/2, or Escape to
%   abort), waits for the scanner trigger, then presents
%   ../study_design/Checkerboard3Cond_events.tsv (rest, center, rest, left,
%   rest, right, x4 + a trailing rest block; 12s blocks, 25 blocks, 300s
%   total). Matches conf/checkerboard_3cond.toml's 3-way one-vs-rest GLM
%   contrast (glmCondA=center / glmCondB=left / glmCondC=right, each
%   contrasted against the mean of the other two) for live analysis.
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: Checkerboard3Cond_events.tsv)
%     'Duration'      total run length in seconds (default: end of the last
%                     event); pass nVols*TR to also show trailing rest
%     'FlickerHz'     how many times per second the checkerboard's state
%                     changes during a CENTER/LEFT/RIGHT block (default 8):
%                     OFF (blank) -> ON (pattern A) -> OFF -> ON (pattern
%                     B, the black<->white inverse of A) -> repeat, each
%                     state lasting 1/FlickerHz -- same semantics as
%                     checkerboard_1cond_task.m
%     'Windowed'      true for a windowed test window (default false)
%     'ScreenWidth'   \
%     'ScreenHeight'   } pixel resolution to open at, e.g. 1920/1080 for a
%                     known scanner-room projector (default: [], auto-detect
%                     the display's own native resolution -- see
%                     ptb_open_window.m). Ignored if 'Windowed' is true.
%     'SkipSyncTests' true to disable PTB's flip-timing sync tests, for
%                     testing on a non-research display (default false)
%     'LogPath'       timing log path (default:
%                     stimuli_ptb/logs/checkerboard_3cond_task_<timestamp>.tsv)
%
%   Example:
%     checkerboard_3cond_task('Windowed', true, 'TriggerKey', {'space'})   % test
%     checkerboard_3cond_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', 'Checkerboard3Cond_events.tsv'));
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
            sprintf('checkerboard_3cond_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[checkerboard_3cond_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca);   % guarantees the display is released on ANY exit --
                                       % normal completion, Escape-abort, or an uncaught error

    % ---- build the two phase-inverted checkerboard textures for CENTER
    %      and for LEFT/RIGHT (which share the same width, so share one
    %      texture pair) up front. Each texture's own pixel grid is sized
    %      to match that stim's real width/height in squareSizePx cells, so
    %      the checker cells are genuinely SQUARE regardless of the stim's
    %      own aspect ratio -- rather than stretching one shared square
    %      texture into a non-square destRect, which would elongate the
    %      cells. ----
    squareSizePx = 40;
    [screenW, screenH] = Screen('WindowSize', win);
    shortSide = min(screenW, screenH);

    centerWidthFraction = 0.288; % fraction of the screen's shorter
                                 % dimension -- CENTER's own WIDTH, also
                                 % used as its HEIGHT (a square -- see
                                 % destRects below); LEFT/RIGHT bars span
                                 % the full screen HEIGHT instead
    sideWidthFraction = 0.32;    % still smaller than centerWidthFraction
                                 % so LEFT/RIGHT stay visually distinct
                                 % from CENTER

    barWidthCenter = shortSide * centerWidthFraction;   % CENTER's own width AND height
    barWidthSide = shortSide * sideWidthFraction;

    nColsCenter = max(2, round(barWidthCenter / squareSizePx));
    nRowsCenter = nColsCenter;   % CENTER is a square, so rows == cols
    nColsSide = max(2, round(barWidthSide / squareSizePx));
    nRowsSide = max(2, round(screenH / squareSizePx));

    [Xc, Yc] = meshgrid(0:nColsCenter - 1, 0:nRowsCenter - 1);
    checkerCenter = mod(Xc + Yc, 2);
    texCenterA = Screen('MakeTexture', win, uint8(checkerCenter * 255));
    texCenterB = Screen('MakeTexture', win, uint8((1 - checkerCenter) * 255));

    [Xs, Ys] = meshgrid(0:nColsSide - 1, 0:nRowsSide - 1);
    checkerSide = mod(Xs + Ys, 2);
    texSideA = Screen('MakeTexture', win, uint8(checkerSide * 255));
    texSideB = Screen('MakeTexture', win, uint8((1 - checkerSide) * 255));

    % CENTER is a SQUARE centered on screen (stimulates only the fovea);
    % LEFT/RIGHT span the FULL window height and are anchored flush
    % against the window's left/right edge (no margin/gap), so each
    % reaches as far into the periphery as the window allows.
    destRects = struct( ...
        'center', CenterRectOnPointd([0 0 barWidthCenter barWidthCenter], ...
            screenW / 2, screenH / 2), ...
        'left', [0, 0, barWidthSide, screenH], ...
        'right', [screenW - barWidthSide, 0, screenW, screenH]);

    texA = struct('center', texCenterA, 'left', texSideA, 'right', texSideA);
    texB = struct('center', texCenterB, 'left', texSideB, 'right', texSideB);
    flickerHz = opt.FlickerHz;

    function stimFor(win, trialType, tInEvent, ~)
        if isfield(destRects, trialType)
            % True flicker: fully OFF (blank -- nothing drawn, so the
            % window's black background shows through) between each ON
            % flash, and the ON flash itself alternates pattern A/B
            % (black<->white inverse) so a given screen location genuinely
            % reverses polarity from one flash to the next -- same 4-phase
            % cycle as checkerboard_1cond_task.m.
            phase = mod(floor(tInEvent * flickerHz), 4);
            if phase == 1
                Screen('DrawTexture', win, texA.(trialType), [], destRects.(trialType));
            elseif phase == 3
                Screen('DrawTexture', win, texB.(trialType), [], destRects.(trialType));
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
    fprintf('[checkerboard_3cond_task] triggered at t0=%.3fs -- starting task\n', t0);
    ptb_run_block_loop(win, events, @stimFor, t0, opt.Duration, logPath);

    DrawFormattedText(win, 'Task complete -- thank you!', 'center', 'center', [1 1 1]);
    Screen('Flip', win);
    WaitSecs(2.0);
end
