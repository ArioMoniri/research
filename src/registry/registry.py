"""Validate the registries and print the /status table.

    python -m src.registry.registry validate
    python -m src.registry.registry status
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..common.config import ROOT, UNSET, load_yaml, project

ENGINES = {"oracle", "postgresql", "sqlserver", "mysql"}
LAYERS = {"model", "test", "harness", "data"}
STATUSES = ["proposed", "reviewed", "approved", "running", "written", "submitted", "dropped"]
REVIEWERS = ["clinician-reviewer", "ml-reviewer", "methods-reviewer", "skeptic"]
SECRET_KEYS = {"password", "passwd", "pwd", "secret", "token", "key"}


def load(root: Path = ROOT) -> tuple[list, list, list]:
    reg = root / "registry"
    return (load_yaml(reg / "databases.yaml").get("databases") or [],
            load_yaml(reg / "ideas.yaml").get("ideas") or [],
            load_yaml(reg / "studies.yaml").get("studies") or [])


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k
            yield from _walk_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def validate(root: Path = ROOT) -> list[str]:
    dbs, ideas, studies = load(root)
    errors = []

    def need(entry, fields, where):
        for f in fields:
            if f not in entry:
                errors.append(f"{where}: missing '{f}'")

    def unique(entries, where):
        ids = [e.get("id") for e in entries]
        for dup in sorted({i for i in ids if ids.count(i) > 1}, key=str):
            errors.append(f"{where}: duplicate id '{dup}'")
        return set(ids)

    db_ids = unique(dbs, "databases")
    for d in dbs:
        w = f"database {d.get('id')}"
        need(d, ["id", "engine", "connection", "schema", "owner", "ethics", "last_audit",
                 "audit_path", "node_card_path"], w)
        if d.get("engine") not in ENGINES:
            errors.append(f"{w}: engine must be one of {sorted(ENGINES)}")
        for path, key in _walk_keys(d):
            if str(key).lower() in SECRET_KEYS:
                errors.append(f"{w}: '{path}' looks like a credential; registries never hold credentials")

    idea_ids = unique(ideas, "ideas")
    for i in ideas:
        w = f"idea {i.get('id')}"
        need(i, ["id", "title", "claim", "layer", "databases", "fields", "status", "verdicts", "study_repo"], w)
        if i.get("layer") not in LAYERS:
            errors.append(f"{w}: layer must be one of {sorted(LAYERS)}")
        if i.get("status") not in STATUSES:
            errors.append(f"{w}: status must be one of {STATUSES}")
        for d in i.get("databases") or []:
            if d not in db_ids:
                errors.append(f"{w}: unknown database '{d}'")
        if i.get("status") in ("running", "written", "submitted") and not i.get("study_repo"):
            errors.append(f"{w}: status '{i.get('status')}' needs a study_repo")

    unique(studies, "studies")
    for s in studies:
        w = f"study {s.get('id')}"
        need(s, ["id", "idea", "repo_url", "hub_commit", "venue", "phase"], w)
        if s.get("idea") not in idea_ids:
            errors.append(f"{w}: unknown idea '{s.get('idea')}'")
    return errors


def _unset(entry, prefix="") -> list[str]:
    out = []
    for k, v in (entry or {}).items():
        if isinstance(v, dict):
            out += _unset(v, f"{prefix}{k}.")
        elif v == UNSET:
            out.append(f"{prefix}{k}")
    return out


def next_decision(idea: dict) -> str:
    return {
        "proposed": "run /review-idea, or drop",
        "reviewed": "lead: approve, revise or drop",
        "approved": "lead: confirm repository name, then /start-study",
        "running": "none until the next gate",
        "written": "lead: review package (GATE 4)",
        "submitted": "none",
        "dropped": "none",
    }.get(idea.get("status"), "?")


def status(root: Path = ROOT) -> str:
    dbs, ideas, studies = load(root)
    cfg = project()
    out = ["## Databases", "", "| id | engine | last audit | missing values | next decision |", "|---|---|---|---|---|"]
    for d in dbs:
        missing = _unset(d)
        nxt = ("lead: fill " + ", ".join(missing)) if missing else (
            "run Phase 1 audit" if not d.get("last_audit") else "none")
        out.append(f"| {d['id']} | {d.get('engine')} | {d.get('last_audit') or 'never'} | "
                   f"{', '.join(missing) or 'none'} | {nxt} |")
    out += ["", "## Ideas", "", "| id | title | layer | status | blocking verdicts | next decision |", "|---|---|---|---|---|---|"]
    for i in ideas:
        v = i.get("verdicts") or {}
        blocking = [r for r in REVIEWERS if (v.get(r) or {}).get("verdict") == "blocking"]
        out.append(f"| {i['id']} | {i.get('title')} | {i.get('layer')} | {i.get('status')} | "
                   f"{', '.join(blocking) or ('not reviewed' if not v else 'none')} | {next_decision(i)} |")
    out += ["", "## Studies", ""]
    if studies:
        out += ["| id | idea | repository | hub commit | venue | phase |", "|---|---|---|---|---|---|"]
        out += [f"| {s['id']} | {s['idea']} | {s['repo_url']} | {str(s['hub_commit'])[:12]} | "
                f"{s.get('venue') or 'not chosen'} | {s.get('phase')} |" for s in studies]
    else:
        out.append("_No study has been started._")
    proj_missing = [k for k, v in cfg.items() if v == UNSET]
    if proj_missing:
        out += ["", f"Project settings still unset in configs/project.yaml: {', '.join(proj_missing)}."]
    return "\n".join(out)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv[:1] == ["validate"]:
        errors = validate()
        print("\n".join(errors) if errors else "registries valid")
        return 1 if errors else 0
    if argv[:1] == ["status"]:
        print(status())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
