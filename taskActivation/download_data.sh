#!/usr/bin/env bash
# Download one HcpMotor bold (+ events/json) from OpenNeuro's public S3 mirror.
# Same mechanism rt-cloud uses internally (aws s3 sync --no-sign-request).
# Requires awscli (present in the brainiak/rtcloud image) and network access.
set -e
DS=${1:-ds000244}
SUB=${2:-01}
SES=${3:-03}
TASK=${4:-HcpMotor}
ACQ=${5:-ap}
DEST="$(dirname "$0")/openneuro_cache/${DS}/sub-${SUB}/ses-${SES}/func"
mkdir -p "$DEST"
echo "Downloading sub-${SUB} ses-${SES} task-${TASK} acq-${ACQ} -> ${DEST}"
aws s3 sync --no-sign-request \
  "s3://openneuro.org/${DS}/sub-${SUB}/ses-${SES}/func/" \
  "$DEST" --exclude "*" --include "*task-${TASK}*acq-${ACQ}*"
echo "Done:"; ls -lh "$DEST"
