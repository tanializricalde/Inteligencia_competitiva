import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _local_environment() -> str:
    return "\n".join(
        (
            "SECRET_KEY=" + ("x" * 64),
            "DEBUG=true",
            "ALLOWED_HOSTS=localhost,127.0.0.1",
            "CSRF_TRUSTED_ORIGINS=http://localhost:8000",
            "APP_BASE_URL=http://localhost:8000",
            "DATABASE_PATH=data/market-watch.sqlite3",
            "SECURE_SSL_REDIRECT=false",
            "SESSION_COOKIE_SECURE=false",
            "CSRF_COOKIE_SECURE=false",
            "SCRAPER_ALLOW_PRIVATE_HOSTS=false",
            "",
        )
    )


def _isolated_bash_deploy(tmp_path: Path, environment: str) -> tuple[Path, dict[str, str]]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    deploy = scripts / "deploy-production.sh"
    deploy.write_text(
        (ROOT / "scripts/deploy-production.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    deploy.chmod(deploy.stat().st_mode | stat.S_IXUSR)
    (tmp_path / ".env").write_text(environment, encoding="utf-8")

    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    process_environment = os.environ.copy()
    process_environment["PATH"] = f"{binaries}{os.pathsep}{process_environment['PATH']}"
    return deploy, process_environment


def test_bash_local_http_accepts_only_explicit_loopback_profile(tmp_path):
    deploy, environment = _isolated_bash_deploy(tmp_path, _local_environment())

    local = subprocess.run(
        [str(deploy), "--check", "--local-http"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    strict = subprocess.run(
        [str(deploy), "--check"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert local.returncode == 0
    assert "Configuración local HTTP válida" in local.stdout
    assert strict.returncode != 0
    assert "SECURE_SSL_REDIRECT debe ser true" in strict.stderr


def test_bash_local_http_rejects_non_loopback_host(tmp_path):
    unsafe = _local_environment().replace(
        "ALLOWED_HOSTS=localhost,127.0.0.1", "ALLOWED_HOSTS=192.0.2.10"
    )
    deploy, environment = _isolated_bash_deploy(tmp_path, unsafe)

    result = subprocess.run(
        [str(deploy), "--check", "--local-http"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode != 0
    assert "ALLOWED_HOSTS sólo puede contener" in result.stderr


def _production_security_values(local_http: bool) -> str:
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "ALLOW_INSECURE_LOCAL_HTTP": "true" if local_http else "false",
            "SECURE_SSL_REDIRECT": "false",
            "SESSION_COOKIE_SECURE": "false",
            "CSRF_COOKIE_SECURE": "false",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; "
            "print(settings.DEBUG, settings.SECURE_SSL_REDIRECT, "
            "settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment,
    )

    return result.stdout.strip()


def test_production_settings_allow_insecure_cookies_only_with_explicit_local_flag():
    assert _production_security_values(local_http=True) == "False False False False"
    assert _production_security_values(local_http=False) == "False True True True"
