import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_skills as vs  # noqa: E402


def make(tmp_path: Path, front: str, name: str = "demo") -> Path:
    d = tmp_path / "plugins" / "p" / "skills" / name
    d.mkdir(parents=True)
    p = d / "SKILL.md"
    p.write_text(f"---\n{front}\n---\n\nBody.\n", encoding="utf-8", newline="\n")
    return p


def check(monkeypatch, tmp_path, path):
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    return vs.check_file(path, "skill")


def test_unquoted_description_with_colon_fails(monkeypatch, tmp_path):
    p = make(tmp_path, "name: demo\ndescription: Use when: anything")
    assert any("not valid YAML" in e for e in check(monkeypatch, tmp_path, p))


def test_unquoted_plain_description_fails(monkeypatch, tmp_path):
    p = make(tmp_path, "name: demo\ndescription: Plain words")
    assert any("quoted string" in e for e in check(monkeypatch, tmp_path, p))


def test_quoted_description_passes(monkeypatch, tmp_path):
    p = make(tmp_path, 'name: demo\ndescription: "Trigger: anything. Do NOT load for: nothing"')
    assert check(monkeypatch, tmp_path, p) == []


def test_claude_code_fields_need_marker(monkeypatch, tmp_path):
    p = make(tmp_path, 'name: demo\ndescription: "x"\ncontext: fork')
    assert any("not allowed" in e for e in check(monkeypatch, tmp_path, p))
    p2 = make(tmp_path, 'name: demo2\ndescription: "Trigger: x. Do NOT load for: y"\ncompatibility: "Claude Code only"\ncontext: fork', "demo2")
    assert check(monkeypatch, tmp_path, p2) == []


def test_name_must_match_directory(monkeypatch, tmp_path):
    p = make(tmp_path, 'name: other\ndescription: "x"')
    assert any("differs from directory" in e for e in check(monkeypatch, tmp_path, p))


def test_repository_skills_pass():
    assert vs.main() == 0


def test_description_needs_trigger_form(monkeypatch, tmp_path):
    p = make(tmp_path, 'name: demo\ndescription: "Use when researching."')
    assert any("trigger list" in e for e in check(monkeypatch, tmp_path, p))
