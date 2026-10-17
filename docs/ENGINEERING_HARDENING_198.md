# FIELDMIND Engineering Hardening — 198-topic adoption plan

**Status:** Engineering policy and release gate, **not** a claim that all controls are implemented or audited. Scope: FIELDMIND FastAPI/Railway/PostgreSQL backend, member authentication, and future private multi-tenant Footage Lab.

## Risk-ranked rollout

### P0 — Block public consumer launch until verified
- **Identity, tenancy, authorization:** server-side auth on every private endpoint; program_id isolation on queries and storage; RBAC roles for Head Coach, Coordinator, Position Coach, and separate Owner/Admin privilege; IDOR tests; least-privilege database credentials; PostgreSQL RLS where appropriate (not a substitute for API checks). Role selection must never grant admin rights.
- **Accounts:** Argon2id (or reviewed bcrypt) salted password hashes; short-lived signed sessions/tokens, rotation and invalidation; CSRF protection if using cookie auth; secure HttpOnly SameSite cookies; MFA for admins; brute-force rate limits; uniform login/reset responses; session fixation prevention; OAuth/OIDC only with state/nonce/PKCE and issuer/audience checks.
- **Application threats:** parameterized SQL, output encoding/XSS controls, strict input validation, mass-assignment allowlists, SSRF egress and hostname/IP checks, path traversal-safe storage keys, restricted CORS, CSP, clickjacking protection, security headers, HSTS only after TLS confirmed, webhook signature verification.
- **Uploads:** authenticated, program-scoped private object storage; content sniffing, size/duration limits, decode sandbox, malicious-file rejection, quotas, retention/deletion controls, signed URLs and audit logs. Never put user footage or uploaded proprietary playbooks in a public Git repo.
- **Secrets/supply chain:** .env ignored, repository secret scanning, rotate previously exposed Resend credential, no secret values in logs; dependency locking, SBOM/scans, review external YOLO/OSNet model weight licenses and provenance; non-root containers, staged deployment and rollback.
- **Recovery:** encrypted backups, restore rehearsal, documented RPO/RTO, incident runbook, owner alerting. No payment collection until independent payment provider and threat review.

### P1 — Reliability and performance before beta scale
- Database: explain/analyze real slow queries; indexes on program_id, job_id, created_at; prevent N+1 queries; transaction boundaries, unique constraints, foreign keys, optimistic locking for coach corrections, forward and rollback migration drills; connection pool limits; cursor pagination; VACUUM and storage monitoring.
- Jobs: queue and isolate FFmpeg/CV workers; concurrency limits; idempotency keys; at-least-once processing; bounded retries with jitter, dead-letter queues, poison-job quarantine; backpressure/load shedding; progress SSE; graceful shutdown; cache keys/versioning and expiry; CDN only for public assets.
- Operations: health/readiness probes; structured redacted logs, request/job correlation IDs, tracing, p95/p99, metrics cardinality limits, error budget, SLO, alerts, runbooks, rollback and canary process; load test large uploads and long jobs; memory/OOM limits and video decode timeouts.
- APIs: versioned OpenAPI, size/rate limits, consistent status codes, idempotent semantics, ETags where useful, backward compatibility tests, browser security integration tests.

### P2 — Architecture only if actual scale demands it
- Redis caching/eviction, read replicas and replication lag, partitioning, materialized views, CDC/outbox, CQRS/event sourcing, Kafka ordering/consumer groups, distributed locks, sharding and hot partitions, Raft/leader election, quorums, multi-region failover, service mesh, gRPC/protobuf, Terraform/GitOps, Kubernetes PDBs and ingress controllers. Do **not** install these for a single-worker pilot without measured need.

## Traceability index for all 198 user-requested topics

Each category includes the original topic numbers; every topic is either a **release gate**, **operational practice**, or **defer until scale**. This is a coverage map, not a compliance certificate.

| Area | Original items | Adoption |
|---|---|---|
| AppSec and secure web delivery | 1–16, 33–40 | P0 |
| Identity, secrets and cryptography | 17–32 | P0 |
| Relational DB design/performance and recovery | 41–75 | P0 backups, P1 most DB topics; advanced P2 |
| Distributed systems and concurrency | 76–97 | P1 retries/races/backpressure; P2 consensus/2PC |
| Caching and delivery | 98–106 | P1 basic caching; P2 Redis/CDN |
| Queues and background processing | 107–115 | P1 |
| Networking, API and protocol design | 116–132 | P0 TLS, P1 APIs; P2 WebSockets/gRPC |
| Infrastructure/network security | 133–150 | P0 network exposure; P1 resilience; P2 multi-region/mesh |
| SRE and disaster recovery | 151–179 | P0 restore/incident; P1 telemetry/SLO; P2 chaos |
| Delivery, containers, versioning, source controls | 180–198 | P0 secrets/dependencies/branch protection, P1 CI/CD, P2 orchestration |

## Implementation acceptance checklist

- [ ] Tenant A cannot read/edit/export Tenant B clips, tracks, notes or member data (API + DB + object storage).
- [ ] Head Coach/Coordinator/Position Coach selection cannot access owner admin analytics.
- [ ] CSRF/XSS/SQLi/SSRF/path traversal/IDOR/mass assignment tests cover real routes.
- [ ] Resend secret rotated and stored in Railway; no secret exposed in git/history/logs.
- [ ] Video file spoofing, oversized uploads, decompression bombs, codec errors and processing timeouts rejected safely.
- [ ] Background job replay is idempotent and worker failure leaves recoverable state.
- [ ] Postgres restore from a backup demonstrated in staging, with recovery time recorded.
- [ ] Dependencies, container images and model weights reviewed for licenses and vulnerabilities.
- [ ] Logs, traces, and exports exclude raw private footage, passwords, secrets and sensitive tokens.
- [ ] Rate-limited authentication and owner MFA exercised end-to-end.
- [ ] Staging-to-production rollback tested; branch protection and required CI enabled.
- [ ] Each control has owner, test evidence, date, and pass/fail status in a separate audit log.

## Release rule

Do not declare production-safe until the P0 checklist has real test evidence. Never confuse a written checklist with implemented protections. Prioritize the existing FastAPI service and member portal; keep Footage Lab uploads local until tenant isolation and private media storage pass tests.
