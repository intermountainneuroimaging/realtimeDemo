function [textSize, wrapat] = ptb_fit_text_size(win, text, targetWFrac, targetHFrac, maxTextSize, minTextSize)
%PTB_FIT_TEXT_SIZE Find a TextSize + wrapat for `text` that actually fits
%   within targetWFrac * (this window's real width) and targetHFrac * (this
%   window's real height) -- shared by ptb_show_instructions.m and any task
%   that needs text sized correctly at whatever resolution the window
%   actually opened at (fullscreen on a scanner-room projector, or the
%   small 1024x768 'Windowed' test window), rather than a fixed font size
%   and wrap-at character count eyeballed on one particular screen.
%
%   [textSize, wrapat] = PTB_FIT_TEXT_SIZE(win, text, targetWFrac, targetHFrac, maxTextSize, minTextSize)
%
%   targetWFrac, targetHFrac - fraction (0-1) of the window's actual width/
%                              height the text should fit within.
%   maxTextSize, minTextSize - starting point and floor for the search
%                              (default 48 / 14).
%
%   Measures with DrawFormattedText's DoDraw=0 "measure only" mode against
%   Screen('Rect') -- see ptb_show_instructions.m's own header for why this
%   is more robust than a fixed size/wrapat.
%
%   NOTE: sets Screen('TextSize', win, ...) as a side effect of measuring
%   (needed to measure at each candidate size) -- callers should always
%   Screen('TextSize', win, textSize) again right before actually drawing,
%   rather than assume it's still set to the returned value.

    if nargin < 5 || isempty(maxTextSize); maxTextSize = 48; end
    if nargin < 6 || isempty(minTextSize); minTextSize = 14; end

    winRect = Screen('Rect', win);
    targetW = targetWFrac * RectWidth(winRect);
    targetH = targetHFrac * RectHeight(winRect);

    textSize = maxTextSize;
    wrapat = 60;
    while true
        Screen('TextSize', win, textSize);
        % average character width at THIS size, for THIS window's font --
        % converts the width budget (pixels) into DrawFormattedText's
        % wrapat (characters), which is otherwise resolution/font-size blind
        charBounds = Screen('TextBounds', win, repmat('m', 1, 20));
        avgCharW = RectWidth(charBounds) / 20;
        wrapat = max(20, floor(targetW / avgCharW));

        [~, ~, textbounds] = DrawFormattedText(win, text, 'center', 'center', ...
            [1 1 1], wrapat, [], [], [], [], [], 0);   % DoDraw=0: measure, don't draw
        if RectHeight(textbounds) <= targetH || textSize <= minTextSize
            break
        end
        textSize = textSize - 2;
    end
end
