"""Scene geometry for the Blender hero renders. Pure Python: no bpy, no numpy.

Everything the render scripts need to *decide* lives here, so it can be unit-tested without
Blender (tests/test_blender_layout.py). The bpy scripts only turn these numbers into objects.

Axes follow Blender: +X right, +Y into the screen, +Z up. Units are Blender units.

Colours are sRGB floats in 0..1. Blender colour inputs are linear, so the bpy scripts convert
with srgb_to_linear() before writing them to a shader node.

Palette: the categorical palette of the `dataviz` skill (references/palette.md), light-mode
column, in slot order. That order is validated for adjacent pairs, which is what a stack of
slabs (or neighbouring bar panels) needs; the first three slots are also validated for all
pairs. Surface and ink are the same file's chart-chrome values.

The skill's validator (scripts/validate_palette.py, light mode, adjacent pairs) passes the first
five slots, and warns that aqua, yellow and magenta have under 3:1 contrast against the light
surface. Its stated relief is visible direct labels, which every slab has.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

Vec3 = tuple[float, float, float]

# ----------------------------------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------------------------------

# blue, orange, aqua, yellow, magenta, green, violet, red
PALETTE_HEX = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
)
SURFACE_HEX = "#fcfcfb"  # chart surface, light mode: the render background
INK_HEX = "#0b0b0b"  # primary ink, light mode: label text


def hex_to_rgb(hex_colour: str) -> Vec3:
    """'#rrggbb' -> sRGB floats in 0..1."""
    text = hex_colour.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"expected '#rrggbb', got {hex_colour!r}")
    return (int(text[0:2], 16) / 255, int(text[2:4], 16) / 255, int(text[4:6], 16) / 255)


def srgb_to_linear(rgb: Vec3) -> Vec3:
    """sRGB floats -> linear floats (the IEC 61966-2-1 transfer function)."""

    def one(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (one(rgb[0]), one(rgb[1]), one(rgb[2]))


PALETTE_RGB = tuple(hex_to_rgb(h) for h in PALETTE_HEX)

# ----------------------------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------------------------


def _positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")


def _non_negative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative finite number, got {value!r}")


# ----------------------------------------------------------------------------------------------
# Milestone 0: the architecture stack
# ----------------------------------------------------------------------------------------------


class Layer(NamedTuple):
    name: str
    label: str


# Bottom to top: data flows upward, from the outside world to the screen.
ARCHITECTURE_LAYERS = (
    Layer("source", "Source: Yahoo Finance / yfinance"),
    Layer("raw_cache", "Raw cache: $VOL_DATA_DIR"),
    Layer("python_core", "Python core: arima_forecasting"),
    Layer("delivery", "Delivery: versioned JSON"),
    Layer("app", "App: React + three.js"),
)


@dataclass(frozen=True)
class Slab:
    name: str
    label: str
    centre: Vec3
    size: Vec3  # (width along x, depth along y, height along z)
    colour: Vec3  # sRGB 0..1


def architecture_slabs(
    n_layers: int, *, slab_height: float, gap: float, width: float, depth: float
) -> list[Slab]:
    """The first `n_layers` architecture layers as slabs stacked along +Z, bottom to top.

    Slab i (0 = bottom) sits `gap` above slab i-1, so consecutive centres are
    `slab_height + gap` apart, and slab 0 rests on z = 0:

        z_i = i * (slab_height + gap) + slab_height / 2
    """
    if isinstance(n_layers, bool) or not isinstance(n_layers, int):
        raise TypeError(f"n_layers must be an int, got {n_layers!r}")
    if n_layers < 1:
        raise ValueError(f"n_layers must be >= 1, got {n_layers}")
    if n_layers > len(ARCHITECTURE_LAYERS):
        raise ValueError(
            f"n_layers must be <= {len(ARCHITECTURE_LAYERS)} (only that many layers are defined), "
            f"got {n_layers}"
        )
    _positive("slab_height", slab_height)
    _positive("width", width)
    _positive("depth", depth)
    _non_negative("gap", gap)

    pitch = slab_height + gap
    return [
        Slab(
            name=layer.name,
            label=layer.label,
            centre=(0.0, 0.0, i * pitch + slab_height / 2),
            size=(width, depth, slab_height),
            colour=PALETTE_RGB[i % len(PALETTE_RGB)],
        )
        for i, layer in enumerate(ARCHITECTURE_LAYERS[:n_layers])
    ]


# ----------------------------------------------------------------------------------------------
# Bounds and camera
# ----------------------------------------------------------------------------------------------


def bounds(items) -> tuple[Vec3, Vec3]:
    """Axis-aligned bounding box (low corner, high corner) of anything with `centre` and `size`."""
    items = list(items)
    if not items:
        raise ValueError("bounds() needs at least one item")
    lo = tuple(min(it.centre[a] - it.size[a] / 2 for it in items) for a in range(3))
    hi = tuple(max(it.centre[a] + it.size[a] / 2 for it in items) for a in range(3))
    return lo, hi


def stack_extent(items) -> float:
    """Length of the bounding box's diagonal: the diameter of a sphere that holds everything."""
    lo, hi = bounds(items)
    return math.dist(lo, hi)


# Camera sits towards the viewer (-Y), a little to the right (+X) and above (+Z): a three-quarter
# view in which every slab's front (-Y) face is visible and not hidden by the slab above it.
DEFAULT_VIEW_DIRECTION: Vec3 = (0.45, -1.0, 0.55)


def _unit(v: Vec3, what: str) -> Vec3:
    length = math.hypot(*v)
    if length == 0:
        raise ValueError(f"{what} must not be the zero vector")
    return (v[0] / length, v[1] / length, v[2] / length)


def camera_for(
    slabs, *, fov_deg: float, margin: float, direction: Vec3 = DEFAULT_VIEW_DIRECTION
) -> tuple[Vec3, Vec3]:
    """Where to put a camera so the whole stack is in frame: (location, look_at).

    Derivation. Aim at the middle of the bounding box (look_at). Every point of the stack is
    within R = extent / 2 of that middle, where extent is the box diagonal. A camera at distance D
    with full field of view `fov` sees, at distance D, a slice whose half-width is
    D * tan(fov / 2). Ask for that to be R:

        D * tan(fov / 2) = R   =>   D = (extent / 2) / tan(fov / 2)

    and multiply by `margin` (>= 1) for breathing room:

        distance = (extent / 2) / tan(fov / 2) * margin

    Strictly, a sphere of radius R fits inside the view cone only when D >= R / sin(fov / 2),
    i.e. margin >= 1 / cos(fov / 2) (1.05 at 35 degrees, 1.06 at 40). Any margin above that
    contains every corner of the box, from any `direction`.

    `fov_deg` must be the field of view of the *narrower* image axis, or the stack can be cut off
    on that axis; see limiting_fov_deg().
    """
    if not 0 < fov_deg < 180:
        raise ValueError(f"fov_deg must be between 0 and 180 (exclusive), got {fov_deg!r}")
    _positive("margin", margin)
    ux, uy, uz = _unit(direction, "direction")

    lo, hi = bounds(slabs)
    look_at = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
    extent = math.dist(lo, hi)
    distance = (extent / 2) / math.tan(math.radians(fov_deg) / 2) * margin
    location = (look_at[0] + ux * distance, look_at[1] + uy * distance, look_at[2] + uz * distance)
    return location, look_at


def limiting_fov_deg(fov_deg: float, res_x: int, res_y: int) -> float:
    """Field of view of the narrower image axis, given the field of view of the wider one.

    Blender's camera angle (with the default "auto" sensor fit) applies to the longer side of the
    image. The sensor is flat, so the half-width on each axis scales with that axis' pixel count:

        tan(narrow / 2) = tan(wide / 2) * min(res_x, res_y) / max(res_x, res_y)
    """
    if not 0 < fov_deg < 180:
        raise ValueError(f"fov_deg must be between 0 and 180 (exclusive), got {fov_deg!r}")
    if res_x <= 0 or res_y <= 0:
        raise ValueError(f"resolution must be positive, got {res_x}x{res_y}")
    ratio = min(res_x, res_y) / max(res_x, res_y)
    return math.degrees(2 * math.atan(math.tan(math.radians(fov_deg) / 2) * ratio))


def aim_euler(location: Vec3, target: Vec3) -> Vec3:
    """XYZ Euler angles (radians) that point a camera or area light at `target`.

    Both look down their local -Z axis with local +Y up. At (0, 0, 0) that is straight down; a
    rotation of +90 degrees about X turns the view to look along +Y (Blender's front view). With
    f = unit vector from `location` to `target`:

        rx = 90 degrees + elevation = pi/2 + asin(f_z)      (tilt up or down)
        rz = atan2(-f_x, f_y)                               (heading about the vertical)
        ry = 0                                              (no roll)
    """
    fx, fy, fz = _unit(
        (target[0] - location[0], target[1] - location[1], target[2] - location[2]),
        "target - location",
    )
    # "+ 0.0" turns a negative zero (from atan2(-0.0, y)) into a plain zero.
    return (math.pi / 2 + math.asin(fz), 0.0, math.atan2(-fx, fy) + 0.0)


# ----------------------------------------------------------------------------------------------
# Milestone 2 (not wired to any data yet): the AIC bar chart
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bar:
    d: int
    p: int
    q: int
    aic: float
    relative_aic: float  # aic minus the smallest aic within the same d
    centre: Vec3
    size: Vec3
    colour: Vec3  # sRGB 0..1, one per d panel


class BarSet(list):
    """A list of Bar that also remembers the failed fits it skipped.

    skipped_by_d maps every d present in the grid to the number of rows with aic = None;
    `skipped` is their sum.
    """

    def __init__(self, bars=(), *, skipped_by_d: dict[int, int] | None = None):
        super().__init__(bars)
        self.skipped_by_d = dict(skipped_by_d or {})

    @property
    def skipped(self) -> int:
        return sum(self.skipped_by_d.values())


def _int(name: str, row_index: int, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"row {row_index}: {name} must be an int, got {value!r}")
    return value


def aic_bars(
    grid: list[dict],
    *,
    pitch: float = 1.0,
    footprint: float = 0.8,
    panel_gap: float = 1.5,
    height_per_aic: float = 0.05,
    base_height: float = 0.0,
) -> BarSet:
    """One bar per successful (d, p, q) fit, laid out as one panel per d, side by side along +X.

    `grid` holds rows `{"d": int, "p": int, "q": int, "aic": float | None}`: the planned
    `aic_grid` JSON contract. aic is None when the fit failed; those rows get no bar and are
    counted in the result's `skipped_by_d` / `skipped`.

    Within a panel, p maps to x and q to y, `pitch` apart, starting at the smallest p and q found
    anywhere in the grid (so every panel has the same footprint and panels compare like with
    like). Height is the *relative* AIC, aic minus the smallest aic within the same d, times
    `height_per_aic`, plus `base_height`. The best model of each d therefore has height
    `base_height`; pass a base_height above zero to keep it visible.

    A panel is (n_p - 1) * pitch + footprint wide, where n_p is the number of p values in the
    grid, and panels are `panel_gap` apart. Panels are ordered by d. A d whose fits all failed
    still keeps its (empty) slot, so positions do not shift when a fit fails.
    """
    _positive("pitch", pitch)
    _positive("footprint", footprint)
    if footprint > pitch:
        raise ValueError(
            f"footprint ({footprint}) must not exceed pitch ({pitch}): bars would overlap"
        )
    _non_negative("panel_gap", panel_gap)
    _positive("height_per_aic", height_per_aic)
    _non_negative("base_height", base_height)

    rows = []
    seen = set()
    for index, row in enumerate(grid):
        try:
            d, p, q, aic = row["d"], row["p"], row["q"], row["aic"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"row {index}: expected keys d, p, q, aic, got {row!r}") from exc
        d, p, q = _int("d", index, d), _int("p", index, p), _int("q", index, q)
        if aic is not None and (
            isinstance(aic, bool) or not isinstance(aic, (int, float)) or not math.isfinite(aic)
        ):
            raise ValueError(f"row {index}: aic must be a finite number or None, got {aic!r}")
        if (d, p, q) in seen:
            raise ValueError(f"row {index}: duplicate (d, p, q) = {(d, p, q)}")
        seen.add((d, p, q))
        rows.append((d, p, q, aic))
    if not rows:
        return BarSet()

    ds = sorted({d for d, _, _, _ in rows})
    p_min = min(p for _, p, _, _ in rows)
    p_max = max(p for _, p, _, _ in rows)
    q_min = min(q for _, _, q, _ in rows)

    panel_width = (p_max - p_min) * pitch + footprint
    stride = panel_width + panel_gap

    # Per-d minimum over successful fits only.
    best: dict[int, float] = {}
    skipped_by_d = {d: 0 for d in ds}
    for d, _, _, aic in rows:
        if aic is None:
            skipped_by_d[d] += 1
        else:
            best[d] = min(aic, best.get(d, aic))

    bars = []
    for d, p, q, aic in sorted(rows, key=lambda r: r[:3]):
        if aic is None:
            continue
        panel = ds.index(d)
        relative = aic - best[d]
        height = base_height + relative * height_per_aic
        x = panel * stride + (p - p_min) * pitch
        y = (q - q_min) * pitch
        bars.append(
            Bar(
                d=d,
                p=p,
                q=q,
                aic=aic,
                relative_aic=relative,
                centre=(x, y, height / 2),
                size=(footprint, footprint, height),
                colour=PALETTE_RGB[panel % len(PALETTE_RGB)],
            )
        )
    return BarSet(bars, skipped_by_d=skipped_by_d)
