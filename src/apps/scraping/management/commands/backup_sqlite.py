import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Crea una copia consistente de SQLite usando la API de backup"

    def add_arguments(self, parser):
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"])
        if not source.is_file():
            raise CommandError(f"No existe la base SQLite: {source}")
        destination = options["output"]
        if destination is None:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            destination = source.parent / "backups" / f"market-watch-{stamp}.sqlite3"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == source.resolve():
            raise CommandError("El backup no puede sobrescribir la base activa")
        with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
            source_db.backup(backup_db, pages=100)
            result = backup_db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            destination.unlink(missing_ok=True)
            raise CommandError("El backup no superó integrity_check")
        self.stdout.write(self.style.SUCCESS(str(destination)))
