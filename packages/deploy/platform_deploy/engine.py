from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.config import Settings
from platform_core.enums import DeploymentStatus
from platform_core.repositories import DeploymentRepository, LogRepository
from platform_core.security import TokenCipher, generate_db_password, generate_slug
from platform_deploy.token_validator import BotIdentity, TokenValidationError, validate_bot_token

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeploymentEngine:
    """
    Creates independent Mafia bot instances from the owned template.

    IMPORTANT:
    - Never modifies the template source tree.
    - Copies template into data/deployments/{slug}/
    - Writes only .env (and runtime metadata) into the copy.
    - Starts process or Docker container automatically.
    """

    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.cipher = TokenCipher(settings)

    async def validate_token(self, token: str) -> BotIdentity:
        return await validate_bot_token(token)

    async def deploy_for_user(
        self,
        user_id: int,
        subscription_id: int,
        bot_token: str,
        bot_identity: BotIdentity,
        progress_callback=None,
    ) -> int:
        async def report(step: str) -> None:
            if progress_callback:
                await progress_callback(step)

        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            logs = LogRepository(session)

            existing = await deps.get_by_user(user_id)
            if existing and existing.status == DeploymentStatus.RUNNING.value:
                # Token update path for running bot
                return await self._update_token(existing.id, bot_token, bot_identity)

            if existing and existing.status in {
                DeploymentStatus.SUSPENDED.value,
                DeploymentStatus.STOPPED.value,
            }:
                # Reactivate with possibly new token
                existing.bot_token_encrypted = self.cipher.encrypt(bot_token)
                existing.bot_id = bot_identity.id
                existing.bot_username = bot_identity.username
                existing.bot_first_name = bot_identity.first_name
                await deps.save(existing)
                await self.start(existing.id)
                return existing.id

            if existing and existing.status == DeploymentStatus.FAILED.value:
                deployment = existing
                deployment.status = DeploymentStatus.PROVISIONING.value
                deployment.last_error = None
            else:
                slug = generate_slug(12)
                deployment = await deps.create(
                    user_id=user_id,
                    subscription_id=subscription_id,
                    slug=slug,
                )
                deployment.status = DeploymentStatus.PROVISIONING.value

            deployment.bot_token_encrypted = self.cipher.encrypt(bot_token)
            deployment.bot_id = bot_identity.id
            deployment.bot_username = bot_identity.username
            deployment.bot_first_name = bot_identity.first_name
            deployment.redis_namespace = f"mafia:{deployment.slug}"
            await deps.save(deployment)
            dep_id = deployment.id
            slug = deployment.slug

            await logs.activity("deploy_started", user_id=user_id, deployment_id=dep_id)
            await logs.audit(
                action="deploy_started",
                entity_type="deployment",
                entity_id=str(dep_id),
                detail=f"@{bot_identity.username}",
            )

        try:
            await report("📁 1/4 · fayllar")
            project_path = await asyncio.to_thread(self._prepare_project_dir, slug)

            await report("🔐 2/4 · sozlamalar")
            database_url, db_name = self._build_database_url(slug)
            env_path = project_path / ".env"
            await asyncio.to_thread(
                self._write_env_file,
                env_path,
                bot_token,
                bot_identity.username or f"bot_{bot_identity.id}",
                database_url,
            )

            async with self.session_factory() as session:
                deps = DeploymentRepository(session)
                deployment = await deps.get(dep_id)
                assert deployment is not None
                deployment.project_path = str(project_path)
                deployment.db_name = db_name
                deployment.database_url_encrypted = self.cipher.encrypt(database_url)
                deployment.container_name = f"mafia-{slug}"
                await deps.save(deployment)

            # Shared runtime once — avoids multi-minute pip freeze per bot
            await report("📦 3/4 · runtime")
            await asyncio.to_thread(self._ensure_shared_runtime)

            await report("🚀 4/4 · start")
            if self.settings.deploy_provider == "docker":
                container_id = await asyncio.to_thread(self._start_docker, project_path, slug)
                pid = None
            else:
                container_id = None
                pid = await asyncio.to_thread(self._start_process, project_path, slug)

            await report("❤️ health…")
            await asyncio.sleep(2)
            healthy = await asyncio.to_thread(self._health_check, project_path, pid, container_id)
            if not healthy:
                await asyncio.sleep(3)
                healthy = await asyncio.to_thread(self._health_check, project_path, pid, container_id)

            async with self.session_factory() as session:
                deps = DeploymentRepository(session)
                logs = LogRepository(session)
                deployment = await deps.get(dep_id)
                assert deployment is not None
                deployment.container_id = container_id
                deployment.process_pid = pid
                deployment.provisioned_at = utcnow()
                deployment.last_heartbeat_at = utcnow()
                if healthy or pid or container_id:
                    deployment.status = DeploymentStatus.RUNNING.value
                    deployment.last_error = None
                else:
                    deployment.status = DeploymentStatus.FAILED.value
                    deployment.last_error = "Health check failed after start"
                await deps.save(deployment)
                await logs.activity(
                    "deploy_finished",
                    user_id=user_id,
                    deployment_id=dep_id,
                    detail=deployment.status,
                )

            if deployment.status == DeploymentStatus.FAILED.value:
                raise RuntimeError(deployment.last_error or "Deploy failed")

            await report("✅ Deploy muvaffaqiyatli!")
            return dep_id

        except Exception as exc:  # noqa: BLE001
            logger.exception("Deploy failed dep=%s", dep_id)
            async with self.session_factory() as session:
                deps = DeploymentRepository(session)
                logs = LogRepository(session)
                deployment = await deps.get(dep_id)
                if deployment:
                    deployment.status = DeploymentStatus.FAILED.value
                    deployment.last_error = str(exc)[:2000]
                    await deps.save(deployment)
                await logs.activity(
                    "deploy_failed",
                    user_id=user_id,
                    deployment_id=dep_id,
                    detail=str(exc)[:1000],
                )
            raise

    async def _update_token(self, deployment_id: int, token: str, identity: BotIdentity) -> int:
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if not dep or not dep.project_path:
                raise RuntimeError("Deployment topilmadi")
            dep.bot_token_encrypted = self.cipher.encrypt(token)
            dep.bot_id = identity.id
            dep.bot_username = identity.username
            dep.bot_first_name = identity.first_name
            await deps.save(dep)
            project_path = Path(dep.project_path)
            database_url = (
                self.cipher.decrypt(dep.database_url_encrypted)
                if dep.database_url_encrypted
                else self._sqlite_url(project_path)
            )
            self._write_env_file(
                project_path / ".env",
                token,
                identity.username or f"bot_{identity.id}",
                database_url,
            )
        await self.restart(deployment_id)
        return deployment_id

    def _prepare_project_dir(self, slug: str) -> Path:
        template = self.settings.template_dir
        if not template.exists():
            raise FileNotFoundError(
                f"Template topilmadi: {template}. "
                "template/mafia-bot ichida o'z Mafia bot kodingiz bo'lishi kerak."
            )
        dest = self.settings.deployments_dir / slug
        if dest.exists():
            # Keep existing data DB if re-provisioning same slug folder
            env_backup = dest / ".env"
            db_files = list((dest / "storage").glob("*")) if (dest / "storage").exists() else []
            # Full refresh of code from template without touching template itself
            # Preserve storage/
            storage_tmp = None
            if (dest / "storage").exists():
                storage_tmp = self.settings.deployments_dir / f".storage-{slug}"
                if storage_tmp.exists():
                    shutil.rmtree(storage_tmp, ignore_errors=True)
                shutil.copytree(dest / "storage", storage_tmp)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(
                template,
                dest,
                ignore=shutil.ignore_patterns(
                    ".venv",
                    "__pycache__",
                    "*.pyc",
                    ".env",
                    ".git",
                    "storage",
                ),
            )
            (dest / "storage").mkdir(exist_ok=True)
            if storage_tmp and storage_tmp.exists():
                for item in storage_tmp.iterdir():
                    target = dest / "storage" / item.name
                    if item.is_dir():
                        if target.exists():
                            shutil.rmtree(target)
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
                shutil.rmtree(storage_tmp, ignore_errors=True)
        else:
            shutil.copytree(
                template,
                dest,
                ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", ".env", ".git"),
            )
            (dest / "storage").mkdir(exist_ok=True)
        return dest

    def _sqlite_url(self, project_path: Path) -> str:
        db_path = (project_path / "storage" / "mafia.db").resolve().as_posix()
        return f"sqlite+aiosqlite:///{db_path}"

    def _build_database_url(self, slug: str) -> tuple[str, str]:
        """
        Prefer isolated sqlite per deployment (zero ops for user).
        If PLATFORM uses postgres and env wants postgres-per-bot, can be extended later.
        """
        project_path = self.settings.deployments_dir / slug
        db_name = f"mafia_{slug}"
        # Isolated sqlite inside deployment folder — no DBA required, fully automatic
        url = self._sqlite_url(project_path)
        return url, db_name

    def _write_env_file(self, env_path: Path, bot_token: str, bot_username: str, database_url: str) -> None:
        """
        Write ONLY runtime configuration for the copied instance.
        Does not modify template source files.
        Matches keys expected by the original Mafia bot config.
        """
        content = f"""# Auto-generated by Mafia Builder SaaS — do not edit manually
BOT_TOKEN={bot_token}
BOT_USERNAME={bot_username}
DATABASE_URL={database_url}
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DEFAULT_LANGUAGE=uz
NEWS_CHANNEL_URL=https://t.me/WorldMafiaNews
NEWS_BONUS_CHANNEL=@WorldMafiaNews
SUPPORT_URL={self.settings.support_url}
ADMIN_IDS=
MIN_PLAYERS=4
REGISTRATION_TIMEOUT=90
NIGHT_TIMEOUT=60
DAY_DISCUSSION_TIMEOUT=45
DAY_VOTING_TIMEOUT=60
WINNER_REWARD_DOLLAR=15
WINNER_REWARD_DIAMOND=0
LOSER_REWARD_DOLLAR=10
LOSER_REWARD_DIAMOND=0
NIGHT_MEDIA_FILE_ID=
DAY_MEDIA_FILE_ID=
NIGHT_MEDIA_LOCAL=media/night.gif
DAY_MEDIA_LOCAL=media/day.gif
LOG_LEVEL=INFO
"""
        env_path.write_text(content, encoding="utf-8")

    def _shared_runtime_dir(self) -> Path:
        path = self.settings.deployments_dir.parent / "shared-runtime"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _shared_python(self) -> Path:
        runtime = self._shared_runtime_dir()
        if sys.platform == "win32":
            return runtime / "Scripts" / "python.exe"
        return runtime / "bin" / "python"

    def _runtime_requirements_file(self) -> Path:
        """
        Prefer platform-resolved requirements (conflict-free).
        Falls back to template requirements only if platform file missing.
        Never mutates template source tree.
        """
        root = Path(__file__).resolve().parents[3]
        platform_req = root / "infra" / "mafia-runtime-requirements.txt"
        if platform_req.exists():
            return platform_req
        return self.settings.template_dir / "requirements.txt"

    def _ensure_shared_runtime(self, force: bool = False) -> None:
        """
        One shared venv for all tenant bots.
        First deploy may take 1–2 min; later deploys start in seconds.
        """
        runtime = self._shared_runtime_dir()
        python = self._shared_python()
        marker = runtime / ".deps-ok"
        req = self._runtime_requirements_file()
        req_hash_file = runtime / ".deps-hash"
        req_hash = ""
        if req.exists():
            req_hash = str(hash(req.read_text(encoding="utf-8")))

        if force and marker.exists():
            marker.unlink(missing_ok=True)

        if not python.exists():
            logger.info("Creating shared runtime venv at %s", runtime)
            subprocess.run(
                [self.settings.python_executable, "-m", "venv", str(runtime)],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )

        if (
            marker.exists()
            and python.exists()
            and req_hash_file.exists()
            and req_hash_file.read_text(encoding="utf-8").strip() == req_hash
        ):
            return

        # Upgrade pip for better dependency resolution
        subprocess.run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "-q"],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if not req.exists():
            raise RuntimeError(f"Runtime requirements topilmadi: {req}")

        logger.info("Installing runtime requirements from %s", req)
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(req)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            # Invalidate broken marker
            marker.unlink(missing_ok=True)
            err = (result.stderr or "") + "\n" + (result.stdout or "")
            raise RuntimeError("Runtime o'rnatish xato:\n" + err[:1200])

        # Smoke import critical packages
        smoke = subprocess.run(
            [
                str(python),
                "-c",
                "import aiogram, sqlalchemy, aiosqlite, dotenv, pydantic; print('ok')",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if smoke.returncode != 0:
            marker.unlink(missing_ok=True)
            raise RuntimeError(
                "Runtime smoke-test xato:\n" + (smoke.stderr or smoke.stdout or "")[:800]
            )

        marker.write_text("ok", encoding="utf-8")
        req_hash_file.write_text(req_hash, encoding="utf-8")
        logger.info("Shared runtime ready: %s", python)

    def _ensure_venv_and_deps(self, project_path: Path) -> None:
        """Backward-compatible alias — uses shared runtime."""
        self._ensure_shared_runtime()

    def _start_process(self, project_path: Path, slug: str) -> int:
        self._ensure_shared_runtime()
        python = self._shared_python()
        if not python.exists():
            raise RuntimeError(f"Shared runtime python topilmadi: {python}")

        log_path = project_path / "bot.out.log"
        err_path = project_path / "bot.err.log"
        pid_path = project_path / "bot.pid"

        if pid_path.exists():
            try:
                old_pid = int(pid_path.read_text(encoding="utf-8").strip())
                self._kill_pid(old_pid)
            except Exception:  # noqa: BLE001
                pass

        stdout = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
        stderr = open(err_path, "a", encoding="utf-8")  # noqa: SIM115

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

        proc = subprocess.Popen(
            [str(python), "-m", "app.main"],
            cwd=str(project_path),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=(sys.platform != "win32"),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        meta = project_path / "runtime.json"
        meta.write_text(
            f'{{"pid": {proc.pid}, "slug": "{slug}", "started_at": "{utcnow().isoformat()}"}}',
            encoding="utf-8",
        )
        return proc.pid

    def _start_docker(self, project_path: Path, slug: str) -> str:
        try:
            import docker  # type: ignore
        except ImportError as exc:
            raise RuntimeError("docker package not installed") from exc

        client = docker.from_env()
        name = f"mafia-{slug}"
        # stop existing
        try:
            old = client.containers.get(name)
            old.remove(force=True)
        except Exception:  # noqa: BLE001
            pass

        # Use image or build from Dockerfile next to platform (not modifying template)
        dockerfile = Path(__file__).resolve().parents[3] / "infra" / "Dockerfile.mafia"
        image = self.settings.mafia_image_name
        try:
            client.images.get(image)
        except Exception:  # noqa: BLE001
            if dockerfile.exists():
                client.images.build(
                    path=str(self.settings.template_dir),
                    dockerfile=str(dockerfile),
                    tag=image,
                )
            else:
                # fallback run with python image mounting project
                image = "python:3.11-slim"

        container = client.containers.run(
            image=image,
            name=name,
            detach=True,
            working_dir="/app",
            volumes={str(project_path): {"bind": "/app", "mode": "rw"}},
            command="bash -lc 'pip install -q -r requirements.txt && python -m app.main'",
            restart_policy={"Name": "unless-stopped"},
            network=self.settings.docker_network if self._network_exists(client) else None,
            mem_limit="512m",
        )
        return container.id

    def _network_exists(self, client) -> bool:
        try:
            client.networks.get(self.settings.docker_network)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _health_check(self, project_path: Path, pid: Optional[int], container_id: Optional[str]) -> bool:
        if container_id:
            try:
                import docker

                client = docker.from_env()
                c = client.containers.get(container_id)
                return c.status in {"running", "created"}
            except Exception:  # noqa: BLE001
                return False
        if pid:
            try:
                import psutil

                return psutil.pid_exists(pid)
            except Exception:  # noqa: BLE001
                # fallback
                if sys.platform == "win32":
                    out = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}"],
                        capture_output=True,
                        text=True,
                    )
                    return str(pid) in out.stdout
                try:
                    os.kill(pid, 0)
                    return True
                except OSError:
                    return False
        return False

    def _kill_pid(self, pid: int) -> None:
        try:
            import psutil

            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=8)
                except Exception:  # noqa: BLE001
                    p.kill()
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:  # noqa: BLE001
            pass

    async def start(self, deployment_id: int) -> None:
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if not dep or not dep.project_path:
                raise RuntimeError("Deployment not found")
            project_path = Path(dep.project_path)
            slug = dep.slug

        if self.settings.deploy_provider == "docker":
            cid = await asyncio.to_thread(self._start_docker, project_path, slug)
            pid = None
        else:
            await asyncio.to_thread(self._ensure_shared_runtime)
            cid = None
            pid = await asyncio.to_thread(self._start_process, project_path, slug)

        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            assert dep
            dep.container_id = cid
            dep.process_pid = pid
            dep.status = DeploymentStatus.RUNNING.value
            dep.suspended_at = None
            dep.last_heartbeat_at = utcnow()
            await deps.save(dep)

    async def stop(self, deployment_id: int) -> None:
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if not dep:
                return
            pid = dep.process_pid
            cid = dep.container_id
            project_path = Path(dep.project_path) if dep.project_path else None

        if cid and self.settings.deploy_provider == "docker":
            try:
                import docker

                client = docker.from_env()
                c = client.containers.get(cid)
                c.stop(timeout=10)
            except Exception as exc:  # noqa: BLE001
                logger.warning("docker stop: %s", exc)
        if pid:
            await asyncio.to_thread(self._kill_pid, pid)
        if project_path and (project_path / "bot.pid").exists():
            try:
                (project_path / "bot.pid").unlink()
            except OSError:
                pass

        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if dep:
                dep.status = DeploymentStatus.STOPPED.value
                dep.process_pid = None
                await deps.save(dep)

    async def restart(self, deployment_id: int) -> None:
        await self.stop(deployment_id)
        await asyncio.sleep(1)
        await self.start(deployment_id)

    async def suspend(self, deployment_id: int) -> None:
        await self.stop(deployment_id)
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            logs = LogRepository(session)
            dep = await deps.get(deployment_id)
            if dep:
                dep.status = DeploymentStatus.SUSPENDED.value
                dep.suspended_at = utcnow()
                await deps.save(dep)
                await logs.activity("suspended", deployment_id=deployment_id, user_id=dep.user_id)

    async def reactivate(self, deployment_id: int) -> None:
        await self.start(deployment_id)
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            logs = LogRepository(session)
            dep = await deps.get(deployment_id)
            if dep:
                await logs.activity("reactivated", deployment_id=deployment_id, user_id=dep.user_id)

    async def delete(self, deployment_id: int, wipe_files: bool = False) -> None:
        await self.stop(deployment_id)
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if not dep:
                return
            path = dep.project_path
            dep.status = DeploymentStatus.DELETED.value
            dep.deleted_at = utcnow()
            dep.bot_token_encrypted = None
            await deps.save(dep)
        if wipe_files and path:
            shutil.rmtree(path, ignore_errors=True)

    async def read_logs(self, deployment_id: int, lines: int = 80) -> str:
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if not dep or not dep.project_path:
                return "Log topilmadi."
            err = Path(dep.project_path) / "bot.err.log"
            out = Path(dep.project_path) / "bot.out.log"
        chunks: list[str] = []
        for p in (out, err):
            if p.exists():
                text = p.read_text(encoding="utf-8", errors="replace").splitlines()
                chunks.append(f"=== {p.name} ===")
                chunks.extend(text[-lines:])
        return "\n".join(chunks) if chunks else "Hali log yo'q."

    async def backup(self, deployment_id: int) -> Path:
        async with self.session_factory() as session:
            deps = DeploymentRepository(session)
            dep = await deps.get(deployment_id)
            if not dep or not dep.project_path:
                raise RuntimeError("Deployment not found")
            src = Path(dep.project_path)
            slug = dep.slug

        ts = utcnow().strftime("%Y%m%d_%H%M%S")
        dest = self.settings.backups_dir / f"{slug}_{ts}"
        dest.mkdir(parents=True, exist_ok=True)
        # backup storage + env only (not full venv)
        if (src / "storage").exists():
            shutil.copytree(src / "storage", dest / "storage")
        if (src / ".env").exists():
            shutil.copy2(src / ".env", dest / ".env")
        return dest
