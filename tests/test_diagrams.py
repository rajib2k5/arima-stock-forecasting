"""The generated architecture diagrams must be current with their YAML specs.

tools/diagrams/ is a vendored copy of the diagram kit. Its --check mode rebuilds every output from
docs/architecture/specs/ into a temporary folder and compares the bytes with
docs/architecture/out/, so a spec edited without a rebuild fails here.

--no-png leaves the PNG bytes out: they are only verified on aarch64, and CI runners are x86_64.
The .mmd, .svg, .drawio and .lucid.xml files are still compared byte for byte.

The kit's two dependencies (pyyaml, resvg-py) live in the `diagrams` dependency group, which a
plain `uv run pytest` does not install, so the kit runs through `uv run --group diagrams`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "tools" / "diagrams" / "build.py"
SPECS = REPO / "docs" / "architecture" / "specs"
OUT = REPO / "docs" / "architecture" / "out"


def test_the_committed_diagrams_are_current_with_their_specs():
    # A check over zero specs would pass without comparing anything.
    assert sorted(SPECS.glob("*.yaml")), f"no specs in {SPECS}"
    assert shutil.which("uv"), "uv is needed to run the diagram kit (the `diagrams` group)"

    done = subprocess.run(
        [
            "uv", "run", "--group", "diagrams", "python", str(BUILD),
            str(SPECS), "--out", str(OUT), "--check", "--no-png",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, (
        "The diagrams are stale. Rebuild with: uv run --group diagrams python "
        "tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out\n"
        + done.stdout
        + done.stderr
    )
