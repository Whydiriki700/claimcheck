#!/usr/bin/env python3
"""claimcheck: verify that your docs tell the truth about your repository.

Scans Markdown files and checks their claims against the actual tree:
relative links must point at files that exist, anchors must match real
headings, and file paths mentioned in inline code must exist on disk.
Zero dependencies. Python 3.8+.
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import unquote

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_RE = re.compile(r"`([^`\n]+)`")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
PATH_EXTS = (
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".toml", ".yaml", ".yml",
    ".md", ".txt", ".sh", ".html", ".css", ".xml", ".csv", ".ini", ".cfg",
    ".lock", ".rs", ".go", ".rb", ".java", ".c", ".h", ".sql", ".env",
)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def slugify(heading):
    """GitHub style anchor slug for a heading."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text)


def headings_of(text):
    return {slugify(m.group(1)) for m in HEADING_RE.finditer(text)}


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def looks_like_path(token):
    if any(c in token for c in " \t*<>{}$|[]()\"'"):
        return False
    if token.startswith(("-", "/", "~", ".")) and "/" not in token[1:]:
        if token.startswith("/") or token.startswith("~"):
            return False
    if "/" in token:
        return True
    return token.endswith(PATH_EXTS) and len(token) > 3


def mask_code(text):
    """Blank out fenced blocks and inline code spans, preserving offsets,
    so example markup inside code is not mistaken for real claims."""
    def blank(m):
        return "".join("\n" if c == "\n" else " " for c in m.group(0))
    masked = re.sub(r"```.*?```", blank, text, flags=re.DOTALL)
    masked = re.sub(r"`[^`\n]+`", blank, masked)
    return masked


def check_markdown(md_path, root):
    """Return a list of findings for one Markdown file."""
    findings = []
    with open(md_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    md_dir = os.path.dirname(os.path.abspath(md_path))
    rel = os.path.relpath(md_path, root)
    own_headings = headings_of(text)
    heading_cache = {}

    def target_headings(path):
        if path not in heading_cache:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    heading_cache[path] = headings_of(fh.read())
            except OSError:
                heading_cache[path] = set()
        return heading_cache[path]

    for m in LINK_RE.finditer(mask_code(text)):
        raw = m.group(1).strip("<>")
        if SCHEME_RE.match(raw) or raw.startswith("//"):
            continue
        path_part, _, anchor = raw.partition("#")
        path_part = unquote(path_part)
        anchor = unquote(anchor)
        line = line_of(text, m.start())
        if not path_part:
            if anchor and anchor not in own_headings:
                findings.append({
                    "file": rel, "line": line, "kind": "missing-anchor",
                    "claim": raw,
                    "detail": "no heading in this file matches the anchor",
                })
            continue
        dest = os.path.normpath(os.path.join(md_dir, path_part))
        if not os.path.exists(dest):
            findings.append({
                "file": rel, "line": line, "kind": "missing-file",
                "claim": raw, "detail": "linked file does not exist",
            })
            continue
        if anchor and dest.endswith(".md") and os.path.isfile(dest):
            if anchor not in target_headings(dest):
                findings.append({
                    "file": rel, "line": line, "kind": "missing-anchor",
                    "claim": raw,
                    "detail": "no heading in the target file matches the anchor",
                })

    for m in CODE_RE.finditer(text):
        token = m.group(1).strip()
        if not looks_like_path(token):
            continue
        clean = token.split("#")[0]
        candidates = [
            os.path.normpath(os.path.join(root, clean)),
            os.path.normpath(os.path.join(md_dir, clean)),
        ]
        if not any(os.path.exists(c) for c in candidates):
            findings.append({
                "file": rel, "line": line_of(text, m.start()),
                "kind": "missing-path", "claim": token,
                "detail": "path mentioned in inline code does not exist",
            })
    return findings


def iter_markdown(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def run(root, files=None):
    root = os.path.abspath(root)
    targets = files if files else list(iter_markdown(root))
    findings = []
    for path in targets:
        findings.extend(check_markdown(path, root))
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="claimcheck",
        description="Verify that your docs tell the truth about your repository.",
    )
    parser.add_argument("files", nargs="*", help="Markdown files to check (default: every .md under the root)")
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    args = parser.parse_args(argv)

    files = [os.path.abspath(f) for f in args.files] or None
    findings = run(args.root, files)

    if args.json:
        print(json.dumps(findings, indent=2))
    elif findings:
        for f in findings:
            print(f"{f['file']}:{f['line']}  {f['kind']}  {f['claim']}  ({f['detail']})")
        print(f"\n{len(findings)} broken claim(s).")
    else:
        print("All claims check out.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
