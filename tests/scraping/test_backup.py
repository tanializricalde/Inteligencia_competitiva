import sqlite3
from pathlib import Path

from django.core.management import call_command


def test_backup_command_creates_consistent_copy(tmp_path, settings):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        database.execute("INSERT INTO sample DEFAULT VALUES")
    original_name = settings.DATABASES["default"]["NAME"]
    output = tmp_path / "backup.sqlite3"

    try:
        settings.DATABASES["default"]["NAME"] = source
        call_command("backup_sqlite", output=output)
    finally:
        settings.DATABASES["default"]["NAME"] = original_name

    assert Path(output).is_file()
