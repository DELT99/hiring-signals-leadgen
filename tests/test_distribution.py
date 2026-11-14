#!/usr/bin/env python3
"""Packaging and architecture checks for both Jword distributions.
Run:  python3 tests/test_distribution.py"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def frontmatter(path: Path) -> dict:
    txt = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n", txt, re.S)
    assert m, f"{path} has no frontmatter"
    return {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)}


@test
def distributions_in_sync():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_skill.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@test
def skill_frontmatter_is_uploadable():
    fm = frontmatter(ROOT / "skill" / "jword" / "SKILL.md")
    assert fm["name"] == "jword"
    d = fm["description"]
    assert 50 < len(d) <= 1024 and "<" not in d and ">" not in d, len(d)


@test
def zip_is_chat_ready_and_clean():
    z = zipfile.ZipFile(ROOT / "dist" / "jword.zip")
    names = z.namelist()
    assert "jword/SKILL.md" in names and "jword/scripts/jword.py" in names
    assert all(n.startswith("jword/") for n in names)
    assert not [n for n in names if re.search(r"(^|/)(\.env|tests/|__pycache__|.*\.xlsx$|state\.json)", n)], names
    blob = b"".join(z.read(n) for n in names if not n.endswith("/"))
    assert not re.search(rb"(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|fc-[0-9a-f]{20,})", blob), "secret-like string in zip"
    skill = z.read("jword/SKILL.md").decode()
    assert "Otherwise (Claude chat" in skill            # works without subagents
    assert ".claude/agents" in skill                    # ...and knows how to use them in Claude Code


@test
def zip_engine_runs_standalone():
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(ROOT / "dist" / "jword.zip").extractall(tmp)
        eng = Path(tmp) / "jword" / "scripts" / "jword.py"
        st = Path(tmp) / "run" / "state.json"
        run = lambda *a: json.loads(subprocess.run([sys.executable, "-I", str(eng), "--state", str(st), *a],
                                                   capture_output=True, text=True, check=True).stdout)
        assert run("init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Remote",
                   "--posted-within", "last 10 days")["config"]["posted"].startswith("Last 10 days")
        assert run("next")["action"] == "search"


@test
def claude_code_agents_are_well_formed():
    agents = {p.stem: p for p in (ROOT / ".claude" / "agents").glob("*.md")}
    assert set(agents) == {"job-researcher", "contact-researcher", "application-writer", "outreach-writer"}, agents
    for name, p in agents.items():
        fm = frontmatter(p)
        assert fm["name"] == name and len(fm["description"]) > 40
        assert fm["model"] in ("sonnet", "haiku", "opus", "inherit")
        tools = {t.strip() for t in fm["tools"].split(",")}
        # no shell (can't touch run state), no email or browser: only the orchestrator acts externally
        assert not tools & {"Bash", "Edit"} and not any(re.search(r"gmail|chrome|browser|computer", t, re.I) for t in tools), tools
        body = p.read_text().lower()
        assert "never" in body and ("invent" in body or "guess" in body)
    assert "WebSearch" in frontmatter(agents["job-researcher"])["tools"]
    assert "WebSearch" not in frontmatter(agents["outreach-writer"])["tools"]


@test
def claude_code_skill_copy_and_claude_md():
    assert (ROOT / ".claude" / "skills" / "jword" / "SKILL.md").exists()
    cm = (ROOT / "CLAUDE.md").read_text()
    assert "skill/jword" in cm and "build_skill.py" in cm


@test
def n8n_workflow_untouched_and_valid():
    wf = json.loads((ROOT / "workflow" / "hiring-signal-lead-engine.json").read_text())
    assert wf.get("nodes") and wf.get("connections")
    if shutil.which("node"):
        r = subprocess.run(["node", str(ROOT / "tests" / "simulate.js")], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
