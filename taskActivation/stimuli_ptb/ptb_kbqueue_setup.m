function ptb_kbqueue_setup(keyNames)
%PTB_KBQUEUE_SETUP Create and start a KbQueue restricted to `keyNames` (+ESCAPE).
%   PTB_KBQUEUE_SETUP(keyNames) -- keyNames is a cellstr of PTB key names
%   (see KbName), e.g. {'5','t'} or {'1','2','3','4'}.
%
%   WHY A QUEUE, NOT KbCheck/KbWait: a plain KbCheck only reports whatever
%   is down at the exact instant you call it -- fine for a real keyboard
%   held down for a while, but an MRI-compatible response button box
%   typically presents itself as a keyboard device sending one very brief
%   keydown/keyup pulse per press. In a realtime presentation loop (busy
%   drawing/flipping frames), that pulse can easily fall entirely between
%   two KbCheck calls and simply never be seen. KbQueueCreate/Start hands
%   the keyboard buffering off to PTB's own background collection (a
%   separate low-latency thread), which timestamps and stores every
%   press/release the instant it happens regardless of what the main loop
%   is doing -- so KbQueueCheck (called whenever convenient later) always
%   sees it. See ptb_kbqueue_check_any.m for reading what's been buffered,
%   and ptb_kbqueue_teardown.m to stop/clean up at the end of a run.
%
%   Call this ONCE, before the period during which responses matter (the
%   whole run, in gambling_task.m) -- not once per trial.

    if nargin < 1 || isempty(keyNames)
        keyNames = {};
    end
    allKeys = [keyNames(:)', {'ESCAPE'}];
    keyList = zeros(1, 256);
    for i = 1:numel(allKeys)
        code = KbName(allKeys{i});
        keyList(code(1)) = 1;   % code(1): some key names map to >1 physical key
    end
    KbQueueCreate([], keyList);
    KbQueueStart;
end
