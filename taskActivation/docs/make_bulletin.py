#!/usr/bin/env python3
"""-----------------------------------------------------------------------------
make_bulletin.py -- build docs/realtime_demo_bulletin.pdf, a 3-page bulletin
about the real-time fMRI demo: what it does and how, example tasks, and sample
output.

Everything is drawn from files already in the project, so re-running this after
a task changes keeps the bulletin honest:
  * sample outputs   -- demo-glm-*.png in the project root (live-view current.png
                        screenshots)
  * stimulus thumbs  -- templates/stimulus_snapshots/<task>/<screen>.png (the
                        PsychoPy snapshots utils/make_templates.py also uses)

Needs reportlab + pillow (not part of the analysis pipeline -- install into a
scratch venv):
    python -m venv /tmp/bulletin_venv && /tmp/bulletin_venv/bin/pip install reportlab pillow
    /tmp/bulletin_venv/bin/python docs/make_bulletin.py [--out docs/realtime_demo_bulletin.pdf]

Page size is US Letter. Text uses the built-in Helvetica/Courier (no Unicode
beyond Latin-1), so keep edits to plain characters.
-----------------------------------------------------------------------------"""
import os
import argparse
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
SNAP = os.path.join(ROOT, 'templates', 'stimulus_snapshots')
W, H = letter
MARGIN = 40
CW = W - 2 * MARGIN           # content width

NAVY = HexColor('#0f2233')
TEAL = HexColor('#14808c')
INK = HexColor('#22303c')
MUTED = HexColor('#5d6b78')
PALE = HexColor('#eef3f6')
RULE = HexColor('#cfd8de')
CAT = {'MOVEMENT': HexColor('#d9772b'), 'VISION': HexColor('#2b6fa8'),
       'REWARD': HexColor('#2f9e5f'), 'GAME': HexColor('#7a4fa3')}

REPO_URL = 'github.com/intermountainneuroimaging/realtimeDemo'


# ---------------------------------------------------------------- helpers
def style(size=9.2, leading=None, color=INK, font='Helvetica', align=TA_LEFT):
    return ParagraphStyle('s', fontName=font, fontSize=size, leading=leading or size * 1.32,
                          textColor=color, alignment=align)


def para(c, text, x, top, w, st):
    """Draw a wrapped paragraph whose top edge is `top` (y-up coords); returns its height."""
    p = Paragraph(text, st)
    _, h = p.wrap(w, 10000)
    p.drawOn(c, x, top - h)
    return h


def img(path, max_w=None, crop=None, bg=(0, 0, 0)):
    im = Image.open(path)
    if im.mode == 'RGBA':
        base = Image.new('RGB', im.size, bg)
        base.paste(im, mask=im.split()[3])
        im = base
    else:
        im = im.convert('RGB')
    if crop:
        im = im.crop(crop)
    if max_w and im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    return im


def draw_im(c, im, x, y_bottom, w):
    h = w * im.height / im.width
    c.drawImage(ImageReader(im), x, y_bottom, w, h)
    return h


def heading(c, text, x, top, color=TEAL):
    c.setFillColor(color)
    c.setFont('Helvetica-Bold', 10.5)
    c.drawString(x, top - 10.5, text.upper())
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(x, top - 15, x + CW, top - 15)
    return 20


def band(c, title, subtitle, h, page):
    c.setFillColor(NAVY)
    c.rect(0, H - h, W, h, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.rect(0, H - h - 4, W, 4, stroke=0, fill=1)
    c.setFillColor(HexColor('#7fd6df'))
    c.setFont('Helvetica-Bold', 7.5)
    c.drawString(MARGIN, H - 26, 'REAL-TIME fMRI DEMO  |  BULLETIN')
    c.setFillColor(white)
    if page == 1:
        c.setFont('Helvetica-Bold', 29)
        c.drawString(MARGIN, H - 62, title)
        c.setFillColor(HexColor('#cfe3ea'))
        c.setFont('Helvetica', 12.5)
        c.drawString(MARGIN, H - 86, subtitle)
    else:
        c.setFont('Helvetica-Bold', 21)
        c.drawString(MARGIN, H - 49, title)
        c.setFillColor(HexColor('#cfe3ea'))
        c.setFont('Helvetica', 10)
        c.drawString(MARGIN, H - 66, subtitle)


def footer(c, page):
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(MARGIN, 44, W - MARGIN, 44)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7.5)
    c.drawString(MARGIN, 32, 'Real-Time fMRI Task Activation  -  demo bulletin   |   ' + REPO_URL)
    c.drawRightString(W - MARGIN, 32, 'Page %d of 3' % page)
    c.setFont('Helvetica-Oblique', 7)
    c.drawString(MARGIN, 20, 'Disclaimer: this project was co-developed using Claude Code, '
                             'an AI coding assistant from Anthropic.')


def callout(c, n, x, y, r=8.5):
    c.setFillColor(TEAL)
    c.setStrokeColor(white)
    c.setLineWidth(1.4)
    c.circle(x, y, r, stroke=1, fill=1)
    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 9.5)
    c.drawCentredString(x, y - 3.3, str(n))


def chip(c, text, x, y, color):
    c.setFont('Helvetica-Bold', 6.6)
    tw = c.stringWidth(text, 'Helvetica-Bold', 6.6)
    c.setFillColor(color)
    c.roundRect(x - tw - 10, y - 3, tw + 10, 11.5, 5.5, stroke=0, fill=1)
    c.setFillColor(white)
    c.drawString(x - tw - 5, y, text)


# ---------------------------------------------------------------- page 1
def page1(c):
    band(c, 'Real-Time fMRI Task Activation',
         'Watch the brain respond while the scan is still running - no anatomical scan needed.',
         118, 1)
    y = H - 118 - 4 - 16

    y -= heading(c, 'What it does', MARGIN, y)
    y -= 3
    y -= para(c,
              'As each fMRI volume comes off the scanner it is corrected for head motion, lightly '
              'smoothed, and passed to a statistical model that is <b>updated after every volume</b>. '
              'A web page shows where the brain is responding and how closely each region follows the '
              'task - as early as the first task block, while the participant is still in the scanner. '
              'Nothing has to be prepared in advance: <b>no anatomical scan, atlas or registration</b> '
              'is needed, and any block or event design can be loaded from a standard events file.',
              MARGIN, y, CW, style(9.6, 12.8))
    y -= 8

    # ---- how it works: 5 boxes
    y -= heading(c, 'How it works', MARGIN, y)
    y -= 5
    steps = [('Scanner', 'Each volume arrives as a DICOM file as it is acquired. A mock scanner can '
                         'stand in for testing.'),
             ('Clean up', 'Head-motion correction and 5 mm smoothing, one volume at a time.'),
             ('Find the brain', 'A brain mask is built from the run\'s own first rest volumes - '
                                'no atlas, no warping.'),
             ('Model', 'A GLM with hemodynamic-shaped regressors is re-fit after every volume.'),
             ('Live view', 'Maps and response curves appear in any web browser, refreshed as data arrive.')]
    n, gap = len(steps), 16
    bw = (CW - gap * (n - 1)) / n
    bh = 88
    for i, (t, d) in enumerate(steps):
        x = MARGIN + i * (bw + gap)
        c.setFillColor(PALE)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.roundRect(x, y - bh, bw, bh, 5, stroke=1, fill=1)
        callout(c, i + 1, x + 13, y - 14, r=8)
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 9.2)
        c.drawString(x + 26, y - 17.5, t)
        para(c, d, x + 8, y - 30, bw - 16, style(7.8, 10.2, INK))
        if i < n - 1:
            ax = x + bw + gap / 2
            c.setFillColor(TEAL)
            p = c.beginPath()
            p.moveTo(ax - 3.5, y - bh / 2 + 5)
            p.lineTo(ax + 4, y - bh / 2)
            p.lineTo(ax - 3.5, y - bh / 2 - 5)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
    y -= bh + 10

    # ---- hero figure with callouts
    y -= heading(c, 'Reading a live frame', MARGIN, y)
    y -= 5
    TOP = 52   # crop the empty black margin above the figure
    im = img(os.path.join(ROOT, 'demo-glm-checkerboard-1cond.png'), crop=(0, TOP, 1430, 528))
    hw = CW
    hh = hw * im.height / im.width
    yb = y - hh
    draw_im(c, im, MARGIN, yb, hw)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.rect(MARGIN, yb, hw, hh, stroke=1, fill=0)

    def px(u, v):
        return MARGIN + u * hw / im.width, yb + hh - (v - TOP) * hh / im.height
    callout(c, 1, *px(372, 84))     # frame counter
    callout(c, 2, *px(215, 235))    # activation map
    callout(c, 3, *px(1010, 360))   # measured vs predicted
    callout(c, 4, *px(302, 470))    # shaded task block
    y = yb - 8
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Oblique', 7.6)
    c.drawString(MARGIN, y - 7, 'Sample live output: the visual (checkerboard) task, near the end of the run.')
    y -= 16

    legend = [(1, '<b>Frame counter</b> - which volume is on screen.'),
              (2, '<b>Activation map</b> - voxels that respond to the task, drawn over the participant\'s '
                  'own brain image. Red = increase, blue = decrease.'),
              (3, '<b>Measured vs. predicted</b> - white: the measured signal (% change) at the most '
                  'task-responsive voxel; dashed: the textbook hemodynamic response to this design.'),
              (4, '<b>Task timing</b> - shaded bands mark when the stimulus was on. A good response '
                  'rises and falls with them.')]
    colw = (CW - 18) / 2
    rows = [legend[0:2], legend[2:4]]
    for r, row in enumerate(rows):
        rh = 0
        for k, (num, txt) in enumerate(row):
            x = MARGIN + k * (colw + 18)
            callout(c, num, x + 8, y - 10, r=7.5)
            h = para(c, txt, x + 22, y - 3, colw - 22, style(8.3, 10.8))
            rh = max(rh, h)
        y -= max(rh, 18) + 5

    # ---- why registration-free
    bh = 62
    c.setFillColor(PALE)
    c.setStrokeColor(RULE)
    c.roundRect(MARGIN, y - bh, CW, bh, 5, stroke=1, fill=1)
    c.setFillColor(TEAL)
    c.rect(MARGIN, y - bh, 4, bh, stroke=0, fill=1)
    para(c, '<b>Why "registration-free"?</b> Because the brain mask and regions of interest come from '
            'the participant\'s own functional images, the demo starts working right away and needs no '
            'anatomical scan or template alignment. The trade-off: results are shown in the '
            'participant\'s native space (slice heights are scanner millimetres, not standard MNI '
            'coordinates), so treat anatomy labels as approximate.',
         MARGIN + 14, y - 8, CW - 26, style(8.6, 11.6))


# ---------------------------------------------------------------- page 2
TASKS = [
    dict(name='Visual Perception Task', cat='VISION', meta='Checkerboard vs rest  |  260 s',
         desc='A flickering checkerboard alternates with a fixation cross. Eyes stay on the center of the '
              'screen the whole time.',
         expect='Visual cortex at the back of the brain responds while the checkerboard is on.',
         snaps=[('checkerboard_1cond', 'rest', 'rest'), ('checkerboard_1cond', 'checkerboard', 'checkerboard')],
         result=('demo-glm-checkerboard-1cond.png', 'cb1')),
    dict(name='Visual Perception Task', cat='VISION', meta='Left vs right visual field  |  204 s',
         desc='Checkerboard bars flash at the left or right edge of the screen while the eyes hold the '
              'center cross.',
         expect='Each half of the visual field drives the <b>opposite</b> hemisphere.',
         snaps=[('checkerboard_2cond', 'rest', 'rest'), ('checkerboard_2cond', 'left', 'left'),
                ('checkerboard_2cond', 'right', 'right')],
         result=('demo-glm-checkerboard-2cond.png', 'cb2')),
    dict(name='Voluntary Movement Task', cat='MOVEMENT', meta='Left vs right hand  |  250 s',
         desc='Squeeze the cued hand into a fist, like a stress ball, then relax - again and again while '
              'the cue stays up. Relax on the + cross.',
         expect='The <b>opposite</b> side of motor cortex lights up (left hand = right hemisphere).',
         snaps=[('motor', 'rest', 'rest'), ('motor', 'left_hand', 'left hand'), ('motor', 'right_hand', 'right hand')],
         result=('demo-glm-motor.png', 'motor')),
    dict(name='Hand Guessing Game', cat='GAME', meta='Secret hand  |  250 s',
         desc='The participant <b>secretly</b> picks a hand and moves it whenever MOVE shows. Nobody tells '
              'the experimenter - the group guesses from the live map.',
         expect='Activation sits on one side of motor cortex; the opposite hemisphere gives the answer away.',
         snaps=[('motor_guessing', 'rest', 'rest'), ('motor_guessing', 'move', 'MOVE')],
         result=('demo-glm-motor-guessing.png', 'guess')),
    dict(name='Blackjack Game', cat='REWARD', meta='Win vs lose  |  58 trials, about 5 min',
         desc='Two cards, then hit or stay. A pre-scripted win, loss or tie is revealed (24 wins, 24 '
              'losses, 10 ties).',
         expect='Reward-related regions such as the striatum; these effects are typically subtler than '
                'motor or visual ones.',
         snaps=[('gambling', 'decision', 'decision'), ('gambling', 'win', 'win'),
                ('gambling', 'lose', 'lose'), ('gambling', 'tie', 'tie')],
         result=('demo-glm-gambling.png', 'gam')),
]
# crop boxes (left, top, right, bottom) of the brain-mosaic strip in each sample image, in px
STRIP = {'motor': (170, 92, 1300, 312), 'guess': (170, 64, 1300, 284), 'cb1': (170, 64, 1300, 284),
         'cb2': (170, 92, 1300, 312), 'gam': (170, 92, 1300, 312)}


def card(c, t, x, top, w, h):
    c.setFillColor(white)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.roundRect(x, top - h, w, h, 6, stroke=1, fill=1)
    col = CAT[t['cat']]
    c.setFillColor(col)
    c.rect(x, top - h + 6, 4, h - 12, stroke=0, fill=1)
    pad = 13
    ix, iw = x + pad, w - pad - 10
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 11.2)
    c.drawString(ix, top - 18, t['name'])
    chip(c, t['cat'], x + w - 9, top - 17, col)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7.8)
    c.drawString(ix, top - 29, t['meta'])
    cy = top - 36
    cy -= para(c, t['desc'], ix, cy, iw, style(8.3, 10.6)) + 6
    # stimulus thumbnails
    n = len(t['snaps'])
    gap = 6
    pw = min(70, (iw - gap * (n - 1)) / n)
    ph = pw * 9 / 16
    total = n * pw + (n - 1) * gap
    sx = ix
    for k, (task, screen, label) in enumerate(t['snaps']):
        im = img(os.path.join(SNAP, task, screen + '.png'), max_w=360)
        xx = sx + k * (pw + gap)
        draw_im(c, im, xx, cy - ph, pw)
        c.setStrokeColor(HexColor('#8b98a4'))
        c.setLineWidth(0.6)
        c.rect(xx, cy - ph, pw, ph, stroke=1, fill=0)
        c.setFillColor(MUTED)
        c.setFont('Helvetica', 6.4)
        c.drawCentredString(xx + pw / 2, cy - ph - 7.5, label)
    cy -= ph + 12
    cy -= para(c, '<b>Expect:</b> ' + t['expect'], ix, cy, iw, style(7.9, 10.1, INK)) + 5
    fn, key = t['result']
    im = img(os.path.join(ROOT, fn), crop=STRIP[key], max_w=900)
    sh = iw * im.height / im.width
    draw_im(c, im, ix, cy - sh, iw)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.rect(ix, cy - sh, iw, sh, stroke=1, fill=0)


def battery_card(c, x, top, w, h):
    """Sixth grid slot: the back-to-back battery runner, drawn as three mini screens."""
    c.setFillColor(white)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.roundRect(x, top - h, w, h, 6, stroke=1, fill=1)
    c.setFillColor(TEAL)
    c.rect(x, top - h + 6, 4, h - 12, stroke=0, fill=1)
    pad = 13
    ix, iw = x + pad, w - pad - 10
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 11.2)
    c.drawString(ix, top - 18, 'Run several back-to-back')
    chip(c, 'RUNNER', x + w - 9, top - 17, TEAL)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7.8)
    c.drawString(ix, top - 29, 'Psychtoolbox battery  |  one shared window')
    cy = top - 36
    cy -= para(c, 'A battery runner opens <b>one</b> presentation window for the whole session, so the '
                  'screen never drops back to the desktop between tasks.',
               ix, cy, iw, style(8.3, 10.6)) + 6
    gap = 6
    pw = min(70, (iw - gap * 2) / 3)
    ph = pw * 9 / 16
    screens = [(['Up next:', 'Voluntary', 'Movement Task', '(1 of 3)'], 'staging'),
               (['SQUEEZE', 'LEFT HAND'], 'task runs'),
               (['All tasks complete.', 'Experimenter:', 'press SPACE'], 'end screen')]
    for k, (lines, label) in enumerate(screens):
        xx = ix + k * (pw + gap)
        c.setFillColor(HexColor('#000000'))
        c.rect(xx, cy - ph, pw, ph, stroke=0, fill=1)
        c.setStrokeColor(HexColor('#8b98a4'))
        c.setLineWidth(0.6)
        c.rect(xx, cy - ph, pw, ph, stroke=1, fill=0)
        c.setFillColor(HexColor('#00ff66') if k == 1 else white)
        c.setFont('Helvetica-Bold' if k == 1 else 'Helvetica', 4.8)
        ty = cy - ph / 2 + (len(lines) - 1) * 3.0 - 1.6
        for ln in lines:
            c.drawCentredString(xx + pw / 2, ty, ln)
            ty -= 6
        c.setFillColor(MUTED)
        c.setFont('Helvetica', 6.4)
        c.drawCentredString(xx + pw / 2, cy - ph - 7.5, label)
    cy -= ph + 12
    st = style(7.9, 10.1, INK)
    cy -= para(c, '<b>Between tasks:</b> an "Up next" screen holds until the experimenter presses SPACE '
                  '(Escape stops the session cleanly).', ix, cy, iw, st) + 4
    cy -= para(c, '<b>Friendly names:</b> participants see "Visual Perception Task", "Voluntary Movement '
                  'Task", "Blackjack Game" or "Hand Guessing Game" - never the file names.',
               ix, cy, iw, st) + 4
    para(c, '<b>How to:</b> see the run_battery code on page 3.', ix, cy, iw, st)


def page2(c):
    band(c, 'Example fMRI Demonstration Tasks', 'Each task ships with a stimulus script and a matching '
         'analysis config; the strips show live-view slices.', 76, 2)
    top0 = H - 76 - 4 - 12
    cw2, ch2, gx, gy = (CW - 14) / 2, 206, 14, 8
    for i, t in enumerate(TASKS):
        r, k = divmod(i, 2)
        card(c, t, MARGIN + k * (cw2 + gx), top0 - r * (ch2 + gy), cw2, ch2)
    battery_card(c, MARGIN + cw2 + gx, top0 - 2 * (ch2 + gy), cw2, ch2)


# ---------------------------------------------------------------- page 3
def page3(c):
    band(c, 'Sample output, and how to run it',
         'A live-view frame, the pre-data template, then how to run the analysis and the stimuli.', 76, 3)
    y = H - 76 - 4 - 14
    imw, gap = 340, 14
    tw = CW - imw - gap

    def figure(fn, title, body, y, crop=None):
        im = img(os.path.join(ROOT, fn), crop=crop)
        h = draw_im(c, im, MARGIN, y - imw * im.height / im.width, imw)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.8)
        c.rect(MARGIN, y - h, imw, h, stroke=1, fill=0)
        tx = MARGIN + imw + gap
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 9.6)
        yy = y - 12
        for line in title:
            c.drawString(tx, yy, line)
            yy -= 12
        para(c, body, tx, yy - 2, tw, style(8.2, 10.8))
        return h

    h1 = figure('demo-glm-checkerboard-2cond.png',
                ['Visual task:', 'left vs right'],
                'End of a full run (frame 204). Red marks voxels that respond more to the <b>left</b> '
                'stimulus, blue more to the <b>right</b>. Each lower row compares the measured signal '
                '(white) with the modelled response (dashed) at that condition\'s peak voxel, with the '
                'stimulus blocks shaded.', y)
    y -= h1 + 12
    h2 = figure('templates/current_checkerboard_1cond.png',
                ['Before the first', 'volume arrives'],
                'Each task starts with a template so the screen is never empty: the slices it will show, '
                'the screens the participant sees (top right), and empty response curves with the expected '
                'timing shaded. The first live frame replaces it (shown here for the checkerboard task).', y)
    y -= h2 + 12

    # ---- try it
    y -= heading(c, 'Try it yourself', MARGIN, y)
    y -= 8
    colw = (CW - 16) / 2
    # left: code box
    code = ['./quickstart.sh checkerboard_1cond --run 7',
            './quickstart.sh checkerboard_2cond --run 9',
            './quickstart.sh motor --run 11']
    bh = 90
    c.setFillColor(HexColor('#14202b'))
    c.roundRect(MARGIN, y - bh, colw, bh, 5, stroke=0, fill=1)
    c.setFillColor(HexColor('#7fd6df'))
    c.setFont('Helvetica-Bold', 7.2)
    c.drawString(MARGIN + 10, y - 13, 'START THE ANALYSIS (ONE COMMAND PER TASK)')
    c.setFillColor(white)
    c.setFont('Courier', 8.4)
    for i, line in enumerate(code):
        c.drawString(MARGIN + 10, y - 28 - i * 11.4, line)
    c.setFillColor(HexColor('#9fb3c1'))
    c.setFont('Helvetica', 7.3)
    c.drawString(MARGIN + 10, y - bh + 24, '--run N is optional: it sets the scan run number (7, 9, 11...).')
    c.drawString(MARGIN + 10, y - bh + 11, 'Then open outDir/live/viewer.html in a browser.')
    # right: needs + good to know
    rx = MARGIN + colw + 16
    yy = y
    yy -= para(c, '<b>You will need</b>', rx, yy, colw, style(9, 11.5, NAVY)) + 3
    for b in ['Docker (the brainiak/rtcloud image, which includes FSL)',
              'A scanner\'s DICOM stream - or the included mock scanner for a no-scanner test',
              'PsychoPy or MATLAB + Psychtoolbox on the stimulus computer',
              'A web browser to watch the live view']:
        yy -= para(c, '&bull; ' + b, rx, yy, colw, style(8.1, 10.4)) + 1.5
    yy -= 5
    yy -= para(c, '<b>Good to know</b>', rx, yy, colw, style(9, 11.5, NAVY)) + 3
    for b in ['A research demo - not a clinical tool. Maps are thresholded and shown in native space.']:
        yy -= para(c, '&bull; ' + b, rx, yy, colw, style(8.1, 10.4)) + 1.5

    # ---- run_battery (start below whichever column above is taller)
    y -= max(bh, y - yy) + 12
    y -= heading(c, 'Run the stimuli with run_battery (Psychtoolbox)', MARGIN, y)
    y -= 8
    mcode = ['cd stimuli_ptb',
             'run_battery({ ...',
             '    {@checkerboard_1cond_task, {}}, ...',
             '    {@checkerboard_2cond_task, {}}, ...',
             '    {@motor_task,              {}}  ...',
             '})']
    bh2 = 26 + len(mcode) * 10.2 + 8
    c.setFillColor(HexColor('#14202b'))
    c.roundRect(MARGIN, y - bh2, colw, bh2, 5, stroke=0, fill=1)
    c.setFillColor(HexColor('#7fd6df'))
    c.setFont('Helvetica-Bold', 7.2)
    c.drawString(MARGIN + 10, y - 13, 'IN MATLAB, ON THE STIMULUS COMPUTER')
    c.setFillColor(white)
    c.setFont('Courier', 7.6)
    for i, line in enumerate(mcode):
        c.drawString(MARGIN + 10, y - 26 - i * 10.2, line)
    yy = y
    for b in ['<b>One shared window</b> stays open for the whole session - no flashing back to the '
              'MATLAB desktop between tasks.',
              'Before each task an <b>"Up next"</b> screen appears; the experimenter presses SPACE to '
              'begin it (Escape stops the battery). An "All tasks complete" screen closes the session.',
              'List tasks in the same order as the commands above so each staging screen pairs with '
              'its analysis run (7, 9, 11).',
              'For a desk test, add <font face="Courier">\'TriggerKey\', {\'space\'}</font> to a task and '
              '<font face="Courier">\'Windowed\', true</font> to the call.']:
        yy -= para(c, '&bull; ' + b, rx, yy, colw, style(8.1, 10.4)) + 2


def build(out):
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle('Real-Time fMRI Task Activation - demo bulletin')
    c.setSubject('A 3-page bulletin: how the real-time demo works, example tasks, and sample output')
    for n, fn in enumerate((page1, page2, page3), 1):
        fn(c)
        footer(c, n)
        c.showPage()
    c.save()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Build the 3-page real-time demo bulletin PDF.')
    ap.add_argument('--out', default=os.path.join(HERE, 'realtime_demo_bulletin.pdf'))
    args = ap.parse_args()
    build(args.out)
    print('wrote', args.out)
