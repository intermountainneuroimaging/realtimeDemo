"""-----------------------------------------------------------------------------
make_design.py  —  (optional) write a STATIC per-volume design file from a shipped
events.tsv, for inspection / offline use.

The live script (taskActivation.py) builds the design at runtime from the events
to match the stream's actual volume count, so this static file is only for review.
Codes: 0=REST, 1=condA, 2=condB, 3=other modeled condition (covariate/cue).
Usage: python utils/make_design.py [events_tsv] [condA] [condB]   (from taskActivation/)
-----------------------------------------------------------------------------"""
import os
import sys
import numpy as np
import rt_analysis as mrt

currPath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))   # taskActivation/ root
TR = 2.0
hrf_delay = 2
events_tsv = sys.argv[1] if len(sys.argv) > 1 else 'HcpMotor_acq-ap_events.tsv'
condA = sys.argv[2] if len(sys.argv) > 2 else 'left_hand'
condB = sys.argv[3] if len(sys.argv) > 3 else 'right_hand'

events = mrt.read_events_tsv(os.path.join(currPath, 'study_design', events_tsv))
last = max(o + d for o, d, _ in events)
nVols = int(np.ceil((last + 10) / TR))

design = mrt.build_design_from_events(events, nVols, TR, hrf_delay,
                                      condA_types=[condA], condB_types=[condB])
out = os.path.join(currPath, 'study_design',
                   os.path.splitext(events_tsv)[0] + '_design.txt')
np.savetxt(out, design, fmt='%d')
cls = mrt.classify_conditions(events, condA, condB)
print(f"nVols={nVols} (events end {last:.1f}s + buffer)")
print(f"interest={cls['interest']} covariates={cls['covariates']} rest={cls['rest'] or 'implicit'}")
print(f"REST={(design==0).sum()} A({condA})={(design==1).sum()} "
      f"B({condB})={(design==2).sum()} other={(design==3).sum()}")
print(f"Wrote {out}")
