from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.pipeline.models import RunArtifact, validate_relative_artifact_path


class ArtifactStorageError(ValueError):
    """Raised when an artifact cannot be safely stored."""


class PipelineArtifactStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.PIPELINE_ARTIFACT_ROOT).resolve()

    def resolve(self, relative_path: str) -> Path:
        try:
            validate_relative_artifact_path(relative_path)
        except ValidationError as exc:
            raise ArtifactStorageError(str(exc)) from exc
        target = self.root.joinpath(*PurePosixPath(relative_path).parts).resolve()
        if not target.is_relative_to(self.root):
            raise ArtifactStorageError("La ruta del artefacto sale de PIPELINE_ARTIFACT_ROOT")
        return target

    def store_bytes(
        self,
        *,
        pipeline_run,
        artifact_type: str,
        relative_path: str,
        content: bytes,
        provider_run=None,
        stage_run=None,
    ) -> RunArtifact:
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
        except OSError as exc:
            raise ArtifactStorageError(f"No se pudo escribir {relative_path}: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

        digest = hashlib.sha256(content).hexdigest()
        artifact, _ = RunArtifact.objects.update_or_create(
            pipeline_run=pipeline_run,
            relative_path=relative_path,
            defaults={
                "provider_run": provider_run,
                "stage_run": stage_run,
                "artifact_type": artifact_type,
                "content_sha256": digest,
                "size_bytes": len(content),
            },
        )
        return artifact
