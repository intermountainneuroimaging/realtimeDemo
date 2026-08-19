"""-----------------------------------------------------------------------------
hcp_replay.py  —  OpenNeuro download + local NIfTI replay helpers, used only by
                  this tutorial/ folder's offline demonstration scripts.

The live pipeline (../taskActivation.py) streams DICOMs from a real scanner
and has no need for these; they exist here purely so test_pipeline.py can
validate the analysis against real HCP task designs without a scanner.
-----------------------------------------------------------------------------"""
import os
import numpy as np


def bids_bold_relpath(subject, session, task, acquisition):
    """Relative BIDS path of a bold file from subject/session/task/acquisition."""
    sub = f"sub-{subject}"
    parts = [sub]
    name = sub
    if session:
        parts.append(f"ses-{session}")
        name += f"_ses-{session}"
    parts.append("func")
    name += f"_task-{task}"
    if acquisition:
        name += f"_acq-{acquisition}"
    name += "_bold.nii.gz"
    return os.path.join(*parts, name)


def ensure_openneuro_bold(cacheDir, dsAccession, subject, session, task, acquisition,
                          verbose=True):
    """Download a single bold (+ its events/json) from OpenNeuro's public S3 mirror
    using the same `aws s3 sync --no-sign-request` rt-cloud uses. Returns the local
    path to the 4D bold .nii.gz (downloading only if missing)."""
    rel = bids_bold_relpath(subject, session, task, acquisition)
    local_bold = os.path.join(cacheDir, dsAccession, rel)
    if os.path.exists(local_bold):
        if verbose:
            print(f"[data] using cached bold: {local_bold}")
        return local_bold
    func_dir = os.path.dirname(local_bold)
    os.makedirs(func_dir, exist_ok=True)
    # S3 source = the func/ folder for this subject/session
    s3sub = f"sub-{subject}/" + (f"ses-{session}/" if session else "") + "func/"
    s3 = f"s3://openneuro.org/{dsAccession}/{s3sub}"
    inc = f"*task-{task}*" + (f"acq-{acquisition}*" if acquisition else "")
    cmd = (f'aws s3 sync --no-sign-request "{s3}" "{func_dir}" '
           f'--exclude "*" --include "{inc}"')
    if verbose:
        print(f"[data] downloading: {cmd}")
    os.system(cmd)
    if not os.path.exists(local_bold):
        raise FileNotFoundError(
            f"Could not download {local_bold}. Check the accession/entities and that "
            f"awscli is installed and the container has network access.")
    return local_bold


class NiftiReplaySource:
    """Replays volumes from a local 4D NIfTI, mimicking a realtime stream.
    Volumes are read lazily (no full 4D load)."""
    def __init__(self, path):
        import nibabel as nib
        self.img = nib.load(path)
        if self.img.ndim != 4:
            raise ValueError(f"Expected a 4D bold, got shape {self.img.shape}")
        self.numVolumes = int(self.img.shape[3])
        self.affine = self.img.affine
        self.header = self.img.header

    def get_volume(self, volIdx):
        """Return a 3D nibabel image for 0-based volume volIdx."""
        import nibabel as nib
        vol = np.asarray(self.img.dataobj[..., volIdx])
        return nib.Nifti1Image(vol, self.affine, self.header)
