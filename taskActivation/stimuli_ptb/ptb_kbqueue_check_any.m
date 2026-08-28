function [found, keyName, tStamp] = ptb_kbqueue_check_any()
%PTB_KBQUEUE_CHECK_ANY Return the earliest keypress buffered since the last check.
%   [found, keyName, tStamp] = PTB_KBQUEUE_CHECK_ANY()
%
%   Drains whatever KbQueueCheck has buffered since it was last called (or
%   since ptb_kbqueue_setup started the queue, if this is the first call)
%   and returns the EARLIEST press in that window -- so even if the loop
%   calling this only gets around to it once every few frames, a brief
%   button-box pulse that happened in between is still reported, with its
%   real press timestamp (GetSecs time base), not the time this function
%   happened to be called. Returns found=false if nothing was pressed.
%   Cheap enough to call every frame.

    [pressed, firstPress] = KbQueueCheck;
    found = false;
    keyName = '';
    tStamp = NaN;
    if ~pressed
        return
    end
    codes = find(firstPress > 0);
    if isempty(codes)
        return
    end
    [tStamp, which] = min(firstPress(codes));
    keyName = KbName(codes(which));
    found = true;
end
