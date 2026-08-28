function ptb_kbqueue_teardown()
%PTB_KBQUEUE_TEARDOWN Stop and release the KbQueue started by ptb_kbqueue_setup.
    KbQueueStop;
    KbQueueFlush;
    KbQueueRelease;
end
