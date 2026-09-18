enhanced_bold_template.dcm is a fully anonymized Enhanced-multi-frame Siemens MR
DICOM (all PHI + private tags stripped, all UIDs regenerated, pixels zeroed),
derived from a real MAGNETOM Prisma Fit BOLD acquisition (88x88x56, TR=1000ms).
mock_scanner.py uses it as the geometry/timing reference and packing container
for synthetic volumes -- see --reference-dicom to point at a different one.

current_<task>.png (one per task: motor, checkerboard_1cond/2cond/3cond, gambling, motor_guessing)
are pre-data "template" versions of the live current.png, for display before any
real data has arrived: a brain underlay (MNI152, no overlay) at the task's own
axial slices, and one row per GLM condition showing ONLY the event timing (shaded
blocks) and the predicted HRF response -- no measured traces. The top-right corner
shows what the participant sees (PsychoPy snapshots).

  stimulus_snapshots/<task>/<screen>.png   PsychoPy screenshots of each stimulus screen
      regenerate: conda activate psychopy-env && python stimuli/render_snapshots.py
      (only needed when a task's on-screen stimuli change)
  current_<task>.png                       the templates themselves
      regenerate: python utils/make_templates.py [task ...]   (no PsychoPy needed)
      (re-run after changing a task's events.tsv, conditions, or run_task.py's Z_CUTS)

taskActivation.py installs the matching template as outDir/live/current.png at
startup (looked up by config name: conf/gambling.toml -> current_gambling.png), so the
live viewer shows it until the first real frame replaces it. A config with no
template (e.g. the default taskActivation.toml) just starts with no placeholder.
