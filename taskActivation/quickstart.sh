#!/usr/bin/env bash
# quickstart.sh -- one-command direct-testing run of taskActivation.py.
#
# Does exactly what README.md's "Quick start: direct testing" section walks
# through by hand: exports the env vars the docker command needs, runs the
# container, and opens the live viewer (outDir/live/viewer.html) in your
# browser automatically as soon as it exists -- no separate copy/paste steps.
#
# Usage:
#   ./quickstart.sh
#
# All paths below have sane defaults (this project folder's own dicomDir/ and
# a sibling outDir/), but you can override any of them by exporting first:
#   DICOM_DIR=/path/to/real/dicomDir OUT_DIR=/path/to/outDir ./quickstart.sh
#
# You'll still see rt-cloud's own interactive prompt in this terminal:
#   Unable to connect to projectServer, continue using localfiles? (y/n):
# answer y -- that's expected for this direct-testing pattern (no web
# interface). See README.md if you'd rather use the full web dashboard.
set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- 1. required variables (edit these defaults, or export overrides first) ----
export PROJ_NAME="${PROJ_NAME:-$(basename "$HERE")}"
export PROJ_DIR="${PROJ_DIR:-$HERE}"
export DICOM_DIR="${DICOM_DIR:-$PROJ_DIR/dicomDir}"
export OUT_DIR="${OUT_DIR:-$PROJ_DIR/outDir}"

mkdir -p "$DICOM_DIR" "$OUT_DIR"

echo "PROJ_NAME=$PROJ_NAME"
echo "PROJ_DIR=$PROJ_DIR"
echo "DICOM_DIR=$DICOM_DIR"
echo "OUT_DIR=$OUT_DIR"
echo

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found on PATH -- install/start Docker Desktop first." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# OPTIONAL: dicom_bridge.py / systemd service check -- only relevant when
# streaming from a REAL scanner (skip entirely for mock_scanner.py testing).
# Set DICOM_BRIDGE_SOURCE to the scanner's real drop folder to auto-start
# dicom_bridge.py in the background pointed at $DICOM_DIR; otherwise this
# just reports whether the systemd service (see INSTALLATION.md) is running,
# and does nothing if neither applies.
# ---------------------------------------------------------------------------
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^dicom-bridge\.service'; then
    echo "[dicom_bridge] dicom-bridge.service is installed -- status:"
    systemctl status dicom-bridge.service --no-pager || true
    echo
elif [ -n "$DICOM_BRIDGE_SOURCE" ]; then
    echo "[dicom_bridge] starting: --source $DICOM_BRIDGE_SOURCE --dest $DICOM_DIR"
    python3 "$PROJ_DIR/utils/dicom_bridge.py" \
        --config "$PROJ_DIR/conf/taskActivation.toml" \
        --source "$DICOM_BRIDGE_SOURCE" --dest "$DICOM_DIR" &
    DICOM_BRIDGE_PID=$!
    trap '[ -n "$DICOM_BRIDGE_PID" ] && kill "$DICOM_BRIDGE_PID" 2>/dev/null' EXIT
    echo
else
    echo "[dicom_bridge] no systemd service found and DICOM_BRIDGE_SOURCE not set --"
    echo "               skipping (fine for mock_scanner.py testing). For a real"
    echo "               scanner: either install the systemd service (see"
    echo "               INSTALLATION.md#4-setting-up-dicom_bridgepy-as-a-background-service-systemd),"
    echo "               or set DICOM_BRIDGE_SOURCE=/path/to/scanner/drop/folder"
    echo "               and re-run this script to have it started for you."
    echo
fi

# ---- 2. open the live viewer automatically once it exists ----
(
    for _ in $(seq 1 120); do
        if [ -f "$OUT_DIR/live/viewer.html" ]; then
            echo "[viewer] opening $OUT_DIR/live/viewer.html"
            open "$OUT_DIR/live/viewer.html" 2>/dev/null \
                || xdg-open "$OUT_DIR/live/viewer.html" 2>/dev/null \
                || echo "[viewer] couldn't auto-open a browser -- open $OUT_DIR/live/viewer.html manually"
            break
        fi
        sleep 1
    done
) &

# ---- 3. run the analysis container (interactive -- answer 'y' at the prompt above) ----
docker run -it --rm \
    -v "$PROJ_DIR":/rt-cloud/projects/"$PROJ_NAME" \
    -v "$DICOM_DIR":/rt-cloud/projects/"$PROJ_NAME"/dicomDir \
    -v "$OUT_DIR":/rt-cloud/outDir \
    brainiak/rtcloud:latest python projects/"$PROJ_NAME"/"$PROJ_NAME".py
