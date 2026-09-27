"""Build a clean zip to move nifikb to another machine (e.g. the office laptop).

    python ops/package.py [--out dist] [--with-learnings]

Included: the nifikb package, tests, ops scripts, examples/, evals/cases.example.toml, agent setup (CLAUDE/GEMINI/AGENTS.md, .mcp.json, .gemini/, .claude/),
docs, knowledge/README.md + context.md, and a fresh nifikb.toml template (this machine's config holds local paths and
sandbox databases, so it is saved as nifikb.toml.sandbox for reference only).
Never included: kb/ (rebuild there), caches, logs, secrets.
"""
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nifikb import __version__  # noqa: E402
from nifikb.config import TEMPLATE  # noqa: E402

FILES = ["CLAUDE.md", "GEMINI.md", "AGENTS.md", "README.md", "HANDOFF.md", ".mcp.json", ".gitignore"]
DIRS = ["nifikb", "tests", "ops", ".gemini", ".claude", "examples"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "dist"}
SKIP_NAMES = {"build.log", "settings.local.json", "last-report.html", "cases.toml"}


def collect(with_learnings=False, sandbox_config=True):
    """[(relative path, bytes)] of everything that is shipped - shared by the zip and the paste bundle (ops/bundle.py)."""
    out = []

    def add(path):
        rel = path.relative_to(ROOT)
        if SKIP_PARTS & set(rel.parts) or path.name in SKIP_NAMES or path.suffix == ".pyc":
            return
        out.append((rel.as_posix(), path.read_bytes()))

    for f in FILES:
        if (ROOT / f).is_file():
            add(ROOT / f)
    for d in DIRS:
        for p in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else []:
            if p.is_file():
                add(p)
    if (ROOT / "evals" / "cases.example.toml").is_file():  # the team's own evals/cases.toml holds real tickets: not shipped
        add(ROOT / "evals" / "cases.example.toml")
    knowledge = ROOT / "knowledge"
    for f in ("README.md", "context.md"):
        if (knowledge / f).is_file():
            add(knowledge / f)
    if with_learnings:
        for p in sorted((knowledge / "learnings").glob("*.md")):
            add(p)
    out.append(("knowledge/learnings/.keep", b""))
    out.append(("nifikb.toml", TEMPLATE.format(home="C:/path/to/nifi").encode("utf-8")))  # fresh template
    if sandbox_config and (ROOT / "nifikb.toml").is_file():
        out.append(("nifikb.toml.sandbox", (ROOT / "nifikb.toml").read_bytes()))  # reference only
    return out


def package(out_dir, with_learnings=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"nifi-kb-{__version__}.zip"
    names = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, data in collect(with_learnings):
            z.writestr(f"nifi-kb/{rel}", data)
            names.append(rel)
    return target, names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--with-learnings", action="store_true", help="also copy knowledge/learnings/*.md")
    args = ap.parse_args()
    target, names = package(args.out, args.with_learnings)
    print(f"wrote {target} ({target.stat().st_size / 1024:.0f} KB, {len(names)} entries)")
    print("On the new machine: unzip, then follow HANDOFF.md section 4 (edit nifikb.toml, build, doctor).")


if __name__ == "__main__":
    main()
