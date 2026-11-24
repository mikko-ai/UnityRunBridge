#!/usr/bin/env python3
"""Validate shipped Skill metadata and score a separate judge's routing selections."""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = ROOT / "src/unityctl/unityctl/skill_assets"
DEFAULT_CASES = ROOT / "evals/skill-triggers.json"
LOCALES = {"zh", "en"}
KINDS = {"should", "near-miss", "combo", "none"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
CODE_REFERENCE = re.compile(r"`((?:[\w.-]+/)*[\w.-]+\.md)`")
LINK = re.compile(r"\]\(([^)>\s]+\.md)(?:#[^\s)]*)?\)")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


def frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    head, separator, _ = raw.removeprefix("---\n").partition("\n---\n")
    if not separator or not raw.startswith("---\n"):
        raise ValueError(f"{path}: missing frontmatter")
    meta = {}
    # Built-in Skill metadata intentionally uses one-line, unquoted scalars.
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if not sep or not SLUG.fullmatch(key) or not value.startswith(" ") or key in meta:
            raise ValueError(f"{path}: unsupported or duplicate frontmatter field: {key}")
        meta[key] = value.strip()
    return meta


def verify_references(directory):
    for markdown in sorted(directory.rglob("*.md")):
        if markdown.is_symlink() or not markdown.is_file():
            raise ValueError(f"{markdown}: expected regular Markdown file")
        text = markdown.read_text(encoding="utf-8")
        for relative in sorted(set(CODE_REFERENCE.findall(text)) | set(LINK.findall(text))):
            if "://" in relative:
                continue
            candidate = markdown.parent / relative
            if not candidate.resolve().is_relative_to(directory.resolve()) or not candidate.is_file():
                raise ValueError(f"{markdown}: missing or external Skill reference: {relative}")


def catalog(root):
    result = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        path = directory / "SKILL.md"
        name = directory.name
        if directory.is_symlink() or not path.is_file() or path.is_symlink():
            raise ValueError(f"{directory}: expected regular Skill directory and SKILL.md")
        meta = frontmatter(path)
        if not SLUG.fullmatch(name) or meta.get("name") != name:
            raise ValueError(f"{path}: Skill name must match its directory")
        description = meta.get("description", "")
        if not description or description[0] in "\"'|>" or ": " in description or " #" in description:
            raise ValueError(f"{path}: expected non-empty inline description")
        disable = meta.get("disable-model-invocation", "false")
        if disable not in {"true", "false"}:
            raise ValueError(f"{path}: invalid disable-model-invocation")
        version = meta.get("x-unityctl-version", "")
        if version != "__UNITYCTL_VERSION__" and not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.+-][\w.+-]+)?", version):
            raise ValueError(f"{path}: invalid x-unityctl-version")
        verify_references(directory)
        result.append({"name": name, "description": description, "autoInvocable": disable == "false"})
    if not result:
        raise ValueError("no packaged skills found")
    return result


def skill_set(values, names, label):
    if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
        raise ValueError(f"{label}: expected an array of Skill names")
    chosen = set(values)
    if len(chosen) != len(values) or chosen - names:
        raise ValueError(f"{label}: duplicate or unknown Skill names")
    return chosen


def validate(cases, skills):
    names = {skill["name"] for skill in skills}
    auto = {skill["name"] for skill in skills if skill["autoInvocable"]}
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty JSON array")
    ids = set()
    prompts = set()
    coverage = Counter()
    fields = {"id", "locale", "kind", "prompt", "explicitSkills", "expected"}
    for case in cases:
        if not isinstance(case, dict) or not fields <= case.keys() <= fields | {"reject"}:
            raise ValueError("invalid case fields")
        key, locale, kind, prompt = (case[k] for k in ("id", "locale", "kind", "prompt"))
        if any(not isinstance(x, str) or not x.strip() for x in (key, locale, kind, prompt)):
            raise ValueError("invalid case id, locale, kind or prompt")
        if key in ids or prompt.strip() in prompts or locale not in LOCALES or kind not in KINDS:
            raise ValueError(f"{key}: duplicate case/prompt or invalid category")
        ids.add(key)
        prompts.add(prompt.strip())
        explicit = skill_set(case["explicitSkills"], names, f"{key}.explicitSkills")
        found = set(re.findall(r"\$([a-z][a-z0-9-]*)", prompt)) & names
        if explicit != found:
            raise ValueError(f"{key}: explicit Skills must match named invocations in the prompt")
        expected = skill_set(case["expected"], names, f"{key}.expected")
        if expected - (auto | explicit) or explicit - expected:
            raise ValueError(f"{key}: expected selection violates invocation policy")
        if kind in {"should", "none"} and len(expected) != (1 if kind == "should" else 0):
            raise ValueError(f"{key}: should/none require one/zero expected Skills")
        if kind == "combo" and len(expected) < 2:
            raise ValueError(f"{key}: combo needs at least two expected Skills")
        if kind == "near-miss":
            reject = case.get("reject")
            if not isinstance(reject, str) or reject not in names - expected:
                raise ValueError(f"{key}: near-miss must identify an excluded Skill")
            coverage[locale, kind, reject] += 1
        elif "reject" in case:
            raise ValueError(f"{key}: reject is only valid on near-miss cases")
        if kind == "should":
            coverage[locale, kind, next(iter(expected))] += 1
        coverage[locale, kind] += 1
    for locale in sorted(LOCALES):
        if not all(coverage[locale, kind] for kind in KINDS):
            raise ValueError(f"{locale}: missing a trigger category")
        for name in sorted(names):
            if coverage[locale, "should", name] < 2 or not coverage[locale, "near-miss", name]:
                raise ValueError(f"{locale}/{name}: needs two positive cases and one near-miss")
    return names, auto


def blind_packet(cases, skills):
    public = {
        "instructions": (
            "Classify the requests, do not perform them. Return only a JSON object from each case id "
            "to an array of selected Skill names, or [] when neither applies. Each explicitSkills entry "
            "is an actual user invocation. Only autoInvocable Skills may be selected otherwise. "
            "Select the minimum applicable set; use only the descriptions supplied here."
        ),
        "skills": skills,
        "cases": [{key: case[key] for key in ("id", "prompt", "explicitSkills")} for case in cases],
    }
    encoded = json.dumps(public, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"fingerprint": hashlib.sha256(encoded).hexdigest(), **public}


def score(cases, answers, names, auto, fingerprint):
    if not isinstance(answers, dict):
        raise ValueError("answers must be a JSON object keyed by case id")
    case_ids = {case["id"] for case in cases}
    missing = case_ids - answers.keys()
    unknown = answers.keys() - case_ids
    if missing or unknown:
        raise ValueError(f"answer ids mismatch: missing={sorted(missing)} unknown={sorted(unknown)}")
    failures = []
    counts = {}
    tp = fp = fn = 0
    for case in cases:
        key = case["id"]
        picks = skill_set(answers[key], names, key)
        expected = set(case["expected"])
        disallowed = picks - (auto | set(case["explicitSkills"]))
        tp += len(picks & expected)
        fp += len(picks - expected)
        fn += len(expected - picks)
        group = counts.setdefault(case["kind"], {"total": 0, "passed": 0})
        group["total"] += 1
        if picks != expected or disallowed:
            failures.append({"id": key, "kind": case["kind"], "locale": case["locale"],
                             "missing": sorted(expected - picks), "unexpected": sorted(picks - expected),
                             "disallowed": sorted(disallowed)})
        else:
            group["passed"] += 1
    return {
        "fingerprint": fingerprint, "total": len(cases), "passed": len(cases) - len(failures),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "byKind": counts, "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="shipped or clean installed Skill directory")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate assets and case coverage offline")
    mode.add_argument("--export", action="store_true", help="write judge packet without answer keys")
    mode.add_argument("--score", type=Path, metavar="ANSWERS")
    args = parser.parse_args()
    exit_code = 0
    try:
        skills = catalog(args.assets)
        cases = read_json(args.cases)
        names, auto = validate(cases, skills)
        packet = blind_packet(cases, skills)
        if args.export:
            output = packet
        elif args.score is not None:
            output = score(cases, read_json(args.score), names, auto, packet["fingerprint"])
            exit_code = int(bool(output["failures"]))
        else:
            output = {"ok": True, "caseCount": len(cases), "skills": sorted(names),
                      "fingerprint": packet["fingerprint"]}
    except (OSError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
