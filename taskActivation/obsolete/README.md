# Obsolete tasks (archived, not deployed)

This folder holds the original HCP-dataset task scripts that used to live in
`stimuli/` and `stimuli_ptb/`, kept for reference rather than deleted. They
are **not wired to any `conf/*.toml`**, **not listed in `run_task.py`'s
`TASKS`**, and **not covered by `quickstart.sh`** — the project's deployed
task set is now just: `motor` (`stimuli_ptb/motor_task.m` /
`stimuli/generic_motor_task.py`), the three checkerboard localizers
(`checkerboard_1cond`/`checkerboard_2cond`/`checkerboard_3cond`), and
`gambling` (blackjack; `stimuli_ptb/blackjack_task.m` /
`stimuli/blackjack_task.py`).

## What's here

- `stimuli/hcp_motor_task.py` — the original 5-condition HCP motor task
  (left/right hand, left/right foot, tongue, each with a get-ready cue),
  reading the real ds000244 `HcpMotor_acq-ap_events.tsv` timing. Superseded
  by the project's own simpler `generic_motor_task.py` (left/right hand
  squeezing only, no cues). No Psychtoolbox equivalent ever existed for this
  one — `stimuli_ptb/motor_task.m` was always the *generic* design.
- `stimuli/hcp_gambling_task.py` / `stimuli_ptb/gambling_task.m` — the
  original HCP card-guess task (reward/punishment/neutral; the guess never
  changes the outcome). Superseded by the project's own two-card blackjack
  design (`blackjack_task.py` / `blackjack_task.m`), which reuses the same
  "outcome is pre-scripted by the events.tsv" principle but with a real
  hit/stay decision and blackjack scoring.
- `study_design/HcpGambling_acq-ap_events.tsv` — the events file the two
  gambling scripts above read. (`HcpMotor_acq-ap_events.tsv` is NOT here —
  it stays at the top-level `study_design/`, since `conf/taskActivation.toml`
  — kept as the project's default config — `testing/test_mock_scanner.py`,
  and `tutorial/test_pipeline.py` all still read it from there.)

`tutorial/`'s own offline HCP-data validation (`test_pipeline.py`,
`test_generalize.py`, `replay_real_data.py`) is **unaffected** by this move:
it validates the underlying real-time analysis logic against real ds000244
data, which is a separate concern from which tasks are deployed for live
presentation, and it keeps its own separate copy of
`HcpGambling_acq-ap_events.tsv` under `tutorial/study_design/`.

## If you want to run one of these again

These scripts were moved, not rewritten, so their internal relative paths
still assume their *original* location one level up:

- The `.py` scripts do `import common` assuming they sit next to
  `stimuli/common.py`, and use `common.PROJECT_ROOT` for the events-file
  path. Moving `hcp_motor_task.py` / `hcp_gambling_task.py` back to
  `stimuli/` (their original location) makes them work again unchanged.
- `gambling_task.m` uses `fullfile(here, '..', 'study_design', ...)` for its
  events file and calls the shared `ptb_*.m` helpers by name (resolved via
  MATLAB's path) — moving it back to `stimuli_ptb/` makes both resolve
  correctly again.
- If you restore `hcp_gambling_task.py` / `gambling_task.m`, also move
  `study_design/HcpGambling_acq-ap_events.tsv` (from this folder) back to
  the top-level `study_design/`.

None of this touches `conf/*.toml`, `run_task.py`, or `quickstart.sh` — if
you want one of these deployed again, add it back to `run_task.py`'s
`TASKS` dict (and a `conf/*.toml` for it) the same way any other task is
wired in.
