"""-----------------------------------------------------------------------------
test_generalize.py — verify the design generalizes to a DIFFERENT task design
(ds000244 HcpGambling: reward / punishment / neutral, no cues, implicit rest).

Checks the rest/interest/covariate split, then synthesizes a 4D series where
reward, punishment AND the neutral covariate each drive a distinct region, and
confirms the incremental GLM:
  * localizes the reward-vs-punishment contrast correctly,
  * regresses the neutral covariate OUT of that contrast (neutral region ~0),
  * supports single-condition beta-weight, and that rest is implicit.
-----------------------------------------------------------------------------"""
import os
import numpy as np
from scipy.ndimage import gaussian_filter
import rt_analysis as mrt

TR = 2.0
ev = mrt.read_events_tsv(os.path.join(os.path.dirname(__file__),
                                      'study_design', 'HcpGambling_acq-ap_events.tsv'))
last = max(o + d for o, d, _ in ev); nVols = int(np.ceil((last + 10) / TR))
condA, condB = 'reward', 'punishment'

cls = mrt.classify_conditions(ev, condA, condB)
X, names = mrt.make_glm_design(ev, nVols, TR, drift_order=1)
iRew, iPun, iNeu = names.index('reward'), names.index('punishment'), names.index('neutral')

# three distinct regions driven by the three conditions
shape = (40, 48, 30); rng = np.random.default_rng(0)
brain = np.zeros(shape, bool); brain[5:35, 5:43, 3:27] = True
def blob(cx, cy, cz):
    m = np.zeros(shape, bool); m[cx:cx+3, cy:cy+3, cz:cz+3] = True; return m
Rrew, Rpun, Rneu = blob(28, 30, 16), blob(10, 30, 16), blob(20, 12, 20)
BASE = 1000.0
def mk(v):
    vol = BASE + rng.normal(0, 6, shape)
    vol += 45*X[v, iRew]*Rrew + 45*X[v, iPun]*Rpun + 60*X[v, iNeu]*Rneu
    return gaussian_filter(vol*brain, 1.0)*brain
bmask = mrt.compute_brain_mask(mk(0)).flatten(); midx = np.where(bmask)[0]
Y = np.zeros((nVols, midx.size), np.float32)
for v in range(nVols): Y[v] = mk(v).flatten()[midx]

def scatter(c):
    m = np.zeros(bmask.size, np.float32); m[midx] = c; return m.reshape(shape)

con = scatter(mrt.glm_beta_contrast(X, Y, names, condA, condB, zscore=True))
bw = scatter(mrt.glm_beta_contrast(X, Y, names, condA, None, zscore=True))

def peakpos(m): return np.unravel_index(int(np.nanargmax(m)), m.shape)
def peakneg(m): return np.unravel_index(int(np.nanargmin(m)), m.shape)

checks = {}
checks['interest_is_reward_punishment'] = cls['interest'] == ['reward', 'punishment']
checks['neutral_is_covariate'] = cls['covariates'] == ['neutral']
checks['rest_is_implicit'] = cls['rest'] == []          # no explicit rest type -> gaps
checks['glm_regressors_present'] = all(n in names for n in ['reward', 'punishment', 'neutral', 'intercept'])
checks['contrast_reward_pos_in_Rrew'] = Rrew[peakpos(con)]
checks['contrast_punish_neg_in_Rpun'] = Rpun[peakneg(con)]
# the neutral covariate must be regressed OUT of the reward-vs-punishment contrast
checks['neutral_regressed_out'] = abs(float(con[Rneu].mean())) < 1.0     # ~0 in z despite strong neutral signal
checks['neutral_strong_but_excluded'] = float(np.abs(con[Rneu]).max()) < float(con[Rrew].max())
# single-condition beta weight peaks in the reward region
checks['betaweight_reward_in_Rrew'] = Rrew[peakpos(bw)]
# baseline boundary = first non-rest event (reward @ 8.06 -> 4 frames)
non_rest = [o for o, _, tt in ev if not mrt.is_rest_type(tt)]
checks['baseline_before_first_condition'] = int(min(non_rest)//TR) == 4

print("\n==== HcpGambling generalization ====")
print("interest:", cls['interest'], "| covariates:", cls['covariates'], "| rest:", cls['rest'] or 'implicit')
print(f"reward z @Rrew={con[Rrew].mean():+.2f}  punishment z @Rpun={con[Rpun].mean():+.2f}  "
      f"neutral z @Rneu={con[Rneu].mean():+.2f} (should be ~0)")
print()
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
ok = all(bool(v) for v in checks.values())
print("\nRESULT:", "ALL PASS" if ok else "SEE FAILURES")
import sys; sys.exit(0 if ok else 1)
