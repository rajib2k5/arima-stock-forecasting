# Blender hero renders

Scripts that render the repo's hero images with Blender's Python API (`bpy`).

> **Status: renders are pending.** Blender was not reachable on 2026-10-28: there is no `blender`
> binary on the machine, the Blender MCP could not connect, and `bpy` has no wheel for Linux
> aarch64. So **no image has been rendered yet and nothing in `hero_architecture.py` that calls
> `bpy` has ever run.** What *has* run: all of `layout.py` and the `--dry-run` path, under
> `tests/test_blender_layout.py`. See [After the first render](#after-the-first-render).

## Files

| File | What it is |
|---|---|
| `layout.py` | Pure Python, no `bpy`. Computes the scene geometry: slab positions, camera placement, colours, and (for milestone 2) the AIC bar layout. Unit-tested. |
| `hero_architecture.py` | The `bpy` script for milestone 0: five architecture layers as a stack of rounded slabs. Imports `layout.py` from its own folder. |
| `README.md` | This file. |

The scene is the project's five layers, rising bottom to top, slightly separated: Source (Yahoo
Finance / yfinance), Raw cache (`$VOL_DATA_DIR`), Python core (`arima_forecasting`), Delivery
(versioned JSON), App (React + three.js). Colours are the first five slots of a fixed
categorical palette (the `dataviz` skill's light-mode palette, ordered so neighbouring colours
stay distinguishable; the hex values are in `layout.py`). The background is transparent, so the
image reads on GitHub's light and dark themes.

## Run it

### 0. Without Blender: look at the layout

```bash
uv run python tools/blender/hero_architecture.py --dry-run
```

Prints the five slabs, the camera and the output path. It never imports `bpy`. This is the only
way to run the script on this machine today.

### 1. Command line, headless

```bash
blender --background --python-exit-code 1 --python tools/blender/hero_architecture.py
```

Run it from the repo root, or give `--python` an absolute path. The image goes to
`docs/images/hero_architecture.png` relative to the repo root, wherever you run it from.
`--python-exit-code 1` (it must come before `--python`) makes Blender exit non-zero if the
script raises.

Flags for the script go after a `--`:

```bash
blender --background --python-exit-code 1 --python tools/blender/hero_architecture.py \
  -- --engine CYCLES --out /tmp/hero.png
```

| Flag | Meaning |
|---|---|
| `--dry-run` | Print the layout and exit; no `bpy`. |
| `--out PATH` | Write the PNG here instead of `docs/images/hero_architecture.png`. |
| `--engine NAME` | Try this render engine first (for example `CYCLES` on a machine whose headless EEVEE has no GPU). The script otherwise tries `BLENDER_EEVEE_NEXT`, `BLENDER_EEVEE`, `CYCLES` in that order and uses the first one this Blender accepts. |
| `--factory-reset` / `--no-factory-reset` | Whether to start from Blender's empty factory scene (`bpy.ops.wm.read_factory_settings(use_empty=True)`). Default: **yes** when Blender runs in the background, **no** when it has a window. |

In the default headless mode the script builds the scene from nothing, so the result does not
depend on whatever `.blend` file Blender opened.

### 2. Through the Blender MCP

Start Blender with the MCP addon enabled, then call `execute_blender_code` with code that execs
the file. Exec it rather than pasting it, so that `__file__` is set and the script can find
`layout.py` next to it:

```python
path = "/path/to/arima-stock-forecasting/tools/blender/hero_architecture.py"
exec(compile(open(path, encoding="utf-8").read(), path, "exec"), {"__file__": path, "__name__": "__main__"})
```

Replace `path` with the real location of the file. To pass flags, set `sys.argv` first:

```python
import sys
sys.argv = ["hero_architecture.py", "--", "--engine", "CYCLES"]
```

Through the MCP the Blender has a window, so the script does **not** factory-reset. It adds
its objects to the current scene, in one collection named `arima_hero_architecture`, and removes
that collection's previous contents first, so running it twice does not pile up. It changes the
scene's camera, world and render settings to render, and puts the old ones back afterwards. The
objects it made stay in the scene for you to look at; delete the collection to remove them.
Rendering from a window blocks Blender until the render finishes.

If the Blender behind the MCP runs headless, add `--no-factory-reset` unless you want the scene
wiped.

If you paste the file's text instead of exec-ing it, set the environment variable
`ARIMA_REPO_ROOT` to the repo's path first, or the script cannot find `layout.py`.

## Expected output files

| File | Written by | Status |
|---|---|---|
| `docs/images/hero_architecture.png` | `hero_architecture.py` | **Pending** (1600 x 1000 px, RGBA PNG, transparent background) |

That is the only file milestone 0 produces. Nothing else is written: no `.blend`, no cache.
`docs/images/` is not ignored by git, so the PNG is committed once it exists.

The milestone 2 hero (the 3D AIC surface over the `(p, q)` grid, one panel per `d`) is not part of
this yet. `layout.aic_bars()` already computes its geometry from the planned `aic_grid` JSON rows;
only a `hero_aic.py` that builds bars from those rows and renders them is missing.

## After the first render

The first real run is the test of everything that calls `bpy`. Check:

1. It runs to the end and writes the PNG. If an enum identifier or an API call differs in your
   Blender version, the error says which; the script reads enum identifiers from `bl_rna` and
   tries render engines in turn, but this has not been run on any version.
2. **The whole stack is in frame.** The camera is placed by `layout.camera_for` assuming the
   camera's field of view applies to the longer image side (Blender's default "auto" sensor fit).
3. **Labels fit and face the camera.** Each label is flat text on its slab's front face, shrunk to
   fit 92% of the slab width.
4. **Exposure.** `WORLD_STRENGTH` and `KEY_WATTS_PER_UNIT2` at the top of `hero_architecture.py`
   were estimated from the formula for Blender's light units, not tuned by eye. Adjust them if
   the image is washed out or dark.
5. **Rounded edges look smooth.** The slab edges use a Bevel modifier, with smooth shading and a
   Weighted Normal modifier in a `try` block; if that part raised, the script printed a `note:`
   and the slabs are bevelled but possibly faceted.

## Tests

```bash
uv run pytest -q tests/test_blender_layout.py
```

These cover `layout.py` with hand-worked numbers, and run `hero_architecture.py --dry-run` as a
subprocess, with a fake `bpy` on the path that explodes if imported. They do not cover any code
that needs Blender.
