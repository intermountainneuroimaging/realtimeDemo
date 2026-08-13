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

Usage:
  # one-shot: bridge whatever's already in the drop folder, then exit
  python dicom_bridge.py --config conf/taskActivation.toml \\
      --source /Volumes/sambashare/some_session --series 3 --once

  # continuous: bridge existing files, then keep watching for new ones
  python dicom_bridge.py --config conf/taskActivation.toml \\
      --source /Volumes/sambashare/some_session --series 3
-----------------------------------------------------------------------------"""
import os
import sys
import time
import argparse
import numpy as np

import mock_scanner as mock   # reuses its tiny rtCommon-free toml reader
import rt_analysis as mrt

HERE = os.path.dirname(os.path.realpath(__file__))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bridge real scanner DICOMs into rt-cloud's expected filenames.")
    ap.add_argument('--config', default=os.path.join(HERE, 'conf', 'taskActivation.toml'))
    ap.add_argument('--source', required=True, help='real scanner drop folder to watch')
    ap.add_argument('--dest', default=None, help='dicomDir to bridge into (default: project dicomDir)')
    ap.add_argument('--series', type=int, required=True,
                    help='DICOM SeriesNumber to bridge (read from each file\'s header, not its filename)')
    ap.add_argument('--run', type=int, default=None, help='RUN token for the output filename (default from config runNum)')
    ap.add_argument('--poll-interval', type=float, default=1.0, help='seconds between rescans in watch mode')
    ap.add_argument('--settle-secs', type=float, default=0.5,
                    help='wait this long and re-check file size before treating a file as fully written')
    ap.add_argument('--once', action='store_true', help='bridge whatever matches now, then exit (no watching)')
    args = ap.parse_args(argv)

    try:
        import pydicom
    except Exception:
        print("[bridge] pydicom is required (pip install pydicom)"); return 1

    cfg = mock.load_cfg(args.config)
    pattern = str(cfg.get('dicomNamePattern', '001_{RUN:06d}_{TR:06d}.dcm'))
    run = args.run if args.run is not None else int(np.ravel(cfg.get('runNum', [1]))[0]) \
        if not isinstance(cfg.get('runNum', [1]), str) else 1
    dest_dir = args.dest or os.path.join(HERE, 'dicomDir')
    os.makedirs(dest_dir, exist_ok=True)

    print(f"[bridge] watching {args.source}  series={args.series}  -> {dest_dir}  "
          f"pattern={pattern} (RUN={run})" + ("  (one-shot)" if args.once else ""))

    seen = set()   # source filenames already bridged (or confirmed not-yet-complete this pass)

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
        if series_no != args.series:
            return True   # not our series; don't retry, but don't error either
        instance = int(getattr(ds_head, 'InstanceNumber', -1))
        if instance < 1:
            print(f"[bridge] skip (no InstanceNumber) {os.path.basename(src_path)}")
            return False
        fname = pattern.format(RUN=run, SCAN=run, TR=instance)
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
        print(f"[bridge] vol {instance:3d}  {os.path.basename(src_path)}  ->  {fname}")
        return True

    def scan_once():
        try:
            candidates = sorted(f for f in os.listdir(args.source) if f.lower().endswith('.dcm'))
        except OSError as e:
            print(f"[bridge] cannot list {args.source}: {e}")
            return
        for fname in candidates:
            if fname in seen:
                continue
            src_path = os.path.join(args.source, fname)
            if bridge_one(src_path):
                seen.add(fname)

    scan_once()
    if args.once:
        print(f"[bridge] done (one-shot): {len(seen)} files bridged/skipped")
        return 0

    try:
        while True:
            time.sleep(args.poll_interval)
            scan_once()
    except KeyboardInterrupt:
        print(f"\n[bridge] stopped: {len(seen)} files bridged/skipped")
    return 0


if __name__ == '__main__':
    sys.exit(main())
