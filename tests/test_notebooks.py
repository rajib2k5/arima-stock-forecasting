"""Notebook tests. tools/build_notebooks.py is the single source of truth for every notebook;
these tests check that (a) each committed notebook is exactly what the builder produces, and
(b) each notebook actually runs, on a Jupyter kernel that uses this project's virtual environment.

Missing notebooks FAIL these tests. They are never skipped, because a skipped test would let a
deleted notebook pass silently.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

REPO = Path(__file__).resolve().parent.parent
BUILDER = REPO / "tools" / "build_notebooks.py"
NOTEBOOK_DIR = REPO / "notebooks"


def load_builder():
    """Import tools/build_notebooks.py by path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("build_notebooks", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()
NAMES = sorted(builder.NOTEBOOKS)


def test_the_builder_knows_the_project_tour_and_the_milestone_1_notebook():
    assert NAMES == ["00_project_tour.ipynb", "01_data_and_eda.ipynb"]


# --- (a) committed notebooks equal the in-memory build -----------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_committed_notebook_equals_the_builder_output(name):
    path = NOTEBOOK_DIR / name
    assert path.is_file(), f"{path} is missing. Run: uv run python tools/build_notebooks.py"
    expected = builder.render_all()[name]
    assert path.read_text(encoding="utf-8") == expected, (
        f"{path} is stale. Run: uv run python tools/build_notebooks.py"
    )


def test_every_notebook_file_in_the_folder_is_known_to_the_builder():
    # A hand-made notebook that the builder does not know about would escape the sync check.
    on_disk = sorted(p.name for p in NOTEBOOK_DIR.glob("*.ipynb"))
    assert on_disk == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_notebook_build_is_byte_deterministic_and_clean(name):
    text = builder.render_all()[name]
    assert text == builder.render_all()[name]  # same bytes on a second build
    assert text.endswith("}\n") and not text.endswith("\n\n")

    notebook = json.loads(text)
    assert notebook["metadata"] == {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    cell_ids = [cell["id"] for cell in notebook["cells"]]
    # Ids are fixed by position (cell-00, cell-01, ...), not random.
    assert cell_ids == [f"cell-{i:02d}" for i in range(len(cell_ids))]
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None
            assert cell["outputs"] == []


# --- the builder CLI ---------------------------------------------------------------------

def run_builder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *args], capture_output=True, text=True, check=False
    )


def test_cli_check_passes_on_the_committed_notebooks():
    done = run_builder("--check")
    assert done.returncode == 0, done.stdout + done.stderr


def test_cli_write_then_check_then_detect_stale_and_missing(tmp_path):
    folder = tmp_path / "nb"
    target = folder / "00_project_tour.ipynb"

    # Nothing written yet: --check lists the notebook as missing and exits 1.
    done = run_builder("--check", "--notebooks-dir", str(folder))
    assert done.returncode == 1
    assert f"missing: {target}" in done.stdout

    # Write creates the folder and the file; then --check is happy.
    assert run_builder("--notebooks-dir", str(folder)).returncode == 0
    assert target.is_file()
    done = run_builder("--check", "--notebooks-dir", str(folder))
    assert done.returncode == 0, done.stdout

    # One changed byte makes it stale.
    target.write_text(target.read_text() + " ")
    done = run_builder("--check", "--notebooks-dir", str(folder))
    assert done.returncode == 1
    assert f"stale:   {target}" in done.stdout

    # --check never writes: the file is still the edited one.
    assert target.read_text().endswith("\n ")


# --- (b) every notebook runs on a kernel from this venv -----------------------------------

@pytest.fixture
def kernel_name(tmp_path, monkeypatch):
    """Register a throwaway kernelspec that launches THIS interpreter, inside tmp_path.

    We do not use a user-level "python3" kernel: one may exist in ~/.local/share/jupyter and
    point at a different Python that cannot import arima_forecasting. JUPYTER_PATH is searched
    first, so a uniquely named spec in tmp_path always wins, and nothing is installed outside
    the temp folder.
    """
    spec_dir = tmp_path / "jupyter" / "kernels" / "arima-test"
    spec_dir.mkdir(parents=True)
    (spec_dir / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "arima-test",
                "language": "python",
            }
        )
    )
    monkeypatch.setenv("JUPYTER_PATH", str(tmp_path / "jupyter"))
    # Connection files go to the temp folder too, not the user's runtime directory.
    monkeypatch.setenv("JUPYTER_RUNTIME_DIR", str(tmp_path / "runtime"))
    # IPython runs every file in $IPYTHONDIR/profile_default/startup/ when a kernel starts, and
    # reads its profile config from there. An empty folder keeps a developer's own startup files
    # (which may change sys.path or settings) out of the notebooks, so the test result does not
    # depend on whose machine it runs on.
    ipython_dir = tmp_path / "ipython"
    ipython_dir.mkdir()
    monkeypatch.setenv("IPYTHONDIR", str(ipython_dir))
    return "arima-test"


def execute(path: Path, kernel_name: str) -> nbformat.NotebookNode:
    """Run every cell of the notebook at `path` in memory and return the executed copy.

    The file on disk is not touched. Any exception in a cell raises CellExecutionError, which
    fails the test and shows the notebook's own traceback.
    """
    assert path.is_file(), f"{path} is missing. Run: uv run python tools/build_notebooks.py"
    notebook = nbformat.read(path, as_version=4)
    NotebookClient(
        notebook,
        kernel_name=kernel_name,
        timeout=120,
        resources={"metadata": {"path": str(REPO)}},
    ).execute()
    return notebook


DECOY_MARKER = "ARIMA_TEST_DECOY_STARTUP_RAN"
PROBE_CELL = f"import builtins; print('decoy startup ran:', hasattr(builtins, '{DECOY_MARKER}'))"


@pytest.fixture
def users_ipython_dir(tmp_path, monkeypatch):
    """A stand-in for the developer's own IPython folder, announced through IPYTHONDIR.

    It holds a startup file that sets a marker, the way a real user's startup file might put
    something on sys.path or change a setting. Request this fixture BEFORE kernel_name: it plays
    the part of the environment the tests find when they start.
    """
    startup = tmp_path / "users-ipython" / "profile_default" / "startup"
    startup.mkdir(parents=True)
    (startup / "00-decoy.py").write_text(f"import builtins\nbuiltins.{DECOY_MARKER} = True\n")
    monkeypatch.setenv("IPYTHONDIR", str(tmp_path / "users-ipython"))
    return tmp_path / "users-ipython"


def run_probe(kernel_name: str) -> str:
    """Run PROBE_CELL in a fresh kernel and return what it printed."""
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(PROBE_CELL)])
    NotebookClient(notebook, kernel_name=kernel_name, timeout=120).execute()
    return "".join(o.get("text", "") for o in notebook.cells[0].outputs if o.output_type == "stream")


def test_a_startup_file_in_the_ipython_dir_does_run_in_a_kernel(users_ipython_dir, kernel_name, monkeypatch):
    # The control for the next test: without it, "the marker is absent" could mean the decoy never
    # worked. Pointing IPYTHONDIR back at the decoy folder (after the fixture moved it away) must
    # make the marker appear.
    monkeypatch.setenv("IPYTHONDIR", str(users_ipython_dir))
    assert run_probe(kernel_name).strip() == "decoy startup ran: True"


def test_the_test_kernel_ignores_the_users_ipython_startup_files(users_ipython_dir, kernel_name):
    # users_ipython_dir put IPYTHONDIR on the decoy folder before kernel_name ran. kernel_name
    # must have pointed it at an empty folder, so the decoy startup file never runs.
    assert run_probe(kernel_name).strip() == "decoy startup ran: False"


# Notebooks that read the held artifacts (ADR-0001's owner gate: prices.json and eda.json are
# git-ignored, so a fresh clone lacks them). Their execution tests SKIP, with this message, when the
# files are absent; everywhere the files exist, they run.
NEEDS_HELD_DATA = {"01_data_and_eda.ipynb": ("prices", "eda")}


def skip_without_held_data(name: str) -> None:
    absent = [a for a in NEEDS_HELD_DATA.get(name, ()) if not (REPO / "app" / "public" / "data" / f"{a}.json").is_file()]
    if absent:
        pytest.skip(
            f"{name} reads {', '.join(a + '.json' for a in absent)}, which this copy lacks: held by the "
            "owner gate (ADR-0001). Build with: uv run python tools/fetch_prices.py, then "
            "uv run python tools/export_app_data.py"
        )


@pytest.mark.parametrize("name", NAMES)
def test_notebook_runs_without_errors(name, kernel_name):
    skip_without_held_data(name)
    notebook = execute(NOTEBOOK_DIR / name, kernel_name)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert code_cells, "a notebook with no code cells would pass this test without running anything"
    # Every code cell really ran, and none of them produced an error output.
    for cell in code_cells:
        assert cell.execution_count is not None
        assert not [o for o in cell.outputs if o.output_type == "error"]


def test_project_tour_prints_the_values_it_explains(kernel_name):
    # Proof that the cells ran the real package (not just that nothing crashed): the printed
    # output must contain values we know by hand.
    notebook = execute(NOTEBOOK_DIR / "00_project_tour.ipynb", kernel_name)
    printed = "".join(
        output.get("text", "")
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.outputs
        if output.output_type == "stream" and output.name == "stdout"
    )
    assert "arima_forecasting 0.1.0" in printed
    # The explicit override is a fixed path: /mnt/market-data + slug + "raw".
    assert "with override: /mnt/market-data/arima-stock-forecasting/raw" in printed
    # Course window: 3287 days (9 * 365 + 2 leap days); OOS window: 1004 days.
    assert "course: 2015-01-01 -> 2024-01-01 (exclusive), 3287 calendar days" in printed
    assert "   oos: 2024-01-01 -> 2026-10-01 (exclusive), 1004 calendar days" in printed
    # 12:00 at UTC+2 is 10:00 UTC.
    assert '"generated_at": "2026-10-28T10:00:00Z"' in printed
    assert "problems: []" in printed
    # The NaN envelope was refused.
    assert "rejected: Out of range float values are not JSON compliant" in printed


def test_data_and_eda_notebook_prints_the_values_in_the_committed_files(kernel_name):
    # The notebook reads app/public/data; the expected lines are built here from the same files,
    # read independently with json, so the test proves the cells ran the real package on them.
    skip_without_held_data("01_data_and_eda.ipynb")
    notebook = execute(NOTEBOOK_DIR / "01_data_and_eda.ipynb", kernel_name)
    printed = "".join(
        output.get("text", "")
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.outputs
        if output.output_type == "stream" and output.name == "stdout"
    )
    app_data = REPO / "app" / "public" / "data"
    prices = json.loads((app_data / "prices.json").read_text())["data"]
    eda = json.loads((app_data / "eda.json").read_text())["data"]
    assert f"snapshot sha256: {prices['source']['raw_sha256']}" in printed
    assert "      auto_adjust: True" in printed
    # The trap, shown on a hand-built frame, and the guard.
    assert "type of frame['Close']: DataFrame" in printed
    assert "all NaN: True" in printed
    assert "after normalize_download: Series [10.0, 11.0, 12.0]" in printed
    assert "course call raises TypeError:" in printed
    assert ".ffill() gives: [1.0, 1.0, 3.0]" in printed
    for name in ("train", "test", "oos"):
        s = prices["splits"][name]
        assert f"{name:>5}: {s['start']} to {s['end']}, {s['n']} rows" in printed
    course_n = prices["splits"]["train"]["n"] + prices["splits"]["test"]["n"]
    assert f"int({course_n} * 0.9) = {prices['splits']['train']['n']}" in printed
    # The notebook recomputed eda.json from prices.json and got the same object.
    assert "eda.json matches a fresh computation: True" in printed
    assert f"train rows: {eda['summary']['n']} from {eda['summary']['start']}" in printed
    for kde in eda["kdes"]:
        assert f"bandwidth {kde['bandwidth']:.6f}" in printed
    assert "trend undefined for the first 126 and last 126 rows" in printed
    # Every number the tail and decomposition cells print, against the package called here on the
    # same rows (the functions themselves are pinned by hand-worked tests in tests/test_eda.py).
    from arima_forecasting import eda as eda_module
    from arima_forecasting.artifacts import table_from_prices

    table = table_from_prices(prices)
    train = table[table["segment"] == "train"]
    tails = eda_module.tail_share(eda_module.log_returns(train["log_close"]), 3.0)
    assert f"returns beyond 3 sd: {tails['observed']:.2%} observed, {tails['normal']:.2%} under a normal" in printed
    for key, value in eda_module.course_comparison(train).items():
        assert f"{key:>28}: {value:.6g}" in printed, key
