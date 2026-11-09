# Service runbook — hardened historical replay and pilot scaffold

## What this system is, and what is not validated

The analytics, API and release system are implemented and locally tested. The service replays historical operational-support scores using a smoothed state-only baseline. It **does not approve credit**, prove intervention benefit or validate lending decisions. The release permits 2016 creation cohorts only; new cohorts require a newly trained and validated release with an appropriate scope.

A local smoke/concurrency probe is not a production load test or availability guarantee. The Docker image build, Python 3.12/3.14 test jobs, and full real-data rebuild with release creation passed in GitHub Linux CI. A local Docker build was not run because Docker was unavailable. Hosted container-runtime smoke results are recorded separately in publication evidence. Sustained hosted operation is not established.

## Start locally

From the repository root, after building the analytical project:

```bash
python -m pip install -e '.[api,dev]'
python -m loanflow.pipeline
python -m loanflow.release
# Generate a strong key and keep it in the current process environment:
export LOANFLOW_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn loanflow.service:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

The service fails startup when the key is missing/short, the active pointer is invalid, or a release fails verification. The key is not written into the repository. For a hosted environment, inject it through the deployment platform's secret manager and put TLS plus ingress controls in front of the service. Do not paste it into a frontend or dashboard.

`python scripts/smoke_service.py` starts its own short-lived loopback server, generates a temporary key in memory, replays a real source application, verifies failure cases, runs a bounded concurrent probe and stops its process. It writes measured evidence to `reports/service_smoke.json` without saving the key.

## API contract

| Route | Access | Purpose |
|---|---|---|
| GET /healthz | Public | Process liveness only |
| GET /readyz | Public | Verified release loaded; returns release identity |
| POST /v1/score | Bearer key | Score a complete, strictly pre-day-seven event history |
| GET /v1/model | Bearer key | Release/model policy and training count |
| GET /v1/monitor | Bearer key | Aggregate request-state drift and fallback counts |
| GET /metrics | Bearer key | Prometheus-compatible per-process request/latency/fallback metrics |

Public interactive API docs are disabled. The exported contract is in `docs/openapi.json`. Responses carry request IDs and no-store headers. Input-validation responses omit raw input values. Application logs contain route templates, status, timing and random request IDs; they omit credentials, request bodies, source application IDs and query text. Uvicorn access logs are disabled in the supplied startup commands.

The score request requires timezone-aware creation and scoring times, exactly a seven-day gap, unique strict-integer source sequences, a creation-timestamp event, a known event vocabulary, and no pre-landmark terminal event. Events at or after the landmark are rejected. The body and event counts are bounded; unknown fields are rejected. The API cannot verify that a caller omitted an event: completeness must be enforced by the source adapter and reconciled against its upstream log.

## Release and rollback

`python -m loanflow.release` verifies analytical checks, original source/extraction hashes and the finalized warehouse hash, then exports a JSON state model. The serving process does **not** deserialize pickle/joblib or access the mutable working database. Model probabilities, source evidence, metrics and policy have an immutable content-based release identity and per-file hashes.

`releases/CURRENT` is replaced atomically only after a complete release verifies. The API loads one verified release at startup and remains pinned to it. Building a new release cannot mix artifacts inside an existing process.

```bash
python -m loanflow.release --activate lf-REPLACE_WITH_AN_EXISTING_VERIFIED_RELEASE_ID
# Restart the service; verify /readyz reports the intended release.
```

Only use an actual release ID from your release directory, never the illustrative text above. Activation verifies it before replacing CURRENT. Keep at least the previous known-good release and its deployment image until the new release is accepted. Restore release directories from read-only, checksummed backups; a content hash establishes integrity, not authorship. Protect the release store and image registry through normal deployment access controls.

The local analytical build uses a single-writer lock. If a crashed build leaves `.build.lock`, check that the recorded build is no longer running before removing the stale lock. Service release isolation protects the running API even when an analytical rebuild fails midway.

## Container operation

```bash
docker compose up --build
```

The compose file binds to loopback, mounts releases read-only, runs as UID 10001, drops Linux capabilities, uses a read-only filesystem and limits memory/CPU. It requires an injected key. The image contains code and dependencies, not source data, API keys or release artifacts. Pin a reviewed base-image digest and dependency resolution in your deployment registry before a controlled hosted rollout; the supplied Dockerfile is a portable starting point, not a claim of a locally built/signed image.

## Monitoring and failure response

| Signal | Initial response |
|---|---|
| Readiness fails at startup | Check key injection, release availability and hashes; do not weaken integrity checks |
| Increased 401 | Check key rotation/client configuration; never print credentials for debugging |
| Increased 413/422 | Check request-size or schema/timestamp/eligibility drift; reconcile the source adapter |
| Increased 429 | Check expected volume and upstream throttling; do not infer a model problem |
| Increased 500 / latency | Use request IDs, release identity and aggregate metrics to reproduce safely; roll back if appropriate |
| Elevated fallback / state-distribution change | Inspect source event semantics and cohort mix; require enough volume before interpretation |
| Delayed labeled-outcome deterioration | Re-evaluate calibration, ranking and customer outcomes by cohort; a request-only monitor cannot measure accuracy |

Rate limiting is a shared in-process budget for authenticated calls, not a distributed gateway. The latency metric is a bounded recent-request window, not a Prometheus histogram or durable SLO record. State monitoring is per-process and resets on restart. Multiple replicas require shared ingress controls and external durable monitoring. There is no automatic retraining or outcome feedback endpoint. These boundaries are deliberate and explicit.

Before a live pilot: validate the source adapter and field history; obtain domain-approved endpoints and guardrails; establish data handling, retention, backup, identity and incident procedures; perform hosted load/failure testing; and review intervention cost and customer outcomes. No live institution, sensitive customer data or external bank system is connected in this project.
