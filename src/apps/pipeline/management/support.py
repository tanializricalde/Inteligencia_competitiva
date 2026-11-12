from __future__ import annotations

from django.core.management.base import CommandError

from apps.pipeline.models import PipelineProfile, PipelineProfileVersion, ScheduledJob


def resolve_profile_version(
    *, profile_code: str | None = None, scheduled_job_code: str | None = None
) -> tuple[PipelineProfileVersion, ScheduledJob | None]:
    if scheduled_job_code:
        try:
            job = ScheduledJob.objects.select_related("profile__active_version").get(
                code=scheduled_job_code,
                is_active=True,
            )
        except ScheduledJob.DoesNotExist as exc:
            raise CommandError(f"ScheduledJob activo inexistente: {scheduled_job_code}") from exc
        profile = job.profile
    else:
        if not profile_code:
            raise CommandError("Debes indicar --profile o --scheduled-job")
        try:
            profile = PipelineProfile.objects.select_related("active_version").get(
                code=profile_code,
                is_active=True,
            )
        except PipelineProfile.DoesNotExist as exc:
            raise CommandError(f"Perfil activo inexistente: {profile_code}") from exc
        job = None
    if profile.active_version is None:
        raise CommandError(f"El perfil {profile.code} no tiene versión activa")
    if profile.active_version.status != PipelineProfileVersion.Status.PUBLISHED:
        raise CommandError("La versión activa del perfil no está publicada")
    return profile.active_version, job
