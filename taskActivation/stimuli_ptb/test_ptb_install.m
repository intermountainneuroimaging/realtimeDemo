function test_ptb_install(varargin)
%TEST_PTB_INSTALL Minimal smoke test to confirm Psychtoolbox-3 is installed
%   AND its display/keyboard backend actually works, before running
%   motor_task.m / gambling_task.m / checkerboard_task.m for real.
%   Installing Psychtoolbox doesn't guarantee this -- the window backend
%   (OpenGL/GStreamer drivers) and low-level keyboard queue are the parts
%   that most often fail, silently or not, depending on the OS/GPU drivers.
%
%   Checks, in order: (1) Screen() (the core PTB mex file) is on the path
%   and runs, (2) a window actually opens, (3) a keypress is detected via
%   KbQueue. Each step prints [ok]/[FAIL] so a failure tells you exactly
%   which layer broke.
%
%   Also prints the exact PTB key name for anything you press -- use this to
%   discover what your scanner trigger / response button box actually
%   reports (e.g. '5' vs '5%', '1' vs '1!') before setting TriggerKey /
%   ResponseKeys in the task scripts.
%
%   Name-value options:
%     'Windowed'     true for a windowed test window (default false)
%     'ScreenWidth'  \
%     'ScreenHeight'  } pixel resolution to open at (default: [],
%                     auto-detect native resolution). Ignored if 'Windowed'.
%
%   Run (at the MATLAB prompt, from this folder):
%     test_ptb_install
%     test_ptb_install('Windowed', true)
%     test_ptb_install('ScreenWidth', 1920, 'ScreenHeight', 1080)

    p = inputParser;
    addParameter(p, 'Windowed', false);
    addParameter(p, 'ScreenWidth', []);
    addParameter(p, 'ScreenHeight', []);
    parse(p, varargin{:});
    windowed = p.Results.Windowed;
    screenSize = [];
    if ~isempty(p.Results.ScreenWidth) && ~isempty(p.Results.ScreenHeight)
        screenSize = [p.Results.ScreenWidth, p.Results.ScreenHeight];
    end

    % ---- 1. Screen() is on the path and runs ----
    try
        ver = Screen('Version');
    catch e
        fprintf('[FAIL] Screen() is not available: %s\n', e.message);
        fprintf('       Psychtoolbox-3 is not installed / not on the MATLAB path.\n');
        fprintf('       See stimuli_ptb/README.md''s ''Install and test Psychtoolbox'' section.\n');
        return
    end
    fprintf('[ok] Psychtoolbox %s found\n', ver.string);

    % ---- 2. open a window (this is where display/driver issues usually surface) ----
    try
        win = ptb_open_window(windowed, true, [], screenSize);   % SkipSyncTests=true: smoke test only
    catch e
        fprintf('[FAIL] Psychtoolbox is installed, but couldn''t open a window: %s\n', e.message);
        fprintf('       almost always a display/GPU-driver issue, not a Psychtoolbox bug --\n');
        fprintf('       see stimuli_ptb/README.md.\n');
        sca;
        return
    end
    fprintf('[ok] window opened successfully\n');

    % ---- 3. draw + detect a keypress via KbQueue (same mechanism the task
    %      scripts use for real responses -- see ptb_kbqueue_setup.m) ----
    cleanupWin = onCleanup(@() sca); %#ok<NASGU>
    DrawFormattedText(win, sprintf(['Psychtoolbox %s is working!\n\n' ...
        'Press any key (or wait 5s) to finish the test.'], ver.string), ...
        'center', 'center', [1 1 1]);
    Screen('Flip', win);

    KbQueueCreate([], ones(1, 256));   % every key, not just a restricted list --
                                       % any press should register for this smoke test
    KbQueueStart;

    found = false;
    tStart = GetSecs;
    while GetSecs - tStart < 5.0
        [f, keyName] = ptb_kbqueue_check_any();
        if f
            found = true;
            break
        end
        WaitSecs(0.005);
    end
    ptb_kbqueue_teardown();

    if found
        fprintf('[ok] keypress detected: %s\n', keyName);
    else
        fprintf(['[warn] no keypress detected within 5s (timed out) -- the window rendered\n' ...
                 '       fine, but double check keyboard input is reaching MATLAB/Psychtoolbox\n' ...
                 '       (on macOS this often means granting Accessibility/Input Monitoring\n' ...
                 '       permission to MATLAB in System Settings > Privacy & Security).\n']);
    end
    fprintf(['\n[ok] Psychtoolbox install looks good -- you''re ready to run motor_task.m /\n' ...
             'gambling_task.m / checkerboard_task.m.\n']);
end
