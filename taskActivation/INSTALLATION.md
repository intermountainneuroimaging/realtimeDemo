# Installation

One-time setup: get the rt-cloud Docker image, install the host-side Python
dependencies for the helper scripts, optionally prefetch tutorial data, and
(if you're connecting to a real scanner) install `dicom_bridge.py` as a
background service. See [README.md](README.md) for how to actually run the
project once this is done, and [TESTING.md](TESTING.md) to verify each piece
works before connecting to a real scanner.

## 1. Docker

Install Docker Desktop (Mac/Windows) or Docker Engine (Linux), then pull the
image:

```bash
docker pull brainiak/rtcloud:latest
```

This is about 9–10 GB. A few things worth knowing up front:

- **Apple Silicon / ARM hosts:** the image is `linux/amd64` only, so Docker
  runs it under emulation. You'll see `WARNING: The requested image's
  platform (linux/amd64) does not match the detected host platform
  (linux/arm64/v8)` on every run — that's expected and harmless, just slower
  (FSL's `mcflirt`/`fslmaths` calls in particular).
- **Disk space:** budget the ~10 GB image; if you also plan to run
  [tutorial/](tutorial/) against real downloaded data (optional — the tests
  there use synthetic data by default), add ~1 GB per OpenNeuro dataset
  cached under `tutorial/openneuro_cache/` (see below).
- **First `docker run`:** you'll also see `bash: cannot set terminal process
  group ... / bash: no job control in this shell` — the image's entrypoint
  wraps everything in a login shell; also harmless.

## 2. Host-side Python dependencies

`mock_scanner.py` and `dicom_bridge.py` are deliberately **not** run inside
the container — they have no `rtCommon` dependency, so they run on whatever
host machine sits between the scanner and the container (which may not be the
same machine the analysis container runs on). Install their dependencies
there:

```bash
pip install numpy pydicom nibabel scipy
```

`numpy`/`pydicom` are required by both scripts; `nibabel`/`scipy` are only
needed for `mock_scanner.py --source <bold.nii.gz>` replay mode.

## 3. Prefetch tutorial data (optional)

The live pipeline (`taskActivation.py`) always streams DICOMs and needs none
of this — it's only relevant if you want [tutorial/](tutorial/) to replay
*real* downloaded OpenNeuro data (`hcp_replay.py`'s `ensure_openneuro_bold`)
rather than the synthetic data `test_pipeline.py`/`test_generalize.py` use by
default. `tutorial/download_data.sh` fetches a BOLD run from OpenNeuro's
public S3 mirror into `tutorial/openneuro_cache/` (each is ~600 MB):

```bash
cd tutorial
./download_data.sh ds000244 01 03 HcpMotor ap
./download_data.sh ds000244 01 03 HcpGambling ap
```

This needs `awscli` and network access — either install `awscli` on the host,
or run it inside a throwaway container that already has it:

```bash
docker run -it --rm \
  -v /full/path/to/taskActivation:/rt-cloud/projects/taskActivation \
  brainiak/rtcloud:latest projects/taskActivation/tutorial/download_data.sh ds000244 01 03 HcpMotor ap
```

## 4. Setting up `dicom_bridge.py` as a background service (systemd / launchd)

Only needed when connecting to a **real** scanner (skip this for the demo
datasets or `mock_scanner.py` testing). See [README.md](README.md#running-with-live-scanner-data)
for why `dicom_bridge.py` is needed at all — in short, rt-cloud's DICOM
watcher requires an exact, predictable filename per volume, and real scanner
exports rarely produce one directly.

For routine scanning you don't want a terminal open babysitting the bridge.
It's a lightweight, single-threaded polling loop (a directory listing once a
second, plus a cheap header-only read per new file), so the OS can just run
it in the background indefinitely — run it with no `--series`/`--run` (the
default: bridge everything, `RUN` = each file's own real `SeriesNumber`) so it
never needs restarting or reconfiguring between scan sessions.

**Linux uses `systemd`; macOS has no `systemd` at all** — its equivalent is
`launchd`, configured via a plist instead of a unit file and managed with
`launchctl` instead of `systemctl`. Pick the section for your OS below.

### Linux (systemd)

Create `/etc/systemd/system/dicom-bridge.service` (adjust the paths, and the
`python3` path if `pydicom`/`numpy` live in a venv or conda env rather than
the system interpreter):

```ini
[Unit]
Description=RT-Cloud dicom_bridge.py (rename real scanner DICOMs for rt-cloud)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/full/path/to/taskActivation
ExecStart=/usr/bin/python3 /full/path/to/taskActivation/utils/dicom_bridge.py \
  --config /full/path/to/taskActivation/conf/taskActivation.toml \
  --source /path/to/real/scanner/drop/folder \
  --dest /path/to/dicomDir
Restart=on-failure
RestartSec=5

# "silently": no visible terminal either way -- systemd always runs this
# detached. By default stdout/stderr go to the journal (recommended, so you
# can still debug with journalctl); uncomment below to drop output entirely.
# StandardOutput=null
# StandardError=null

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dicom-bridge.service
```

Useful commands:

```bash
sudo systemctl status dicom-bridge.service     # running? recent restarts?
journalctl -u dicom-bridge.service -f          # live log (unless StandardOutput=null above)
sudo systemctl restart dicom-bridge.service    # e.g. after editing --source/--dest
sudo systemctl stop dicom-bridge.service
```

`Type=simple` + `Restart=on-failure` is enough here — `dicom_bridge.py` has no
startup handshake to wait on, and a plain restart is the right response to a
transient error (e.g. the source share briefly unavailable). `User=` should be
whichever account can read the scanner's drop folder and write into the
`dicomDir` the analysis container has bind-mounted.

### macOS (launchd)

A **LaunchAgent** (runs in your own login session, in `~/Library/LaunchAgents/`)
is normally the right choice here rather than a LaunchDaemon (runs at boot,
before anyone logs in) — the scanner's drop folder is usually a network
share (SMB/AFP) that only gets mounted once you log in, which a LaunchDaemon
can't see. If your site mounts it at the system level instead (e.g. via
`/etc/fstab`) and you want the bridge running even with nobody logged in, use
a LaunchDaemon in `/Library/LaunchDaemons/` instead — same plist, just
installed as root and loaded in the `system/` domain rather than `gui/<uid>`.

A ready-to-edit template ships at
[`utils/com.rtcloud.dicombridge.plist`](utils/com.rtcloud.dicombridge.plist)
— copy it into place and fill in your real paths:

```bash
cp utils/com.rtcloud.dicombridge.plist ~/Library/LaunchAgents/com.rtcloud.dicombridge.plist
open ~/Library/LaunchAgents/com.rtcloud.dicombridge.plist   # or any text editor
```

`ProgramArguments` mirrors the `dicom_bridge.py` command line exactly, one
argument per array entry — replace every `/full/path/to/taskActivation`,
`/path/to/real/scanner/drop/folder`, `/path/to/dicomDir`, and
`/Users/youruser` placeholder with your real paths (launchd won't expand `~`
or `$HOME` inside a plist, so these all need to be absolute). For reference,
here's what it contains:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rtcloud.dicombridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/full/path/to/taskActivation/utils/dicom_bridge.py</string>
        <string>--config</string>
        <string>/full/path/to/taskActivation/conf/taskActivation.toml</string>
        <string>--source</string>
        <string>/path/to/real/scanner/drop/folder</string>
        <string>--dest</string>
        <string>/path/to/dicomDir</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/full/path/to/taskActivation</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/youruser/Library/Logs/dicom-bridge.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/youruser/Library/Logs/dicom-bridge.log</string>
</dict>
</plist>
```

`RunAtLoad` starts it as soon as the plist is loaded (equivalent to
systemd's `enable --now`); `KeepAlive`/`SuccessfulExit=false` restarts it if
it ever exits with an error, but not if it exits cleanly (`dicom_bridge.py`
without `--once` only exits on a crash or being killed, so in practice this
behaves like `Restart=on-failure`). Use the real path to your `python3` (a
venv/conda interpreter if that's where `pydicom`/`numpy` live) — `which
python3` prints it.

Check it's still well-formed XML after editing, then load and start it:

```bash
plutil -lint ~/Library/LaunchAgents/com.rtcloud.dicombridge.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rtcloud.dicombridge.plist
launchctl enable gui/$(id -u)/com.rtcloud.dicombridge
```

Useful commands:

```bash
launchctl print gui/$(id -u)/com.rtcloud.dicombridge          # running? last exit code?
tail -f ~/Library/Logs/dicom-bridge.log                        # live log
launchctl kickstart -k gui/$(id -u)/com.rtcloud.dicombridge    # restart the running job
launchctl bootout gui/$(id -u)/com.rtcloud.dicombridge         # stop + unload
```

**If you edit the plist file itself** (e.g. changing `--source`/`--dest`),
`kickstart` alone won't pick it up — it only restarts the already-loaded job
with its existing config. Reload the plist from disk instead:

```bash
launchctl bootout gui/$(id -u)/com.rtcloud.dicombridge
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rtcloud.dicombridge.plist
launchctl enable gui/$(id -u)/com.rtcloud.dicombridge
```
