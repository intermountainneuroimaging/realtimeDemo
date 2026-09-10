function motor_task(varargin)
%MOTOR_TASK Psychtoolbox presentation of a simple L/R-finger motor task.
%   MOTOR_TASK() waits for the scanner trigger, then presents alternating
%   30-second LEFT FINGER / RIGHT FINGER tapping blocks separated by 10s
%   REST blocks (../study_design/GenericMotorLR_events.tsv: rest,
%   left_finger, rest, right_finger, x3, + a trailing rest block -- 13
%   blocks, 250s total). Matches this project's real-time GLM contrast
%   convention: point
%   taskActivation.toml's eventsFile at GenericMotorLR_events.tsv and set
%   glmCondA='left_finger', glmCondB='right_finger' to analyze it live.
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: GenericMotorLR_events.tsv)
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
%                     stimuli_ptb/logs/motor_task_<timestamp>.tsv)
%
%   Example:
%     motor_task('Windowed', true, 'TriggerKey', {'space'})   % self-trigger, for testing
%     motor_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run, known projector res

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', 'GenericMotorLR_events.tsv'));
    addParameter(p, 'Duration', []);
    addParameter(p, 'Windowed', false);
    addParameter(p, 'ScreenWidth', []);
    addParameter(p, 'ScreenHeight', []);
    addParameter(p, 'SkipSyncTests', false);
    addParameter(p, 'LogPath', '');
    parse(p, varargin{:});
    opt = p.Results;

    logPath = opt.LogPath;
    if isempty(logPath)
        logPath = fullfile(here, 'logs', sprintf('motor_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[motor_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca);   % guarantees the display is released on ANY exit --
                                       % normal completion, Escape-abort, or an uncaught error

    labels = struct('left_finger', 'LEFT\nFINGER', 'right_finger', 'RIGHT\nFINGER');

    function stimFor(win, trialType, ~, ~)
        if isfield(labels, trialType)
            DrawFormattedText(win, labels.(trialType), 'center', 'center', [0 1 0]);
        else
            DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
        end
    end

    t0 = ptb_wait_for_trigger(win, opt.TriggerKey, 'Waiting for scanner trigger...');
    fprintf('[motor_task] triggered at t0=%.3fs -- starting task\n', t0);
    ptb_run_block_loop(win, events, @stimFor, t0, opt.Duration, logPath);

    DrawFormattedText(win, 'Task complete -- thank you!', 'center', 'center', [1 1 1]);
    Screen('Flip', win);
    WaitSecs(2.0);
end
