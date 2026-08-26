# Pre-flight checks: before starting a real-time scanning session

Run through this **before every live scan**, not just the first time. Most of
these failure modes don't fail loudly and immediately — they either fail
silently (a share that quietly stopped being served, a bridge service that
crashed hours ago) or surface mid-scan as a cryptic rt-cloud/DICOM error,
which is a much more expensive place to debug them than right now. See
[INSTALLATION.md](INSTALLATION.md) for one-time setup and
[TESTING.md](TESTING.md) for exercising each piece in isolation — this file
is the short list to run through once that setup is already done, right
before a real subject is in the scanner.

## 1. The shared `dicomDir` is actually being served

If the machine writing/watching DICOMs isn't the same one running the
analysis container — e.g. the scanner (or `dicom_bridge.py`'s host) reaches
`dicomDir` over the network rather than locally — confirm the share is still
up. **macOS** (on whichever Mac is serving the share):

```bash
sharing -l
```

You should see `dicomDir` listed among the shared folders. If it's missing,
the share was never turned on (or macOS silently dropped it after a
restart/network change) — turn it back on in **System Settings → General →
Sharing → File Sharing** before anything downstream will work, since the
consuming machine simply won't see the folder at all.

(Linux equivalent: `sudo smbstatus --shares` for Samba, or `exportfs -v` for
NFS — check whichever your site actually uses.)

## 2. `dicom_bridge.py` is running

Only relevant if you're bridging real scanner filenames (see
[README.md](README.md#running-with-live-scanner-data)) — skip this if
`mock_scanner.py` is standing in for the scanner instead.

**macOS (launchd):**
```bash
launchctl print gui/$(id -u)/com.rtcloud.dicombridge | grep -E "state|last exit"
```

**Linux (systemd):**
```bash
sudo systemctl status dicom-bridge.service
```

Either should show it currently running, not stopped/crashed. If it's not,
see [INSTALLATION.md](INSTALLATION.md#4-setting-up-dicom_bridgepy-as-a-background-service-systemd--launchd)
to restart it, and check its log
(`~/Library/Logs/dicom-bridge.log` on macOS, `journalctl -u dicom-bridge.service -f`
on Linux) for why it stopped — a common cause is the **source** share (the
scanner's own raw drop folder, not `dicomDir`) becoming unreachable.

## 3. `dicomDir` is empty (or only has files you expect)

```bash
ls $DICOM_DIR
```

Leftover DICOMs from an earlier test or a previous subject's session will
crash the run the moment a volume with different geometry gets appended —
see the `RuntimeError: Volume N's DICOM has different geometry` note in
[TESTING.md](TESTING.md#4-mock-scanner-dicom-streaming--the-full-pipeline-docker--live-path-no-real-scanner).
Clear it (or use `mock_scanner.py --clean` for a test run) before starting a
fresh session, real or mock.

If you're bridging real scanner data, `dicom_bridge.py` now auto-cleans
`dicomDir` on its own (files older than `--max-age-hours`, default 24 — see
[README.md](README.md#running-with-live-scanner-data)), so this mostly
matters for same-day back-to-back sessions where nothing's old enough to
have aged out yet — worth a quick look either way.

## 4. Docker is up and the image is there

```bash
docker info >/dev/null && echo "docker OK"
docker images brainiak/rtcloud --format "{{.Repository}}:{{.Tag}}"
```

The first confirms Docker Desktop is actually running (not just installed);
the second confirms the image is pulled so `quickstart.sh`/the direct-run
command doesn't stall on a multi-GB download with a subject already in the
scanner.

## 5. The config matches this session

Open `conf/taskActivation.toml` (or whichever `--config` you're passing) and
confirm, for real:
- `taskName` / `eventsFile` / `glmCondA` / `glmCondB` are the task actually
  being run, not left over from the last test.
- `dicomNamePattern` / `runNum` match what `dicom_bridge.py` (or the scanner
  directly) will actually produce for this session.

## 6. You can see the live viewer

```bash
open $OUT_DIR/live/viewer.html
```

It'll show broken images until the run actually starts writing `current.png`
/ `motion.png` — that's expected — but confirm the *file* opens in a browser
now, rather than discovering a bad `$OUT_DIR` path once the scan is already
running.

## One dry run beats six checks

If there's time, the single best pre-flight check is running the whole
pipeline once end-to-end with `mock_scanner.py` in place of the real scanner
(see [TESTING.md](TESTING.md#4-mock-scanner-dicom-streaming--the-full-pipeline-docker--live-path-no-real-scanner))
before the actual session — it exercises the DICOM watcher, the brain mask,
the GLM, and the live plots together, which is a stronger signal than any
individual check above.
