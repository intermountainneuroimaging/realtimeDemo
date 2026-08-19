# Testing

Verify each component works before connecting to a real scanner. Run these
roughly in order — each builds confidence in a different part of the
pipeline, from pure-Python offline checks (no Docker, no download) up to the
full live DICOM streaming path. See [INSTALLATION.md](INSTALLATION.md) first
if you haven't pulled the image / installed the host-side Python deps yet.

## 1. `test_pipeline.py` — offline, no download, no Docker

Validates the whole analysis (mask → baseline → %change → GLM → ROI → plots)
against the **real HcpMotor event timing**, without needing the (large) BOLD
download: it synthesizes a 4D series with the dataset's actual event onsets
and a realistic geometry/affine, injects HRF-convolved activation into
simulated left/right M1, and runs the exact analysis code used live.

```bash
cd taskActivation
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

The only thing it can't exercise locally is the actual S3 BOLD download,
which rt-cloud performs at runtime via `initOpenNeuroStream`/`aws s3 sync` on
your machine — see #4 below for that.

## 2. `test_generalize.py` — offline generalization check (HcpGambling)

Same idea as `test_pipeline.py`, but proves the analysis is genuinely
task-agnostic rather than tuned to HcpMotor: it verifies on HcpGambling that
reward/punishment localize, and that the `neutral` trial type is correctly
regressed out of the reward−punishment contrast as a covariate (not treated
as rest, not treated as a condition of interest).

```bash
python test_generalize.py
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
python test_mock_scanner.py
```

## 4. Direct-testing Docker run — the full pipeline on demo data

This exercises the real container: rt-cloud's `ClientInterface`,
`mcflirt`/`fslmaths`, the OpenNeuro download (or cache), brain masking, and
the live plot-writing code, end to end. See
[README.md](README.md#quick-start-direct-testing-no-web-interface) for the
full command; in short:

```bash
PROJ_DIR=/full/path/to/taskActivation
docker run -it --rm \
  -v $PROJ_DIR:/rt-cloud/projects/taskActivation \
  brainiak/rtcloud:latest python projects/taskActivation/taskActivation.py
```

Answer `y` at the `continue using localfiles?` prompt. Watch the printed log:
you should see `Data source: nifti | volumes: N` (N is however many timepoints
are in that OpenNeuro run — currently 185 for HcpMotor), a `Brain mask: ...`
line with a coverage percentage roughly in the 20–45% range (much lower or
higher usually means `maskMethod`/`maskFrac` needs adjusting for your data),
then one `--- HcpMotor | vol k/N ---` line per volume. If you mounted `outDir` to the
host (`-v $OUT_DIR:/rt-cloud/outDir`), open `$OUT_DIR/live/current.png`
partway through — you should see a real brain (not noise) with a labeled
condition in the title. Run the same command with `--config
projects/taskActivation/conf/taskActivation_gambling.toml` to check the
HcpGambling config the same way.

## 5. Mock scanner DICOM streaming — the live path without a real scanner

This is the one that actually exercises `dataSource = "dicom"`: the DICOM
watcher, `dcm2niix` conversion, and everything downstream, using synthetic
volumes instead of a real scanner.

1. Edit a copy of the toml (or make a scratch one) and set `dataSource =
   "dicom"`.
2. Start the analysis container as in #4, but also mount a `dicomDir`:
   ```bash
   DICOM_DIR=/full/path/to/dicomDir
   docker run -it --rm \
     -v $PROJ_DIR:/rt-cloud/projects/taskActivation \
     -v $DICOM_DIR:/rt-cloud/projects/taskActivation/dicomDir \
     brainiak/rtcloud:latest python projects/taskActivation/taskActivation.py \
     --config projects/taskActivation/conf/<your-dicom-toml>
   ```
3. In a **second terminal on the host** (not in the container), run the mock
   scanner pointed at the same folder:
   ```bash
   python mock_scanner.py --config conf/<your-dicom-toml> --out $DICOM_DIR
   ```

**What to look for:** the analysis log should show `Data source: dicom |
volumes: N`, then process volumes as they arrive from the mock scanner
(there's no download step here). If you instead see
`rtCommon.errors.RequestError: ... Dicom file ... not found or corrupted`,
the mock scanner either isn't running yet or is writing to a different folder
than the container has mounted — start it first, or use `--no-delay` to write
the whole run up front before starting the analysis.

## 6. Sanity-checking `dicom_bridge.py` before a real scan

`dicom_bridge.py` only renames files and patches one metadata field — it
never touches pixel data — so the fastest way to confirm it works against
your site's actual export format is a `--once` backfill against a small
folder of real DICOMs (even ones left over from a prior non-realtime
session), then inspecting the result:

```bash
python dicom_bridge.py --config conf/taskActivation.toml \
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
for #5's docker run, but with your real scanner in place of `mock_scanner.py`.

## Interpreting failures

The offline tests (`test_pipeline.py`, `test_generalize.py`,
`test_mock_scanner.py`) each print one `[PASS]`/`[FAIL]` line per check and a
final `RESULT: ALL PASS` / `RESULT: SEE FAILURES`, then exit 0/1 accordingly —
safe to wire into CI or a pre-flight script. The Docker-based checks (#4, #5)
don't have a formal pass/fail signal; "it processed every volume without a
traceback, and `current.png` shows a real brain with sensible activation" is
the bar — see [README.md](README.md#data-outputs-to-expect) for what that
should actually look like.
