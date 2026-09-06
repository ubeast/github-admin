# `gen_social.py` — how the "Introducing repo-healthcheck" image is made

`gen_social.py` is a **one-off asset generator**, not part of the
`repo-healthcheck` package. It lives in `attic/` next to its output so the
image isn't a mystery PNG — anyone can see exactly how it was built and
regenerate or tweak it.

It produces `introducing-repo-healthcheck-compressed.{png,jpg}` in this
folder — the clean redraw of the AI concept
`introducing-repo-healthcheck-full.png` (which is gitignored; see
`attic/README.md`).

## Why it exists

The image started as an externally AI-generated concept
(`introducing-repo-healthcheck-full.png`, also in `attic/`). Every AI variant
had garbled placeholder text baked into the pixels — "repo-healthch**a**ck",
"#SOPT code", nonsense in the fake code editors — which can't be edited out.

Drawing the whole thing in code was the way to get a version with clean,
real text at a controlled size.

## What it does

- **No AI image generation, no image editor.** The image is computed and drawn:
  - `numpy` builds the green→blue diagonal gradient and the radial glows
    pixel by pixel.
  - `PIL` (Pillow) draws every element: the branch + check icon, the EKG
    pulse line, the two faint "code editor" windows, the branch/`main`
    diagram, the upward trend chart, the scattered network nodes, the
    sparkles, and all the type.
- **Renders at 2× (2560×1280) then downsamples to 1280×640** with Lanczos, so
  text and thin strokes stay crisp.
- **The faint background code is real source**, copied from
  `src/repo_healthcheck/health.py` (`check()` and `_is_stale()`), not
  invented — so even the decoration doesn't lie.
- **Copy:** headline `Introducing` / `repo-healthcheck`, tagline
  *"Audit every GitHub and GitLab repo you own — sorted worst first."* — the
  project's real `og:description`. The reference art's "Improve. Automate."
  was dropped on purpose: the tool is read-only and those would be false
  claims (see the repo's `CLAUDE.md`, "Read-only v1").

## Output

Both are 1280×640 (2:1 — the ratio GitHub's social preview and `og:image`
expect):

| File | Size | Fits |
|---|---|---|
| `introducing-repo-healthcheck-compressed.png` | ~310 KB | GitHub social preview (1 MB cap) |
| `introducing-repo-healthcheck-compressed.jpg` | ~90 KB | **GitLab project avatar (200 KB cap)**, and everything above |

The JPEG quality is chosen by a loop that steps down from 92 until the file
is ≤ 195 KB.

## Running it

Needs two font files **next to the script** (not committed — ~700 KB total):

```bash
cd attic
curl -sL -o IBMPlexSans.ttf \
  "https://github.com/google/fonts/raw/main/ofl/ibmplexsans/IBMPlexSans%5Bwdth%2Cwght%5D.ttf"
curl -sL -o IBMPlexMono-Regular.ttf \
  "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf"

uv run --with pillow --with numpy python gen_social.py
```

The `.ttf` files are gitignored inside `attic/` (see `attic/.gitignore`) so
re-running the script doesn't stage ~700 KB of fonts.

IBM Plex Sans is loaded as a variable font; `gen_social.sans(size, weight)`
sets the weight axis (100–700). IBM Plex Sans / Mono are the same faces the
docs site uses.

## Design notes (if you tweak it)

- Palette is green→blue to match the reference concept. This **does not**
  match the docs site's teal/cream (`--accent: #2b5d6b`, `--paper: #f1f3ee`).
  That's fine while the image sits in `attic/`; reconcile the palette before
  ever promoting it to a live `og:image`.
- Coordinates in the script are in final 1280×640 space and multiplied by
  `S` (the supersample factor) at draw time. Change `S` for quality vs.
  speed; change `W`/`H` and most things scale, but the hand-placed
  coordinates (text baselines, icon centre, EKG points) would need nudging.
- `repo-healthcheck` is filled with a horizontal green→pale gradient via a
  text mask, with a blurred drop shadow behind it so both the green and the
  light end stay legible on the gradient.
