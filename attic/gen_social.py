"""Recreate the 'Introducing repo-healthcheck' social image, clean, at 1280x640.

Everything is drawn (gradient via numpy, shapes/text via PIL) so there is no
garbled AI text -- the faint background code is real source from this repo.
Rendered at 2x then downsampled for crisp edges. Output kept under GitLab's
200 KB project-avatar limit (also well within GitHub's 1 MB social-preview cap).
"""

from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = pathlib.Path(__file__).parent
W, H = 1280, 640
S = 2  # supersample factor
CW, CH = W * S, H * S

# ---------------------------------------------------------------- fonts
SANS = HERE / "IBMPlexSans.ttf"
MONO = HERE / "IBMPlexMono-Regular.ttf"


def sans(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(SANS), size * S)
    f.set_variation_by_axes([weight, 100])
    return f


def mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(MONO), size * S)


# ---------------------------------------------------------------- background
def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


MINT = (0x8F, 0xDE, 0xB4)
TEAL = (0x3C, 0x9A, 0x9A)
DEEP = (0x14, 0x44, 0x7C)
NAVY = (0x0E, 0x2F, 0x5E)

yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
# diagonal parameter, top-left = 0, bottom-right = 1
t = (xx / CW * 0.55 + yy / CH * 0.45)
t = np.clip(t, 0, 1)

bg = np.zeros((CH, CW, 3), np.float32)
stops = [(0.0, MINT), (0.30, TEAL), (0.60, DEEP), (1.0, NAVY)]
for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
    m = (t >= t0) & (t <= t1)
    local = (t[m] - t0) / (t1 - t0)
    for i in range(3):
        bg[m, i] = c0[i] + (c1[i] - c0[i]) * local

# radial glow behind the icon
gx, gy = 0.635 * CW, 0.30 * CH
r = np.sqrt((xx - gx) ** 2 + (yy - gy) ** 2)
glow = np.exp(-(r / (0.26 * CW)) ** 2)
bg += glow[..., None] * np.array([70, 120, 90], np.float32)

# soft top-left corner light
r2 = np.sqrt((xx - 0) ** 2 + (yy - 0) ** 2)
tl = np.exp(-(r2 / (0.55 * CW)) ** 2)
bg += tl[..., None] * np.array([45, 60, 40], np.float32)

# gentle darkening bottom-right for depth
br = np.clip((xx / CW * 0.5 + yy / CH * 0.5 - 0.55) / 0.45, 0, 1)
bg -= br[..., None] * np.array([18, 22, 30], np.float32)

bg = np.clip(bg, 0, 255).astype(np.uint8)
img = Image.fromarray(bg, "RGB").convert("RGBA")

# ---------------------------------------------------------------- decorative layer
dec = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
d = ImageDraw.Draw(dec)


def rr(box, radius, **kw):
    d.rounded_rectangle(box, radius=radius * S, **kw)


# --- faint code windows (real source, low opacity) ---
CODE_TOP = [
    "def check(info: RepoInfo) -> RepoHealth:",
    '    """What is missing, at a glance."""',
    "    issues: list[str] = []",
    "    if not info.has_readme:",
    '        issues.append("No README")',
    "    if info.license is None:",
    '        issues.append("No license")',
    "    if not info.branch_protected:",
    '        issues.append("Default branch unprotected")',
    "    return RepoHealth(info, issues)",
]
CODE_BOT = [
    "DEFAULT_STALE_DAYS = 180",
    "",
    "def _is_stale(pushed, stale_days, today):",
    "    if not pushed:",
    "        return False",
    "    delta = today - _parse(pushed)",
    "    return delta.days > stale_days",
    "",
    "results.sort(key=lambda h: -h.issue_count)",
]


def code_window(x, y, w, h, lines, alpha=64):
    win = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    wd = ImageDraw.Draw(win)
    box = [x * S, y * S, (x + w) * S, (y + h) * S]
    wd.rounded_rectangle(box, radius=14 * S, fill=(9, 26, 46, 150), outline=(210, 235, 245, 90), width=S)
    for i, cx in enumerate((18, 34, 50)):
        col = [(255, 120, 110), (255, 200, 90), (110, 220, 140)][i]
        wd.ellipse([(x + cx) * S - 5 * S, (y + 16) * S - 5 * S, (x + cx) * S + 5 * S, (y + 16) * S + 5 * S],
                   fill=col + (150,))
    f = mono(13)
    ln = y + 40
    for i, line in enumerate(lines):
        wd.text(((x + 14) * S, ln * S), f"{i + 1:>2}", font=f, fill=(150, 180, 200, 120))
        wd.text(((x + 46) * S, ln * S), line, font=f, fill=(225, 240, 245, 150))
        ln += 22
    win = win.filter(ImageFilter.GaussianBlur(0.6 * S))
    dec.alpha_composite(Image.blend(Image.new("RGBA", (CW, CH), (0, 0, 0, 0)), win, alpha / 255))


code_window(900, -34, 460, 300, CODE_TOP, alpha=42)
code_window(-70, 476, 430, 260, CODE_BOT, alpha=38)

# --- branch diagram, top centre ---
bcol = (235, 245, 245, 66)
f_lbl = mono(13)
# main line
d.line([(455 * S, 150 * S), (760 * S, 150 * S)], fill=bcol, width=2 * S)
d.polygon([(760 * S, 150 * S), (746 * S, 143 * S), (746 * S, 157 * S)], fill=bcol)
d.text((505 * S, 158 * S), "main", font=f_lbl, fill=bcol)
# branch curving up
d.arc([455 * S, 70 * S, 555 * S, 170 * S], start=90, end=180, fill=bcol, width=2 * S)
d.line([(505 * S, 70 * S), (705 * S, 70 * S)], fill=bcol, width=2 * S)
d.polygon([(705 * S, 70 * S), (691 * S, 63 * S), (691 * S, 77 * S)], fill=bcol)
d.text((545 * S, 46 * S), "branch", font=f_lbl, fill=bcol)
d.ellipse([450 * S, 145 * S, 460 * S, 155 * S], fill=(235, 245, 245, 120))

# --- network nodes, right side ---
rng = np.random.default_rng(7)
nodes = []
for _ in range(11):
    nx = rng.uniform(0.58, 1.0) * W
    ny = rng.uniform(0.10, 0.90) * H
    nodes.append((nx, ny))
for i, (ax, ay) in enumerate(nodes):
    for bx, by in nodes[i + 1:]:
        if (ax - bx) ** 2 + (ay - by) ** 2 < 170 ** 2:
            d.line([(ax * S, ay * S), (bx * S, by * S)], fill=(220, 240, 245, 24), width=S)
for nx, ny in nodes:
    rad = rng.uniform(2.5, 5)
    d.ellipse([(nx - rad) * S, (ny - rad) * S, (nx + rad) * S, (ny + rad) * S],
              fill=(225, 245, 248, 60))

# --- upward trend chart, bottom-right ---
pts_x = np.linspace(0.70 * W, 1.02 * W, 9)
base = np.linspace(0.86 * H, 0.60 * H, 9)
jit = rng.uniform(-14, 10, 9)
pts = list(zip(pts_x, base + jit))
area = [(pts_x[0], 0.98 * H)] + pts + [(pts_x[-1], 0.98 * H)]
d.polygon([(x * S, y * S) for x, y in area], fill=(170, 235, 200, 26))
d.line([(x * S, y * S) for x, y in pts], fill=(175, 238, 205, 120), width=3 * S, joint="curve")
ex, ey = pts[-1]
d.ellipse([(ex - 6) * S, (ey - 6) * S, (ex + 6) * S, (ey + 6) * S], fill=(210, 250, 225, 200))

# --- sparkle ---
def sparkle(cx, cy, s, col):
    d.polygon([(cx, cy - s), (cx + s * 0.28, cy - s * 0.28), (cx + s, cy),
               (cx + s * 0.28, cy + s * 0.28), (cx, cy + s), (cx - s * 0.28, cy + s * 0.28),
               (cx - s, cy), (cx - s * 0.28, cy - s * 0.28)], fill=col)


sparkle(1120 * S, 470 * S, 26 * S, (235, 250, 240, 150))
sparkle(0.60 * CW, 0.78 * CH, 10 * S, (235, 250, 240, 110))

# --- faint page glyphs, bottom centre ---
for off in (0, 34):
    px, py = 720 + off, 470 + off // 2
    d.rounded_rectangle([px * S, py * S, (px + 54) * S, (py + 74) * S], radius=6 * S,
                        outline=(230, 245, 248, 55), width=S)
    d.line([((px + 40) * S, py * S), ((px + 54) * S, (py + 14) * S)], fill=(230, 245, 248, 55), width=S)

img.alpha_composite(dec)

# ---------------------------------------------------------------- EKG pulse
ekg = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
ed = ImageDraw.Draw(ekg)
by = 322
pulse = [(0, by), (44, by), (60, by), (72, by - 7), (83, by + 24),
         (94, by - 44), (104, by + 12), (114, by), (168, by)]
ed.line([(x * S, y * S) for x, y in pulse], fill=(255, 255, 255, 210), width=3 * S, joint="curve")
glow_ekg = ekg.filter(ImageFilter.GaussianBlur(3 * S))
img.alpha_composite(glow_ekg)
img.alpha_composite(ekg)

# ---------------------------------------------------------------- icon (branch + check)
icon = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
ic = ImageDraw.Draw(icon)
cx, cy, R = 812, 190, 66
# concentric rings
for rr_ in (R + 16, R + 40, R + 70):
    ic.ellipse([(cx - rr_) * S, (cy - rr_) * S, (cx + rr_) * S, (cy + rr_) * S],
               outline=(255, 255, 255, 45), width=S)
# glassy disc
ic.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S],
           fill=(20, 70, 66, 180), outline=(220, 245, 240, 150), width=2 * S)
# git-branch glyph
gw = (240, 250, 248, 235)
lx, topy, boty = cx - 16, cy - 30, cy + 30
ic.line([(lx * S, topy * S), (lx * S, boty * S)], fill=gw, width=6 * S)
for yy_ in (topy, boty):
    ic.ellipse([(lx - 9) * S, (yy_ - 9) * S, (lx + 9) * S, (yy_ + 9) * S], fill=gw)
# branch off to upper-right
brx, bry = cx + 22, cy - 18
ic.line([(lx * S, cy * S), (brx * S, bry * S)], fill=gw, width=6 * S)
ic.line([(brx * S, bry * S), (brx * S, (bry - 14) * S)], fill=gw, width=6 * S)
ic.ellipse([(brx - 9) * S, (bry - 23) * S, (brx + 9) * S, (bry - 5) * S], fill=gw)
# check badge
bx, byc, brad = cx + 40, cy + 40, 22
ic.ellipse([(bx - brad) * S, (byc - brad) * S, (bx + brad) * S, (byc + brad) * S],
           fill=(46, 200, 120, 255), outline=(255, 255, 255, 230), width=2 * S)
ic.line([((bx - 10) * S, byc * S), ((bx - 3) * S, (byc + 8) * S), ((bx + 11) * S, (byc - 9) * S)],
        fill=(255, 255, 255, 255), width=5 * S, joint="curve")
img.alpha_composite(icon.filter(ImageFilter.GaussianBlur(0.5 * S)))

# ---------------------------------------------------------------- headline text
txt = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
td = ImageDraw.Draw(txt)
MX = 122

td.text((MX * S, 196 * S), "Introducing", font=sans(72, 300), fill=(255, 255, 255, 255))

# "repo-healthcheck": saturated green held through most of the word, resolving
# to white over the final third -- echoes the reference art.
big = sans(108, 700)
word = "repo-healthcheck"
WY = 336
mask = Image.new("L", (CW, CH), 0)
ImageDraw.Draw(mask).text((MX * S, WY * S), word, font=big, fill=255, stroke_width=S)

# soft drop shadow so both the green and the white end read on the gradient
shadow = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
ImageDraw.Draw(shadow).text(((MX + 3) * S, (WY + 4) * S), word, font=big,
                            fill=(6, 24, 44, 150), stroke_width=S)
txt.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3 * S)))

bbox = big.getbbox(word)
grad = np.zeros((CH, CW, 3), np.float32)
x0 = MX * S
x1 = MX * S + (bbox[2] - bbox[0])
green = (0x22, 0x96, 0x4C)
pale = (0xEC, 0xFA, 0xF0)
xs = np.arange(CW)
for i in range(3):
    grad[:, :, i] = np.interp(xs, [x0, x0 + 0.60 * (x1 - x0), x1],
                              [green[i], green[i], pale[i]])
grad_img = Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
txt.paste(grad_img, (0, 0), mask)

td.text((MX * S, 476 * S), "Audit every GitHub and GitLab repo you own — sorted worst first.",
        font=sans(26, 400), fill=(238, 246, 246, 255))

img.alpha_composite(txt)

# ---------------------------------------------------------------- finish
from PIL import ImageEnhance

out = img.convert("RGB").resize((W, H), Image.LANCZOS)
out = ImageEnhance.Color(out).enhance(1.08)
out = ImageEnhance.Contrast(out).enhance(1.03)

# full-quality PNG (fits GitHub's 1 MB social-preview slot)
png_path = HERE / "introducing-repo-healthcheck-compressed.png"
out.save(png_path, optimize=True)

# JPEG kept small enough for GitLab's 200 KB project-avatar limit
jpg_path = HERE / "introducing-repo-healthcheck-compressed.jpg"
for q in (92, 90, 88, 85, 82):
    out.save(jpg_path, quality=q, subsampling=1, optimize=True)
    if jpg_path.stat().st_size <= 195 * 1024:
        break

for p in (png_path, jpg_path):
    print(f"{p.name:44} {p.stat().st_size / 1024:7.1f} KB")
print(f"jpg quality used: {q}")
