function blackjack_task(varargin)
%BLACKJACK_TASK Psychtoolbox presentation of this project's two-card
%   blackjack task (reads ../study_design/Blackjack_events.tsv -- the same
%   file taskActivation.py's live pipeline reads via conf/gambling.toml).
%   Shows a brief task-instructions screen (dismiss with SPACE, or Escape to
%   abort) before waiting for the scanner trigger. Each trial: two cards are dealt face-up, and the subject may press '1'
%   to HIT (deal one more card) or '2' to STAY (freeze the hand) during a
%   brief decision window; then a feedback outcome is shown for the rest of
%   the trial: green WIN +$1.00, red LOSE -$0.50, or gray TIE $0.00. Which
%   outcome appears and when is entirely driven by the events.tsv, exactly
%   like the original gambling_task.m's guess-doesn't-change-the-outcome
%   design -- the displayed cards and the hit/stay choice are cosmetic only
%   and never alter the scheduled result, matching
%   conf/gambling.toml's glmCondA=win / glmCondB=lose contrast (tie as a
%   covariate) for live analysis.
%
%   THE DEALT CARDS ARE NEVER A NATURAL BLACKJACK: the initial two-card hand
%   is never an Ace paired with a 10-value card (10/J/Q/K) -- see
%   deal_initial_hand() below -- so the visible hand can never look like an
%   automatic win regardless of the trial's actual (pre-scripted) outcome.
%
%   NO RESPONSE = NO REWARD/LOSS: if the subject doesn't press a button
%   during the decision phase, the feedback shown is gray "No response
%   $0.00" instead of the trial's scheduled win/lose/tie outcome -- a
%   display-only change (an incentive to actually respond each trial); the
%   events.tsv / GLM design driving the real-time analysis are unaffected.
%
%   RESPONSES ARE RECORDED VIA KbQueue, NOT KbCheck: see gambling_task.m's
%   own header comment for why (an MRI response box's brief keydown pulse
%   can otherwise fall between two per-frame KbCheck calls and be missed).
%   Every hit/stay press during a trial's decision window is logged, in
%   order, in the timing log's response_key column (e.g. "1;1;2"); the
%   response_time_s column records the time of the LAST action (relative to
%   the decision phase's own onset) -- 'none'/NaN if the subject never
%   pressed anything.
%
%   Name-value options (all optional):
%     'TriggerKey'    cellstr of trigger keys (default {'5','5%','t'} -- '5%'
%                     covers sites where the scanner's sync pulse arrives as
%                     the shifted-symbol name PTB gives that key; run
%                     test_ptb_install.m and press your actual trigger/box
%                     once to see exactly what name it reports if unsure)
%     'EventsFile'    path to events.tsv (default: Blackjack_events.tsv)
%     'ResponseKeys'  cellstr of keys/button-box digits that count as a
%                     response (default {'1','1!','2','2@'} -- HIT/STAY --
%                     narrow/rename to your site's actual box if needed)
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
%                     stimuli_ptb/logs/blackjack_task_<timestamp>.tsv)
%
%   Example:
%     blackjack_task('Windowed', true, 'TriggerKey', {'space'})   % test
%     blackjack_task('ScreenWidth', 1920, 'ScreenHeight', 1080)   % real run

    here = fileparts(mfilename('fullpath'));

    p = inputParser;
    addParameter(p, 'TriggerKey', {'5', '5%', 't'});
    addParameter(p, 'EventsFile', fullfile(here, '..', 'study_design', ...
        'Blackjack_events.tsv'));
    addParameter(p, 'ResponseKeys', {'1', '1!', '2', '2@'});
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
            sprintf('blackjack_task_%s.tsv', datestr(now, 'yyyymmdd_HHMMSS')));
    end

    events = ptb_read_events_tsv(opt.EventsFile);
    fprintf('[blackjack_task] loaded %d events from %s\n', height(events), opt.EventsFile);

    outcomeStyle = struct( ...
        'win',  struct('text', 'WIN\n+$1.00',  'color', [0 1 0]), ...
        'lose', struct('text', 'LOSE\n-$0.50', 'color', [1 0 0]), ...
        'tie',  struct('text', 'TIE\n$0.00',   'color', [0.6 0.6 0.6]));
    GUESS_MAX_S = 1.5;       % cap on the hit/stay decision phase, at the start of each trial
    GUESS_FRACTION = 0.4;    % ...or this fraction of the trial's own duration, if shorter
    MAX_HAND_SIZE = 5;       % cosmetic cap on cards in a hand (a held/bouncing key can't blow past this)

    % ---- cosmetic card deck (never drives the real win/lose/tie outcome) ----
    RANKS = {'2','3','4','5','6','7','8','9','10','J','Q','K','A'};
    TEN_RANKS = {'10','J','Q','K'};
    SUIT_SYMS = {'H', char(9829); 'D', char(9830); 'C', char(9827); 'S', char(9824)};

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca); %#ok<NASGU>   % guarantees the display is released on
                                                   % ANY exit -- normal completion,
                                                   % Escape-abort, or an uncaught error

    instructions = ['BLACKJACK CARD TASK\n\n' ...
        'Each round you will be dealt two cards. Press 1 to HIT (take another ' ...
        'card) or press 2 to STAY (keep your current hand). After your choice, ' ...
        'you will see whether you WON (+$1.00), LOST (-$0.50), or TIED ($0.00) ' ...
        'that round.\n\n' ...
        'Goal: choose HIT or STAY however you think will win you the most money. ' ...
        'You must respond within the short decision window each round, or that ' ...
        'round pays out nothing.\n\n' ...
        'Press SPACE when you are ready to begin.'];
    if ptb_show_instructions(win, instructions)
        return
    end

    t0 = ptb_wait_for_trigger(win, opt.TriggerKey, 'Waiting for scanner trigger...');
    fprintf('[blackjack_task] triggered at t0=%.3fs -- starting task\n', t0);

    % Started for the WHOLE run, not per-trial -- see the KbQueue note above
    % and ptb_kbqueue_setup.m for why. ESCAPE is checked through this SAME
    % queue below (not a separate KbCheck) so an abort can't be missed for
    % the same reason a hit/stay press can't: both are brief keydown pulses
    % that could otherwise fall between two checks.
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
    handStr = cell(nEvents, 1);        % dealt cards for this trial, e.g. {'AS','7H'}
    handFrozen = false(nEvents, 1);    % true once STAY is pressed (no more hits)
    actionLog = repmat({'none'}, nEvents, 1);   % ';'-joined sequence, e.g. "1;1;2"
    respRT = nan(nEvents, 1);          % time of the LAST action
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
        % responses -- covers Escape every frame (not just during a decision
        % phase) without a second, separately-fallible KbCheck call.
        [found, keyName, tStamp] = ptb_kbqueue_check_any();
        if found && strcmpi(keyName, 'ESCAPE')
            fprintf('[stimuli] Escape pressed -- aborting early.\n');
            aborted = true;
            break
        end

        % finalize (and log) any trial whose window just closed, before
        % advancing past it -- this is where its recorded action sequence
        % (if any) gets written out, so the log always reflects the FULL trial
        while idx <= nEvents && tNow >= events.onset(idx) + events.duration(idx)
            if ~finalized(idx)
                finalized(idx) = true;
                logRows(end + 1, :) = {char(events.trial_type(idx)), events.onset(idx), ...
                    trialActualOnset(idx), trialActualOnset(idx) - events.onset(idx), ...
                    events.duration(idx), actionLog{idx}, respRT(idx)}; %#ok<AGROW>
            end
            idx = idx + 1;
        end

        if idx <= nEvents && tNow >= events.onset(idx)
            if ~onsetSeen(idx)
                onsetSeen(idx) = true;
                trialActualOnset(idx) = tNow;
                handStr{idx} = deal_initial_hand(RANKS, TEN_RANKS);
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
                % genuine hit/stay press.
                if found && tInEvent < guessDur && ~handFrozen(idx)
                    isHit = strcmp(keyName, '1') || strcmp(keyName, '1!');
                    isStay = strcmp(keyName, '2') || strcmp(keyName, '2@');
                    if isHit && numel(handStr{idx}) < MAX_HAND_SIZE
                        handStr{idx}{end + 1} = deal_card(RANKS, {}, {});
                    end
                    if isHit || isStay
                        if strcmp(actionLog{idx}, 'none')
                            actionLog{idx} = keyName(1);
                        else
                            actionLog{idx} = [actionLog{idx}, ';', keyName(1)];
                        end
                        respRT(idx) = tStamp - t0 - onset;
                    end
                    if isStay
                        handFrozen(idx) = true;
                    end
                end

                handText = format_hand(handStr{idx}, SUIT_SYMS);
                if tInEvent < guessDur
                    Screen('TextSize', win, 48);
                    draw_hand(win, handText);
                    Screen('TextSize', win, 28);
                    draw_prompt(win, '1 = HIT      2 = STAY');
                elseif strcmp(actionLog{idx}, 'none')
                    % no response in time -- no reward/loss for this trial,
                    % regardless of what the scheduled outcome would have
                    % been (the events.tsv / GLM design are unaffected;
                    % this only changes what's shown to the subject)
                    Screen('TextSize', win, 48);
                    DrawFormattedText(win, 'No response\n$0.00', 'center', 'center', [0.6 0.6 0.6]);
                else
                    style = outcomeStyle.(trialType);
                    Screen('TextSize', win, 32);
                    draw_hand_top(win, handText);
                    Screen('TextSize', win, 64);
                    DrawFormattedText(win, style.text, 'center', 'center', style.color);
                end
                Screen('TextSize', win, 36);
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
                events.duration(i), actionLog{i}, respRT(i)}; %#ok<AGROW>
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


function hand = deal_initial_hand(ranks, tenRanks)
%DEAL_INITIAL_HAND Two cosmetic cards, never a natural blackjack (an Ace
%   paired with a 10-value card) -- see blackjack_task.m's own header.
    card1 = deal_card(ranks, {}, {});
    rank1 = card1(1:end-1);
    if strcmp(rank1, 'A')
        card2 = deal_card(ranks, tenRanks, {});
    elseif any(strcmp(rank1, tenRanks))
        card2 = deal_card(ranks, {}, {'A'});
    else
        card2 = deal_card(ranks, {}, {});
    end
    hand = {card1, card2};
end


function card = deal_card(ranks, excludeRanks, excludeAlsoRanks)
%DEAL_CARD One random rank+suit, as a 2-3 char code like '7H' or '10S',
%   optionally excluding some ranks (used to enforce no-natural-blackjack).
    avail = setdiff(ranks, [excludeRanks, excludeAlsoRanks], 'stable');
    rank = avail{randi(numel(avail))};
    suits = {'H', 'D', 'C', 'S'};
    suit = suits{randi(numel(suits))};
    card = [rank, suit];
end


function txt = format_hand(hand, suitSyms)
%FORMAT_HAND Render a cell array of card codes ('7H', '10S', ...) as a
%   single display string with unicode suit symbols, e.g. "7 H  10 S".
    parts = cell(1, numel(hand));
    for i = 1:numel(hand)
        code = hand{i};
        suitLetter = code(end);
        rank = code(1:end-1);
        row = find(strcmp(suitSyms(:, 1), suitLetter), 1);
        parts{i} = sprintf('%s%s', rank, suitSyms{row, 2});
    end
    txt = strjoin(parts, '   ');
end


function draw_hand(win, handText)
%DRAW_HAND Cards centered in the upper-middle of the screen, decision
%   phase (leaves room below for the "1 = HIT   2 = STAY" instruction).
    winRect = Screen('Rect', win);
    yPos = winRect(4) * 0.4;
    DrawFormattedText(win, handText, 'center', yPos, [1 1 1]);
end


function draw_prompt(win, promptText)
%DRAW_PROMPT "1 = HIT   2 = STAY", below the hand during the decision phase.
    winRect = Screen('Rect', win);
    yPos = winRect(4) * 0.6;
    DrawFormattedText(win, promptText, 'center', yPos, [1 1 1]);
end


function draw_hand_top(win, handText)
%DRAW_HAND_TOP Final hand shown small near the top during the outcome
%   phase, so the subject can still see what they were dealt.
    winRect = Screen('Rect', win);
    yPos = winRect(4) * 0.2;
    DrawFormattedText(win, handText, 'center', yPos, [0.8 0.8 0.8]);
end
