"""cite_audit.py and the Stop hook on a matter holding the real Becks v. Pierce opinion."""

import json

from conftest import run_script
from test_ledger import MATTER, create, full_read_payload
from conftest import fixture

FULL = "*Becks v. Pierce*, 282 Ga. App. 229, 234, 638 S.E.2d 390 (2006)"
GOOD_QUOTE = "the Bar’s policy cannot supplant the statutory requirement that the defendant have knowledge that the person will soon be driving"


def primed(project):
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    run_script("ledger.py", ["ingest"], full_read_payload(), project)
    return project / MATTER


def audit(project, text: str, name: str = "memo.md"):
    matter = project / MATTER
    (matter / "drafts" / name).write_text(text, encoding="utf-8")
    r = run_script("cite_audit.py", [str(matter), "--html"], None, project)
    report = json.loads((matter / "audit" / "cite-check.json").read_text(encoding="utf-8"))
    items = [i for d in report["drafts"] for i in d["items"]]
    return r, report, items


def red(items):
    return [i for i in items if i["severity"] == "red" and not i["waived"]]


def test_anchored_quote_with_matching_pin_is_clean(project):
    primed(project)
    r, report, items = audit(project, f"The court held that “{GOOD_QUOTE}.” {FULL}.")
    assert r.returncode == 0 and not red(items)
    assert not any(i["kind"] == "quotation" for i in items)
    assert (project / MATTER / "audit" / "cite-check.html").is_file()
    assert "Becks v. Pierce" in (project / MATTER / "audit" / "toa.md").read_text(encoding="utf-8")


def test_wrong_pin_is_yellow(project):
    primed(project)
    _r, _rep, items = audit(project, f"The court held that “{GOOD_QUOTE}.” *Becks v. Pierce*, 282 Ga. App. 229, 230, 638 S.E.2d 390 (2006).")
    assert any(i["kind"] == "quotation" and i["severity"] == "yellow" and "star page 234" in i["detail"] for i in items)


def test_invented_quote_is_red(project):
    primed(project)
    r, _rep, items = audit(project, f"The court held that “a bar must ask every patron how he plans to get home.” {FULL}.")
    assert r.returncode == 1
    assert any(i["kind"] == "quotation" and "does not anchor" in i["detail"] for i in red(items))


def test_tokens_and_bare_names(project):
    primed(project)
    _r, _rep, items = audit(project, "Knowledge matters. [[src:cl-cluster-1266402 233]] Smith v. Jones went the other way. [[src:cl-cluster-999]]")
    reds = red(items)
    assert any(i["kind"] == "token" and "cl-cluster-999" in i["text"] for i in reds)
    assert any(i["kind"] == "bare_name" and "Smith v. Jones" in i["text"] for i in reds)
    assert not any(i["kind"] == "token" and "1266402" in i["text"] for i in reds)


def test_waiver_clears_a_red_item(project):
    primed(project)
    _r, _rep, items = audit(project, "Smith v. Jones went the other way.")
    key = red(items)[0]["key"]
    w = run_script("ledger.py", ["waive", MATTER, key, "--reason", "hypothetical in a practice problem"], None, project)
    assert w.returncode == 0
    r, report, items = audit(project, "Smith v. Jones went the other way.")
    assert r.returncode == 0 and report["waived"] == 1 and not red(items)


def stop(project, session="s1"):
    return run_script("session_hooks.py", ["stop"], {"hook_event_name": "Stop", "session_id": session,
                                                     "stop_hook_active": False}, project)


def changed(project, rel, session="s1"):
    run_script("session_hooks.py", ["changed"], {"tool_name": "Write", "session_id": session,
                                                 "tool_input": {"file_path": str(project / rel)}}, project)


def test_stop_blocks_on_red_and_passes_when_clean(project):
    primed(project)
    draft = project / MATTER / "drafts" / "memo.md"
    draft.write_text("Smith v. Jones went the other way.", encoding="utf-8")
    changed(project, f"{MATTER}/drafts/memo.md")
    out = stop(project).stdout.decode()
    assert json.loads(out)["decision"] == "block" and "Smith v. Jones" in out
    draft.write_text(f"The court held that “{GOOD_QUOTE}.” {FULL}.", encoding="utf-8")
    assert stop(project).stdout.decode().strip() == ""


def test_stop_ignores_other_sessions_and_active_continuations(project):
    primed(project)
    (project / MATTER / "drafts" / "memo.md").write_text("Smith v. Jones went the other way.", encoding="utf-8")
    changed(project, f"{MATTER}/drafts/memo.md", session="other")
    assert stop(project, session="s1").stdout.decode().strip() == ""
    r = run_script("session_hooks.py", ["stop"], {"session_id": "other", "stop_hook_active": True}, project)
    assert r.stdout.decode().strip() == ""


def test_short_quoted_word_does_not_shift_quote_pairing():
    from cite_extract import quotations

    text = 'The word "wrongful" in the rule adds no element. The court said "there is no requirement in Georgia that an intervening act be wrongful."'
    qs = [q.text for q in quotations(text)]
    assert qs == ["there is no requirement in Georgia that an intervening act be wrongful"]
