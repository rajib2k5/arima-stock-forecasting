"""Tests for tools/blender/layout.py (the pure geometry behind the Blender hero renders) and for the
--dry-run path of tools/blender/hero_architecture.py.

Blender is neither needed nor used. Expected values are literals worked out by hand, with the
arithmetic beside them, never recomputed by the code under test. The bpy calls in
hero_architecture.py are NOT tested here: they only run inside Blender.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BLENDER_DIR = REPO / "tools" / "blender"
HERO = BLENDER_DIR / "hero_architecture.py"


def load_layout():
    """Import tools/blender/layout.py by path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("blender_layout", BLENDER_DIR / "layout.py")
    module = importlib.util.module_from_spec(spec)
    # dataclasses looks its own module up in sys.modules while decorating.
    sys.modules["blender_layout"] = module
    spec.loader.exec_module(module)
    return module


layout = load_layout()


def five_slabs(**overrides):
    params = dict(slab_height=0.4, gap=0.1, width=4.4, depth=2.4)
    params.update(overrides)
    return layout.architecture_slabs(5, **params)


# ---------------------------------------------------------------------------------------------
# architecture_slabs
# ---------------------------------------------------------------------------------------------


def test_z_centres_of_five_slabs():
    # pitch = slab_height + gap = 0.4 + 0.1 = 0.5
    # z_i = i * 0.5 + slab_height / 2 = i * 0.5 + 0.2  ->  0.2, 0.7, 1.2, 1.7, 2.2
    slabs = five_slabs()
    assert [s.centre[2] for s in slabs] == pytest.approx([0.2, 0.7, 1.2, 1.7, 2.2])


def test_zero_gap_slabs_touch_and_the_first_rests_on_the_ground():
    # slab_height = 0.5, gap = 0: pitch = 0.5, z_i = i * 0.5 + 0.25  ->  0.25, 0.75, 1.25
    # The first spans 0.25 +- 0.25 = [0, 0.5], the second [0.5, 1.0]: touching, starting at z = 0.
    slabs = layout.architecture_slabs(3, slab_height=0.5, gap=0.0, width=1.0, depth=1.0)
    assert [s.centre[2] for s in slabs] == pytest.approx([0.25, 0.75, 1.25])


def test_neighbouring_slabs_are_exactly_gap_apart():
    # slab_height = 0.4, gap = 0.25: pitch = 0.65, z = 0.2, 0.85, 1.5
    # Slab 0 tops out at 0.2 + 0.2 = 0.4; slab 1 starts at 0.85 - 0.2 = 0.65; 0.65 - 0.4 = 0.25.
    slabs = five_slabs(gap=0.25)
    assert [s.centre[2] for s in slabs[:3]] == pytest.approx([0.2, 0.85, 1.5])
    assert slabs[1].centre[2] - slabs[1].size[2] / 2 - (
        slabs[0].centre[2] + slabs[0].size[2] / 2
    ) == pytest.approx(0.25)


def test_size_and_horizontal_centre():
    # size is (width along x, depth along y, slab_height along z); every slab is centred on
    # x = y = 0.
    for slab in five_slabs():
        assert slab.size == (4.4, 2.4, 0.4)
        assert slab.centre[:2] == (0.0, 0.0)


def test_layers_run_bottom_to_top_in_pipeline_order():
    slabs = five_slabs()
    assert [s.name for s in slabs] == ["source", "raw_cache", "python_core", "delivery", "app"]
    assert [s.label for s in slabs] == [
        "Source: Yahoo Finance / yfinance",
        "Raw cache: $VOL_DATA_DIR",
        "Python core: arima_forecasting",
        "Delivery: versioned JSON",
        "App: React + three.js",
    ]


def test_fewer_layers_keep_the_bottom_ones():
    slabs = layout.architecture_slabs(2, slab_height=0.4, gap=0.1, width=4.4, depth=2.4)
    assert [s.name for s in slabs] == ["source", "raw_cache"]
    assert [s.centre[2] for s in slabs] == pytest.approx([0.2, 0.7])


def test_colours_are_the_first_five_palette_slots_in_order():
    # Palette slots 1-5, typed as bytes from the hex values, then divided by 255:
    #   #2a78d6 = (0x2a, 0x78, 0xd6) = (42, 120, 214)    blue
    #   #eb6834 = (235, 104, 52)                         orange
    #   #1baf7a = (27, 175, 122)                         aqua
    #   #eda100 = (237, 161, 0)                          yellow
    #   #e87ba4 = (232, 123, 164)                        magenta
    as_bytes = [(42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (232, 123, 164)]
    slabs = five_slabs()
    for slab, (r, g, b) in zip(slabs, as_bytes, strict=True):
        assert slab.colour == pytest.approx((r / 255, g / 255, b / 255))
    assert len({s.colour for s in slabs}) == 5


# Each case names the offending argument in the message it expects: several of these would raise
# the same exception type from somewhere else (slicing by a float, for instance), so the type
# alone would not show that the explicit check is there.
@pytest.mark.parametrize(
    "call, error, message",
    [
        (dict(n_layers=0), ValueError, "n_layers must be >= 1"),
        (dict(n_layers=-1), ValueError, "n_layers must be >= 1"),
        (dict(n_layers=6), ValueError, "n_layers must be <= 5"),  # only five layers are defined
        (dict(n_layers=2.0), TypeError, "n_layers must be an int"),
        (dict(n_layers=True), TypeError, "n_layers must be an int"),
        (dict(slab_height=0), ValueError, "slab_height must be"),
        (dict(slab_height=-0.4), ValueError, "slab_height must be"),
        (dict(slab_height=math.nan), ValueError, "slab_height must be"),
        (dict(width=0), ValueError, "width must be"),
        (dict(width=-1.0), ValueError, "width must be"),
        (dict(depth=0), ValueError, "depth must be"),
        (dict(depth=math.inf), ValueError, "depth must be"),
        (dict(gap=-0.1), ValueError, "gap must be"),
        (dict(gap=math.nan), ValueError, "gap must be"),
    ],
)
def test_slab_input_validation(call, error, message):
    params = dict(n_layers=5, slab_height=0.4, gap=0.1, width=4.4, depth=2.4)
    params.update(call)
    n_layers = params.pop("n_layers")
    with pytest.raises(error, match=message):
        layout.architecture_slabs(n_layers, **params)


def test_zero_gap_and_a_single_layer_are_valid():
    slabs = layout.architecture_slabs(1, slab_height=1.0, gap=0, width=1.0, depth=1.0)
    assert [s.name for s in slabs] == ["source"]


# ---------------------------------------------------------------------------------------------
# colour helpers
# ---------------------------------------------------------------------------------------------


def test_hex_to_rgb():
    assert layout.hex_to_rgb("#000000") == (0.0, 0.0, 0.0)
    assert layout.hex_to_rgb("#ffffff") == (1.0, 1.0, 1.0)
    # #2a78d6: 0x2a = 42, 0x78 = 120, 0xd6 = 214
    assert layout.hex_to_rgb("#2a78d6") == pytest.approx((42 / 255, 120 / 255, 214 / 255))
    # Anything but exactly six hex digits is refused, including 8-digit "#rrggbbaa", which would
    # otherwise parse as its first six digits.
    for bad in ("#fff", "#2a78d6ff"):
        with pytest.raises(ValueError):
            layout.hex_to_rgb(bad)


def test_srgb_to_linear():
    # 0 and 1 are fixed points.
    assert layout.srgb_to_linear((0.0, 1.0, 0.0)) == (0.0, 1.0, 0.0)
    # 0.04 is on the linear segment (<= 0.04045): 0.04 / 12.92 = 0.0030960
    # 0.5 is on the power segment: ((0.5 + 0.055) / 1.055) ** 2.4 = 0.526066 ** 2.4 = 0.214041
    r, g, b = layout.srgb_to_linear((0.04, 0.5, 0.5))
    assert r == pytest.approx(0.003096, abs=1e-6)
    assert g == pytest.approx(0.214041, abs=1e-6)
    assert b == pytest.approx(0.214041, abs=1e-6)


# ---------------------------------------------------------------------------------------------
# camera_for, limiting_fov_deg, aim_euler
# ---------------------------------------------------------------------------------------------


def single_slab():
    # One 2 x 2 x 1 slab at the origin-ish: x, y in [-1, 1], z in [0, 1]. Box diagonal:
    # sqrt(2**2 + 2**2 + 1**2) = sqrt(9) = 3, centre (0, 0, 0.5).
    return layout.architecture_slabs(1, slab_height=1.0, gap=0.0, width=2.0, depth=2.0)


def test_camera_distance_for_a_90_degree_lens():
    # extent = 3, fov = 90: tan(45 degrees) = 1, so distance = (3 / 2) / 1 * margin = 1.5 * 1.0.
    # Looking along +Y from -Y: the camera is 1.5 in front of the box centre (0, 0, 0.5).
    location, look_at = layout.camera_for(
        single_slab(), fov_deg=90, margin=1.0, direction=(0, -1, 0)
    )
    assert look_at == pytest.approx((0.0, 0.0, 0.5))
    assert location == pytest.approx((0.0, -1.5, 0.5))


def test_camera_distance_uses_half_the_fov_and_the_margin():
    # fov = 60: tan(30 degrees) = 1 / sqrt(3) = 0.577350, so
    # distance = 1.5 / 0.577350 * 1.2 = 1.5 * 1.732051 * 1.2 = 3.117691.
    location, _ = layout.camera_for(single_slab(), fov_deg=60, margin=1.2, direction=(0, -1, 0))
    assert location == pytest.approx((0.0, -3.117691, 0.5), abs=1e-6)


def test_camera_direction_is_normalised_before_use():
    # (3, -4, 0) has length 5, so the unit vector is (0.6, -0.8, 0). distance = 1.5 (as above):
    # location = (0, 0, 0.5) + 1.5 * (0.6, -0.8, 0) = (0.9, -1.2, 0.5).
    location, _ = layout.camera_for(single_slab(), fov_deg=90, margin=1.0, direction=(3, -4, 0))
    assert location == pytest.approx((0.9, -1.2, 0.5))


def test_camera_aims_at_the_middle_of_the_bounding_box():
    # Two 2-wide cubes, centres x = 0 and x = 4: the box spans x in [-1, 5], so the middle is x = 2.
    # y and z span [-1, 1], so the middle is 0 on both.
    left = layout.Slab("a", "a", (0.0, 0.0, 0.0), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0))
    right = layout.Slab("b", "b", (4.0, 0.0, 0.0), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0))
    _, look_at = layout.camera_for([left, right], fov_deg=90, margin=1.0)
    assert look_at == pytest.approx((2.0, 0.0, 0.0))
    # extent = sqrt(6**2 + 2**2 + 2**2) = sqrt(44) = 6.633250; distance = 3.316625 with the default
    # direction, so the camera ends up that far from the middle.
    location, look_at = layout.camera_for([left, right], fov_deg=90, margin=1.0)
    assert math.dist(location, look_at) == pytest.approx(3.316625, abs=1e-6)


@pytest.mark.parametrize("fov_deg", [22.3, 35.0, 60.0])
@pytest.mark.parametrize(
    "direction", [(0.45, -1.0, 0.55), (1.0, -1.0, 0.3), (-0.5, -1.0, 1.5), (0.0, -1.0, 0.1)]
)
def test_camera_keeps_every_corner_of_the_stack_in_frame(fov_deg, direction):
    # An independent pinhole check, not a copy of camera_for. Corners of the default stack:
    #   x = +-2.2 (width 4.4 / 2), y = +-1.2 (depth 2.4 / 2), z = 0 and 2.4 (5 * 0.4 + 4 * 0.1).
    # With margin 1.2 (above 1 / cos(fov / 2) = 1.154 at 60 degrees, the largest here), each corner
    # must sit inside the view cone: lateral offset / depth <= tan(fov / 2) on both image axes.
    location, look_at = layout.camera_for(
        five_slabs(), fov_deg=fov_deg, margin=1.2, direction=direction
    )

    def sub(a, b):
        return tuple(x - y for x, y in zip(a, b, strict=True))

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    def cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def unit(a):
        n = math.sqrt(dot(a, a))
        return tuple(x / n for x in a)

    forward = unit(sub(look_at, location))
    right = unit(cross(forward, (0.0, 0.0, 1.0)))
    up = cross(right, forward)
    limit = math.tan(math.radians(fov_deg) / 2)
    for x in (-2.2, 2.2):
        for y in (-1.2, 1.2):
            for z in (0.0, 2.4):
                offset = sub((x, y, z), location)
                depth = dot(offset, forward)
                assert depth > 0
                assert abs(dot(offset, right)) / depth <= limit
                assert abs(dot(offset, up)) / depth <= limit


@pytest.mark.parametrize(
    "call",
    [
        dict(fov_deg=0, margin=1.0),
        dict(fov_deg=180, margin=1.0),
        dict(fov_deg=-30, margin=1.0),
        dict(fov_deg=math.nan, margin=1.0),
        dict(fov_deg=35, margin=0),
        dict(fov_deg=35, margin=-1.0),
        dict(fov_deg=35, margin=1.0, direction=(0, 0, 0)),
    ],
)
def test_camera_input_validation(call):
    with pytest.raises(ValueError):
        layout.camera_for(five_slabs(), **call)


def test_camera_needs_something_to_frame():
    with pytest.raises(ValueError, match="at least one"):
        layout.camera_for([], fov_deg=35, margin=1.1)


def test_limiting_fov_is_the_narrower_axis():
    # fov = 90 along the long side, 1600 x 800:
    #   tan(narrow / 2) = tan(45 degrees) * 800 / 1600 = 0.5
    #   narrow = 2 * atan(0.5) = 2 * 26.565051 = 53.130102 degrees. The same in portrait.
    assert layout.limiting_fov_deg(90, 1600, 800) == pytest.approx(53.130102, abs=1e-6)
    assert layout.limiting_fov_deg(90, 800, 1600) == pytest.approx(53.130102, abs=1e-6)
    # A square image has no narrower axis.
    assert layout.limiting_fov_deg(35, 1000, 1000) == pytest.approx(35.0)


def test_limiting_fov_input_validation():
    with pytest.raises(ValueError):
        layout.limiting_fov_deg(0, 1600, 1000)
    with pytest.raises(ValueError):
        layout.limiting_fov_deg(35, 0, 1000)


@pytest.mark.parametrize(
    "location, target, expected",
    [
        # Blender's front view: camera at -Y looking along +Y is (90, 0, 0) degrees.
        ((0, -5, 0), (0, 0, 0), (math.pi / 2, 0.0, 0.0)),
        # At +X looking along -X: level, turned a quarter turn: rz = atan2(1, 0) = 90 degrees.
        ((5, 0, 0), (0, 0, 0), (math.pi / 2, 0.0, math.pi / 2)),
        # At (-3, -3, 0) looking along (+1, +1, 0): rz = atan2(-0.7071, 0.7071) = -45 degrees.
        ((-3, -3, 0), (0, 0, 0), (math.pi / 2, 0.0, -math.pi / 4)),
        # Looking down 45 degrees: f = (0, 1, -1) / sqrt(2), elevation = asin(-0.7071) = -45
        # degrees, so rx = 90 - 45 = 45 degrees.
        ((0, -1, 1), (0, 0, 0), (math.pi / 4, 0.0, 0.0)),
        # Straight down is the unrotated pose: elevation -90 degrees, rx = 0.
        ((0, 0, 5), (0, 0, 0), (0.0, 0.0, 0.0)),
    ],
)
def test_aim_euler(location, target, expected):
    assert layout.aim_euler(location, target) == pytest.approx(expected, abs=1e-12)


def test_aim_euler_needs_two_different_points():
    with pytest.raises(ValueError):
        layout.aim_euler((1, 2, 3), (1, 2, 3))


# ---------------------------------------------------------------------------------------------
# aic_bars (milestone 2; not wired to any data yet)
# ---------------------------------------------------------------------------------------------

# d = 0: successful aics 100.0, 103.0, 101.5 -> smallest 100.0 -> relative 0, 3, 1.5
# d = 1: successful aics 200.0, 190.0, 195.0 -> smallest 190.0 -> relative 10, 0, 5
# (A single smallest over the whole grid, 100.0, would give d = 1 relative 100, 90, 95.)
# One failed fit (aic None) in each d, at (p, q) = (1, 1).
GRID = [
    {"d": 0, "p": 0, "q": 0, "aic": 100.0},
    {"d": 0, "p": 1, "q": 0, "aic": 103.0},
    {"d": 0, "p": 0, "q": 1, "aic": 101.5},
    {"d": 0, "p": 1, "q": 1, "aic": None},
    {"d": 1, "p": 0, "q": 0, "aic": 200.0},
    {"d": 1, "p": 1, "q": 0, "aic": 190.0},
    {"d": 1, "p": 0, "q": 1, "aic": 195.0},
    {"d": 1, "p": 1, "q": 1, "aic": None},
]

# Defaults except height_per_aic = 0.5, which keeps every height exact in binary floating point.
OPTIONS = dict(pitch=1.0, footprint=0.8, panel_gap=1.5, height_per_aic=0.5)


def by_key(bars):
    return {(b.d, b.p, b.q): b for b in bars}


def test_relative_aic_is_taken_within_each_d():
    bars = by_key(layout.aic_bars(GRID, **OPTIONS))
    relative = {key: b.relative_aic for key, b in bars.items()}
    assert relative == {
        (0, 0, 0): 0.0,
        (0, 1, 0): 3.0,
        (0, 0, 1): 1.5,
        (1, 0, 0): 10.0,
        (1, 1, 0): 0.0,
        (1, 0, 1): 5.0,
    }
    # height = relative * 0.5: d = 0 -> 0, 1.5, 0.75; d = 1 -> 5.0, 0, 2.5
    heights = {key: b.size[2] for key, b in bars.items()}
    assert heights == {
        (0, 0, 0): 0.0,
        (0, 1, 0): 1.5,
        (0, 0, 1): 0.75,
        (1, 0, 0): 5.0,
        (1, 1, 0): 0.0,
        (1, 0, 1): 2.5,
    }


def test_failed_fits_are_skipped_and_counted():
    bars = layout.aic_bars(GRID, **OPTIONS)
    assert len(bars) == 6  # 8 rows - 2 failed fits
    assert (0, 1, 1) not in by_key(bars) and (1, 1, 1) not in by_key(bars)
    assert bars.skipped == 2
    assert bars.skipped_by_d == {0: 1, 1: 1}


def test_p_and_q_map_to_x_and_y_and_panels_sit_side_by_side():
    # p range 0..1 -> panel width = (1 - 0) * 1.0 + 0.8 = 1.8; stride = 1.8 + 1.5 = 3.3.
    # d = 0 panel starts at x = 0, d = 1 panel at x = 3.3. y = q * pitch.
    # z centre = height / 2.
    bars = by_key(layout.aic_bars(GRID, **OPTIONS))
    assert bars[(0, 1, 0)].centre == pytest.approx((1.0, 0.0, 0.75))  # height 1.5
    assert bars[(0, 0, 1)].centre == pytest.approx((0.0, 1.0, 0.375))  # height 0.75
    assert bars[(1, 0, 1)].centre == pytest.approx((3.3, 1.0, 1.25))  # height 2.5
    assert bars[(1, 1, 0)].centre == pytest.approx((4.3, 0.0, 0.0))  # height 0
    assert bars[(1, 0, 0)].size == pytest.approx((0.8, 0.8, 5.0))


def test_panels_are_exactly_panel_gap_apart():
    # Panel 0 spans x = 0 - 0.4 .. 1 + 0.4 = [-0.4, 1.4]; panel 1 spans 3.3 - 0.4 .. 4.3 + 0.4 =
    # [2.9, 4.7]. The space between them is 2.9 - 1.4 = 1.5 = panel_gap.
    bars = layout.aic_bars(GRID, **OPTIONS)
    right_of_panel_0 = max(b.centre[0] + b.size[0] / 2 for b in bars if b.d == 0)
    left_of_panel_1 = min(b.centre[0] - b.size[0] / 2 for b in bars if b.d == 1)
    assert right_of_panel_0 == pytest.approx(1.4)
    assert left_of_panel_1 == pytest.approx(2.9)


def overlaps(a, b):
    """True when two bars' footprints share any area."""
    for axis in (0, 1):
        low = max(a.centre[axis] - a.size[axis] / 2, b.centre[axis] - b.size[axis] / 2)
        high = min(a.centre[axis] + a.size[axis] / 2, b.centre[axis] + b.size[axis] / 2)
        if high - low <= 1e-9:
            return False
    return True


@pytest.mark.parametrize("panel_gap", [1.5, 0.0])
def test_no_two_bars_overlap(panel_gap):
    # d 0..2, p 0..3, q 0..3 is 3 * 16 = 48 fits. The fit fails whenever p + q is a multiple of 5;
    # with p, q in 0..3 that is (0, 0), (2, 3) and (3, 2): 3 failures per d, 9 in all, 39 bars.
    grid = [
        {"d": d, "p": p, "q": q, "aic": None if (p + q) % 5 == 0 else 1000.0 + 7 * d + 3 * p + q}
        for d in range(3)
        for p in range(4)
        for q in range(4)
    ]
    bars = layout.aic_bars(grid, panel_gap=panel_gap)
    assert len(bars) == 3 * (16 - 3)
    assert bars.skipped == 9
    for i, a in enumerate(bars):
        for b in bars[i + 1 :]:
            assert not overlaps(a, b), (a, b)


def test_a_d_whose_fits_all_failed_keeps_its_slot():
    # d = 0 has no usable fit, so it gets no bars but is still counted, and d = 1 stays in the
    # second slot: x = stride + p = 3.3 + p (stride = (1 - 0) * 1.0 + 0.8 + 1.5 = 3.3).
    grid = [
        {"d": 0, "p": 0, "q": 0, "aic": None},
        {"d": 0, "p": 1, "q": 0, "aic": None},
        {"d": 1, "p": 0, "q": 0, "aic": 10.0},
        {"d": 1, "p": 1, "q": 0, "aic": 12.0},
    ]
    bars = layout.aic_bars(grid, **OPTIONS)
    assert [(b.d, b.p) for b in bars] == [(1, 0), (1, 1)]
    assert [b.centre[0] for b in bars] == pytest.approx([3.3, 4.3])
    assert [b.size[2] for b in bars] == pytest.approx([0.0, 1.0])  # relative 0 and 2, times 0.5
    assert bars.skipped_by_d == {0: 2, 1: 0}
    assert bars.skipped == 2


def test_base_height_lifts_every_bar_including_the_best():
    # aic 10 and 14 -> relative 0 and 4 -> heights 0.25 + 0 and 0.25 + 4 * 0.5 = 2.25.
    grid = [
        {"d": 0, "p": 0, "q": 0, "aic": 10.0},
        {"d": 0, "p": 1, "q": 0, "aic": 14.0},
    ]
    bars = layout.aic_bars(grid, base_height=0.25, **OPTIONS)
    assert [b.size[2] for b in bars] == pytest.approx([0.25, 2.25])
    assert [b.centre[2] for b in bars] == pytest.approx([0.125, 1.125])


def test_each_d_panel_gets_its_own_palette_colour():
    # d = 0 is the first panel: palette slot 1 blue #2a78d6 = (42, 120, 214); d = 1: slot 2 orange
    # #eb6834 = (235, 104, 52).
    bars = by_key(layout.aic_bars(GRID, **OPTIONS))
    assert bars[(0, 0, 0)].colour == pytest.approx((42 / 255, 120 / 255, 214 / 255))
    assert bars[(1, 0, 0)].colour == pytest.approx((235 / 255, 104 / 255, 52 / 255))


def test_the_result_is_a_list_and_an_empty_grid_is_fine():
    bars = layout.aic_bars(GRID, **OPTIONS)
    assert isinstance(bars, list)
    empty = layout.aic_bars([])
    assert empty == [] and empty.skipped == 0


ROW = {"d": 0, "p": 0, "q": 0, "aic": 1.0}


@pytest.mark.parametrize(
    "grid, options, message",
    [
        # the same (d, p, q) twice
        ([ROW, {**ROW, "aic": 2.0}], {}, "duplicate"),
        # aic must be a finite number or None: JSON uses null, never NaN
        ([{**ROW, "aic": math.nan}], {}, "finite number or None"),
        ([{**ROW, "aic": math.inf}], {}, "finite number or None"),
        ([{**ROW, "aic": "12.5"}], {}, "finite number or None"),
        # missing key / wrong types
        ([{"d": 0, "p": 0, "aic": 1.0}], {}, "expected keys"),
        (["not a row"], {}, "expected keys"),
        ([{**ROW, "d": 0.0}], {}, "d must be an int"),
        ([{**ROW, "d": True}], {}, "d must be an int"),
        # bad layout options. NaN slips past `footprint > pitch` (every comparison with NaN is
        # False), and pitch = 0 trips that comparison too, so only the message tells which check
        # ran.
        ([ROW], dict(pitch=0), "pitch must be"),
        ([ROW], dict(pitch=math.nan), "pitch must be"),
        ([ROW], dict(footprint=1.2, pitch=1.0), "must not exceed"),  # bars would overlap
        ([ROW], dict(panel_gap=-1.0), "panel_gap must be"),
        ([ROW], dict(height_per_aic=0), "height_per_aic must be"),
        ([ROW], dict(base_height=-0.1), "base_height must be"),
    ],
)
def test_aic_bars_input_validation(grid, options, message):
    with pytest.raises(ValueError, match=message):
        layout.aic_bars(grid, **options)


# ---------------------------------------------------------------------------------------------
# hero_architecture.py --dry-run, run as a real subprocess
# ---------------------------------------------------------------------------------------------

SLAB_LINE = re.compile(
    r"^slab (?P<i>\d+)/5 (?P<name>\w+) centre=\((?P<x>[-\d.]+), (?P<y>[-\d.]+), (?P<z>[-\d.]+)\)",
    re.MULTILINE,
)


def run_hero(tmp_path, *args, poison: str):
    """Run hero_architecture.py with the interpreter that runs pytest (the uv-managed one).

    `poison` is the content of a fake bpy.py placed first on PYTHONPATH, so a stray `import bpy`
    does something observable. The working directory is elsewhere on purpose.
    """
    fake = tmp_path / "fake_bpy"
    fake.mkdir(exist_ok=True)
    (fake / "bpy.py").write_text(poison, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(fake)}
    return subprocess.run(
        [sys.executable, str(HERO), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


# Importing this would blow up loudly: --dry-run must never get that far.
BPY_EXPLODES = "raise RuntimeError('bpy was imported')\n"
# Importing this fails the way a missing bpy does.
BPY_MISSING = "raise ImportError('no bpy here')\n"


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory):
    return run_hero(tmp_path_factory.mktemp("dry"), "--dry-run", poison=BPY_EXPLODES)


def test_dry_run_succeeds_without_importing_bpy(dry_run):
    assert dry_run.returncode == 0, dry_run.stderr
    assert "Traceback" not in dry_run.stderr


def test_dry_run_prints_the_five_slabs_bottom_to_top(dry_run):
    lines = SLAB_LINE.findall(dry_run.stdout)
    assert [int(i) for i, *_ in lines] == [1, 2, 3, 4, 5]
    assert [name for _, name, *_ in lines] == [
        "source",
        "raw_cache",
        "python_core",
        "delivery",
        "app",
    ]
    heights = [float(z) for *_, z in lines]
    assert heights == sorted(heights) and len(set(heights)) == 5
    assert "5 slabs" in dry_run.stdout.splitlines()[0]


def test_dry_run_reports_the_camera_and_the_output_file_under_the_repo_root(dry_run):
    # The subprocess ran from a temp directory, so this also proves the path is anchored to the
    # repo root and not to the working directory.
    assert re.search(r"^camera location=\(.*\) look_at=\(.*\)", dry_run.stdout, re.MULTILINE)
    expected = REPO / "docs" / "images" / "hero_architecture.png"
    assert f"output: {expected}" in dry_run.stdout.splitlines()


def test_flags_after_a_double_dash_reach_the_script(tmp_path):
    # `blender ... --python file -- --dry-run` hands the flags over after "--".
    result = run_hero(tmp_path, "--", "--dry-run", poison=BPY_EXPLODES)
    assert result.returncode == 0, result.stderr
    assert len(SLAB_LINE.findall(result.stdout)) == 5


def test_out_flag_changes_the_reported_output_file(tmp_path):
    target = tmp_path / "elsewhere.png"
    result = run_hero(tmp_path, "--dry-run", "--out", str(target), poison=BPY_EXPLODES)
    assert f"output: {target}" in result.stdout.splitlines()


def test_rendering_without_bpy_fails_cleanly(tmp_path):
    result = run_hero(tmp_path, poison=BPY_MISSING)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "--dry-run" in result.stderr  # tells the reader what to do instead


# ---------------------------------------------------------------------------------------------
# hero_architecture.py inside a pretend Blender: bad flags and --help must not end the session
# ---------------------------------------------------------------------------------------------

STILL_OPEN = "BLENDER SESSION STILL OPEN"

# What Blender does before it runs `--python file`: bpy is already imported, and sys.argv is
# Blender's own command line with the script's flags after "--". Reaching the last line means
# nothing called sys.exit.
FAKE_BLENDER_DRIVER = f"""\
import runpy
import sys

import bpy  # the fake one from fake_bpy/: from here on "bpy" is in sys.modules, as in Blender

sys.argv = ["blender", "--python", {str(HERO)!r}, "--", *sys.argv[1:]]
runpy.run_path({str(HERO)!r}, run_name="__main__")
print({STILL_OPEN!r})
"""


# The same pretend Blender, but the script is loaded under another name (it still runs once, since
# Blender started it) and then main() is called directly, to see the status it hands back.
FAKE_BLENDER_CALLS_MAIN = f"""\
import runpy
import sys

import bpy

sys.argv = ["blender", "--", "--dry-run"]
namespace = runpy.run_path({str(HERO)!r}, run_name="hero_architecture")
for flags in (["--bogus"], ["--help"]):
    print("main returned", namespace["main"](["blender", "--", *flags]))
"""


def run_in_fake_blender(tmp_path, *flags, background: bool, driver_source: str = FAKE_BLENDER_DRIVER):
    """Run hero_architecture.py the way Blender would, with a fake bpy whose app.background is
    `background`. The fake has nothing else on it: these runs must not get as far as rendering."""
    fake = tmp_path / "fake_bpy"
    fake.mkdir(exist_ok=True)
    (fake / "bpy.py").write_text(f"class app:\n    background = {background}\n", encoding="utf-8")
    driver = tmp_path / "fake_blender_driver.py"
    driver.write_text(driver_source, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(fake)}
    return subprocess.run(
        [sys.executable, str(driver), *flags],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("background", [False, True], ids=["windowed", "background"])
def test_the_pretend_blender_runs_a_dry_run_to_the_end(tmp_path, background):
    # The control for the tests below: it shows the harness really starts the script as Blender
    # would (a dry run prints the layout and returns), so what the other runs show is the script's.
    result = run_in_fake_blender(tmp_path, "--dry-run", background=background)
    assert result.returncode == 0, result.stderr
    assert len(SLAB_LINE.findall(result.stdout)) == 5
    assert STILL_OPEN in result.stdout


@pytest.mark.parametrize(
    "flags, message",
    [
        (["--bogus"], "unrecognized arguments: --bogus"),
        (["--out"], "expected one argument"),
        (["--engine"], "expected one argument"),
    ],
    ids=["unknown-flag", "missing-value-out", "missing-value-engine"],
)
def test_a_flag_error_in_a_windowed_blender_prints_the_message_and_keeps_the_session(
    tmp_path, flags, message
):
    result = run_in_fake_blender(tmp_path, *flags, background=False)
    assert STILL_OPEN in result.stdout  # nothing exited the interpreter
    assert result.returncode == 0
    assert message in result.stderr  # argparse's own message reached the console
    assert "usage:" in result.stderr
    assert "Traceback" not in result.stderr


def test_help_in_a_windowed_blender_prints_the_usage_and_keeps_the_session(tmp_path):
    result = run_in_fake_blender(tmp_path, "--help", background=False)
    assert STILL_OPEN in result.stdout.splitlines()[-1]
    assert result.returncode == 0
    assert "usage: hero_architecture.py" in result.stdout
    assert "--dry-run" in result.stdout
    assert "Traceback" not in result.stderr


def test_main_hands_back_the_status_argparse_chose_in_a_windowed_blender(tmp_path):
    # 2 for a usage error, 0 for --help: the same numbers argparse would have exited with.
    result = run_in_fake_blender(tmp_path, background=False, driver_source=FAKE_BLENDER_CALLS_MAIN)
    assert result.returncode == 0, result.stderr
    assert [line for line in result.stdout.splitlines() if line.startswith("main returned")] == [
        "main returned 2",
        "main returned 0",
    ]


def test_a_flag_error_in_a_background_blender_still_fails_the_shell_command(tmp_path):
    # `blender --background` must exit non-zero so that a script or CI step notices.
    result = run_in_fake_blender(tmp_path, "--bogus", background=True)
    assert result.returncode == 2
    assert STILL_OPEN not in result.stdout
    assert "unrecognized arguments: --bogus" in result.stderr


def test_help_in_a_background_blender_exits_cleanly(tmp_path):
    result = run_in_fake_blender(tmp_path, "--help", background=True)
    assert result.returncode == 0
    assert STILL_OPEN not in result.stdout
    assert "usage: hero_architecture.py" in result.stdout


def test_a_flag_error_under_plain_python_exits_with_status_2(tmp_path):
    result = run_hero(tmp_path, "--bogus", poison=BPY_EXPLODES)
    assert result.returncode == 2
    assert "unrecognized arguments: --bogus" in result.stderr
