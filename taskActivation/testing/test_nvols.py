"""-----------------------------------------------------------------------------
test_nvols.py — offline test of how many volumes a run expects.

A live DICOM stream can't report its own length, so taskActivation.py works the
count out itself (rt_analysis.resolve_nvols) and waits for every volume up to
it. A count that is too HIGH makes the run stall at the end until dicomTimeout
and abort BEFORE the final plot / recap / GIF are written -- so this checks:
  * resolve_nvols(): nVols beats scanTime beats the events-file estimate;
    scanTime is rounded DOWN (a missing last partial volume is harmless, waiting
    on one that never arrives is not) and scales with TR; bad input is refused,
  * every shipped task config prescribes scanTime, and it equals its events
    file's last event end (so the two can't drift apart),
  * the resulting counts (e.g. 250 volumes at TR 1 s / 125 at TR 2 s for motor),
  * the mock scanner writes exactly the prescribed number of DICOMs by default
    (what a real scan of the task acquires), not the old design + 10.
No FSL / Docker / scanner needed.

Run:  python testing/test_nvols.py
-----------------------------------------------------------------------------"""
import os
import sys
import shutil
import tempfile
import warnings

HERE = os.path.dirname(os.path.realpath(__file__))           # testing/
PROJECT_ROOT = os.path.dirname(HERE)                          # taskActivation/
sys.path.append(os.path.join(PROJECT_ROOT, 'utils'))
sys.path.append(PROJECT_ROOT)
import rt_analysis as mrt
import mock_scanner as mock
import run_task
warnings.filterwarnings('ignore')

events = [(0.0, 10.0, 'rest'), (10.0, 20.0, 'left'), (30.0, 12.0, 'rest')]   # ends at 42.0 s
checks = {}
r = mrt.resolve_nvols

checks['explicit_nVols_wins_over_everything'] = r(1.0, events, n_vols=99, scan_time=250.0)[0] == 99
checks['scanTime_over_events_estimate'] = r(1.0, events, scan_time=250.0)[0] == 250
checks['scanTime_scales_with_TR'] = (r(2.0, events, scan_time=250.0)[0] == 125
                                     and r(1.0, events, scan_time=250.0)[0] == 250)
checks['scanTime_rounds_down'] = r(2.5, events, scan_time=204.0)[0] == 81          # 81.6 -> 81
checks['scanTime_float_noise_is_not_a_volume_short'] = r(0.1, events, scan_time=1.0)[0] == 10
checks['fallback_is_events_end_plus_padding'] = r(1.0, events)[0] == 42 + 10
checks['fallback_padding_is_a_parameter'] = r(2.0, events, padding=0)[0] == 21
checks['unset_values_mean_not_set'] = r(1.0, events, n_vols=0, scan_time=0.0)[0] == 52
checks['source_text_says_where_it_came_from'] = (
    'scanTime' in r(1.0, events, scan_time=42.0)[1] and 'nVols' in r(1.0, events, n_vols=7)[1]
    and 'estimated' in r(1.0, events)[1])
try:
    r(5.0, events, scan_time=3.0)
    checks['scanTime_shorter_than_one_TR_is_refused'] = False
except ValueError:
    checks['scanTime_shorter_than_one_TR_is_refused'] = True

# ---- every shipped task config prescribes its own scan length
expected = {}
for name in sorted(run_task.TASKS):
    conf_file = run_task.TASKS[name][0]
    cfg = mock.load_cfg(os.path.join(PROJECT_ROOT, 'conf', conf_file))
    ev = mrt.read_events_tsv(os.path.join(PROJECT_ROOT, 'study_design', cfg['eventsFile']))
    end = max(o + d for o, d, _ in ev)
    scan = float(cfg.get('scanTime', 0) or 0)
    checks[f'{name}_prescribes_scanTime'] = scan > 0
    checks[f'{name}_scanTime_matches_events_end'] = abs(scan - end) < 0.01
    checks[f'{name}_needs_no_padding_volumes'] = r(1.0, ev, scan_time=scan)[0] <= end + 1e-6
    expected[name] = (scan, r(1.0, ev, scan_time=scan)[0], r(2.0, ev, scan_time=scan)[0])
checks['known_counts_at_TR_1s'] = {k: v[1] for k, v in expected.items()} == {
    'motor': 250, 'motor_guessing': 250, 'checkerboard_1cond': 260, 'checkerboard_2cond': 204,
    'checkerboard_3cond': 300, 'gambling': 298}
checks['known_counts_at_TR_2s'] = {k: v[2] for k, v in expected.items()} == {
    'motor': 125, 'motor_guessing': 125, 'checkerboard_1cond': 130, 'checkerboard_2cond': 102,
    'checkerboard_3cond': 150, 'gambling': 149}

# ---- the mock scanner writes what the config prescribes (no --nvols)
tmp = tempfile.mkdtemp(prefix='nvols_')
cfg_path = os.path.join(PROJECT_ROOT, 'conf', run_task.TASKS['checkerboard_2cond'][0])
rc = mock.main(['--config', cfg_path, '--out', tmp, '--no-delay', '--clean'])
written = sorted(f for f in os.listdir(tmp) if f.endswith('.dcm'))
tr = mrt.dicom_header_info(mock.DEFAULT_REFERENCE)['TR']
checks['mock_scanner_ok'] = rc == 0
checks['mock_writes_exactly_the_prescribed_volumes'] = len(written) == expected['checkerboard_2cond'][0] / tr

print("\n==== expected volume count ====")
print(f"{'task':<20s} {'scanTime':>9s} {'TR 1 s':>7s} {'TR 2 s':>7s}")
for name, (scan, n1, n2) in expected.items():
    print(f"{name:<20s} {scan:>8g}s {n1:>7d} {n2:>7d}")
print(f"mock scanner (checkerboard_2cond, TR {tr:g} s) wrote {len(written)} DICOMs\n")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
ok = all(bool(v) for v in checks.values())
print("\nRESULT:", "ALL PASS" if ok else "SEE FAILURES")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)
