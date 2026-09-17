function checkerboard_lr_task(varargin)
%CHECKERBOARD_LR_TASK Psychtoolbox presentation of a 3-position flickering-
%   checkerboard visual localizer: a full-contrast checkerboard patch
%   flickers ON/OFF (fully visible, then fully blank -- NOT the
%   phase-reversal black<->white flip checkerboard_task.m uses) at
%   'FlickerHz', shown in one of three screen positions per block: CENTER,
%   LEFT, or RIGHT. A small + fixation cross stays visible at screen center
%   THROUGHOUT every block (including LEFT/RIGHT, and the OFF half of every
%   flicker cycle), so the subject can hold central gaze while the
%   checkerboard stimulates each position -- standard practice for a
%   peripheral visual localizer, so the resulting activation reflects
%   retinotopic stimulus location rather than eye movements.
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
%     'FlickerHz'     ON/OFF flicker rate, i.e. how many times per second
%                     the checkerboard toggles fully visible <-> fully
%                     blank (default 4 -- half the pattern-reversal rate
%                     checkerboard_task.m uses, since a full on/off cycle
%                     here is twice as long as one reversal there for the
%                     same perceived flicker rate)
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
    addParameter(p, 'FlickerHz', 4);
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

    % ---- build ONE checkerboard texture up front (ON/OFF flicker just
    %      toggles whether it's drawn at all, unlike checkerboard_task.m's
    %      two phase-inverted textures for a reversal flicker) ----
    squareSizePx = 40;
    [screenW, screenH] = Screen('WindowSize', win);
    shortSide = min(screenW, screenH);

    centerFraction = 0.45;  % fraction of the screen's shorter dimension
    sideFraction = 0.40;    % still smaller than centerFraction so a
                            % LEFT/RIGHT patch fits inside the outer screen
                            % thirds without clipping
    nSquaresCenter = max(2, round(shortSide * centerFraction / squareSizePx));
    patchSizeCenter = nSquaresCenter * squareSizePx;
    [X, Y] = meshgrid(0:patchSizeCenter - 1, 0:patchSizeCenter - 1);
    checker = mod(floor(X / squareSizePx) + floor(Y / squareSizePx), 2);
    texChecker = Screen('MakeTexture', win, uint8(checker * 255));

    patchSizeSide = max(2, round(shortSide * sideFraction / squareSizePx)) * squareSizePx;
    margin = 0.04 * screenW;   % gap between the patch and the screen edge

    destRects = struct( ...
        'center', CenterRectOnPointd([0 0 patchSizeCenter patchSizeCenter], ...
            screenW / 2, screenH / 2), ...
        'left', CenterRectOnPointd([0 0 patchSizeSide patchSizeSide], ...
            margin + patchSizeSide / 2, screenH / 2), ...
        'right', CenterRectOnPointd([0 0 patchSizeSide patchSizeSide], ...
            screenW - margin - patchSizeSide / 2, screenH / 2));
    flickerHz = opt.FlickerHz;

    function stimFor(win, trialType, tInEvent, ~)
        if isfield(destRects, trialType)
            % ON/OFF: draw the checkerboard for the first half of each
            % flicker cycle, nothing (just the fixation cross below) for
            % the second half -- a true on/off flicker, not a
            % black<->white pattern reversal.
            if mod(floor(tInEvent * flickerHz * 2), 2) == 0
                Screen('DrawTexture', win, texChecker, [], destRects.(trialType));
            end
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
