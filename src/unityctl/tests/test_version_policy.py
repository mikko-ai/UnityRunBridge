import runpy
import json
import subprocess
from pathlib import Path

import pytest


policy = runpy.run_path(str(Path(__file__).resolve().parents[3] / ".github/scripts/check-version-policy.py"))


@pytest.mark.parametrize(
    "messages, version, passes",
    [
        (["docs: update guide"], "0.4.0", True),
        (["fix(watch): preserve state"], "0.4.0", False),
        (["fix: preserve state"], "0.4.1", True),
        (["fix: correct state", "feat(cli): add option"], "0.4.1", False),
        (["fix: correct state", "feat(cli): add option"], "0.5.0", True),
        (["refactor!: remove endpoint"], "0.5.0", False),
        (["feat: redesign\n\nBREAKING CHANGE: remove endpoint"], "1.0.0", True),
        (["chore: roll back"], "0.3.9", False),
    ],
)
def test_version_policy(messages, version, passes):
    level = policy["required_bump"](messages)
    target = policy["parse_version"](version)
    if passes:
        policy["validate_bump"]((0, 4, 0), target, level)
    else:
        with pytest.raises(ValueError):
            policy["validate_bump"]((0, 4, 0), target, level)


@pytest.fixture
def version_repo(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
             "-c", "commit.gpgsign=false", "-c", "tag.gpgSign=false", *args],
            cwd=tmp_path, text=True,
        ).strip()

    git("init", "-q", "-b", "main")
    manifest = tmp_path / policy["MANIFEST"]
    manifest.parent.mkdir(parents=True)
    monkeypatch.setitem(policy["git"].__globals__, "ROOT", tmp_path)

    def commit(message, version):
        manifest.write_text(json.dumps({"version": version}) + "\n")
        git("add", policy["MANIFEST"])
        git("commit", "-q", "--allow-empty", "-m", message)
        return git("rev-parse", "HEAD")

    return git, commit


def test_batch_keeps_candidate_for_multiple_features_until_release(version_repo):
    git, commit = version_repo
    commit("chore: stable baseline", "0.4.1")
    git("tag", "v0.4.1")
    first = commit("feat(midscene): shared configuration", "0.5.0")
    second = commit("feat(midscene): initializer", "0.5.0")
    git("tag", "v1.0.0-rc.1")
    assert policy["validate_batch"](first, second, (0, 5, 0)) == "v0.4.1"
    assert policy["validate_batch"](second, second, (0, 5, 0)) == "v0.4.1"
    with pytest.raises(ValueError, match="低于基线"):
        policy["validate_batch"](first, second, (0, 4, 2))

    git("tag", "v0.5.0")
    third = commit("fix: preserve template", "0.5.0")
    with pytest.raises(ValueError, match="Patch"):
        policy["validate_batch"](second, third, (0, 5, 0))
    assert policy["validate_batch"](second, third, (0, 5, 1)) == "v0.5.0"


def test_batch_ignores_unreachable_release_and_counts_pr_title(version_repo):
    git, commit = version_repo
    base = commit("chore: stable baseline", "0.4.1")
    git("tag", "v0.4.1")
    git("switch", "-q", "-c", "other")
    commit("feat: unrelated", "1.0.0")
    git("tag", "v1.0.0")
    git("switch", "-q", "main")
    head = commit("docs: initial commit title", "0.4.1")
    with pytest.raises(ValueError, match="Minor"):
        policy["validate_batch"](base, head, (0, 4, 1), ["feat: new command"])
    assert policy["validate_batch"](base, head, (0, 5, 0), ["feat: new command"]) == "v0.4.1"
