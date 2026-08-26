# Testing

Verify each component works before connecting to a real scanner. Run these
roughly in order — each builds confidence in a different part of the
pipeline, from pure-Python offline checks (no Docker, no download) up to the
full live DICOM streaming path. See [INSTALLATION.md](INSTALLATION.md) first
if you haven't pulled the image / installed the host-side Python deps yet.

## 1. `tutorial/test_pipeline.py` — offline, no download, no Docker

Validates the whole analysis (mask → baseline → %change → GLM → ROI → plots)
against the **real HcpMotor event timing**, without needing the (large) BOLD
download: it synthesizes a 4D series with the dataset's actual event onsets
and a realistic geometry/affine, injects HRF-convolved activation into
simulated left/right M1, and runs the exact analysis code used live.

```bash
cd taskActivation/tutorial
python test_pipeline.py
```

**What to look for:** it prints PASS/FAIL for each check and exits 0 only if
everything passed:
- brain mask coverage is sane
- each hand localizes to the correct **contralateral** hemisphere/cluster
  (left hand → right motor cortex, right hand → left motor cortex)
- ROI timecourses lateralize (LEFT-ROI up in LEFT blocks, RIGHT-ROI up in
  RIGHT blocks)
- the nilearn realtime plot and live bundles are produced

The only thing it can't exercise locally is real imaging data — it uses
synthetic volumes throughout. See `tutorial/README.md` if you want to replay
real downloaded OpenNeuro data instead.

## 2. `tutorial/test_generalize.py` — offline generalization check (HcpGambling)

Same idea as `test_pipeline.py`, but proves the analysis is genuinely
task-agnostic rather than tuned to HcpMotor: it verifies on HcpGambling that
reward/punishment localize, and that the `neutral` trial type is correctly
regressed out of the reward−punishment contrast as a covariate (not treated
as rest, not treated as a condition of interest).

```bash
python test_generalize.py   # from taskActivation/tutorial
```

## 3. `test_mock_scanner.py` — offline, mock DICOM scanner

Writes 120 synthetic Enhanced-multi-frame DICOMs with `mock_scanner.py` (no
Docker, no dcm2niix, no real scanner) and confirms:
- filenames match `dicomNamePattern`
- files exceed `minExpectedDicomSize`
- each DICOM parses to the reference DICOM's exact shape (what pydicom /
  dcm2niix would actually read)
- frame packing round-trips exactly
- the injected condA/condB activation is recoverable from the written series

```bash
python testing/test_mock_scanner.py
```

## 4. Mock scanner DICOM streaming — the full pipeline, Docker + live path, no real scanner

This is the one that exercises the real container end to end: rt-cloud's
`ClientInterface`, the DICOM watcher, `dcm2niix` conversion, `mcflirt`/
`fslmaths`, brain masking, and the live plot-writing code — using synthetic
volumes from `mock_scanner.py` instead of a real scanner. See
[README.md](README.md#quick-start-direct-testing-no-web-interface) for the
full command; in short:

1. Start the analysis container, mounting a `dicomDir`:
   ```bash
   PROJ_DIR=/full/path/to/taskActivation
   DICOM_DIR=/full/path/to/dicomDir
   OUT_DIR=/full/path/to/outDir
   docker run -it --rm \
     -v $PROJ_DIR:/rt-cloud/projects/taskActivation \
     -v $DICOM_DIR:/rt-cloud/projects/taskActivation/dicomDir \
     -v $OUT_DIR:/rt-cloud/outDir \
     brainiak/rtcloud:latest python projects/taskActivation/taskActivation.py
   ```
   Answer `y` at the `continue using localfiles?` prompt.
2. In a **second terminal on the host** (not in the container), run the mock
   scanner pointed at the same folder:
   ```bash
   python utils/mock_scanner.py --config conf/taskActivation.toml --out $DICOM_DIR
   ```

**What to look for:** the analysis log should show `Data source: dicom |
volumes: N`, a `Brain mask: ...` line with a coverage percentage roughly in
the 20–45% range (much lower or higher usually means `maskMethod`/`maskFrac`
needs adjusting), then process volumes as they arrive from the mock scanner.
Partway through, open `$OUT_DIR/live/viewer.html` in a browser (auto-refreshes
every 0.5s) or `$OUT_DIR/live/current.png` directly — you should see a real
brain (not noise) with a labeled condition and frame number in the title.
(Skip `-v $OUT_DIR:...` and you'll never see these — they're written inside the
`--rm` container and vanish when it exits.) Each volume waits up to
`dicomTimeout` seconds (default 30) before giving up, so a normal startup gap
won't crash the run — but if you see `RuntimeError: No DICOM for volume N
arrived within dicomTimeout=...s`, the mock scanner either isn't running yet
or is writing to a different folder than the container has mounted — start
it first, or use `--no-delay` to write the whole run up front before
starting the analysis.

**Start each fresh test with an empty `dicomDir`.** If you see `RuntimeError:
Volume N's DICOM has different geometry than earlier volumes in this run`,
`dicomDir` has DICOMs from two different acquisitions mixed together —
almost always leftovers from an earlier test (a different `mock_scanner.py
--reference-dicom`, or a real scan with a different protocol) that matched
the same `dicomNamePattern`/`runNum` and never got cleared. Pass
`mock_scanner.py --clean` (removes existing `*.dcm` in the output dir first)
or clear `$DICOM_DIR` yourself before switching configs.

If you use `--no-delay` (or otherwise pre-write the whole `dicomDir`), every
DICOM already exists before `taskActivation.py` starts, so by default it
processes and plots them essentially instantly rather than at a live pace.
Set `demoStep` in the toml (commented out by default) to an artificial
per-volume delay in seconds for a more realistic-feeling test run — it only
paces delivery, it never affects TR or timing math.

## 5. Sanity-checking `dicom_bridge.py` before a real scan

`dicom_bridge.py` only renames files and patches one metadata field — it
never touches pixel data — so the fastest way to confirm it works against
your site's actual export format is a `--once` backfill against a small
folder of real DICOMs (even ones left over from a prior non-realtime
session), then inspecting the result:

```bash
python utils/dicom_bridge.py --config conf/taskActivation.toml \
  --source /path/to/a/folder/of/real/dicoms --dest /tmp/bridge_test --once
```

Check that:
- the file count in `/tmp/bridge_test` matches what you expect (files from
  series you didn't ask about are silently skipped if you passed `--series`;
  omit it and every series gets bridged, each with its own `RUN` label)
- filenames look like `demo_<SeriesNumber>_<InstanceNumber>.dcm` (zero-padded)
- `python -c "import pydicom; print(pydicom.dcmread('/tmp/bridge_test/<a file>').RepetitionTime)"`
  prints a real number — this is the metadata patch that prevents
  `MissingMetadataError` downstream (see
  [README.md](README.md#running-with-live-scanner-data))

Once that looks right, point `--dest` at the real `dicomDir` and you're ready
for #4's docker run, but with your real scanner in place of `mock_scanner.py`.

## Interpreting failures

The offline tests (`tutorial/test_pipeline.py`, `tutorial/test_generalize.py`,
`testing/test_mock_scanner.py`) each print one `[PASS]`/`[FAIL]` line per check and a
final `RESULT: ALL PASS` / `RESULT: SEE FAILURES`, then exit 0/1 accordingly —
safe to wire into CI or a pre-flight script. The Docker-based check (#4)
doesn't have a formal pass/fail signal; "it processed every volume without a
traceback, and `current.png` shows a real brain with sensible activation" is
the bar — see [README.md](README.md#data-outputs-to-expect) for what that
should actually look like.
