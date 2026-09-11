function blackjack_task(varargin)
%BLACKJACK_TASK Psychtoolbox presentation of this project's two-card
%   blackjack task (reads ../study_design/Blackjack_events.tsv -- the same
%   file taskActivation.py's live pipeline reads via conf/gambling.toml).
%   Shows a brief task-instructions screen (dismiss with SPACE, or Escape to
%   abort) before waiting for the scanner trigger. Each trial (a fixed 3.0s
%   in Blackjack_events.tsv): two cards are dealt face-up, and the subject
%   may press '1' to HIT or '2' to STAY, any time during a 2.0s decision
%   window. Whichever comes first: the SAME instant the subject responds,
%   HIT deals one more card and immediately reveals the outcome; STAY
%   immediately reveals the outcome with the current hand -- there's no
%   waiting for the rest of the decision window once an answer is given.
%   The outcome (shown for whatever time is left in the trial, at least
%   1.0s): green WIN +$1.00, gray TIE $0.00, or red -$0.50 -- labeled
%   "BUST" if the cosmetic hand's own blackjack value (see hand_value()
%   below) is over 21, otherwise "DEALER WON". Which outcome
%   appears and when is entirely driven by the events.tsv, exactly
%   like the original gambling_task.m's guess-doesn't-change-the-outcome
%   design -- the displayed cards and the hit/stay choice are cosmetic only
%   and never alter the scheduled result, matching conf/gambling.toml's
%   glmCondA=win / glmCondB=lose contrast (tie as a covariate) for live
%   analysis. Trials are separated by a variable inter-trial interval
%   (jittered 1.0-3.0s, ~2s mean) of plain fixation, so the design isn't
%   perfectly periodic. 58 trials (24 win / 24 lose / 10 tie), ~5 minutes
%   total.
%
%   THE DEALT CARDS ARE ALWAYS CONSISTENT WITH THE TRIAL'S OUTCOME: the
%   initial two-card hand is never a natural blackjack (an Ace paired with
%   a 10-value card, value 21) on ANY trial -- a 2-card 21 is unbeatable in
%   real blackjack, so it's excluded outright. Beyond that, the hand's own
%   (cosmetic) blackjack value is drawn from a range that actually fits the
%   trial's pre-scripted outcome -- see deal_initial_hand() below: LOSE
%   gets no Aces at all and a value of 12-20; WIN gets a value of 16-20 or
%   under 10 (never the awkward 10-15 middle); TIE is otherwise
%   unconstrained. And whichever card a HIT deals (see deal_hit_card()
%   below) never busts the hand on a WIN or TIE trial, and never brings it
%   to exactly 21 on a LOSE trial -- a real blackjack hand can't win/tie
%   while busted, or lose while sitting on a clean 21.
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
%   The hit/stay response is logged in the timing log's response_key /
%   response_time_s columns (the latter relative to the decision phase's
%   own onset) -- 'none'/NaN if the subject never pressed anything.
%
%   CARD/PROMPT/OUTCOME TEXT FITS THE ACTUAL WINDOW, AT ANY RESOLUTION: like
%   the instructions screen (see ptb_show_instructions.m), the hand,
%   "1 = HIT / 2 = STAY" prompt, and outcome text are each sized with
%   ptb_fit_text_size.m against the real window and given their own
%   non-overlapping vertical region -- so nothing runs off-screen or
%   overlaps at any resolution, whether the hand has two cards or three.
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

    % 'lose' has no fixed text -- it's decided per-trial (BUST vs DEALER WON,
    % see hand_value() and the response-handling below), depending on the
    % cosmetic hand's own blackjack value.
    outcomeStyle = struct( ...
        'win',  struct('text', 'WIN\n+$1.00',  'color', [0 1 0]), ...
        'lose', struct('text', '',             'color', [1 0 0]), ...
        'tie',  struct('text', 'TIE\n$0.00',   'color', [0.6 0.6 0.6]));
    DECISION_S = 2.0;        % max hit/stay decision phase, at the start of each trial
                             % (ends the instant the subject responds -- see the header
                             % comment); Blackjack_events.tsv gives every trial a fixed
                             % 3.0s duration, so the outcome always gets at least 1.0s

    % ---- cosmetic card deck (never drives the real win/lose/tie outcome) ----
    % A hand is at most the 2 initial cards + 1 hit -- never more than 3,
    % since any response (hit or stay) ends the decision phase immediately.
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
        'The goal of the game is to get as close to 21 points as possible, ' ...
        'without going over. Add up the value of the cards in your hand: ' ...
        'number cards are worth their face value, face cards (J, Q, K) are ' ...
        'worth 10 points, and Aces are worth 1 or 11 points. Going over 21 ' ...
        'points means you BUST. If you have more points than the dealer ' ...
        'without busting, you WIN!\n\n' ...
        'Each round you will be dealt two cards. Press 1 to HIT (take another ' ...
        'card) or press 2 to STAY (keep your current hand). You will then see ' ...
        'whether you WON (+$1.00), LOST (-$0.50), or TIED ($0.00) that ' ...
        'round.\n\n' ...
        'Goal: win money by getting the best hand without going BUST. ' ...
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

    % Fixed-text font sizes/wraps computed ONCE against the real window
    % (see ptb_fit_text_size.m) -- the prompt and outcome strings never
    % change trial to trial, so there's no need to remeasure them every
    % frame. Only the hand's own fit (fit_hand(), below) needs recomputing
    % when its cards actually change.
    [promptSize, promptWrap] = ptb_fit_text_size(win, '1 = HIT      2 = STAY', 0.6, 0.10, 32, 14);
    [noRespSize, noRespWrap] = ptb_fit_text_size(win, 'No response\n$0.00', 0.6, 0.3, 48, 18);
    [outcomeStyle.win.fitSize, outcomeStyle.win.fitWrap] = ...
        ptb_fit_text_size(win, outcomeStyle.win.text, 0.6, 0.30, 72, 24);
    [outcomeStyle.tie.fitSize, outcomeStyle.tie.fitWrap] = ...
        ptb_fit_text_size(win, outcomeStyle.tie.text, 0.6, 0.30, 72, 24);

    nEvents = height(events);
    trialActualOnset = nan(nEvents, 1);
    onsetSeen = false(nEvents, 1);
    finalized = false(nEvents, 1);
    handStr = cell(nEvents, 1);          % dealt cards for this trial, e.g. {'AS','7H'}
    handFitSize = nan(nEvents, 1);       % font size/wrap for the big decision-phase
    handFitWrap = nan(nEvents, 1);       % hand display -- see fit_hand() below
    handSmallFitSize = nan(nEvents, 1);  % ...and for the small hand shown alongside
    handSmallFitWrap = nan(nEvents, 1);  % the outcome
    responseTime = nan(nEvents, 1);      % tInEvent of the hit/stay response, if any --
                                          % the decision phase ends the INSTANT this is set
    loseText = cell(nEvents, 1);         % dynamic BUST/DEALER WON text for 'lose' trials --
    loseFitSize = nan(nEvents, 1);       % see hand_value() and the response handling below
    loseFitWrap = nan(nEvents, 1);
    actionTaken = repmat({'none'}, nEvents, 1);   % '1', '2', or 'none'
    respRT = nan(nEvents, 1);            % time of that action, relative to trial onset
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
        % advancing past it -- this is where its recorded response (if any)
        % gets written out, so the log always reflects the FULL trial
        while idx <= nEvents && tNow >= events.onset(idx) + events.duration(idx)
            if ~finalized(idx)
                finalized(idx) = true;
                logRows(end + 1, :) = {char(events.trial_type(idx)), events.onset(idx), ...
                    trialActualOnset(idx), trialActualOnset(idx) - events.onset(idx), ...
                    events.duration(idx), actionTaken{idx}, respRT(idx)}; %#ok<AGROW>
            end
            idx = idx + 1;
        end

        if idx <= nEvents && tNow >= events.onset(idx)
            if ~onsetSeen(idx)
                onsetSeen(idx) = true;
                trialActualOnset(idx) = tNow;
                handStr{idx} = deal_initial_hand(RANKS, TEN_RANKS, ...
                    char(events.trial_type(idx)));
                [handFitSize(idx), handFitWrap(idx), handSmallFitSize(idx), handSmallFitWrap(idx)] = ...
                    fit_hand(win, handStr{idx}, SUIT_SYMS);
            end
            trialType = char(events.trial_type(idx));
            onset = events.onset(idx);
            duration = events.duration(idx);
            tInEvent = tNow - onset;

            if isfield(outcomeStyle, trialType)
                decisionDeadline = min(DECISION_S, duration);   % clamp in case a trial
                                                                 % is ever shorter than DECISION_S
                % `found`/`keyName`/`tStamp` came from the single per-frame
                % queue check above (not a second call) -- a non-response
                % key can't reach here since ResponseKeys is exactly what
                % ptb_kbqueue_setup restricted the queue to (+ESCAPE, already
                % handled above), so any `found` left at this point is a
                % genuine hit/stay press. Only the FIRST one counts -- the
                % instant either key is pressed, the decision phase ends and
                % the outcome (with the extra card, if HIT) is shown right
                % away, for whatever time is left in the trial.
                if found && isnan(responseTime(idx)) && tInEvent < decisionDeadline
                    isHit = strcmp(keyName, '1') || strcmp(keyName, '1!');
                    isStay = strcmp(keyName, '2') || strcmp(keyName, '2@');
                    if isHit || isStay
                        responseTime(idx) = tInEvent;
                        actionTaken{idx} = keyName(1);
                        respRT(idx) = tStamp - t0 - onset;
                        if isHit
                            handStr{idx}{end + 1} = deal_hit_card(RANKS, handStr{idx}, trialType);
                            [handFitSize(idx), handFitWrap(idx), handSmallFitSize(idx), handSmallFitWrap(idx)] = ...
                                fit_hand(win, handStr{idx}, SUIT_SYMS);
                        end
                        if strcmp(trialType, 'lose')
                            % the hand is final now (any hit already happened
                            % above), so BUST/DEALER WON can be decided once,
                            % here, rather than every frame
                            if hand_value(handStr{idx}) > 21
                                reason = 'BUST';
                            else
                                reason = 'DEALER WON';
                            end
                            loseText{idx} = sprintf('%s\n-$0.50', reason);
                            [loseFitSize(idx), loseFitWrap(idx)] = ...
                                ptb_fit_text_size(win, loseText{idx}, 0.6, 0.30, 72, 24);
                        end
                    end
                end

                handText = format_hand(handStr{idx}, SUIT_SYMS);
                if isnan(responseTime(idx)) && tInEvent < decisionDeadline
                    Screen('TextSize', win, handFitSize(idx));
                    draw_at_y(win, handText, 0.28, [1 1 1], handFitWrap(idx));
                    Screen('TextSize', win, promptSize);
                    draw_at_y(win, '1 = HIT      2 = STAY', 0.62, [1 1 1], promptWrap);
                elseif isnan(responseTime(idx))
                    % decision window fully elapsed with no response -- no
                    % reward/loss for this trial, regardless of what the
                    % scheduled outcome would have been (the events.tsv /
                    % GLM design are unaffected; this only changes what's
                    % shown to the subject)
                    Screen('TextSize', win, noRespSize);
                    DrawFormattedText(win, 'No response\n$0.00', 'center', 'center', ...
                        [0.6 0.6 0.6], noRespWrap);
                else
                    if strcmp(trialType, 'lose')
                        outText = loseText{idx};
                        outColor = outcomeStyle.lose.color;
                        outFitSize = loseFitSize(idx);
                        outFitWrap = loseFitWrap(idx);
                    else
                        style = outcomeStyle.(trialType);
                        outText = style.text;
                        outColor = style.color;
                        outFitSize = style.fitSize;
                        outFitWrap = style.fitWrap;
                    end
                    Screen('TextSize', win, handSmallFitSize(idx));
                    draw_at_y(win, handText, 0.12, [0.8 0.8 0.8], handSmallFitWrap(idx));
                    Screen('TextSize', win, outFitSize);
                    draw_at_y(win, outText, 0.45, outColor, outFitWrap);
                end
            else
                Screen('TextSize', win, 36);
                DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
            end
        else
            Screen('TextSize', win, 36);
            DrawFormattedText(win, '+', 'center', 'center', [1 1 1]);
        end

        Screen('Flip', win);
    end

    % flush whichever trial was still active/unfinalized when the run ended
    for i = 1:nEvents
        if onsetSeen(i) && ~finalized(i)
            logRows(end + 1, :) = {char(events.trial_type(i)), events.onset(i), ...
                trialActualOnset(i), trialActualOnset(i) - events.onset(i), ...
                events.duration(i), actionTaken{i}, respRT(i)}; %#ok<AGROW>
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


function total = hand_value(hand)
%HAND_VALUE Standard blackjack scoring of the cosmetic hand: number cards
%   count at face value, face cards (J/Q/K) are worth 10, Aces are worth 11
%   (downgraded to 1 one at a time to avoid busting, if possible) -- used
%   only to decide whether a LOSE trial's feedback says BUST or DEALER WON;
%   the real win/lose/tie outcome stays whatever Blackjack_events.tsv
%   scheduled, regardless of this value.
    total = 0;
    aces = 0;
    for i = 1:numel(hand)
        rank = hand{i}(1:end-1);
        if strcmp(rank, 'A')
            total = total + 11;
            aces = aces + 1;
        elseif any(strcmp(rank, {'J', 'Q', 'K'}))
            total = total + 10;
        else
            total = total + str2double(rank);
        end
    end
    while total > 21 && aces > 0
        total = total - 10;
        aces = aces - 1;
    end
end


function hand = deal_initial_hand(ranks, tenRanks, trialType)
%DEAL_INITIAL_HAND Two cosmetic cards, drawn so their (cosmetic) blackjack
%   value lines up with how plausible the trial's pre-scripted outcome
%   actually is. The opening hand is NEVER a natural blackjack (an Ace
%   paired with a 10-value card, value 21) on ANY trial -- a 2-card 21 is
%   unbeatable in real blackjack, so it's excluded outright. On top of
%   that:
%     - LOSE: no Aces at all (a losing hand that could show an Ace and a
%       10-value card would look like an impossible blackjack loss -- see
%       blackjack_task.m's own header), and a value between 12 and 20 --
%       a hand that's neither an implausible near-certain loss nor
%       obviously about to bust.
%     - WIN: a value of 16-20 (a strong hand) or under 10 (an early hand
%       with plenty of room) -- never the awkward 10-15 middle where
%       staying to win would look odd.
%     - TIE (or anything else): unconstrained beyond the universal
%       no-natural-blackjack rule above.
%   Plain rejection sampling: both target ranges above cover the majority
%   of possible hands, so this converges in a couple of draws on average;
%   the attempt cap below guarantees it terminates even in the unlikely
%   worst case.
    MAX_ATTEMPTS = 300;
    allowAce = ~strcmp(trialType, 'lose');
    aceExclude = {};
    if ~allowAce
        aceExclude = {'A'};
    end
    hand = {};
    for attempt = 1:MAX_ATTEMPTS
        card1 = deal_card(ranks, aceExclude, {});
        rank1 = card1(1:end-1);
        if strcmp(rank1, 'A')
            card2 = deal_card(ranks, tenRanks, aceExclude);
        elseif any(strcmp(rank1, tenRanks))
            card2 = deal_card(ranks, {'A'}, aceExclude);
        else
            card2 = deal_card(ranks, aceExclude, {});
        end
        hand = {card1, card2};
        if in_initial_hand_range(hand_value(hand), trialType)
            return
        end
    end
end


function ok = in_initial_hand_range(value, trialType)
%IN_INITIAL_HAND_RANGE See deal_initial_hand()'s own header for the target
%   range per trial type.
    if strcmp(trialType, 'lose')
        ok = value >= 12 && value <= 20;
    elseif strcmp(trialType, 'win')
        ok = (value >= 16 && value <= 20) || value < 10;
    else
        ok = true;
    end
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


function card = deal_hit_card(ranks, hand, trialType)
%DEAL_HIT_CARD Pick a HIT card that keeps the cosmetic hand's value
%   consistent with the trial's pre-scripted outcome -- a real blackjack
%   hand can never win/tie while busted, and can never lose while sitting
%   on a clean 21:
%     - on a WIN or TIE trial, never deal a card that would push the hand
%       over 21 (bust)
%     - on a LOSE trial, never deal a card that would bring the hand to
%       exactly 21 (Aces are already excluded entirely on LOSE trials --
%       see deal_initial_hand() -- so this only has to watch for
%       10-value cards completing a 21)
%   Falls back to any card if every rank would violate the rule (e.g. the
%   hand is already at 21 before the hit, so any card busts it -- there's
%   no avoiding that one).
    candidates = ranks;
    if strcmp(trialType, 'lose')
        candidates = setdiff(candidates, {'A'}, 'stable');
    end
    safe = {};
    for i = 1:numel(candidates)
        rank = candidates{i};
        candidateHand = [hand, {[rank, 'H']}];
        value = hand_value(candidateHand);
        if (strcmp(trialType, 'win') || strcmp(trialType, 'tie')) && value > 21
            continue
        end
        if strcmp(trialType, 'lose') && value == 21
            continue
        end
        safe{end + 1} = rank; %#ok<AGROW>
    end
    if isempty(safe)
        safe = candidates;
    end
    rank = safe{randi(numel(safe))};
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


function [bigSize, bigWrap, smallSize, smallWrap] = fit_hand(win, hand, suitSyms)
%FIT_HAND Recompute the font-size/wrap fits a hand's display text needs --
%   the large decision-phase display and the smaller top-of-screen display
%   shown alongside the outcome -- against the REAL window (see
%   ptb_fit_text_size.m), so a 2- or 3-card hand is never too big to fit or
%   small enough to be unreadable. Called only when the hand's cards
%   actually change (initial deal, or a hit) -- not every frame.
    handText = format_hand(hand, suitSyms);
    [bigSize, bigWrap] = ptb_fit_text_size(win, handText, 0.8, 0.20, 56, 20);
    [smallSize, smallWrap] = ptb_fit_text_size(win, handText, 0.7, 0.08, 32, 14);
end


function draw_at_y(win, text, yFrac, color, wrapat)
%DRAW_AT_Y Draw `text` horizontally centered at a fixed fraction of the
%   window's actual height (0 = top, 1 = bottom) -- keeps the hand,
%   prompt, outcome, and small-hand elements in separate, non-overlapping
%   vertical regions regardless of resolution, using the wrapat
%   ptb_fit_text_size.m already computed for this text/size pair.
    winRect = Screen('Rect', win);
    yPos = RectHeight(winRect) * yFrac;
    DrawFormattedText(win, text, 'center', yPos, color, wrapat);
end
