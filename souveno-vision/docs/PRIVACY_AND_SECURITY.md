# Privacy & Security — Souveno Vision Intelligence

**UI statement (shown on every page):**
> This demonstration uses anonymous, camera-local tracking IDs. It does not identify employees.

## What the demo does and does not do

| Topic | Position |
|---|---|
| Identification | **No facial recognition, no biometric templates, no employee-name assignment.** Every person is a temporary, camera-local `Person N` that resets when the source restarts. The same person is *not* recognised across cameras or sessions. |
| Processing location | **On-premise.** Video is decoded and analysed on the machine running the app. No frames leave the host. |
| Data leaving the host | Only if the operator explicitly enables the **webhook**: structured event JSON (type, time, camera, zone, anonymous ID, severity). Snapshots and clips are never posted. |
| Camera credentials | Entered at runtime or via environment variables. Kept in memory only, **masked in all logs** (`rtsp://***:***@host/...`), never written to SQLite or YAML. Recommend a **read-only** camera/NVR account. |
| Evidence | Annotated snapshot per alert; short pre/post clip where feasible. Stored locally under `data/evidence/`, **configurable retention** (default 14 days), storage cap, automatic cleanup. No continuous recording. |
| Audit | Every acknowledgement / resolution / dismissal is logged with actor, note and time (`acknowledgements` table). |
| Logs | Rotating text + JSON logs, credential-redacting patcher on every record. |
| Access to the dashboard | Bound to `127.0.0.1` by default. Binding to `0.0.0.0` exposes it on the LAN **without authentication** — do this only on a trusted network for a demo. |

## Requirements before production (not implemented in this proof of concept)

1. **Role-based access control** (viewer / operator / administrator) with SSO; per-action audit.
2. **Restricted access to snapshots and clips** — file-system permissions, signed URLs, expiry.
3. **Privacy notice & employee-policy review** — works council / HR consultation, signage,
   purpose limitation (safety, operations — not performance surveillance of individuals),
   retention schedule signed off by the client's DPO/legal.
4. **Data protection impact assessment** for the pilot areas.
5. **Network isolation**: camera VLAN, read-only service credentials, no inbound access from cameras.
6. **Encryption at rest** for evidence and the event database where policy requires it.
7. **Retention policy** per data class (events, evidence, health logs) enforced centrally.
8. **Model governance**: document what the model detects (persons only), known failure modes, and
   how false alerts are measured and reviewed.

## Threat notes for this build

* The dashboard has no login. Anyone who can reach the port can start/stop sources, view video and
  evidence, and change rules. Keep it on localhost during the demo.
* Uploaded videos and evidence live in `data/`. Do not run the app from a shared folder.
* The webhook posts to whatever URL is configured; use HTTPS endpoints and the optional
  `SOUVENO_WEBHOOK_AUTH` header in anything beyond a local test.
* The AGPL-licensed detector is a licensing risk, not a security one — see `LICENSING.md`.
