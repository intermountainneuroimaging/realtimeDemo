enhanced_bold_template.dcm is a fully anonymized Enhanced-multi-frame Siemens MR
DICOM (all PHI + private tags stripped, all UIDs regenerated, pixels zeroed),
derived from a real MAGNETOM Prisma Fit BOLD acquisition (88x88x56, TR=1000ms).
mock_scanner.py uses it as the geometry/timing reference and packing container
for synthetic volumes -- see --reference-dicom to point at a different one.
