function [win, winRect] = ptb_open_window(windowed, skipSyncTests, bgColor, screenSize)
%PTB_OPEN_WINDOW Standard Psychtoolbox window setup used by every task script.
%   [win, winRect] = PTB_OPEN_WINDOW(windowed, skipSyncTests, bgColor, screenSize)
%
%   windowed       - false (default): fill `screenSize` (or the display's
%                    native resolution if screenSize is empty) on the
%                    stimulus display. true: a windowed 1024x768 patch for
%                    testing on a laptop.
%   skipSyncTests  - true disables PTB's flip-timing sync tests
%                    (Screen('Preference','SkipSyncTests',1)) -- only for
%                    testing on a non-research display (laptop, VM, remote
%                    desktop) that can't pass them; leave false in the
%                    scanner room so real timing problems aren't hidden.
%   bgColor        - background color, default black ([0 0 0]).
%   screenSize     - [width height] in pixels to open, e.g. [1920 1080] to
%                    match a known scanner-room projector's native output.
%                    Default []: auto-detect the display's own resolution
%                    (Screen('Rect')) rather than assuming a fixed size --
%                    pass this explicitly whenever the projector's reported
%                    resolution can't be trusted, or to keep stimulus size
%                    in pixels reproducible across different rooms/monitors.
%
%   Display selection: with more than one screen attached, this opens on
%   the SECOND one (Screen('Screens') index 2) -- the stimulus/projector
%   display in a typical two-monitor scanner-room setup (control room
%   monitor = screen 1, projector/display = screen 2) -- falling back to
%   the only screen available if there's just one.
%
%   Calls KbName('UnifyKeyNames') once, so every task script gets
%   consistent cross-platform key names without repeating that boilerplate.
%   Deliberately does NOT call PsychDefaultSetup -- that wraps an
%   AssertOpenGL check which has been observed to fail on some working
%   Psychtoolbox installs even though Screen()/PsychImaging work fine
%   called directly (this matches a known-working lab script for this
%   project, which never calls PsychDefaultSetup either). Screen('ColorRange')
%   below gets the same normalized 0-1 color convention PsychDefaultSetup(2)
%   would have set, without going through AssertOpenGL to get it.

    if nargin < 1 || isempty(windowed);      windowed = false;      end
    if nargin < 2 || isempty(skipSyncTests);  skipSyncTests = false; end
    if nargin < 3 || isempty(bgColor);        bgColor = [0 0 0];     end
    if nargin < 4;                            screenSize = [];       end

    KbName('UnifyKeyNames');
    Screen('Preference', 'SkipSyncTests', double(skipSyncTests));

    screens = Screen('Screens');
    screenNumber = screens(min(2, numel(screens)));   % prefer the 2nd (stimulus) display

    if windowed
        rect = [0 0 1024 768];
        [win, winRect] = PsychImaging('OpenWindow', screenNumber, bgColor, rect);
    elseif ~isempty(screenSize)
        rect = [0 0 screenSize(1) screenSize(2)];
        [win, winRect] = PsychImaging('OpenWindow', screenNumber, bgColor, rect);
    else
        [win, winRect] = PsychImaging('OpenWindow', screenNumber, bgColor);
    end
    Screen('ColorRange', win, 1);   % normalized 0.0-1.0 color values (this project's
                                    % task scripts all use e.g. [1 1 1], [0 1 0])
    Screen('TextSize', win, 36);
    Screen('BlendFunction', win, 'GL_SRC_ALPHA', 'GL_ONE_MINUS_SRC_ALPHA');
end
