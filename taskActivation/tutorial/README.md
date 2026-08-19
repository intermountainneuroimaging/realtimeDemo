# Tutorial: offline validation against real HCP task data

This folder validates the analysis in
[`../utils/rt_analysis.py`](../utils/rt_analysis.py) — the same code
`../taskActivation.py` runs live against a scanner — without needing a
scanner, Docker, or rt-cloud at all. It's useful for two things:

1. **Proving the pipeline is correct** against known ground truth: real event
   timing from OpenNeuro ds000244, with synthetic (but HRF-realistic)
   activation injected into anatomically correct regions, so each check has a
   known right answer (e.g. "LEFT hand block → activation localizes to the
   RIGHT motor cortex").
2. **Showing what the live output actually looks like** before you have
   scanner access — the sample images below were produced by literally
   replaying real downloaded ds000244 BOLD data through this analysis.

`../taskActivation.py` itself only streams DICOMs from a real (or mock)
scanner — see the main [README.md](../README.md) and
[TESTING.md](../TESTING.md) for that. Nothing here is needed to run the live
pipeline; this folder is purely for offline validation/demonstration.

## Running the tests

```bash
cd taskActivation/tutorial
python test_pipeline.py       # HcpMotor: synthetic data, real event timing, no download
python test_generalize.py     # HcpGambling: proves the design generalizes to a 3-condition task
```

Both are self-contained (numpy/nibabel/scipy — no download, no Docker) and
print PASS/FAIL per check, exiting 0 only if everything passed. See
[TESTING.md](../TESTING.md#1-tutorialtest_pipelinepy--offline-no-download-no-docker)
for what each check verifies.

## Files here

- `test_pipeline.py` — offline end-to-end test on the real HcpMotor event
  timing (synthetic imaging data, no download needed).
- `test_generalize.py` — generalization test on HcpGambling (reward vs
  punishment vs the `neutral` covariate).
- `hcp_replay.py` — OpenNeuro-download + local-NIfTI-replay helpers
  (`ensure_openneuro_bold`, `NiftiReplaySource`). Only used by this folder —
  the live pipeline streams DICOMs and has no use for them.
- `download_data.sh` — prefetch a real BOLD run from OpenNeuro's public S3
  mirror into `openneuro_cache/` (only needed if you want to replay *real*
  downloaded data yourself rather than the synthetic data the tests use).
- `conf/taskActivation_gambling.toml` — reference config documenting the
  GLM/task settings (`glmCondA`/`glmCondB`, `eventsFile`) used to produce the
  HcpGambling sample image below via a NIfTI replay. Kept for reference only
  — `taskActivation.py` no longer has a NIfTI-replay data source, so this
  file isn't consumed by any script.
- `study_design/HcpGambling_acq-ap_events.tsv` — real ds000244 HcpGambling
  events (HcpMotor's events.tsv is used by both the live pipeline and
  `test_pipeline.py`, so it stays in `../study_design/`).

## Sample output

Both were produced by replaying real ds000244 BOLD data (via `hcp_replay.py`)
through this same analysis pipeline — this is what `outDir/live/current.png`
looks like from a real run.

**HcpMotor** (LEFT vs RIGHT hand): LEFT hand drives the right motor cortex;
RIGHT hand drives the left motor cortex — the two peak-voxel rows at the
bottom show that lateralized, HRF-shaped response recovered live, volume by
volume:

![HcpMotor sample current.png](docs/images/hcpmotor_sample.png)

**HcpGambling** (reward vs punishment, `neutral` regressed out as a
covariate):

![HcpGambling sample current.png](docs/images/hcpgambling_sample.png)
