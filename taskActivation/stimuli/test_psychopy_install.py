#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
test_psychopy_install.py -- minimal smoke test to confirm PsychoPy is
installed AND its display backend actually works, before running
hcp_motor_task.py / hcp_gambling_task.py for real. A successful `pip install`
doesn't guarantee this -- the window backend (pyglet by default) is the part
that most often fails, silently or not, depending on the OS/GPU drivers.

Checks, in order: (1) psychopy imports at all, (2) a window actually opens,
(3) a keypress is detected. Each step prints [ok]/[FAIL] on its own so a
failure tells you exactly which layer broke.

Run:
    python test_psychopy_install.py
    python test_psychopy_install.py --windowed   # not fullscreen
-----------------------------------------------------------------------------"""
import argparse
import sys


def main():
    ap = argparse.ArgumentParser(description='Smoke-test a PsychoPy install.')
    ap.add_argument('--windowed', action='store_true', help='windowed instead of fullscreen')
    args = ap.parse_args()

    # ---- 1. import ----
    try:
        import psychopy
        from psychopy import visual, core, event
    except Exception as e:
        print(f"[FAIL] could not import psychopy: {e}")
        print("       try: pip install psychopy")
        print("       see stimuli/README.md's 'Install and test PsychoPy' section for "
              "platform-specific notes.")
        sys.exit(1)
    print(f"[ok] psychopy {psychopy.__version__} imported successfully")

    # ---- 2. open a window (this is where backend/display issues usually surface) ----
    try:
        win = visual.Window(fullscr=not args.windowed, color='black', units='height')
    except Exception as e:
        print(f"[FAIL] psychopy imported, but couldn't open a window: {e}")
        print("       this is almost always a display/GPU-driver/window-backend issue, "
              "not a PsychoPy bug -- see stimuli/README.md.")
        sys.exit(1)
    print("[ok] window opened successfully")

    # ---- 3. draw + detect a keypress ----
    msg = visual.TextStim(
        win, height=0.06, color='white', wrapWidth=1.6,
        text=(f"PsychoPy {psychopy.__version__} is working!\n\n"
              "Press any key (or wait 5s) to finish the test."))
    msg.draw()
    win.flip()
    keys = event.waitKeys(maxWait=5.0)
    win.close()
    if keys:
        print(f"[ok] keypress detected: {keys}")
    else:
        print("[warn] no keypress detected within 5s (timed out) -- the window and text "
              "rendered fine, but double check keyboard input is reaching PsychoPy (on "
              "macOS this often means granting Accessibility/Input Monitoring permission "
              "to your terminal app in System Settings > Privacy & Security).")
    print("\n[ok] PsychoPy install looks good -- you're ready to run hcp_motor_task.py / "
          "hcp_gambling_task.py.")
    core.quit()


if __name__ == '__main__':
    main()
