"""Render the milestone-0 hero image: the five architecture layers as a stack of rounded slabs.

Three ways to run it (details in tools/blender/README.md):

    uv run python tools/blender/hero_architecture.py --dry-run     # no Blender: print the layout
    blender --background --python tools/blender/hero_architecture.py [-- flags]
    # or paste/exec this file through the Blender MCP's execute_blender_code

Writes docs/images/hero_architecture.png (relative to the repo root) unless --out says otherwise.

STATUS: written on 2026-10-28 without a reachable Blender. layout.py (every number below) is
unit-tested; the bpy calls in this file have never been executed. Treat the first real run as the
test, and check the "after the first render" list in the README.

All geometry comes from layout.py. This file only turns those numbers into Blender objects, and it
follows the rules for running in someone else's Blender: shader nodes are found by type, enum
identifiers are read from bl_rna (or assigned inside try/except TypeError), and material colours go
on the shader node inputs.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

# True when Blender started us: it has imported bpy before running any script. Read before this
# file imports bpy itself, and never re-evaluated.
IN_BLENDER = "bpy" in sys.modules

# Set by _load_bpy(). They stay None for --dry-run, so that path never touches Blender at all.
bpy = None
bmesh = None


def _here() -> Path:
    """The folder this file lives in. When exec'd, needs __file__ or ARIMA_REPO_ROOT to be set."""
    if "__file__" in globals():
        return Path(__file__).resolve().parent
    root = os.environ.get("ARIMA_REPO_ROOT")
    if root:
        return Path(root) / "tools" / "blender"
    raise RuntimeError(
        "cannot find tools/blender: __file__ is not set (the code was pasted, not exec'd from the "
        "file). Exec the file with {'__file__': path} in its globals, or set ARIMA_REPO_ROOT."
    )


HERE = _here()
REPO_ROOT = HERE.parent.parent
DEFAULT_OUT = REPO_ROOT / "docs" / "images" / "hero_architecture.png"

# layout.py sits next to this file. Drop any copy a long-lived Blender session imported earlier,
# so an edited layout.py is picked up on the next run.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.modules.pop("layout", None)
import layout  # noqa: E402

# ----------------------------------------------------------------------------------------------
# Scene constants. Everything is in Blender units.
# ----------------------------------------------------------------------------------------------

N_LAYERS = 5
SLAB_HEIGHT = 0.4
GAP = 0.1
WIDTH = 4.4
DEPTH = 2.4
BEVEL_RADIUS = 0.06  # how round the slab edges are; must stay under half the slab height
BEVEL_SEGMENTS = 4

LABEL_SIZE_RATIO = 0.42  # label text height as a fraction of the slab height
LABEL_FILL = 0.92  # a label is shrunk to fit within this fraction of the slab width
LABEL_OFFSET = 0.005  # how far in front of the slab face the text floats, against z-fighting

RESOLUTION = (1600, 1000)
FOV_DEG = 35.0  # field of view along the LONGER image side (Blender's "auto" sensor fit)
MARGIN = 1.1  # see layout.camera_for: anything above 1 / cos(fov / 2) contains every corner
SAMPLES = 64

# Lighting. Not calibrated against a real render: adjust after the first one.
WORLD_STRENGTH = 0.5  # even ambient light from a near-white sky
KEY_DIRECTION = (-0.7, -0.6, 1.0)  # key light sits above, left of and in front of the stack
KEY_WATTS_PER_UNIT2 = 30.0  # key power grows with distance squared, so exposure is scale-free
KEY_SIZE_RATIO = 0.7  # area light edge as a fraction of the stack's diagonal: bigger = softer

ENGINE_PREFERENCE = ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES")

PREFIX = "arima_hero_"  # every datablock this script creates starts with this
COLLECTION_NAME = PREFIX + "architecture"


# ----------------------------------------------------------------------------------------------
# Plain-Python side: arguments, layout, dry run
# ----------------------------------------------------------------------------------------------


def script_argv(argv: list[str]) -> list[str]:
    """The part of argv that belongs to this script.

    Everything after "--" always does (that is how `blender ... -- flags` passes flags through).
    Without "--": inside Blender, argv is Blender's own command line, so none of it is ours; under
    plain Python, it is argv[1:].
    """
    if "--" in argv:
        return list(argv[argv.index("--") + 1 :])
    if IN_BLENDER:
        return []
    return list(argv[1:])


def _windowed_blender() -> bool:
    """True inside a Blender that has a window. Exiting one of those would close the session.

    Reads bpy from sys.modules, not from this file's `bpy` variable: that one stays None until
    _load_bpy() runs, which is after the arguments are parsed.
    """
    return IN_BLENDER and not sys.modules["bpy"].app.background


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hero_architecture.py",
        description="Render the milestone-0 architecture hero image with Blender.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the computed layout and exit; does not import bpy",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="PNG to write (default: docs/images/hero_architecture.png in this repo)",
    )
    parser.add_argument(
        "--factory-reset",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "start from Blender's empty factory scene (read_factory_settings(use_empty=True)). "
            "Default: yes when Blender runs in the background, no when it has a window (then only "
            "the objects this script created earlier are replaced). Never use it on a scene you "
            "want to keep."
        ),
    )
    parser.add_argument(
        "--engine",
        metavar="NAME",
        help="render engine to try first, e.g. CYCLES on a machine without a GPU for EEVEE",
    )
    return parser.parse_args(argv)


def build_layout():
    """(slabs, camera_location, look_at) for the milestone-0 scene."""
    slabs = layout.architecture_slabs(
        N_LAYERS, slab_height=SLAB_HEIGHT, gap=GAP, width=WIDTH, depth=DEPTH
    )
    # The camera angle is set for the longer image side; frame by the shorter one.
    fov = layout.limiting_fov_deg(FOV_DEG, *RESOLUTION)
    location, look_at = layout.camera_for(slabs, fov_deg=fov, margin=MARGIN)
    return slabs, location, look_at


def _fmt(v) -> str:
    return "(" + ", ".join(f"{c:.3f}" for c in v) + ")"


def describe(slabs, location, look_at, out: Path) -> str:
    """The dry-run report: one 'slab' line per slab, then the camera, then the output file."""
    lines = [f"hero_architecture dry run: {len(slabs)} slabs, no Blender involved"]
    for i, s in enumerate(slabs, start=1):
        lines.append(
            f"slab {i}/{len(slabs)} {s.name} centre={_fmt(s.centre)} size={_fmt(s.size)} "
            f"rgb={_fmt(s.colour)} label={s.label!r}"
        )
    lines.append(f"camera location={_fmt(location)} look_at={_fmt(look_at)} fov_deg={FOV_DEG}")
    lines.append(f"output: {out}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------
# Blender side. Nothing below runs unless bpy was imported.
# ----------------------------------------------------------------------------------------------


def _load_bpy() -> bool:
    global bpy, bmesh
    try:
        import bmesh as _bmesh
        import bpy as _bpy
    except ImportError:
        return False
    bpy, bmesh = _bpy, _bmesh
    return True


def pick_enum(struct, prop: str, *preferred: str, required: bool = True):
    """The first of `preferred` that this Blender's enum really has, read from bl_rna.

    `struct` is an RNA instance or class. With required=False, returns None instead of raising.
    """
    rna_prop = struct.bl_rna.properties.get(prop)
    available = [item.identifier for item in rna_prop.enum_items] if rna_prop else []
    for identifier in preferred:
        if identifier in available:
            return identifier
    if required:
        raise RuntimeError(f"{struct}.{prop}: none of {preferred} exists; available: {available}")
    return None


def choose_engine(scene, first: str | None = None) -> str:
    """Set scene.render.engine to the first engine this Blender accepts and return its identifier.

    Assigning an unknown identifier raises TypeError, so each candidate is simply tried in turn.
    """
    candidates = ((first,) if first else ()) + ENGINE_PREFERENCE
    for engine in candidates:
        try:
            scene.render.engine = engine
            return engine
        except TypeError:
            continue
    raise RuntimeError(f"none of {candidates} is a render engine in this Blender")


def _ensure_node_tree(block) -> None:
    # Older Blenders create the node tree lazily; newer ones may always have one.
    if block.node_tree is None:
        block.use_nodes = True


def _find_node(tree, node_type: str):
    """A node by its `type` (e.g. "BSDF_PRINCIPLED"), never by name: names are localised."""
    return next((n for n in tree.nodes if n.type == node_type), None)


def make_material(name: str, srgb, *, roughness: float):
    mat = bpy.data.materials.new(PREFIX + name)
    _ensure_node_tree(mat)
    tree = mat.node_tree
    bsdf = _find_node(tree, "BSDF_PRINCIPLED")
    if bsdf is None:
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        output = _find_node(tree, "OUTPUT_MATERIAL") or tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(bsdf.outputs[0], output.inputs[0])
    r, g, b = layout.srgb_to_linear(srgb)
    # The colour that renders lives on the shader node input...
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    # ...diffuse_color only tints the viewport's solid mode; set it so the two agree.
    mat.diffuse_color = (r, g, b, 1.0)
    return mat


def build_world(scene) -> None:
    world = bpy.data.worlds.new(PREFIX + "world")
    _ensure_node_tree(world)
    tree = world.node_tree
    background = _find_node(tree, "BACKGROUND")
    if background is None:
        background = tree.nodes.new("ShaderNodeBackground")
        output = _find_node(tree, "OUTPUT_WORLD") or tree.nodes.new("ShaderNodeOutputWorld")
        tree.links.new(background.outputs[0], output.inputs[0])
    r, g, b = layout.srgb_to_linear(layout.hex_to_rgb(layout.SURFACE_HEX))
    background.inputs["Color"].default_value = (r, g, b, 1.0)
    background.inputs["Strength"].default_value = WORLD_STRENGTH
    scene.world = world


def _move_to_collection(obj, collection) -> None:
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)


# Cube corners, indexed ix + 2 * iy + 4 * iz with each i in {0, 1} (0 = low side, 1 = high side).
# Each face lists four corners that share one coordinate, in ring order. The winding is left to
# recalc_face_normals.
_BOX_FACES = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))


def make_slab(slab, collection, material):
    """A box of slab.size centred on slab.centre, with a bevel modifier for the rounded edges.

    The box is built from vertices directly (not a primitive operator), so the bevel width is in
    real units and the object keeps scale 1.
    """
    w, d, h = slab.size
    mesh = bpy.data.meshes.new(PREFIX + slab.name)
    bm = bmesh.new()
    verts = [
        bm.verts.new(((ix - 0.5) * w, (iy - 0.5) * d, (iz - 0.5) * h))
        for iz in (0, 1)
        for iy in (0, 1)
        for ix in (0, 1)
    ]
    for face in _BOX_FACES:
        bm.faces.new([verts[i] for i in face])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(PREFIX + slab.name, mesh)
    obj.location = slab.centre
    collection.objects.link(obj)
    mesh.materials.append(material)

    modifier = obj.modifiers.new("Bevel", pick_enum(bpy.types.Modifier, "type", "BEVEL"))
    modifier.width = min(BEVEL_RADIUS, 0.45 * min(w, d, h))
    modifier.segments = BEVEL_SEGMENTS

    # Cosmetic: smooth shading with weighted normals keeps big faces flat and the bevel round.
    # Not worth failing the render over, and the relevant API changed between Blender versions.
    try:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        if hasattr(mesh, "use_auto_smooth"):  # removed in Blender 4.1
            mesh.use_auto_smooth = True
        weighted = obj.modifiers.new(
            "WeightedNormal", pick_enum(bpy.types.Modifier, "type", "WEIGHTED_NORMAL")
        )
        weighted.keep_sharp = True
    except Exception as exc:  # noqa: BLE001
        print(f"note: skipped normal smoothing on {obj.name}: {exc}")
    return obj


def make_label(slab, collection, material):
    """The slab's label as flat text standing on its front (-Y) face, facing the camera."""
    w, d, h = slab.size
    x, y, z = slab.centre
    location = (x, y - d / 2 - LABEL_OFFSET, z)
    rotation = (math.pi / 2, 0.0, 0.0)  # +90 degrees about X: text stands up, faces -Y
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.location = location
    obj.rotation_euler = rotation
    obj.name = PREFIX + "label_" + slab.name

    text = obj.data
    text.name = obj.name
    text.body = slab.label
    text.size = LABEL_SIZE_RATIO * h
    for prop in ("align_x", "align_y"):
        centre = pick_enum(text, prop, "CENTER", required=False)
        if centre:
            setattr(text, prop, centre)
    text.materials.append(material)
    _move_to_collection(obj, collection)

    # Long labels would run off the slab: shrink until they fit. Width scales with size.
    bpy.context.view_layer.update()
    limit = LABEL_FILL * w
    if obj.dimensions.x > limit:
        text.size *= limit / obj.dimensions.x
    return obj


def make_camera(scene, collection, location, look_at):
    data = bpy.data.cameras.new(PREFIX + "camera")
    data.angle = math.radians(FOV_DEG)  # applies to the longer image side (auto sensor fit)
    data.clip_end = max(100.0, 10 * math.dist(location, look_at))
    obj = bpy.data.objects.new(PREFIX + "camera", data)
    obj.location = location
    obj.rotation_euler = layout.aim_euler(location, look_at)
    collection.objects.link(obj)
    scene.camera = obj
    return obj


def make_key_light(collection, look_at, camera_distance, extent):
    data = bpy.data.lights.new(PREFIX + "key", pick_enum(bpy.types.Light, "type", "AREA"))
    distance = 0.9 * camera_distance
    ux, uy, uz = KEY_DIRECTION
    norm = math.sqrt(ux * ux + uy * uy + uz * uz)
    location = tuple(look_at[a] + (ux, uy, uz)[a] / norm * distance for a in range(3))
    data.energy = KEY_WATTS_PER_UNIT2 * distance**2
    data.size = KEY_SIZE_RATIO * extent
    obj = bpy.data.objects.new(PREFIX + "key", data)
    obj.location = location
    obj.rotation_euler = layout.aim_euler(location, look_at)  # lights also shine along local -Z
    collection.objects.link(obj)
    return obj


def clear_previous() -> None:
    """Remove what an earlier run of this script left behind, and nothing else."""
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is not None:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)
    # Their data is orphaned now (users == 0); the world may be too if a run was interrupted.
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.materials,
        bpy.data.worlds,
    ):
        for block in list(datablocks):
            if block.name.startswith(PREFIX) and block.users == 0:
                datablocks.remove(block)


def _snapshot(scene) -> list:
    """The scene settings this script changes, so a run in someone's own scene can undo them."""
    render = scene.render
    targets = (
        (scene, "camera"),
        (scene, "world"),
        (render, "engine"),
        (render, "resolution_x"),
        (render, "resolution_y"),
        (render, "resolution_percentage"),
        (render, "filepath"),
        (render, "film_transparent"),
        (render.image_settings, "file_format"),  # before color_mode: it can reset it
        (render.image_settings, "color_mode"),
        (scene.view_settings, "view_transform"),
    )
    return [(target, attr, getattr(target, attr)) for target, attr in targets]


def _restore(saved: list) -> None:
    for target, attr, value in saved:
        try:
            setattr(target, attr, value)
        except (TypeError, AttributeError, ValueError) as exc:
            print(f"note: could not restore {attr}: {exc}")


def configure_render(scene, out: Path, engine_first: str | None) -> str:
    render = scene.render
    engine = choose_engine(scene, engine_first)
    render.resolution_x, render.resolution_y = RESOLUTION
    render.resolution_percentage = 100
    render.filepath = str(out)
    # A transparent background works on GitHub's light and dark themes alike.
    render.film_transparent = True
    image = render.image_settings
    image.file_format = pick_enum(image, "file_format", "PNG")
    image.color_mode = pick_enum(image, "color_mode", "RGBA")
    # The default view transform (Filmic/AgX) would shift the palette; keep the colours as chosen.
    # A dynamic enum, so assign inside try/except TypeError rather than reading its items.
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        print("note: no 'Standard' view transform; colours will be tone-mapped")
    for owner_name, attr in (("eevee", "taa_render_samples"), ("cycles", "samples")):
        owner = getattr(scene, owner_name, None)
        if owner is not None and hasattr(owner, attr):
            setattr(owner, attr, SAMPLES)
    return engine


def render_hero(args: argparse.Namespace, slabs, camera_location, look_at) -> None:
    factory = args.factory_reset if args.factory_reset is not None else bpy.app.background
    if factory:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    saved = None if factory else _snapshot(scene)
    if not factory:
        clear_previous()

    try:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        scene.collection.children.link(collection)

        for slab in slabs:
            make_slab(slab, collection, make_material(slab.name, slab.colour, roughness=0.35))
        ink = make_material("ink", layout.hex_to_rgb(layout.INK_HEX), roughness=0.6)
        for slab in slabs:
            make_label(slab, collection, ink)

        make_camera(scene, collection, camera_location, look_at)
        make_key_light(
            collection,
            look_at,
            camera_distance=math.dist(camera_location, look_at),
            extent=layout.stack_extent(slabs),
        )
        build_world(scene)
        engine = configure_render(scene, args.out, args.engine)

        args.out.parent.mkdir(parents=True, exist_ok=True)
        print(f"rendering {args.out} with {engine} at {RESOLUTION[0]}x{RESOLUTION[1]} ...")
        bpy.ops.render.render(write_still=True)
    finally:
        if saved is not None:
            _restore(saved)

    if not args.out.exists():
        raise RuntimeError(f"render finished but {args.out} was not written")
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes)")


# ----------------------------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(script_argv(sys.argv if argv is None else argv))
    except SystemExit as stop:
        # argparse ends a bad command line (status 2) and --help (status 0) with sys.exit, after
        # printing the usage error or the help text itself. That is right for plain Python and for
        # `blender --background`, where the status reaches the shell. In a Blender with a window it
        # would close the user's session, so there the message stays on the console and we return
        # the status like any other result.
        if not _windowed_blender():
            raise
        return int(stop.code or 0)
    slabs, camera_location, look_at = build_layout()

    if args.dry_run:
        print(describe(slabs, camera_location, look_at, args.out))
        return 0

    if not _load_bpy():
        print(
            "error: cannot import bpy, so there is nothing to render with. Run this file inside "
            "Blender (see tools/blender/README.md), or pass --dry-run to print the layout.",
            file=sys.stderr,
        )
        return 2
    render_hero(args, slabs, camera_location, look_at)
    return 0


def _run() -> None:
    status = main()
    # Exit codes matter for `blender --background` (a non-zero code fails the shell command), but
    # never exit a Blender that has a window: that would close the user's session.
    if status and not _windowed_blender():
        sys.exit(status)


# `blender --python file.py` and plain `python file.py` set __name__ to "__main__". The Blender MCP
# may exec the code in a namespace that does not, so also run whenever Blender started us.
if __name__ == "__main__" or IN_BLENDER:
    _run()
