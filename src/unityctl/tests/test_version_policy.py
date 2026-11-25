import runpy
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
