import json
import subprocess
import sys
from pathlib import Path

from unityctl.skills import install_all_skills


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "scripts/eval-skill-triggers.py"
CASES = ROOT / "evals/skill-triggers.json"


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                          text=True, capture_output=True, check=False)


def test_repository_corpus_and_distribution_assets_validate():
    result = run("--check")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["caseCount"] >= 18
    assert set(data["skills"]) == {"unityctl", "unityctl-project-skill-creator"}


def test_blind_export_does_not_include_answer_keys_or_trigger_kind(tmp_path):
    result = run("--export")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert all(set(case) == {"id", "prompt", "explicitSkills"} for case in data["cases"])
    assert all("name" in skill and "description" in skill for skill in data["skills"])
    manual = next(x for x in data["skills"] if x["name"] == "unityctl-project-skill-creator")
    assert manual["autoInvocable"] is False


def test_score_reports_good_missing_and_unwanted_picks(tmp_path):
    cases = json.loads(CASES.read_text())
    answers = {case["id"]: case["expected"] for case in cases}
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers))
    result = run("--score", path)
    assert result.returncode == 0, result.stderr
    score = json.loads(result.stdout)
    assert score["passed"] == len(cases) and score["precision"] == score["recall"] == 1.0
    case = next(x for x in cases if x["kind"] == "should" and x["expected"] == ["unityctl"])
    answers[case["id"]] = ["unityctl-project-skill-creator"]
    path.write_text(json.dumps(answers))
    result = run("--score", path)
    assert result.returncode == 1
    score = json.loads(result.stdout)
    failed, = score["failures"]
    assert failed["missing"] == ["unityctl"]
    assert failed["unexpected"] == failed["disallowed"] == ["unityctl-project-skill-creator"]


def test_score_rejects_incomplete_answers_as_bad_input(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text("{}")
    result = run("--score", path)
    assert result.returncode == 2
    assert "missing" in result.stderr


def test_validates_real_installed_skill_metadata_and_links(tmp_path):
    install_all_skills(tmp_path, "0.3.0", overwrite=False)
    assert run("--assets", tmp_path, "--check").returncode == 0
    entry = tmp_path / "unityctl" / "SKILL.md"
    with entry.open("a", encoding="utf-8") as stream:
        stream.write("\n[broken](references/not-present.md)\n")
    result = run("--assets", tmp_path, "--check")
    assert result.returncode == 2
    assert "not-present.md" in result.stderr


def test_dataset_rejects_disabled_skill_possibly_selected_without_invocation(tmp_path):
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    case = next(x for x in cases if x["kind"] == "should" and x["explicitSkills"])
    case["prompt"] = case["prompt"].split(" ", 1)[1]
    case["explicitSkills"] = []
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    result = run("--cases", path, "--check")
    assert result.returncode == 2
    assert "violates invocation policy" in result.stderr


def test_score_rejects_duplicate_case_id_in_json(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text('{"zh01": [], "zh01": ["unityctl"]}')
    result = run("--score", path)
    assert result.returncode == 2
    assert "duplicate JSON key: zh01" in result.stderr
