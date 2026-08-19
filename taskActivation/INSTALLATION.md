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

## 4. Setting up `dicom_bridge.py` as a background service (systemd)

Only needed when connecting to a **real** scanner (skip this for the demo
datasets or `mock_scanner.py` testing). See [README.md](README.md#running-with-live-scanner-data)
for why `dicom_bridge.py` is needed at all — in short, rt-cloud's DICOM
watcher requires an exact, predictable filename per volume, and real scanner
exports rarely produce one directly.

For routine scanning you don't want a terminal open babysitting the bridge.
It's a lightweight, single-threaded polling loop (a directory listing once a
second, plus a cheap header-only read per new file), so `systemd` can just run
it in the background indefinitely — run it with no `--series`/`--run` (the
default: bridge everything, `RUN` = each file's own real `SeriesNumber`) so it
never needs restarting or reconfiguring between scan sessions.

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
ExecStart=/usr/bin/python3 /full/path/to/taskActivation/dicom_bridge.py \
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
