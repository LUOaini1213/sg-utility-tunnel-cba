"""README provenance, CI workflow and repository hygiene."""
import json
import re
import subprocess
import sys

import pytest
import yaml

from cstcba import run
from scripts import build_readme

ROOT = build_readme.ROOT
NUM = re.compile(r"(?<![A-Za-z0-9_.$])-?\d+(?:\.\d+)?%?")


def _leaves(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _leaves(v)
    elif isinstance(x, list):
        for v in x:
            yield from _leaves(v)
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        yield x


def allowed_numbers(results: dict) -> set[str]:
    ok = set()
    for data in results.values():
        for v in _leaves(data):
            for d in range(0, 5):
                ok.add(f"{v:.{d}f}")
                ok.add(f"{v * 100:.{d}f}%")
            ok.add(f"{v:g}")
    return ok


def readme_numbers(text: str) -> list[str]:
    body = re.sub(r"```.*?```", "", text, flags=re.S)   # reproduce commands
    body = re.sub(r"\([^)]*\.md\)|\(LICENSE\)", "", body)  # link targets
    return NUM.findall(body)


def test_every_readme_number_comes_from_results():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    ok = allowed_numbers(build_readme.load_results())
    bad = [n for n in readme_numbers(text) if n not in ok]
    assert not bad, f"README numbers not in results/*.json: {bad}"


def test_number_check_catches_a_planted_number():
    ok = allowed_numbers(build_readme.load_results())
    assert [n for n in readme_numbers("NPV was 123456.7 per km") if n not in ok] == ["123456.7"]


def test_template_has_no_literal_numbers():
    text = (ROOT / "docs" / "README.template.md").read_text(encoding="utf-8")
    stripped = re.sub(r"\{\{[^}]+\}\}", "", text)
    assert readme_numbers(stripped) == []


def test_readme_is_fresh():
    assert build_readme.render() == (ROOT / "README.md").read_text(encoding="utf-8")


def test_ci_yaml_parses_and_is_offline():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["test"]["steps"]
    runs = " ".join(s.get("run", "") for s in steps)
    assert "pytest" in runs and "build_readme.py --check" in runs
    assert "curl" not in runs and "wget" not in runs


def _tracked_text_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    files = out.stdout.split() if out.returncode == 0 and out.stdout.strip() else [
        str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
        if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts and "__pycache__" not in p.parts
    ]
    return [ROOT / f for f in files if not f.endswith((".pyc",))]


def test_no_absolute_local_paths():
    users, home = "Us" + "ers", "ho" + "me"
    pat = re.compile(r"[A-Za-z]:[\\/]+" + users + "|/" + users + "/|/" + home + "/[a-z]")
    for f in _tracked_text_files():
        assert not pat.search(f.read_text(encoding="utf-8", errors="ignore")), f


@pytest.mark.golden
def test_results_match_inputs():
    from cstcba import costmodel, schedule
    fresh = run._round(run.cost_results(costmodel.load_inputs()))
    assert json.loads(json.dumps(fresh)) == json.loads((ROOT / "results" / "cost.json").read_text(encoding="utf-8"))
    fresh_s = run._round(run.schedule_results(schedule.load()))
    assert json.loads(json.dumps(fresh_s)) == json.loads((ROOT / "results" / "schedule.json").read_text(encoding="utf-8"))
