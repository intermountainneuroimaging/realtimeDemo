function gambling_task(varargin)
%GAMBLING_TASK Psychtoolbox presentation of the HCP gambling (card-guessing) task.
%   Same timing as the HCP project's own design (reads
%   ../study_design/HcpGambling_acq-ap_events.tsv -- the same file
%   taskActivation.py's live pipeline reads via conf/gambling.toml, and a
%   copy of the one this project's tutorial/ offline validation and the
%   PsychoPy version both use). Each
%   trial: the subject briefly guesses whether a hidden card is higher or
%   lower (any response button -- as in the real HCP task, the guess
%   doesn't actually change the outcome), then a feedback outcome is shown
%   for the rest of the trial: green +$1.00 (reward), red -$0.50
%   (punishment), or gray $0.00 (neutral). Which outcome appears and when
%   is entirely driven by the events.tsv, matching
%   taskActivation.toml's glmCondA=reward / glmCondB=punishment contrast
%   (neutral as a covariate) for live analysis.
%
%   NO RESPONSE = NO REWARD/LOSS: if the subject doesn't press a button
%   during the guess phase, the feedback shown is gray "No response $0.00"
%   instead of the trial's scheduled reward/punishment outcome -- this is a
%   display-only change (an incentive to actually respond each trial); the
%   events.tsv / GLM design driving the real-time analysis are unaffected.
%
%   RESPONSES ARE RECORDED VIA KbQueue, NOT KbCheck: an MRI response button
%   box typically presents itself as a keyboard sending one brief keydown
%   pulse per press. A plain per-frame KbCheck can miss that pulse entirely
%   if it falls between two checks (e.g. while this loop is mid-draw or
%   waiting on Screen('Flip')). ptb_kbqueue_setup.m starts a KbQueue once
%   for the whole run, which buffers every press with its own timestamp in
%   the background regardless of what the main loop is doing -- so
%   ptb_kbqueue_check_any.m (polled every frame during each trial's guess
%   phase, see below) never loses a response. The response key and its
%   reaction time (relative to guess-phase onset) are written into the
%   timing log's response_key / response_time_s columns; 'none'/NaN if the
%   subject didn't respond in time.
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: HcpGambling_acq-ap_events.tsv)
%     'ResponseKeys'  cellstr of keys/button-box digits that count as a
%                     response (default {'1','1!','2','2@','3','3#','4','4$'}
%                     -- a typical 4-button MRI response box, covering both
%                     the plain-digit and shifted-symbol names PTB may
%                     report for it; narrow this to your site's actual box)
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
%                     stimuli_ptb/logs/gambling_task_<timestamp>.tsv)
%
%   Example:
%     gambling_task('Windowed', true, 'TriggerKey', {'space'})   % test
%     gambling_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', ...
        'HcpGambling_acq-ap_events.tsv'));
    addParameter(p, 'ResponseKeys', {'1', '1!', '2', '2@', '3', '3#', '4', '4$'});
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
        logPath = fullfile(here, 'logs', ...
            sprintf('gambling_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[gambling_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    outcomeStyle = struct( ...
        'reward',     struct('text', '+$1.00', 'color', [0 1 0]), ...
        'punishment', struct('text', '-$0.50', 'color', [1 0 0]), ...
        'neutral',    struct('text', '$0.00',  'color', [0.6 0.6 0.6]));
    GUESS_MAX_S = 1.5;       % cap on the guess phase, at the start of each trial
    GUESS_FRACTION = 0.4;    % ...or this fraction of the trial's own duration, if shorter

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca); %#ok<NASGU>   % guarantees the display is released on
                                                   % ANY exit -- normal completion,
                                                   % Escape-abort, or an uncaught error

    t0 = ptb_wait_for_trigger(win, opt.TriggerKey, 'Waiting for scanner trigger...');
    fprintf('[gambling_task] triggered at t0=%.3fs -- starting task\n', t0);

    % Started for the WHOLE run, not per-trial -- see the KbQueue note above
    % and ptb_kbqueue_setup.m for why. ESCAPE is checked through this SAME
    % queue below (not a separate KbCheck) so an abort can't be missed for
    % the same reason a button response can't: both are brief keydown
    % pulses that could otherwise fall between two checks.
    ptb_kbqueue_setup(opt.ResponseKeys);
    cleanupQueue = onCleanup(@() ptb_kbqueue_teardown()); %#ok<NASGU>

    if isempty(opt.Duration)
        runDuration = max(events.onset + events.duration);
    else
        runDuration = opt.Duration;
    end

    nEvents = height(events);
    trialActualOnset = nan(nEvents, 1);
    onsetSeen = false(nEvents, 1);
    finalized = false(nEvents, 1);
    respKey = repmat({'none'}, nEvents, 1);
    respRT = nan(nEvents, 1);
    logRows = cell(0, 7);
    idx = 1;
    aborted = false;

    while true
        % NOTE: named tNow, not `now` -- assigning to a variable called `now`
        % anywhere in a function shadows MATLAB's built-in now() (used above
        % for the default log filename's timestamp) for the WHOLE function,
        % not just after this line, causing "Unrecognized function or
        % variable 'now'" at the datestr(now,...) call above.
        tNow = GetSecs() - t0;
        if tNow >= runDuration
            break
        end

        % Checked ONCE per frame, unconditionally, through the same queue as
        % responses -- covers Escape every frame (not just during a guess
        % phase) without a second, separately-fallible KbCheck call.
        [found, keyName, tStamp] = ptb_kbqueue_check_any();
        if found && strcmpi(keyName, 'ESCAPE')
            fprintf('[stimuli] Escape pressed -- aborting early.\n');
            aborted = true;
            break
        end

        % finalize (and log) any trial whose window just closed, before
        % advancing past it -- this is where its recorded response (if any)
        % gets written out, so the log always reflects the FULL trial
        while idx <= nEvents && tNow >= events.onset(idx) + events.duration(idx)
            if ~finalized(idx)
                finalized(idx) = true;
                logRows(end + 1, :) = {char(events.trial_type(idx)), events.onset(idx), ...
                    trialActualOnset(idx), trialActualOnset(idx) - events.onset(idx), ...
                    events.duration(idx), respKey{idx}, respRT(idx)}; %#ok<AGROW>
            end
            idx = idx + 1;
        end

        if idx <= nEvents && tNow >= events.onset(idx)
            if ~onsetSeen(idx)
                onsetSeen(idx) = true;
                trialActualOnset(idx) = tNow;
            end
            trialType = char(events.trial_type(idx));
            onset = events.onset(idx);
            duration = events.duration(idx);
            tInEvent = tNow - onset;

            if isfield(outcomeStyle, trialType)
                guessDur = min(GUESS_MAX_S, duration * GUESS_FRACTION);
                % `found`/`keyName`/`tStamp` came from the single per-frame
                % queue check above (not a second call) -- a non-response
                % key can't reach here since ResponseKeys is exactly what
                % ptb_kbqueue_setup restricted the queue to (+ESCAPE, already
                % handled above), so any `found` left at this point is a
                % genuine response.
                if found && tInEvent < guessDur && strcmp(respKey{idx}, 'none')
                    respKey{idx} = keyName;
                    respRT(idx) = tStamp - t0 - onset;
                end
                if tInEvent < guessDur
                    DrawFormattedText(win, '?\n\nHigher or Lower?\n(press any button)', ...
                        'center', 'center', [1 1 1]);
                elseif strcmp(respKey{idx}, 'none')
                    % no response in time -- no reward/loss for this trial,
                    % regardless of what the scheduled outcome would have
                    % been (the events.tsv / GLM design are unaffected;
                    % this only changes what's shown to the subject)
                    Screen('TextSize', win, 48);
                    DrawFormattedText(win, 'No response\n$0.00', 'center', 'center', [0.6 0.6 0.6]);
                    Screen('TextSize', win, 36);
                else
                    style = outcomeStyle.(trialType);
                    Screen('TextSize', win, 72);
                    DrawFormattedText(win, style.text, 'center', 'center', style.color);
                    Screen('TextSize', win, 36);
                end
            else
                DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
            end
        else
            DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
        end

        Screen('Flip', win);
    end

    % flush whichever trial was still active/unfinalized when the run ended
    for i = 1:nEvents
        if onsetSeen(i) && ~finalized(i)
            logRows(end + 1, :) = {char(events.trial_type(i)), events.onset(i), ...
                trialActualOnset(i), trialActualOnset(i) - events.onset(i), ...
                events.duration(i), respKey{i}, respRT(i)}; %#ok<AGROW>
        end
    end

    ptb_write_event_log(logPath, {'trial_type', 'expected_onset', 'actual_onset', 'error_s', ...
        'duration', 'response_key', 'response_time_s'}, logRows);

    if ~aborted
        DrawFormattedText(win, 'Task complete -- thank you!', 'center', 'center', [1 1 1]);
        Screen('Flip', win);
        WaitSecs(2.0);
    end
end
