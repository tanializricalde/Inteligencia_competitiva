from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _template_keys(path: Path) -> set[str]:
    return {
        line.split("=", 1)[0]
        for raw_line in path.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#") and "=" in line
    }


def test_environment_reference_covers_both_templates():
    documented = (ROOT / "docs/development/ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    expected = _template_keys(ROOT / ".env.example") | _template_keys(
        ROOT / ".env.production.example"
    )

    missing = sorted(key for key in expected if f"`{key}`" not in documented)
    assert missing == []
