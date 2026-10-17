# FIELDMIND security hardening evidence — 2026-10-17

Scope: continue draft PR #11 from `ec2fdf8` against main `86b5192`. Review the mounted `app.pilot:app`, its two routers, browser UI, migrations 001–007, dependency lock and CI. This is a focused code review and regression suite, not a penetration test, platform audit or production-safety certificate.

## Verified issues and changes

| Finding | Change | Evidence |
|---|---|---|
| A viewer could create/delete saved searches, contradicting the locked read-only role | Apply the existing write-role guard to both routes | HTTP rejection tests; real PostgreSQL search ownership test |
| Entity alias creation checked that a team/player existed but not whether its roster was private to another program | Scope customer roster references by program; retain public-source references | PostgreSQL tests distinguish own, foreign, missing and shared team/player IDs |
| Week/player references relied on DB triggers for foreign-roster rejection, producing server errors | Validate roster ownership in the API before mutation; retain existing DB triggers | Cross-program plan and player-evidence tests |
| Week-plan upsert could alter opponent/team after Thursday freeze; repeat freeze changed its timestamp | Conditional SQL upsert rejects frozen rows; preserve the original freeze timestamp | PostgreSQL regression exercises update, repeat freeze, blocked inputs and permitted outcome log |
| Write models silently discarded unknown fields | Forbid extra fields, including nested tag and telestrate models; reject non-finite typed floats | Actual HTTP requests with injected program/role/resolver fields |
| No pilot request-body limit | Enforce a 1 MiB JSON-metadata limit with the already-pinned Starlette middleware | Declared, absent-length/chunked and underdeclared body tests; no handler completion on over-limit body |
| No CSP/clickjacking/security-header policy | Deny frames/objects, same-origin scripts/connections, no inline JS/eval; nosniff, no-referrer, no-store and restricted browser permissions; HSTS only for server-trusted HTTPS scheme | Production-entrypoint tests on success, auth, unavailable, missing and unhandled-error responses |
| Inline browser event handlers prevented a useful strict script policy | Move JS to an explicit same-origin file route and dispatch only named allowed actions | Browser regression script exercises finder, clip bay, tags, call review and freeze, plus actual CSP blocking |
| Stored historical URLs were trusted by the browser | Require HTTPS/no embedded credentials for new film links and validate historical URLs before rendering | API bad-scheme/credentials tests; browser rejects a malicious stored URL |
| Arbitrary request IDs were echoed into response headers/log correlation | Accept 1–64 safe identifier characters; otherwise generate a UUID | Production-entrypoint tests with normal and oversized/invalid IDs |
| `.env.production` and other environment variants were not ignored | Ignore `.env.*` except `.env.example`, plus private-key extensions | Git ignore smoke check; this is not historical secret scanning |
| Workflow token privileges were implicit | Declare `contents: read` | Workflow diff review |

## Verification and reproduction

Local baseline: **32 passed, 1 skipped** before changes. Updated local suite: **55 passed, 8 skipped**. The eight skips require migrated PostgreSQL: one existing hub test plus seven new hardening cases. Local PostgreSQL provisioning was unavailable in this execution environment. CI run [43](https://github.com/lvlitup808-ship-it/NFL-COLLEGE-FOOTBALL-DATA-/actions/runs/39064303944) passed on code commit `1c10d44592821d28e6cf5af46bc6ec2ef6b4044d`: 55 passed / 8 skipped in the general stage, then 21 passed / 0 skipped in the hub + PostgreSQL stage (including the eight previously skipped database cases). The stages overlap; do not add them as unique test counts. Migration/seed/idempotent ingest, source/tag separation, the small-fixture benchmark, browser workflows/CSP, Docker build and both startup smoke checks all passed. This proves behavior on synthetic test data, not production scale.

```bash
python -m pip install -r requirements.lock
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
```

Disposable database only (the tests create and remove uniquely named fixtures):

```bash
python scripts/migrate.py
python scripts/seed.py
python scripts/ingest_nflverse.py --season 2025 --url tests/fixtures/nflverse_sample.csv
python scripts/ingest_cfbd.py --season 2025 --week 1 --fixture tests/fixtures/cfbd_sample.json
HUB_DB_TEST=1 HARDENING_DB_TEST=1 python -m pytest -q tests/test_hub_clip_ids.py tests/test_security_db.py
```

With Node, Playwright 1.62.1 and its Chromium installed, start the local pilot on port 8765 and run `node tests/browser_security.cjs`. `PILOT_TEST_URL` can select another local port. The browser suite supplies API fixtures; it tests UI behavior and browser policy enforcement, not real backend authentication. PostgreSQL tests cover that separate boundary. Chromium was unavailable locally and its download failed; the same browser suite passed in CI run 43, which installs pinned Playwright and runs this check alongside Python/database/container checks.

## Behavior changes to review

- Saved searches now require owner/coach/GA. Viewers retain reads. Role labels remain the existing `owner`, `coach`, `ga`, `viewer`; display/job titles cannot grant permissions.
- Unknown JSON keys now return 422 instead of being ignored. Clients with extra fields must remove them.
- JSON bodies above 1 MiB return 413. Video upload endpoints do not exist in this pilot; introduce a separate bounded, private media design before adding them.
- Film links must use HTTPS and omit user/password URL credentials. Existing non-HTTPS links will not open in the clip bay; replace them with authorized HTTPS links.
- CSP allows inline **styles** for the existing UI, but forbids inline **JavaScript**. HTTPS media remains allowed for authorized external film. No claim is made that the destination's sharing permissions are private.
- No migration, data rewrite, merge, production config change or deployment is part of this PR. Existing migrations, source/tag separation, n-guards, two-GA resolution and post-freeze outcome logging remain in place.

## Open risks and next acceptance gates

1. **Auth abuse and lifecycle:** no distributed rate limit, owner MFA, self-service logout/revocation or short-session flow yet. Tokens expire/revoke in the database; provisioning defaults to 30 days. The UI still uses sessionStorage, so an origin compromise could expose a token. CSP reduces risk; it does not eliminate it.
2. **Operational evidence:** production TLS/proxy trust, backup encryption, restore/PITR exercise, RTO/RPO, least-privilege runtime DB role, branch protection, secret rotation, dependency advisories/image scanning, billing alerts and data residency were not inspected or changed. A lockfile is not a vulnerability scan or a byte-hash guarantee.
3. **Concurrency/immutability:** existing child-table freeze triggers do not lock the parent plan while checking its status. Race testing and a forward-only migration may be needed to establish a strict concurrent freeze boundary. Tag recomputation/coach resolution and simultaneous roster creation need separate transaction/race review. This patch closes the reproducible sequential upsert bypass, not every race.
4. **Privacy:** historical entity aliases, external film sharing permissions, logs (including exception content), retention, exports and incident audit coverage still need review. No database-wide RLS has been enabled. Existing API scoping and selective triggers are not full RLS.
5. **Performance/reliability:** measured query plans, pool-acquisition deadlines, load/soak tests, p99, pagination and restore rehearsals remain unverified. Advanced queues/replicas/sharding/consensus are deferred for this single-worker pilot.
6. **Future features:** there is no mounted upload, payment, email, webhook or AI endpoint. Their controls are explicit pre-launch gates, not implemented protections. No Footage Lab or proprietary footage is brought into this branch.

## References used for the HTTP design

- [OWASP Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [OWASP Cross-Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [Starlette middleware](https://www.starlette.io/middleware/) and the installed `starlette==1.6.0` request-body-limit implementation

The complete 250-topic adoption plan is [ENGINEERING_HARDENING_250.md](ENGINEERING_HARDENING_250.md). Current CI outcomes and review status are recorded on PR #11; this dated report must not be interpreted as a live production-health claim.
