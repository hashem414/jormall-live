from __future__ import annotations

import json
import html
import os
import secrets
import socket
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse


RUNNER_SOCKET = os.environ.get("RUNNER_SOCKET", "/run/jormall-deployer/runner.sock")
UPLOAD_ROOT = Path(os.environ.get("UPLOAD_ROOT", "/var/lib/jormall/deployer/uploads"))
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
app = FastAPI(title="JorMall Deployer", docs_url=None, redoc_url=None)


def call_runner(operation: str, payload: dict[str, Any] | None = None, actor: str = "admin") -> dict[str, Any]:
    request = json.dumps({"operation": operation, "actor": actor, "payload": payload or {}}, separators=(",", ":")) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(920)
            client.connect(RUNNER_SOCKET)
            client.sendall(request.encode())
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
        response = json.loads(b"".join(chunks))
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Deployment runner is unavailable") from exc
    if not response.get("ok"):
        raise HTTPException(400, response.get("error", "Runner rejected the request"))
    return response["result"]


STYLE = """
*{box-sizing:border-box}body{font-family:Inter,system-ui,sans-serif;background:#f3f6f8;color:#142b35;margin:0}main{max-width:1280px;margin:auto;padding:28px 22px 60px}
a{color:#168dc1;text-decoration:none}h1{margin:0 0 8px}.top{display:flex;align-items:center;justify-content:space-between;gap:18px}.top nav{display:flex;gap:10px}.muted{color:#607680}.card{background:white;border:1px solid #d9e4e8;border-radius:16px;padding:22px;margin:18px 0;box-shadow:0 4px 18px #102a330b}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat strong{display:block;font-size:1.7rem}.app-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.app-card{margin:0;display:flex;flex-direction:column;gap:12px}.app-card h3{margin:0}.app-meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px}.app-meta span{color:#607680;display:block}.pill{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;background:#eaf2f5;font-size:11px;font-weight:800;text-transform:uppercase}.pill.ready{background:#e7f7ed;color:#147d3f}.pill.offline,.pill.failed{background:#feeceb;color:#b42318}.pill.compose{background:#fff1dc;color:#945500}.pill.standalone{background:#ede9fe;color:#5b21b6}
form.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}label{font-size:13px;font-weight:700}input,select,textarea{width:100%;box-sizing:border-box;padding:11px;border:1px solid #bdcbd1;border-radius:9px;margin-top:5px;background:#fff}textarea{min-height:90px;resize:vertical}
button,.button{display:inline-flex;align-items:center;justify-content:center;background:#1769aa;color:white;border:0;border-radius:9px;padding:10px 14px;cursor:pointer;font-weight:750}.danger{background:#9e2a2b}.secondary{background:#536775}.success{background:#147d3f}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px;border-bottom:1px solid #e5eaee;vertical-align:top}.ready{color:#147d3f;font-weight:700}.failed,.offline{color:#b42318;font-weight:700}.actions form{display:inline}.actions button{padding:6px 9px;margin:2px}code{font-family:ui-monospace,monospace;font-size:12px}.release-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.notice{border-left:4px solid #1769aa}details summary{cursor:pointer;font-weight:800}
@media(max-width:950px){.app-grid{grid-template-columns:repeat(2,1fr)}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:680px){form.grid,.app-grid,.stats{grid-template-columns:1fr}.table-wrap{overflow:auto}.top,.release-head{align-items:flex-start;flex-direction:column}}
"""


def layout(body: str, notice: str = "") -> str:
    message = f'<div class="card notice">{notice}</div>' if notice else ""
    return f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>JorMall Deployer</title><style>{STYLE}</style></head><body><main><div class=top><div><h1>JorMall Deployer</h1><p class=muted>All server applications, releases, and rollbacks in one place</p></div><nav><a class='button secondary' href='/'>Applications</a><a class='button secondary' href='https://jormallapp.com'>Main site</a></nav></div>{message}{body}</main></body></html>"


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def store_source_archive(source_archive: UploadFile | None) -> str | None:
    if source_archive is None or not source_archive.filename:
        return None
    if not source_archive.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Source upload must be a ZIP archive")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    upload_id = secrets.token_hex(16)
    temporary = UPLOAD_ROOT / f".{upload_id}.part"
    final = UPLOAD_ROOT / f"{upload_id}.zip"
    total = 0
    try:
        with temporary.open("xb") as destination:
            while chunk := source_archive.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Source archive exceeds the 50 MiB limit")
                destination.write(chunk)
        if total == 0:
            raise HTTPException(400, "Source archive is empty")
        os.chmod(temporary, 0o600)
        temporary.replace(final)
        return upload_id
    except Exception:
        temporary.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "healthy", "runner": call_runner("ping")["status"]}


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    applications = call_runner("catalog")["applications"]
    rows = call_runner("list")["deployments"]
    ready_count = sum(1 for item in applications if item["status"] == "READY")
    version_count = sum(int(item["version_count"]) for item in applications)
    application_cards = []
    for item in applications:
        app_name = esc(item["application"])
        status = str(item["status"]).lower()
        mode = str(item["mode"]).lower()
        current = esc(item.get("current_version") or "No release yet")
        url = "https://" + esc(item["domain"])
        application_cards.append(f"""
        <article class='card app-card'>
          <div><span class='pill {mode}'>{esc(mode)}</span> <span class='pill {status}'>{esc(item['status'])}</span></div>
          <div><h3>{esc(item['display_name'])}</h3><code>{app_name}</code></div>
          <div class=app-meta><div><span>Current version</span><strong>{current}</strong></div><div><span>Versions</span><strong>{int(item['version_count'])}</strong></div><div><span>Environment</span><strong>{esc(item['environment'])}</strong></div><div><span>Health</span><strong>{esc(item['health_status'])}</strong></div></div>
          <div style='display:flex;gap:8px;margin-top:auto'><a class=button href='/apps/{app_name}'>Manage versions</a><a class='button secondary' href='{url}' target=_blank rel=noopener>Open</a></div>
        </article>""")

    rendered = []
    for row in rows[:80]:
        did = esc(row["deployment_id"])
        actions = "".join(
            f'<form method=post action="/actions/{op}"><input type=hidden name=deployment_id value="{did}"><button class="{("danger" if op == "delete" else "secondary")}">{op.replace("_", " ").title()}</button></form>'
            for op in ("restart", "stop", "redeploy", "logs", "rotate_password", "promote", "rollback", "delete")
        )
        rendered.append(f"<tr><td>{esc(row['application'])}</td><td>{esc(row['environment'])}</td><td>{esc(row.get('release_version') or did[:12])}</td><td class='{esc(row['status'].lower())}'>{esc(row['status'])}</td><td>{esc(row['health_status'])}</td><td>{esc(row['container_state'])}</td><td>{esc(row['host_port'])}</td><td class=actions>{actions}</td></tr>")
    table = "".join(rendered) or "<tr><td colspan=11>No managed deployments yet.</td></tr>"
    body = f"""
<section class=stats><div class='card stat'><span class=muted>Registered applications</span><strong>{len(applications)}</strong></div><div class='card stat'><span class=muted>Online</span><strong>{ready_count}</strong></div><div class='card stat'><span class=muted>Recorded versions</span><strong>{version_count}</strong></div><div class='card stat'><span class=muted>ZIP maximum</span><strong>50 MiB</strong></div></section>
<section><div class=release-head><div><h2>Application registry</h2><p class=muted>Choose an application to upload a named version or roll back.</p></div></div><div class=app-grid>{''.join(application_cards)}</div></section>
<details class=card><summary>Advanced: create a custom deployment</summary><p class=muted>Use the application cards above for normal version updates. This form is for new or exceptional deployments.</p><form class=grid method=post action=/deploy enctype='multipart/form-data'>
<label>Application<input name=application required pattern='[a-z][a-z0-9-]{{0,39}}'></label>
<label>Environment<select name=environment><option>preview</option><option>staging</option><option>production</option></select></label>
<label>Docker image (option 1)<input name=image placeholder='registry/image:tag'></label>
<label>Source ZIP (option 2)<input name=source_archive type=file accept='.zip,application/zip'></label>
<label>Approved server build context (option 3)<input name=build_context placeholder='/opt/jormall/apps/app/build'></label>
<label>Container port<input name=container_port type=number min=1 max=65535 required></label>
<label>Health path<input name=health_path value='/' required></label>
<label>Protection<select name=password_protected><option value=default>environment default</option><option value=true>on</option><option value=false>off</option></select></label>
<label>Preview expiry<select name=expiry_hours><option value=''>none</option><option value=24>24 hours</option><option value=72>3 days</option><option value=168>7 days</option></select></label>
<label style='grid-column:span 2'>Environment (KEY=value, one per line)<input name=environment_variables placeholder='Leave blank to reuse the existing protected app.env'></label>
<label style='grid-column:span 2'>Persistent container paths (comma separated)<input name=persistent_mounts placeholder='/app/instance,/app/uploads'></label>
<p class=muted style='grid-column:1/-1;margin:0'>Choose exactly one source. Uploaded ZIP files must contain a root-level Dockerfile. Do not include .env files, credentials, private keys, Compose files, or Git metadata. Maximum compressed size: 50 MiB.</p>
<div><label>&nbsp;</label><button style='width:100%;margin-top:5px'>Deploy</button></div>
</form></details>
<section class=card><h2>Technical deployment history</h2><div class=table-wrap><table><thead><tr><th>App</th><th>Env</th><th>Version</th><th>Status</th><th>Health</th><th>Container</th><th>Port</th><th>Actions</th></tr></thead><tbody>{table}</tbody></table></div></section>"""
    return layout(body)


@app.get("/apps/{application}", response_class=HTMLResponse)
def application_versions(application: str) -> str:
    result = call_runner("versions", {"application": application})
    profile = result["application"]
    versions = result["versions"]
    rows = []
    for version in versions:
        status = str(version["status"]).lower()
        active = "<span class='pill ready'>current</span>" if version["active"] else ""
        rows.append(
            f"<tr><td><strong>{esc(version['version_label'])}</strong><br>{active}</td>"
            f"<td class='{esc(status)}'>{esc(version['status'])}</td>"
            f"<td>{esc(version['mode'])}</td><td><code>{esc(version['version_id'][:12])}</code></td>"
            f"<td>{esc(version['created_at'][:19].replace('T',' '))}</td>"
            f"<td>{esc(version.get('release_notes') or '')}</td></tr>"
        )
    history = "".join(rows) or "<tr><td colspan=6>No versions have been recorded yet.</td></tr>"
    current = next((version for version in versions if version["active"]), None)
    rollback = ""
    if current and current.get("previous_version_id"):
        rollback = f"<form method=post action='/apps/{esc(profile['application'])}/rollback'><button class=danger>Rollback to previous version</button></form>"
    required_dockerfile = profile.get("dockerfile") or "Dockerfile"
    body = f"""
<section class='card release-head'><div><span class='pill {esc(profile['mode'])}'>{esc(profile['mode'])}</span><h2>{esc(profile['display_name'])}</h2><p class=muted><code>{esc(profile['application'])}</code> · {esc(profile['environment'])} · <a href='https://{esc(profile['domain'])}' target=_blank rel=noopener>{esc(profile['domain'])}</a></p></div>{rollback}</section>
<section class=card><h2>Upload a new version</h2><form class=grid method=post action='/apps/{esc(profile['application'])}/release' enctype='multipart/form-data'>
<label>Version<input name=version required maxlength=64 pattern='[A-Za-z0-9][A-Za-z0-9._+\x2d]{{0,63}}' placeholder='v1.2.0'></label>
<label style='grid-column:span 2'>Source ZIP<input name=source_archive type=file required accept='.zip,application/zip'></label>
<label style='grid-column:1/-1'>Release notes<textarea name=release_notes maxlength=2000 placeholder='What changed in this version?'></textarea></label>
<p class=muted style='grid-column:1/-1;margin:0'>The ZIP must contain a root-level <code>{esc(required_dockerfile)}</code>. Secrets, .env files, keys, Git metadata, and Compose files are rejected. Existing server environment files and persistent data are preserved.</p>
<div><button class=success>Validate, build, and deploy</button></div></form></section>
<section class=card><h2>Version history</h2><div class=table-wrap><table><thead><tr><th>Version</th><th>Status</th><th>Mode</th><th>ID</th><th>Created</th><th>Notes</th></tr></thead><tbody>{history}</tbody></table></div></section>"""
    return layout(body)


@app.post("/apps/{application}/release", response_class=HTMLResponse)
def upload_release(application: str, request: Request, version: str = Form(),
                   release_notes: str = Form(""), source_archive: UploadFile = File()) -> str:
    upload_id = store_source_archive(source_archive)
    try:
        result = call_runner(
            "release",
            {"application": application, "version": version, "release_notes": release_notes, "upload_id": upload_id},
            actor=request.headers.get("x-authenticated-user", "admin"),
        )
    except Exception:
        if upload_id:
            (UPLOAD_ROOT / f"{upload_id}.zip").unlink(missing_ok=True)
        raise
    body = f"<section class='card notice'><h2>Version deployed successfully</h2><p><strong>{esc(result.get('application', application))}</strong> is now running version <code>{esc(result.get('version', version))}</code>.</p><p>Status: <span class='pill ready'>{esc(result['status'])}</span></p><p><a class=button href='/apps/{esc(application)}'>Return to version history</a> <a class='button secondary' href='https://{esc(result['domain'])}' target=_blank rel=noopener>Open application</a></p></section>"
    return layout(body)


@app.post("/apps/{application}/rollback", response_class=HTMLResponse)
def rollback_application(application: str, request: Request) -> RedirectResponse:
    call_runner(
        "rollback_app", {"application": application},
        actor=request.headers.get("x-authenticated-user", "admin"),
    )
    return RedirectResponse(f"/apps/{application}", status_code=303)


@app.post("/deploy", response_class=HTMLResponse)
def create_deployment(request: Request, application: str = Form(), environment: str = Form(), image: str = Form(),
                      container_port: int = Form(), health_path: str = Form("/"), password_protected: str = Form("default"),
                      expiry_hours: str = Form(""), build_context: str = Form(""), environment_variables: str = Form(""),
                      persistent_mounts: str = Form(""), source_archive: UploadFile | None = File(None)) -> str:
    upload_id = store_source_archive(source_archive)
    payload: dict[str, Any] = {"application": application, "environment": environment, "image": image,
                               "container_port": container_port, "health_path": health_path,
                               "expiry_hours": int(expiry_hours) if expiry_hours else None,
                               "build_context": build_context or None, "upload_id": upload_id}
    if persistent_mounts.strip():
        payload["persistent_mounts"] = [
            {
                "name": path.strip().rstrip("/").rsplit("/", 1)[-1].replace("_", "-").lower(),
                "container_path": path.strip(),
            }
            for path in persistent_mounts.split(",") if path.strip()
        ]
    if environment_variables.strip():
        values = {}
        for raw_line in environment_variables.splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            if "=" not in raw_line:
                raise HTTPException(400, "Environment lines must use KEY=value")
            key, value = raw_line.split("=", 1)
            if key.strip() in values:
                raise HTTPException(400, "Duplicate environment key")
            values[key.strip()] = value
        payload["environment_variables"] = values
    if password_protected != "default":
        payload["password_protected"] = password_protected == "true"
    try:
        result = call_runner("deploy", payload, actor=request.headers.get("x-authenticated-user", "admin"))
    except Exception:
        if upload_id:
            (UPLOAD_ROOT / f"{upload_id}.zip").unlink(missing_ok=True)
        raise
    secret = ""
    if result.get("password"):
        secret = f"<p><strong>One-time preview credential:</strong> username <code>{result['password_username']}</code>, password <code>{result['password']}</code>. Save it now; it is not logged.</p>"
    return layout(f"<div class=card><h2>Deployment {result['status']}</h2><p>{result['domain']} on loopback port {result['host_port']}.</p>{secret}<p><a href='/'>Return to dashboard</a></p></div>")


@app.post("/actions/{operation}", response_class=HTMLResponse)
def action(operation: str, request: Request, deployment_id: str = Form()):
    if operation not in {"restart", "stop", "redeploy", "logs", "rotate_password", "rollback", "promote", "delete"}:
        raise HTTPException(404)
    result = call_runner(operation, {"deployment_id": deployment_id}, actor=request.headers.get("x-authenticated-user", "admin"))
    if operation == "logs":
        import html
        return layout(f"<div class=card><h2>Container logs</h2><pre>{html.escape(result['logs'])}</pre><p><a href='/'>Return to dashboard</a></p></div>")
    if result.get("password"):
        return layout(f"<div class=card><h2>{operation.replace('_', ' ').title()} complete</h2><p><strong>One-time credential:</strong> username <code>{result['password_username']}</code>, password <code>{result['password']}</code>.</p><p>Save it now; it is not logged.</p><p><a href='/'>Return to dashboard</a></p></div>")
    return RedirectResponse("/", status_code=303)
