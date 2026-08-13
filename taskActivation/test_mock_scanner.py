"""-----------------------------------------------------------------------------
test_mock_scanner.py — offline test of the mock DICOM scanner.

Writes Enhanced-multi-frame DICOMs with mock_scanner, then unpacks them and
confirms:
  * files are named per dicomNamePattern and exceed minExpectedDicomSize,
  * each DICOM's pixel_array matches the reference DICOM's geometry
    (pydicom parses Enhanced multi-frame natively -- this is the same shape
    dcm2niix would read),
  * frame packing round-trips exactly,
  * the streamed series carries recoverable task activation (condA / condB
    peaks land in their injected regions).
No FSL / dcm2niix / scanner needed.
-----------------------------------------------------------------------------"""
import os
import sys
import glob
import tempfile
import warnings
import numpy as np

import rt_analysis as mrt
import mock_scanner as mock
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG = os.path.join(HERE, 'conf', 'taskActivation.toml')
tmp = tempfile.mkdtemp(prefix='mockdcm_')

# run the mock scanner (fast, no delay) using the default synthetic HcpMotor source
rc = mock.main(['--config', CONFIG, '--out', tmp, '--no-delay', '--clean', '--nvols', '120'])

cfg = mock.load_cfg(CONFIG)
min_size = int(cfg.get('minExpectedDicomSize', 300000))
ref_info = mrt.dicom_header_info(mock.DEFAULT_REFERENCE)

events = mrt.read_events_tsv(os.path.join(HERE, 'study_design', 'HcpMotor_acq-ap_events.tsv'))
files = sorted(glob.glob(os.path.join(tmp, '001_000001_*.dcm')))

import pydicom
# pydicom parses Enhanced multi-frame natively -> (nFrames, rows, cols) directly,
# no custom de-mosaic needed. unpack_frames just reorders to (rows, cols, slices).
vols = [mrt.unpack_frames(pydicom.dcmread(f).pixel_array) for f in files]
Y4 = np.stack(vols, -1).astype(np.float32)
shape = Y4.shape[:3]; nV = Y4.shape[3]; R = shape[0]
TR = mrt.dicom_header_info(files[0])['TR']   # read back what the scanner actually used

# injected regions (must mirror synthetic_series)
A_rows = range(R//2+6, R//2+11); B_rows = range(R//2-11, R//2-6)

X, names = mrt.make_glm_design(events, nV, TR, 1)
bmask = mrt.compute_brain_mask(Y4[..., 0]).flatten(); midx = np.where(bmask)[0]
flatY = Y4.reshape(-1, nV).T[:, midx]
con = mrt.glm_beta_contrast(X, flatY, names, 'left_hand', 'right_hand', zscore=True)
cmap = np.zeros(bmask.size, np.float32); cmap[midx] = con; cmap = cmap.reshape(shape)
pA = np.unravel_index(int(np.nanargmax(cmap)), shape)   # most condA>condB
pB = np.unravel_index(int(np.nanargmin(cmap)), shape)   # most condB>condA

# pydicom (dcm2niix proxy) parseability + shape, checked against the reference
# DICOM's own geometry rather than a hardcoded constant
expected_shape = (ref_info['nFrames'], ref_info['rows'], ref_info['cols'])
pydicom_shapes = {pydicom.dcmread(f).pixel_array.shape for f in files[:3]}

checks = {}
checks['scanner_returned_0'] = (rc == 0)
checks['nvols_written'] = len(files) == 120
checks['naming_matches_pattern'] = os.path.basename(files[0]) == '001_000001_000001.dcm'
checks['size_over_min'] = all(os.path.getsize(f) >= min_size for f in files[:5])
checks['multiframe_shape_matches_reference'] = (pydicom_shapes == {expected_shape})
_v = mrt.unpack_frames(mrt.pack_frames(vols[5]))
checks['frame_pack_roundtrip_exact'] = np.array_equal(_v, vols[5])
checks['condA_peak_in_A_region'] = pA[0] in A_rows
checks['condB_peak_in_B_region'] = pB[0] in B_rows
checks['contrast_regions_separated'] = abs(pA[0] - pB[0]) >= 8

print("\n==== mock DICOM scanner ====")
print(f"wrote {len(files)} DICOMs to {tmp}  (shape={shape}, TR={TR}s, from {os.path.basename(mock.DEFAULT_REFERENCE)})")
print(f"condA(left) peak {pA} in rows {list(A_rows)} | condB(right) peak {pB} in rows {list(B_rows)}")
print()
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
ok = all(bool(v) for v in checks.values())
print("\nRESULT:", "ALL PASS" if ok else "SEE FAILURES")
import shutil; shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)
