#!/usr/bin/env python3
"""Scaffold a study repository locally from the hub (used by /start-study).

    python scripts/new_study.py --idea P1 --short-name transportability --dest ../

Creates <dest>/vivax-<idea id>-<short-name>/ with the rules, agents, safety
check and log scaffold, records the hub commit, and makes the first commit.
It does NOT create anything on GitHub: /start-study does that with the gh CLI,
privately, and only after the project lead has said yes to the name and
description.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common import runlog  # noqa: E402
from src.common.config import load_yaml  # noqa: E402

DIRS = ["src", "sql", "configs", "prompts/reviews", "results", "figures", "manuscripts", "docs", "logs"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold a study repository")
    ap.add_argument("--idea", required=True)
    ap.add_argument("--short-name", required=True)
    ap.add_argument("--dest", required=True, help="parent directory for the new repository")
    ap.add_argument("--allow-dirty", action="store_true", help="for tests only")
    args = ap.parse_args(argv)

    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", args.short_name):
        sys.exit("short name must be lower-case words joined by hyphens")
    ideas = {i["id"]: i for i in load_yaml(ROOT / "registry" / "ideas.yaml")["ideas"]}
    idea = ideas.get(args.idea) or sys.exit(f"idea {args.idea} is not in registry/ideas.yaml")
    if idea["status"] != "approved":
        sys.exit(f"idea {args.idea} has status '{idea['status']}'. Only the project lead "
                 f"marks an idea 'approved'; a study starts only after that.")
    if runlog.dirty() and not args.allow_dirty:
        sys.exit("the hub has uncommitted changes; commit first so the study can record an exact hub commit")
    hub_commit = runlog.commit()

    name = f"vivax-{args.idea.lower()}-{args.short_name}"
    dest = Path(args.dest).resolve() / name
    if dest.exists():
        sys.exit(f"{dest} already exists")
    for d in DIRS:
        (dest / d).mkdir(parents=True)
        (dest / d / ".gitkeep").touch()

    tpl = ROOT / "templates" / "study"
    subs = {"{{STUDY_NAME}}": name, "{{IDEA_ID}}": idea["id"], "{{IDEA_TITLE}}": idea["title"],
            "{{IDEA_CLAIM}}": idea["claim"], "{{HUB_COMMIT}}": hub_commit, "{{DATE}}": date.today().isoformat(),
            "{{DATABASES}}": ", ".join(idea["databases"])}
    for src in tpl.iterdir():
        text = src.read_text(encoding="utf-8")
        for k, v in subs.items():
            text = text.replace(k, v)
        (dest / src.name.replace("dot.", ".")).write_text(text, encoding="utf-8")

    shutil.copytree(ROOT / ".claude" / "agents", dest / ".claude" / "agents")
    (dest / "scripts").mkdir()
    for f in ("precommit_check.py", "install_hooks.sh"):
        shutil.copy2(ROOT / "scripts" / f, dest / "scripts" / f)
    shutil.copy2(ROOT / "configs" / "patient_id_patterns.txt", dest / "configs" / "patient_id_patterns.txt")
    shutil.copy2(ROOT / "configs" / "project.yaml", dest / "configs" / "project.yaml")
    prompt = idea.get("prompt_path")
    if prompt and (ROOT / prompt).exists():
        shutil.copy2(ROOT / prompt, dest / "prompts" / Path(prompt).name)
        reviews = ROOT / "prompts" / "reviews"
        for r in reviews.glob(f"{args.idea.lower()}_*"):
            shutil.copy2(r, dest / "prompts" / "reviews" / r.name)

    def git(*a):
        subprocess.run(["git", *a], cwd=dest, check=True, capture_output=True)
    git("init", "-b", "main")
    subprocess.run(["bash", "scripts/install_hooks.sh"], cwd=dest, check=True, capture_output=True)
    git("add", "-A")
    git("commit", "-m", f"Scaffold {name} from hub commit {hub_commit[:12]}")
    print(f"created {dest}")
    print(f"hub commit {hub_commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
