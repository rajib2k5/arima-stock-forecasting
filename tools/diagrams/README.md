# Diagram kit

This folder is a vendored copy of the author's vol-diagram-kit: the `diagram_kit/` package and `build.py`.
It was copied from kit commit `7493b4b`. Do not edit it here; copy a newer commit over it instead.

The specs are in `docs/architecture/specs/`. The generated files are in `docs/architecture/out/`.
To rebuild them, run `uv run --group diagrams python tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out`.
To check that they are current, add `--check --no-png`.
The kit refuses to overwrite files it did not write, so never point `--out` at `docs/architecture/` itself.
