from django.core.management.base import BaseCommand, CommandError

from apps.scraping.infrastructure.scheduler import (
    build_scheduler,
    default_lock_path,
    process_manual_pipeline_queue,
    scheduler_process_lock,
    update_heartbeat,
)


class Command(BaseCommand):
    help = "Ejecuta la instancia única del scheduler"

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="Heartbeat y una solicitud; luego sale"
        )

    def handle(self, *args, **options):
        try:
            with scheduler_process_lock(default_lock_path()):
                update_heartbeat()
                if options["once"]:
                    process_manual_pipeline_queue()
                    self.stdout.write(self.style.SUCCESS("Scheduler verificado"))
                    return
                scheduler = build_scheduler()
                scheduler.start()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
