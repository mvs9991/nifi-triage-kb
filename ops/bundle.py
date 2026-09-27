"""Pack nifi-kb into ONE plain-text Python file (or a few) for machines where nothing can be downloaded but text can be
pasted - e.g. open it in a browser / Bitbucket / e-mail on the office laptop, copy all, paste into a new file, run it.

    python ops/bundle.py [--out dist] [--max-kb 0] [--no-tests] [--with-learnings]

--max-kb splits the bundle into parts of about that size (clipboard / editor limits); each part is self-contained and
unpacked the same way into the same folder. The unpacker (ops/bundle_unpack.py) checks every file's hash, so a paste
that was cut off or damaged is reported instead of producing broken files. Same content as ops/package.py (minus the
sandbox config).
"""
import argparse
import base64
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ops"))

from bundle_unpack import DATA_LINE, text_hash  # noqa: E402
from nifikb import __version__  # noqa: E402
from package import collect  # noqa: E402


def encode(rel, data):
    """Header + '#|' lines for one file."""
    if " " in rel:
        raise ValueError(f"file names with blanks are not supported in a bundle: {rel}")
    try:
        text = data.decode("utf-8")
        if "\x00" in text or "\r" in text.replace("\r\n", ""):
            raise UnicodeDecodeError("utf-8", data, 0, 1, "binary-looking")
    except UnicodeDecodeError:
        b64 = base64.b64encode(data).decode("ascii")
        lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
        return [f"#@@ FILE {rel} b {hashlib.sha256(data).hexdigest()[:16]}"] + [f"#|{x}" for x in lines]
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")
    newline = text.endswith("\n")
    mode = ("tc" if crlf else "t") if newline else ("tcn" if crlf else "tn")
    body = text[:-1] if newline else text
    lines = body.split("\n") if body else []
    return [f"#@@ FILE {rel} {mode} {text_hash(text)}"] + [f"#|{x}" for x in lines]


def bundle(out_dir, max_kb=0, tests=True, with_learnings=False):
    files = [(rel, data) for rel, data in collect(with_learnings, sandbox_config=False)
             if tests or not rel.startswith("tests/")]
    first_of = {}
    items = []  # (rel, lines, source rel for copies)
    for rel, data in files:
        digest = hashlib.sha256(data).hexdigest()
        if digest in first_of and data:
            items.append((rel, [f"#@@ COPY {rel} {first_of[digest]}"], first_of[digest]))  # CLAUDE.md = GEMINI.md = AGENTS.md
        else:
            first_of[digest] = rel
            items.append((rel, encode(rel, data), None))
    parts, current, size = [], [], 0
    part_of = {}
    for rel, lines, source in items:
        n = sum(len(x) + 1 for x in lines)
        if source is None and max_kb and current and size + n > max_kb * 1024:
            parts.append(current)
            current, size = [], 0
        if source is not None:  # a copy goes with its source
            parts_list = parts + [current]
            parts_list[part_of[source]].append((rel, lines))
            part_of[rel] = part_of[source]
            continue
        current.append((rel, lines))
        part_of[rel] = len(parts)
        size += n
    parts.append(current)
    stub = (ROOT / "ops" / "bundle_unpack.py").read_text(encoding="utf-8")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"nifi-kb-{__version__}-bundle*.py"):
        old.unlink()
    written = []
    for i, part in enumerate(parts, 1):
        name = f"nifi-kb-{__version__}-bundle.py" if len(parts) == 1 else f"nifi-kb-{__version__}-bundle-part{i}of{len(parts)}.py"
        head = (f"# nifi-kb {__version__} - paste bundle" + (f", part {i} of {len(parts)}" if len(parts) > 1 else "")
                + f" - {len(part)} files. Save as {name}, then run:  python {name}\n")
        body = [line for _, lines in part for line in lines]
        text = (head + stub.rstrip("\n") + "\n\n" + DATA_LINE + "\n" + "\n".join(body) + "\n"
                + f"#@@ END part {i} of {len(parts)} files {len(part)}\n")
        path = out_dir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append((path, len(part)))
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--max-kb", type=int, default=0, help="split into parts of about this many KB (0 = one file)")
    ap.add_argument("--no-tests", action="store_true", help="leave tests/ out (smaller; you cannot run the test suite there)")
    ap.add_argument("--with-learnings", action="store_true", help="also copy knowledge/learnings/*.md")
    args = ap.parse_args()
    for path, n in bundle(args.out, args.max_kb, not args.no_tests, args.with_learnings):
        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB, {n} files)")
    print("On the office laptop: create an empty file with the same name, paste the whole content, save as UTF-8, "
          "run  python <file>  - it recreates the nifi-kb folder next to it.")


if __name__ == "__main__":
    main()
