import re
from pathlib import Path

from domain.value_objects.role import Role
from tests.api.test_documents import DocStack

STATIC = Path(__file__).resolve().parents[2] / "src" / "api" / "static"


def stack() -> DocStack:
    s = DocStack()
    s.add_user("tech1", Role.TECHNICIAN)
    return s


def test_the_root_redirects_to_the_ui_and_the_ui_is_served():
    s = stack()

    root = s.client.get("/", follow_redirects=False)
    page = s.client.get("/ui/")

    assert root.status_code in (302, 307) and root.headers["location"] == "/ui/"
    assert page.status_code == 200 and "Domain Copilot" in page.text
    assert s.client.get("/ui/app.js").status_code == 200
    assert s.client.get("/ui/app.css").status_code == 200


def test_the_ui_runs_under_the_strict_content_security_policy():
    s = stack()

    csp = s.client.get("/ui/").headers["content-security-policy"]

    assert "default-src 'self'" in csp and "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp


def test_the_page_needs_no_inline_script_style_or_handlers():
    """The strict CSP would silently break any of these, so guard against
    them creeping in."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert not re.search(r"\sstyle=", html)
    assert not re.search(r"\son[a-z]+=", html)
    assert "<style" not in html


def test_the_script_never_writes_server_text_as_markup():
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in js


def test_equipment_list_needs_a_login_and_lists_known_machines():
    s = stack()
    s.upload()

    assert s.client.get("/equipment").status_code == 401
    listed = s.client.get("/equipment", headers=s.auth("tech1")).json()

    assert listed == [{"equipment_id": "eq-test-press-tp100", "name": "Test Press TP-100"}]
