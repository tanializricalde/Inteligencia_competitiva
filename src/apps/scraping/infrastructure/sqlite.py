from django.db.backends.signals import connection_created


def configure_sqlite(sender, connection, **_kwargs) -> None:
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 20000")
        if connection.settings_dict["NAME"] != ":memory:":
            cursor.execute("PRAGMA journal_mode = WAL")


connection_created.connect(configure_sqlite, dispatch_uid="scraping.configure_sqlite")
