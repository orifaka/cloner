from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "packages" / "billing"))
sys.path.insert(0, str(ROOT / "packages" / "deploy"))
sys.path.insert(0, str(ROOT / "packages" / "monitoring"))

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from platform_core.config import Settings, get_settings
from platform_core.database import get_session_factory, init_db
from platform_core.repositories import DeploymentRepository, PaymentRepository, UserRepository
from platform_core.security import JWTService
from platform_deploy.engine import DeploymentEngine
from platform_monitoring.service import MonitoringService

app = FastAPI(title="Mafia Builder SaaS API", version="1.0.0")


def settings_dep() -> Settings:
    return get_settings()


async def startup() -> None:
    await init_db(get_settings())


app.add_event_handler("startup", startup)


class TokenBody(BaseModel):
    subject: str
    role: str = "admin"


def require_admin(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required")
    token = authorization.split(" ", 1)[1]
    try:
        payload = JWTService(settings).decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "Invalid token") from exc
    if payload.get("role") not in {"admin", "superadmin"}:
        # allow platform admin telegram ids via claim
        if payload.get("role") != "admin":
            raise HTTPException(403, "Admin only")
    return payload


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/dev-token")
async def dev_token(body: TokenBody, settings: Settings = Depends(settings_dep)) -> dict[str, str]:
    """Issue JWT for dashboard (protect this in production behind firewall)."""
    token = JWTService(settings).create_access_token(body.subject, {"role": body.role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/admin/overview")
async def admin_overview(
    _: dict = Depends(require_admin),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    factory = get_session_factory(settings)
    monitor = MonitoringService()
    async with factory() as session:
        users = await UserRepository(session).list_all(1000)
        deps = await DeploymentRepository(session).list_all(1000)
        stars = await PaymentRepository(session).total_stars_income()
    return {
        "users": len(users),
        "deployments": len(deps),
        "running": sum(1 for d in deps if d.status == "running"),
        "suspended": sum(1 for d in deps if d.status == "suspended"),
        "failed": sum(1 for d in deps if d.status == "failed"),
        "stars_income": stars,
        "host": monitor.host_metrics_dict(),
    }


@app.get("/admin/deployments")
async def list_deployments(
    _: dict = Depends(require_admin),
    settings: Settings = Depends(settings_dep),
) -> list[dict[str, Any]]:
    factory = get_session_factory(settings)
    async with factory() as session:
        deps = await DeploymentRepository(session).list_all(500)
    return [
        {
            "id": d.id,
            "slug": d.slug,
            "status": d.status,
            "bot_username": d.bot_username,
            "user_id": d.user_id,
            "pid": d.process_pid,
            "container_id": d.container_id,
            "last_error": d.last_error,
        }
        for d in deps
    ]


@app.post("/admin/deployments/{deployment_id}/restart")
async def restart_deployment(
    deployment_id: int,
    _: dict = Depends(require_admin),
    settings: Settings = Depends(settings_dep),
) -> dict[str, str]:
    engine = DeploymentEngine(settings, get_session_factory(settings))
    await engine.restart(deployment_id)
    return {"status": "restarted"}


@app.post("/admin/deployments/{deployment_id}/stop")
async def stop_deployment(
    deployment_id: int,
    _: dict = Depends(require_admin),
    settings: Settings = Depends(settings_dep),
) -> dict[str, str]:
    engine = DeploymentEngine(settings, get_session_factory(settings))
    await engine.stop(deployment_id)
    return {"status": "stopped"}


@app.post("/admin/deployments/{deployment_id}/start")
async def start_deployment(
    deployment_id: int,
    _: dict = Depends(require_admin),
    settings: Settings = Depends(settings_dep),
) -> dict[str, str]:
    engine = DeploymentEngine(settings, get_session_factory(settings))
    await engine.start(deployment_id)
    return {"status": "started"}


@app.get("/admin/deployments/{deployment_id}/logs")
async def deployment_logs(
    deployment_id: int,
    _: dict = Depends(require_admin),
    settings: Settings = Depends(settings_dep),
) -> dict[str, str]:
    engine = DeploymentEngine(settings, get_session_factory(settings))
    text = await engine.read_logs(deployment_id)
    return {"logs": text}


@app.get("/", response_class=HTMLResponse)
async def dashboard_home() -> str:
    return """
<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8"/>
  <title>Mafia Builder Admin</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#0b1220; color:#e8eefc; margin:0; padding:24px; }
    .card { background:#121a2b; border:1px solid #24314d; border-radius:16px; padding:20px; max-width:880px; }
    code { background:#1b2740; padding:2px 6px; border-radius:6px; }
    a { color:#7db4ff; }
  </style>
</head>
<body>
  <div class="card">
    <h1>True Mafia Builder API</h1>
    <p>Admin overview: <code>GET /admin/overview</code> (Bearer JWT)</p>
    <p>Docs: <a href="/docs">/docs</a></p>
    <p>Health: <a href="/health">/health</a></p>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("main:app", host=s.api_host, port=s.api_port, reload=False)
