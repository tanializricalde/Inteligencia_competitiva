"""Validate repository-local Markdown links without shell-specific dependencies."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
LINK_RE = re.compile(r"\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)")
IGNORED_SCHEMES = {"http", "https", "mailto", "app", "data"}


def markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for candidate in (root / "README.md", root / "docs", root / "codex"):
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(candidate.rglob("*.md"))
    return sorted(files)


def resolve_target(root: Path, source: Path, raw_target: str) -> Path | None:
    target = raw_target.removeprefix("<").removesuffix(">")
    split = urlsplit(target)
    if split.scheme.lower() in IGNORED_SCHEMES or not split.path:
        return None
    path = Path(unquote(split.path))
    if path.is_absolute():
        return root / str(path).lstrip("/\\")
    return source.parent / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="raíz que contiene README.md y docs/ (por defecto, el repositorio)",
    )
    return parser.parse_args()


def main() -> int:
    root = parse_args().root.resolve()
    failures: list[str] = []
    files = markdown_files(root)
    for source in files:
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group("target")
            resolved = resolve_target(root, source, target)
            if resolved is None or resolved.exists():
                continue
            line = text.count("\n", 0, match.start()) + 1
            relative_source = source.relative_to(root)
            failures.append(
                f"{relative_source}:{line}: enlace local inexistente: {target}"
            )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Enlaces Markdown válidos ({len(files)} archivos).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
