function events = ptb_read_events_tsv(path)
%PTB_READ_EVENTS_TSV Read a BIDS-style events.tsv (onset, duration, trial_type).
%   events = PTB_READ_EVENTS_TSV(path) returns a table with columns
%   onset (double, seconds), duration (double, seconds), and trial_type
%   (cellstr), sorted by onset. Same file format/columns as this project's
%   Python side (utils/rt_analysis.py's read_events_tsv) -- both read the
%   exact same study_design/*_events.tsv files, so the schedule actually
%   presented to the subject can never drift out of sync with what
%   taskActivation.py's real-time GLM design assumes.

    opts = detectImportOptions(path, 'FileType', 'text', 'Delimiter', '\t');
    opts = setvartype(opts, 'trial_type', 'string');
    events = readtable(path, opts);
    events.trial_type = strtrim(string(events.trial_type));
    events = sortrows(events, 'onset');
end
