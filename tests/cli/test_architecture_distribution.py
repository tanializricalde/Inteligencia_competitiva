import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI_TEMPLATES = ROOT / "cli_dist"
PACKAGES = (
    ROOT / "src/scraping_core",
    ROOT / "src/scraper_cli",
    ROOT / "src/data_pipeline",
    ROOT / "src/data_cleaning",
    ROOT / "src/data_transformation",
)


def test_standalone_packages_have_no_web_or_orm_imports():
    forbidden_roots = {"django", "apps", "config"}
    forbidden_parts = {"models", "migrations", "repositories"}
    violations = []
    for package in PACKAGES:
        for path in package.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if (
                        name.split(".")[0] in forbidden_roots
                        or set(name.split(".")) & forbidden_parts
                    ):
                        violations.append((path, name))
    assert violations == []


def test_distribution_templates_are_complete_and_requirements_are_minimal():
    expected_files = {"README.md", "THIRD_PARTY_NOTICES.md", "requirements.txt", "run.py"}
    assert {path.name for path in CLI_TEMPLATES.iterdir() if path.is_file()} == expected_files

    requirements = {
        line.strip()
        for line in (CLI_TEMPLATES / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert requirements == {
        "httpx>=0.28,<1",
        "beautifulsoup4>=4.13,<5",
        "lxml>=5.3,<7",
        "playwright>=1.52,<2",
        "pandas>=2.2,<3",
    }


def test_distribution_is_isolated_allowlisted_and_manifested(tmp_path):
    destination = tmp_path / "scraper-cli"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_cli_dist.py"), "--output", str(destination)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert not (destination / "apps").exists()
    assert not (destination / "manage.py").exists()
    assert (destination / "docs/cli/CLI_CONFIG.md").is_file()
    assert (destination / "docs/cli/CLI_LEER_PRIMERO.md").is_file()
    assert (destination / "docs/cli/CLI_USAGE.md").is_file()
    assert (destination / "docs/development/WINDOWS_LINUX.md").is_file()
    assert (destination / "docs/data/DATA_PIPELINE.md").is_file()
    assert (destination / "docs/data/DATA_CLEANING.md").is_file()
    assert (destination / "docs/data/DATA_TRANSFORMATION.md").is_file()
    assert (destination / "docs/data/FEATURE_EQUIVALENCE_RULES.md").is_file()
    assert (destination / "docs/data/FEATURE_EQUIVALENCE_ANALYSIS.md").is_file()
    assert (destination / "feature_rules/feature-equivalence.schema.json").is_file()
    assert (destination / "feature_rules/feature-equivalence.example.json").is_file()
    assert (destination / "data_cleaning/__main__.py").is_file()
    assert (destination / "data_transformation/__main__.py").is_file()
    assert (destination / "requirements.txt").read_text(encoding="utf-8") == (
        CLI_TEMPLATES / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert not list(destination.rglob("*.sqlite3"))
    assert not list(destination.rglob("__pycache__"))

    manifest = json.loads((destination / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == 1
    assert "docs/cli/CLI_LEER_PRIMERO.md" in {item["path"] for item in manifest["files"]}
    assert manifest["files"] == sorted(manifest["files"], key=lambda item: item["path"])
    for item in manifest["files"]:
        content = (destination / item["path"]).read_bytes()
        assert len(content) == item["size"]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["DATABASE_URL"] = "sqlite:////definitely/not/usable/database.sqlite3"
    run = subprocess.run(
        [sys.executable, "-m", "scraper_cli", "list-adapters"],
        cwd=destination,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert run.returncode == 0, run.stderr
