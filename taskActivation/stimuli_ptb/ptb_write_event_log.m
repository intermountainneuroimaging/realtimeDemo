function ptb_write_event_log(logPath, header, rows)
%PTB_WRITE_EVENT_LOG Write a tab-delimited log: a header row + cell rows.
%   PTB_WRITE_EVENT_LOG(logPath, header, rows)
%   header - cellstr, one column name per column.
%   rows   - cell array, one row per presented/scored event; each element
%            converted with num2str for numeric values.
%   No-ops if logPath is empty.

    if isempty(logPath)
        return
    end
    [logDir, ~, ~] = fileparts(logPath);
    if ~isempty(logDir) && ~exist(logDir, 'dir')
        mkdir(logDir);
    end
    fid = fopen(logPath, 'w');
    if fid == -1
        warning('ptb_write_event_log:openFailed', 'Could not open %s for writing.', logPath);
        return
    end
    cleaner = onCleanup(@() fclose(fid));
    fprintf(fid, '%s\n', strjoin(header, '\t'));
    for r = 1:size(rows, 1)
        parts = cell(1, size(rows, 2));
        for c = 1:size(rows, 2)
            v = rows{r, c};
            if isnumeric(v)
                parts{c} = num2str(v, '%.3f');
            else
                parts{c} = char(v);
            end
        end
        fprintf(fid, '%s\n', strjoin(parts, '\t'));
    end
    fprintf('[stimuli] wrote timing log: %s\n', logPath);
end
