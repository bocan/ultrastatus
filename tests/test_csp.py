import base64
import hashlib
import re

from statusboard.render import content_security_policy, map_js, render, script_hash

from conftest import utc

NOW = utc(2026, 9, 6, 22, 0, 0)


def test_script_hash_is_sha256_of_the_exact_bytes():
    digest = base64.b64encode(hashlib.sha256(b"alert(1)").digest()).decode()
    assert script_hash("alert(1)") == f"'sha256-{digest}'"


def test_policy_locks_everything_down():
    policy = content_security_policy("x")
    assert policy.startswith("default-src 'none'; script-src 'sha256-")
    assert "style-src 'unsafe-inline'" in policy
    assert "img-src data:" in policy
    assert "base-uri 'none'" in policy
    assert "form-action 'none'" in policy
    assert "unsafe-inline" not in policy.split("script-src")[1].split(";")[0]


def test_rendered_page_carries_a_policy_whose_hash_matches_its_script(conn, tmp_path):
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    meta = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html
    )
    assert meta is not None
    policy = meta.group(1)
    body = re.search(r"<script>(.*)</script>", html, re.DOTALL)
    assert body is not None
    assert script_hash(body.group(1)) in policy
    assert script_hash(map_js()) in policy
    # The policy comes before anything it governs: right after the charset.
    assert html.find("Content-Security-Policy") < html.find("<style>")
    assert html.find("Content-Security-Policy") < html.find("<link")
