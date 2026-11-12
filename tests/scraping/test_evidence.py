from apps.scraping.infrastructure.evidence import sanitize_html_evidence


def test_evidence_removes_scripts_credentials_and_sensitive_urls():
    raw = """<html><script>token='secret'</script><form action='/token?a=secret'>
    <input type='password' value='secret'><a href='https://x.test/?token=secret'>safe label</a>
    </form></html>"""

    sanitized = sanitize_html_evidence(raw)

    assert "secret" not in sanitized
    assert "safe label" in sanitized
