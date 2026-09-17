function run_battery(tasks, varargin)
%RUN_BATTERY Run several stimuli_ptb task functions back-to-back in ONE
%   shared Psychtoolbox window, with a harmless "staging" screen between
%   each one instead of the screen closing and dumping back to the MATLAB
%   desktop/workspace after every task.
%
%   RUN_BATTERY(tasks) where `tasks` is a cell array, one entry per task to
%   run in order, each entry itself a 2-element cell {fnHandle, argsCell}:
%     fnHandle  - a stimuli_ptb task function handle, e.g. @motor_task,
%                 @checkerboard_1cond_task, @checkerboard_2cond_task,
%                 @checkerboard_3cond_task, @blackjack_task -- any function
%                 that accepts a 'Win' name-value option (see motor_task.m's
%                 own help for why that option exists).
%     argsCell  - cell array of that task's OWN name-value args (e.g.
%                 {'TriggerKey', {'5','5%','t'}, 'EventsFile', '...'}) --
%                 {} for defaults. 'Win' is added automatically; don't pass
%                 it yourself (it's overridden either way, to keep the
%                 whole battery on the one shared window).
%
%   Name-value options for the SHARED window (apply to every task in the
%   battery -- same physical display/session, so these shouldn't vary
%   task to task):
%     'Windowed'       true for a windowed test window (default false)
%     'ScreenWidth'    \
%     'ScreenHeight'    } pixel resolution to open at (default: [],
%                      auto-detect native resolution). Ignored if 'Windowed'.
%     'SkipSyncTests'  true to disable PTB's flip-timing sync tests, for
%                      testing on a non-research display (default false)
%     'StagingMessage' sprintf template for the between-tasks screen, with
%                      one %s for the upcoming task's name (default:
%                      'Up next: %s (i of N)\n\nExperimenter: press SPACE
%                      to continue.').
%
%   Shows the staging screen BEFORE every task, including the first -- so
%   the experimenter always has a controlled moment to hit SPACE right
%   before a task starts, rather than it auto-starting the instant
%   run_battery is called. Escape at any staging screen stops the whole
%   battery early (the already-open window is still closed cleanly). The
%   window itself is opened ONCE at the start and closed ONCE at the end
%   (or on an aborted battery/any error), never in between -- that's the
%   whole point of this script over calling each task function directly.
%
%   Example:
%     run_battery({ ...
%         {@motor_task,               {}}, ...
%         {@checkerboard_3cond_task,  {}}, ...
%         {@blackjack_task,           {}}, ...
%     })
%     run_battery({{@motor_task, {'TriggerKey', {'space'}}}}, 'Windowed', true)   % quick test

    if nargin < 1 || isempty(tasks)
        fprintf('[run_battery] nothing to run -- `tasks` is empty.\n');
        return
    end

    p = inputParser;
    addParameter(p, 'Windowed', false);
    addParameter(p, 'ScreenWidth', []);
    addParameter(p, 'ScreenHeight', []);
    addParameter(p, 'SkipSyncTests', false);
    addParameter(p, 'StagingMessage', '');
    parse(p, varargin{:});
    opt = p.Results;

    screenSize = [];
    if ~isempty(opt.ScreenWidth) && ~isempty(opt.ScreenHeight)
        screenSize = [opt.ScreenWidth, opt.ScreenHeight];
    end
    win = ptb_open_window(opt.Windowed, opt.SkipSyncTests, [], screenSize);
    cleanupWin = onCleanup(@() sca);   % guarantees the display is released on ANY exit --
                                       % a completed battery, an early Escape-stop, or an error

    for i = 1:numel(tasks)
        fn = tasks{i}{1};
        args = tasks{i}{2};
        taskName = func2str(fn);

        if isempty(opt.StagingMessage)
            msg = sprintf('Up next: %s  (%d of %d)\n\nExperimenter: press SPACE to continue.', ...
                taskName, i, numel(tasks));
        else
            msg = sprintf(opt.StagingMessage, taskName);
        end
        if ptb_show_staging_screen(win, msg)
            fprintf('[run_battery] stopped before task %d/%d (%s).\n', i, numel(tasks), taskName);
            return
        end

        fprintf('[run_battery] starting %d/%d: %s\n', i, numel(tasks), taskName);
        fn(args{:}, 'Win', win);
    end

    plural = '';
    if numel(tasks) ~= 1
        plural = 's';
    end
    fprintf('[run_battery] battery complete (%d task%s).\n', numel(tasks), plural);
end
