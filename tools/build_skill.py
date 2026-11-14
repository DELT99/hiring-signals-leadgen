#!/usr/bin/env python3
"""Build both Jword distributions from the single source in skill/jword/.

    python3 tools/build_skill.py          # copy to .claude/skills/jword/ and write dist/jword.zip
    python3 tools/build_skill.py --check  # fail if either copy is out of date (used by tests)

Only SKILL.md, references/ and scripts/ are shipped. Tests, caches and run data stay out.
"""
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "skill" / "jword"
CODE_COPY = ROOT / ".claude" / "skills" / "jword"
ZIP = ROOT / "dist" / "jword.zip"
SHIP = ("SKILL.md", "references", "scripts")


def files(base: Path) -> dict:
    out = {}
    for name in SHIP:
        p = base / name
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                out[str(f.relative_to(base)).replace("\\", "/")] = f.read_bytes()
    return out


def digest(d: dict) -> str:
    h = hashlib.sha256()
    for k in sorted(d):
        h.update(k.encode() + b"\0" + d[k] + b"\0")
    return h.hexdigest()


def zip_files() -> dict:
    with zipfile.ZipFile(ZIP) as z:
        return {n[len("jword/"):]: z.read(n) for n in z.namelist() if not n.endswith("/")}


def check() -> list:
    src = files(SRC)
    problems = []
    if not CODE_COPY.exists() or digest(files(CODE_COPY)) != digest(src):
        problems.append(".claude/skills/jword is out of date")
    if not ZIP.exists() or digest(zip_files()) != digest(src):
        problems.append("dist/jword.zip is out of date")
    return problems


def build():
    src = files(SRC)
    if CODE_COPY.exists():
        shutil.rmtree(CODE_COPY)
    for rel, data in src.items():
        dst = CODE_COPY / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        dirs = sorted({"/".join(r.split("/")[:i]) for r in src for i in range(1, r.count("/") + 1)})
        z.writestr("jword/", "")
        for d in dirs:
            z.writestr(f"jword/{d}/", "")
        for rel in sorted(src):
            z.writestr(f"jword/{rel}", src[rel])
    print(f"built {CODE_COPY.relative_to(ROOT)} and {ZIP.relative_to(ROOT)} ({len(src)} files, {ZIP.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if "--check" in sys.argv:
        p = check()
        print("\n".join(p) if p else "distributions are up to date")
        sys.exit(1 if p else 0)
    build()
