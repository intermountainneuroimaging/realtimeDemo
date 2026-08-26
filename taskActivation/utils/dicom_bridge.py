#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
dicom_bridge.py  —  bridge a real scanner's raw DICOM drop folder into the
predictable filenames RT-Cloud's DICOM watcher requires.

WHY THIS EXISTS: rt-cloud's DicomToBidsStream builds the exact filename it
expects for each volume with plain str.format() (`filePattern.format(TR=n)`)
and waits for that one exact path — there is no wildcard/glob matching. Real
scanner exports commonly append an unpredictable SOPInstanceUID to the
filename (e.g. Siemens real-time push scripts:
`002_000003_000001_1.3.12.2.1107....dcm`), which rt-cloud can never match no
matter what dicomNamePattern is configured. This script watches the real drop
folder, reads each file's actual SeriesNumber/InstanceNumber from its DICOM
header (not the filename — filename conventions vary by site), and copies it
into dicomDir/ renamed to match dicomNamePattern exactly, so rt-cloud's
watcher can find it.

It also has to patch one metadata field: rt-cloud's own metadata reader
(rtCommon.bidsCommon.getDicomMetadata) only iterates TOP-LEVEL DICOM elements,
so it never sees an Enhanced-multi-frame file's RepetitionTime, which lives
nested in SharedFunctionalGroupsSequence per the Enhanced MR IOD -- every
volume would otherwise fail with MissingMetadataError even though the file is
perfectly valid and dcm2niix parses it fine. This script copies that one value
up to a top-level element on the way through (see
rt_analysis.promote_repetition_time_to_top_level). Pixel data itself is never
touched or re-encoded -- dcm2niix (which rt-cloud uses internally) already
handles Enhanced multi-frame DICOM natively.

PHI note: real scanner files carry real PatientName/PatientID/etc. until
rt-cloud's own `anonymize=True` (already set in taskActivation.py's
initDicomBidsStream call) strips them on read — the same as a real scanner's
raw feed would. This script doesn't change that; it's expected, not a new
exposure introduced here.

--source is searched recursively, so it's fine to point it at a parent
directory the scanner organizes into per-session subfolders (e.g.
`<source>/20260812.some_study.some_study/*.dcm`) rather than a single flat
folder -- every .dcm found at any depth underneath --source is a candidate,
tracked by its full path (not just its basename) so two sessions that happen
to reuse the same instance filenames (e.g. both starting at IM001.dcm) never
collide or get skipped as duplicates of each other.

RUN in the output filename is, by default, each file's own real SeriesNumber
-- not a fixed value -- so bridging every series present is collision-safe
(series 2 and series 3 land in dicomDir/ with distinct RUN labels, never the
same filename). Pass --series to bridge only one series, and/or --run to
force a fixed RUN label instead (e.g. to keep the toml's runNum stable across
sessions whose real series numbers change); --run requires --series, since
forcing one RUN value while bridging multiple series would collide.

AUTO-CLEANUP: this also deletes *.dcm/*.dcm.part files older than
--max-age-hours (default 24) in --dest -- once at startup (after this
session's own files have had their chance to bridge first) and again every
--clean-interval-hours while watching, so a long-running background service
(see INSTALLATION.md's systemd/launchd section) doesn't quietly accumulate
DICOMs from every past session across days or weeks, and so stale leftovers
can't mix with a new run's DICOMs the way that caused
`MetadataMismatchError: ... mismatch in dimensions and pixdim fields` before
(see TESTING.md). Cleanup recurses the same way scanning does, and removes
any per-session subfolder left empty afterward. Pass --max-age-hours 0 to
disable it.

--dest cleanup is ON by default (it's this script's own disposable output).
--source cleanup (the real scanner's own export folder) is OPT-IN only, via
--source-max-age-hours -- that folder may be the only copy of that data, and
retention there is a site policy decision, not something this script should
default to doing.

Usage (run from the taskActivation/ project root):
  # bridge every series found; each gets its own RUN = its real SeriesNumber
  python utils/dicom_bridge.py --config conf/taskActivation.toml \\
      --source /Volumes/sambashare/some_session

  # only series 3, one-shot backfill of what's already there
  python utils/dicom_bridge.py --config conf/taskActivation.toml \\
      --source /Volumes/sambashare/some_session --series 3 --once

  # only series 3, but relabel it as RUN 1 (matches a toml with runNum = [1])
  python utils/dicom_bridge.py --config conf/taskActivation.toml \\
      --source /Volumes/sambashare/some_session --series 3 --run 1

  # also clean the scanner's own export folder (opt-in -- see AUTO-CLEANUP above)
  python utils/dicom_bridge.py --config conf/taskActivation.toml \\
      --source /Volumes/sambashare/some_session --source-max-age-hours 72
-----------------------------------------------------------------------------"""
import os
import sys
import time
import argparse

import mock_scanner as mock   # reuses its tiny rtCommon-free toml reader
import rt_analysis as mrt

HERE = os.path.dirname(os.path.realpath(__file__))          # utils/ -- this script's own dir
PROJECT_ROOT = os.path.dirname(HERE)                         # taskActivation/ -- conf/, dicomDir/


def clean_old_files(folder, max_age_hours, label=''):
    """Delete *.dcm/*.dcm.part files anywhere under `folder` (recursively --
    --source in particular may have a subfolder per session, e.g.
    20260812.realtime_test.realtime_test/*.dcm) whose mtime is older than
    `max_age_hours`, then remove any subfolder that's now empty (so old
    per-session folders don't pile up forever once their contents have all
    aged out). `max_age_hours <= 0` disables this (no-op). `label` is just
    for the log line (e.g. 'dest' vs 'source'). Returns the number of files
    removed.

    Called on BOTH --dest and --source in main() -- --dest is this script's
    own disposable output, safe to age out by default; --source is the real
    scanner's own export and may be the only copy of that data, so its
    cleanup is opt-in only (see --source-max-age-hours) rather than sharing
    --dest's default."""
    if max_age_hours <= 0:
        return 0
    cutoff = time.time() - max_age_hours * 3600

    def _walk_error(e):
        print(f"[bridge][clean] cannot list {getattr(e, 'filename', folder)}: {e}")

    removed = 0
    emptied_dirs = 0
    # topdown=False so subfolders are visited (and can be found empty) before
    # their own parent is checked
    for dirpath, dirnames, filenames in os.walk(folder, topdown=False, onerror=_walk_error):
        for name in filenames:
            if not (name.lower().endswith('.dcm') or name.lower().endswith('.dcm.part')):
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass   # already gone, or a permissions blip -- next sweep will retry
        if dirpath != folder:   # never remove `folder` itself, only session subfolders under it
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    emptied_dirs += 1
            except OSError:
                pass   # not actually empty (non-.dcm files present), or a permissions blip
    if removed or emptied_dirs:
        tag = f" ({label})" if label else ""
        print(f"[bridge][clean]{tag} removed {removed} file(s) and {emptied_dirs} now-empty "
              f"folder(s) older than {max_age_hours:g}h from {folder}")
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bridge real scanner DICOMs into rt-cloud's expected filenames.")
    ap.add_argument('--config', default=os.path.join(PROJECT_ROOT, 'conf', 'taskActivation.toml'))
    ap.add_argument('--source', required=True, help='real scanner drop folder to watch')
    ap.add_argument('--dest', default=None, help='dicomDir to bridge into (default: project dicomDir)')
    ap.add_argument('--series', type=int, default=None,
                    help='only bridge this DICOM SeriesNumber (read from each file\'s header, not '
                         'its filename); omit to bridge every series found, each kept separate by '
                         'its own SeriesNumber in the output filename')
    ap.add_argument('--run', type=int, default=None,
                    help='force this RUN value in the output filename instead of each file\'s own '
                         'SeriesNumber. Requires --series -- forcing one RUN value while bridging '
                         'multiple series would collide in dicomDir/')
    ap.add_argument('--poll-interval', type=float, default=1.0, help='seconds between rescans in watch mode')
    ap.add_argument('--settle-secs', type=float, default=0.5,
                    help='wait this long and re-check file size before treating a file as fully written')
    ap.add_argument('--once', action='store_true', help='bridge whatever matches now, then exit (no watching)')
    ap.add_argument('--max-age-hours', type=float, default=24.0,
                    help='delete *.dcm/*.dcm.part files in --dest older than this (0 disables). '
                         'Runs once at startup and again every --clean-interval-hours while '
                         'watching.')
    ap.add_argument('--source-max-age-hours', type=float, default=0.0,
                    help="ALSO delete *.dcm files older than this in --source, the real scanner's "
                         'own export folder (0/default: disabled -- opt in explicitly, since unlike '
                         '--dest this may be the only copy of that data and some sites need to '
                         'retain it under their own policy regardless of what this script does).')
    ap.add_argument('--clean-interval-hours', type=float, default=1.0,
                    help='how often to re-run the age sweep(s) while watching (ignored with '
                         '--once, and if both age options are 0)')
    args = ap.parse_args(argv)

    if args.run is not None and args.series is None:
        print("[bridge] --run requires --series (forcing one RUN value while bridging "
              "multiple series would collide in dicomDir/)")
        return 1

    try:
        import pydicom
    except Exception:
        print("[bridge] pydicom is required (pip install pydicom)"); return 1

    cfg = mock.load_cfg(args.config)
    pattern = str(cfg.get('dicomNamePattern', 'demo_{RUN:06d}_{TR:06d}.dcm'))
    dest_dir = args.dest or os.path.join(PROJECT_ROOT, 'dicomDir')
    os.makedirs(dest_dir, exist_ok=True)

    series_desc = f"series={args.series}" if args.series is not None else "series=ALL"
    run_desc = f"RUN forced to {args.run}" if args.run is not None else "RUN = each file's own SeriesNumber"
    print(f"[bridge] watching {args.source}  {series_desc}  -> {dest_dir}  "
          f"pattern={pattern}  {run_desc}" + ("  (one-shot)" if args.once else ""))
    if args.source_max_age_hours > 0:
        print(f"[bridge][clean] auto-cleanup ENABLED for --source too "
              f"(>{args.source_max_age_hours:g}h) -- this deletes real scanner DICOMs, "
              "not just bridged copies")

    def run_cleanup():
        # dest first, then source -- bridging always gets first crack at a file (scan_once()
        # runs before every call to this, see below) before source cleanup could ever delete it
        clean_old_files(dest_dir, args.max_age_hours, label='dest')
        if args.source_max_age_hours > 0:
            clean_old_files(args.source, args.source_max_age_hours, label='source')

    seen = set()   # source FULL PATHS already bridged (or confirmed not-yet-complete this pass) --
                   # full path, not just the basename, since --source can have one subfolder per
                   # session (e.g. 20260812.realtime_test.realtime_test/*.dcm) and different
                   # sessions can easily reuse the same instance filenames

    def settled(path):
        try:
            sz1 = os.path.getsize(path)
        except OSError:
            return False
        time.sleep(args.settle_secs)
        try:
            sz2 = os.path.getsize(path)
        except OSError:
            return False
        return sz1 == sz2 and sz1 > 0

    def bridge_one(src_path):
        try:
            ds_head = pydicom.dcmread(src_path, stop_before_pixels=True)
        except Exception as e:
            print(f"[bridge] skip (unreadable, retry later) {os.path.basename(src_path)}: {e}")
            return False
        series_no = int(getattr(ds_head, 'SeriesNumber', -1))
        if args.series is not None and series_no != args.series:
            return True   # not the one we want; don't retry, but don't error either
        instance = int(getattr(ds_head, 'InstanceNumber', -1))
        if instance < 1:
            print(f"[bridge] skip (no InstanceNumber) {os.path.basename(src_path)}")
            return False
        run_for_file = args.run if args.run is not None else series_no
        fname = pattern.format(RUN=run_for_file, SCAN=run_for_file, TR=instance)
        dst_path = os.path.join(dest_dir, fname)
        if os.path.exists(dst_path):
            return True
        if not settled(src_path):
            return False   # still being written; try again next pass
        ds = pydicom.dcmread(src_path)   # full read (incl. pixel data) to write back out
        if not mrt.promote_repetition_time_to_top_level(ds):
            print(f"[bridge][warn] {os.path.basename(src_path)} has no RepetitionTime "
                  "anywhere -- rt-cloud will reject this volume with MissingMetadataError")
        tmp = dst_path + '.part'
        ds.save_as(tmp, write_like_original=False)
        os.replace(tmp, dst_path)
        print(f"[bridge] series {series_no} vol {instance:3d}  {os.path.basename(src_path)}  ->  {fname}")
        return True

    def scan_once():
        # os.walk, not os.listdir -- --source may have a subfolder per session
        # (e.g. 20260812.realtime_test.realtime_test/*.dcm) rather than DICOMs
        # sitting directly in --source itself; walking finds them at any depth.
        # onerror is required -- os.walk silently swallows listing errors
        # otherwise (e.g. --source itself unmounted/unreadable), which would
        # look identical to "just no new files yet" instead of a real problem.
        def _walk_error(e):
            print(f"[bridge] cannot list {getattr(e, 'filename', args.source)}: {e}")
        candidates = []
        for dirpath, _dirnames, filenames in os.walk(args.source, onerror=_walk_error):
            for fname in filenames:
                if fname.lower().endswith('.dcm'):
                    candidates.append(os.path.join(dirpath, fname))
        candidates.sort()
        for src_path in candidates:
            if src_path in seen:
                continue
            if bridge_one(src_path):
                seen.add(src_path)

    scan_once()
    run_cleanup()   # startup sweep -- catches leftovers from a previous session, after this
                    # session's own files have had their chance to bridge first
    if args.once:
        print(f"[bridge] done (one-shot): {len(seen)} files bridged/skipped")
        return 0

    last_clean = time.time()
    try:
        while True:
            time.sleep(args.poll_interval)
            scan_once()
            if time.time() - last_clean >= args.clean_interval_hours * 3600:
                run_cleanup()
                last_clean = time.time()
    except KeyboardInterrupt:
        print(f"\n[bridge] stopped: {len(seen)} files bridged/skipped")
    return 0


if __name__ == '__main__':
    sys.exit(main())
