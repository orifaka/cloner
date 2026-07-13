"""
Process-only deployment engine.
- Copies template/mafia-bot → data/deployments/{slug}/
- Writes only .env into the copy (template source never modified)
- Shared runtime venv for all tenants
- Starts: python -m app.main
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from builder.config import ROOT_DIR, Settings
from builder.models import Deployment
from builder.security import TokenCipher, generate_slug

logger = logging.getLogger("builder.deploy")

TOKEN_RE = re.compile(r"^\d{6,15}:[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True)
class BotIdentity:
    id: int
    username: Optional[str]
    first_name: str


class TokenError(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def validate_bot_token(token: str) -> BotIdentity:
    token = token.strip()
    if not TOKEN_RE.match(token):
        raise TokenError("Token formati noto'g'ri.\n<code>123456:AA...</code>")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = r.json()
    except httpx.HTTPError as e:
        raise TokenError(f"Telegram API: {e}") from e
    if not data.get("ok"):
        raise TokenError(f"Token yaroqsiz: {data.get('description', '?')}")
    res = data["result"]
    if not res.get("is_bot"):
        raise TokenError("Bu token bot emas.")
    return BotIdentity(id=int(res["id"]), username=res.get("username"), first_name=res.get("first_name") or "Bot")


class DeploymentEngine:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.sf = session_factory
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
            logger.info("deploy step user=%s | %s", user_id, step)
            if progress_callback:
                await progress_callback(step)

        async with self.sf() as s:
            existing = (
                await s.execute(
                    select(Deployment)
                    .where(Deployment.user_id == user_id, Deployment.status != "deleted")
                    .order_by(Deployment.id.desc())
                )
            ).scalars().first()

            if existing and existing.status == "running":
                return await self._update_token(existing.id, bot_token, bot_identity)

            if existing and existing.status in {"suspended", "stopped"}:
                existing.bot_token_encrypted = self.cipher.encrypt(bot_token)
                existing.bot_id = bot_identity.id
                existing.bot_username = bot_identity.username
                existing.bot_first_name = bot_identity.first_name
                await s.commit()
                await self.start(existing.id)
                return existing.id

            if existing and existing.status == "failed":
                dep = existing
                dep.status = "provisioning"
                dep.last_error = None
            else:
                # free unique subscription_id from deleted
                for old in (
                    await s.execute(
                        select(Deployment).where(
                            Deployment.subscription_id == subscription_id,
                            Deployment.status == "deleted",
                        )
                    )
                ).scalars().all():
                    old.subscription_id = None
                dep = Deployment(
                    user_id=user_id,
                    subscription_id=subscription_id,
                    slug=generate_slug(12),
                    status="provisioning",
                )
                s.add(dep)

            dep.bot_token_encrypted = self.cipher.encrypt(bot_token)
            dep.bot_id = bot_identity.id
            dep.bot_username = bot_identity.username
            dep.bot_first_name = bot_identity.first_name
            await s.commit()
            await s.refresh(dep)
            dep_id, slug = dep.id, dep.slug

        try:
            await report("📁 1/4 · fayllar")
            project = await asyncio.to_thread(self._copy_template, slug)

            await report("🔐 2/4 · sozlamalar")
            db_url = self._sqlite_url(project)
            await asyncio.to_thread(
                self._write_env,
                project / ".env",
                bot_token,
                bot_identity.username or f"bot_{bot_identity.id}",
                db_url,
            )

            async with self.sf() as s:
                dep = await s.get(Deployment, dep_id)
                assert dep
                dep.project_path = str(project)
                dep.db_name = f"mafia_{slug}"
                dep.database_url_encrypted = self.cipher.encrypt(db_url)
                await s.commit()

            await report("📦 3/4 · runtime")
            await asyncio.to_thread(self._ensure_shared_runtime)

            await report("🚀 4/4 · start")
            pid = await asyncio.to_thread(self._start_process, project, slug)

            await asyncio.sleep(2)
            healthy = await asyncio.to_thread(self._pid_alive, pid)
            if not healthy:
                await asyncio.sleep(3)
                healthy = await asyncio.to_thread(self._pid_alive, pid)

            async with self.sf() as s:
                dep = await s.get(Deployment, dep_id)
                assert dep
                dep.process_pid = pid
                dep.provisioned_at = utcnow()
                dep.last_heartbeat_at = utcnow()
                if healthy or pid:
                    dep.status = "running"
                    dep.last_error = None
                else:
                    dep.status = "failed"
                    dep.last_error = "Process ishga tushmadi"
                await s.commit()
                if dep.status == "failed":
                    raise RuntimeError(dep.last_error)

            await report("✅ Tayyor")
            return dep_id
        except Exception as e:
            logger.exception("deploy fail dep=%s", dep_id)
            async with self.sf() as s:
                dep = await s.get(Deployment, dep_id)
                if dep:
                    dep.status = "failed"
                    dep.last_error = str(e)[:2000]
                    await s.commit()
            raise

    async def _update_token(self, deployment_id: int, token: str, identity: BotIdentity) -> int:
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if not dep or not dep.project_path:
                raise RuntimeError("Deployment yo'q")
            dep.bot_token_encrypted = self.cipher.encrypt(token)
            dep.bot_id = identity.id
            dep.bot_username = identity.username
            dep.bot_first_name = identity.first_name
            project = Path(dep.project_path)
            db_url = (
                self.cipher.decrypt(dep.database_url_encrypted)
                if dep.database_url_encrypted
                else self._sqlite_url(project)
            )
            await s.commit()
        await asyncio.to_thread(
            self._write_env,
            project / ".env",
            token,
            identity.username or f"bot_{identity.id}",
            db_url,
        )
        await self.restart(deployment_id)
        return deployment_id

    def _copy_template(self, slug: str) -> Path:
        src = self.settings.template_dir
        if not src.exists():
            raise FileNotFoundError(f"Template yo'q: {src}")
        dest = self.settings.deployments_dir / slug
        ignore = shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", ".env", ".git")
        if dest.exists():
            storage_tmp = None
            if (dest / "storage").exists():
                storage_tmp = self.settings.deployments_dir / f".st-{slug}"
                if storage_tmp.exists():
                    shutil.rmtree(storage_tmp, ignore_errors=True)
                shutil.copytree(dest / "storage", storage_tmp)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src, dest, ignore=ignore)
            (dest / "storage").mkdir(exist_ok=True)
            if storage_tmp and storage_tmp.exists():
                for item in storage_tmp.iterdir():
                    t = dest / "storage" / item.name
                    if item.is_dir():
                        if t.exists():
                            shutil.rmtree(t)
                        shutil.copytree(item, t)
                    else:
                        shutil.copy2(item, t)
                shutil.rmtree(storage_tmp, ignore_errors=True)
        else:
            shutil.copytree(src, dest, ignore=ignore)
            (dest / "storage").mkdir(exist_ok=True)
        return dest

    def _sqlite_url(self, project: Path) -> str:
        return f"sqlite+aiosqlite:///{(project / 'storage' / 'mafia.db').resolve().as_posix()}"

    def _write_env(self, path: Path, token: str, username: str, database_url: str) -> None:
        path.write_text(
            f"""# Auto-generated — do not edit template source
BOT_TOKEN={token}
BOT_USERNAME={username}
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
""",
            encoding="utf-8",
        )

    def _runtime_dir(self) -> Path:
        p = self.settings.deployments_dir.parent / "shared-runtime"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _runtime_python(self) -> Path:
        r = self._runtime_dir()
        return r / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    def _runtime_req(self) -> Path:
        platform = ROOT_DIR / "infra" / "mafia-runtime-requirements.txt"
        if platform.exists():
            return platform
        return self.settings.template_dir / "requirements.txt"

    def _ensure_shared_runtime(self, force: bool = False) -> None:
        runtime = self._runtime_dir()
        py = self._runtime_python()
        marker = runtime / ".deps-ok"
        req = self._runtime_req()
        hfile = runtime / ".deps-hash"
        h = hash(req.read_text(encoding="utf-8")) if req.exists() else 0

        if force and marker.exists():
            marker.unlink(missing_ok=True)

        if not py.exists():
            logger.info("Creating shared runtime %s", runtime)
            subprocess.run(
                [self.settings.python_executable, "-m", "venv", str(runtime)],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            # if ensurepip missing — try without-pip + get-pip not here; user may have working venv
            if not py.exists():
                subprocess.run(
                    [self.settings.python_executable, "-m", "venv", "--without-pip", str(runtime)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

        if marker.exists() and hfile.exists() and hfile.read_text().strip() == str(h) and py.exists():
            return

        if not req.exists():
            raise RuntimeError(f"requirements yo'q: {req}")

        # upgrade pip if possible
        subprocess.run(
            [str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel", "-q"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        logger.info("pip install -r %s", req)
        r = subprocess.run(
            [str(py), "-m", "pip", "install", "-r", str(req)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            raise RuntimeError("Runtime o'rnatish xato:\n" + ((r.stderr or "") + (r.stdout or ""))[:1200])

        smoke = subprocess.run(
            [str(py), "-c", "import aiogram, sqlalchemy, aiosqlite; print('ok')"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if smoke.returncode != 0:
            raise RuntimeError("Runtime smoke fail:\n" + (smoke.stderr or smoke.stdout or "")[:500])

        marker.write_text("ok", encoding="utf-8")
        hfile.write_text(str(h), encoding="utf-8")
        logger.info("Shared runtime ready")

    def _start_process(self, project: Path, slug: str) -> int:
        self._ensure_shared_runtime()
        py = self._runtime_python()
        if not py.exists():
            raise RuntimeError(f"Runtime python yo'q: {py}")

        pid_path = project / "bot.pid"
        if pid_path.exists():
            try:
                self._kill_pid(int(pid_path.read_text().strip()))
            except Exception:  # noqa: BLE001
                pass

        out = open(project / "bot.out.log", "a", encoding="utf-8")  # noqa: SIM115
        err = open(project / "bot.err.log", "a", encoding="utf-8")  # noqa: SIM115
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

        proc = subprocess.Popen(
            [str(py), "-m", "app.main"],
            cwd=str(project),
            stdout=out,
            stderr=err,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            start_new_session=(sys.platform != "win32"),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        logger.info("started slug=%s pid=%s", slug, proc.pid)
        return proc.pid

    def _pid_alive(self, pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            import psutil

            return psutil.pid_exists(pid)
        except Exception:  # noqa: BLE001
            try:
                os.kill(pid, 0)
                return True
            except OSError:
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
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if not dep or not dep.project_path:
                raise RuntimeError("Deployment yo'q")
            project, slug = Path(dep.project_path), dep.slug
        pid = await asyncio.to_thread(self._start_process, project, slug)
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            assert dep
            dep.process_pid = pid
            dep.status = "running"
            dep.suspended_at = None
            dep.last_heartbeat_at = utcnow()
            await s.commit()

    async def stop(self, deployment_id: int) -> None:
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if not dep:
                return
            pid = dep.process_pid
            project = Path(dep.project_path) if dep.project_path else None
        if pid:
            await asyncio.to_thread(self._kill_pid, pid)
        if project and (project / "bot.pid").exists():
            try:
                (project / "bot.pid").unlink()
            except OSError:
                pass
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if dep:
                dep.status = "stopped"
                dep.process_pid = None
                await s.commit()

    async def restart(self, deployment_id: int) -> None:
        await self.stop(deployment_id)
        await asyncio.sleep(1)
        await self.start(deployment_id)

    async def suspend(self, deployment_id: int) -> None:
        await self.stop(deployment_id)
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if dep:
                dep.status = "suspended"
                dep.suspended_at = utcnow()
                await s.commit()

    async def read_logs(self, deployment_id: int, lines: int = 40) -> str:
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if not dep or not dep.project_path:
                return "Log yo'q"
            base = Path(dep.project_path)
        chunks: list[str] = []
        for name in ("bot.out.log", "bot.err.log"):
            p = base / name
            if p.exists():
                chunks.append(f"=== {name} ===")
                chunks.extend(p.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
        return "\n".join(chunks) or "Hali log yo'q"

    async def backup(self, deployment_id: int) -> Path:
        async with self.sf() as s:
            dep = await s.get(Deployment, deployment_id)
            if not dep or not dep.project_path:
                raise RuntimeError("Deployment yo'q")
            src, slug = Path(dep.project_path), dep.slug
        dest = self.settings.backups_dir / f"{slug}_{utcnow().strftime('%Y%m%d_%H%M%S')}"
        dest.mkdir(parents=True, exist_ok=True)
        if (src / "storage").exists():
            shutil.copytree(src / "storage", dest / "storage")
        if (src / ".env").exists():
            shutil.copy2(src / ".env", dest / ".env")
        return dest
