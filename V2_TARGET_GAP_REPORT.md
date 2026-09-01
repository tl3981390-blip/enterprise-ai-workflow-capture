# V2 Target Gap Report — enterprise-ai-workflow-capture v1.0.1 → v2.0.0

Date: 2026-09-01. Baseline: tag `v1.0.1` = commit `b56ee0d53d8b73e237b1ba1f4f29d37390edc3e0`, working tree clean and identical to tag, 20/20 baseline tests PASS (Python 3.14.6, SQLite 3.50.4).

Purpose: reconcile the shipped v1.0.1 product against the v2 product target — *"企业规定业务任务调用 Skill 后，低负担自动沉淀真实 AI 工作路径"* — before any construction. Every current asset is classified as **KEEP** (inherit as-is), **MODIFY** (change behavior/contract), **REMOVE** (delete because it blocks high-frequency enterprise capture without adding truthfulness), **DELEGATE_TO_HARNESS** (enterprise/harness responsibility, never built here), or **NOT_NEEDED** (explicitly not built this round).

## 1. Product-level reconciliation

| # | v1.0.1 behavior | v2 target | Disposition |
|---|---|---|---|
| P1 | Record created only after explicit invocation + interactive TTY confirmation | Two lawful entry modes: `ENTERPRISE_MANAGED_CAPTURE` (harness-authorized, no per-record human interaction) and `PERSONAL_EXPLICIT_CAPTURE` (explicit confirmation preserved) | **MODIFY** — confirmation stops being the product-level hard gate; Enterprise Capture Authorization becomes the gate |
| P2 | "Save a chat workflow occasionally" framing | "Enterprise-mandated, low-friction structured sedimentation of real task paths" framing | **MODIFY** — README/SKILL/docs repositioning |
| P3 | Active-call only, no passive monitoring | Unchanged boundary | **KEEP** (+ mechanical no-network/no-background test) |
| P4 | Skill, not a platform | Unchanged; identity/authorization/workspace/storage credentials stay outside | **KEEP** + **DELEGATE_TO_HARNESS** (see §5) |
| P5 | No employee scoring, no BEST_KNOWN_PATH promotion | Unchanged; additionally machine-enforced at validation | **KEEP** + harden |
| P6 | SQLite is the only storage | SQLite = local/personal/reference; Storage Adapter Contract added; enterprise storage via adapter | **MODIFY** |
| P7 | Business success and capture persistence not distinguished | `TASK_COMPLETED_CAPTURE_PERSISTED / _PENDING / _FAILED`; capture failure never masks task outcome | **MODIFY** (new state taxonomy) |

## 2. KEEP — directly inherited (verified correct, do not regress)

| Asset | What is kept |
|---|---|
| `workflow_capture/redaction.py` | Sanitize-before-validate-before-persist pipeline; redaction finding reporting (patterns extended, mechanism kept) |
| `workflow_capture/util.py` | `canonical_json`, `digest` (SHA-256), `new_id` prefixed-UUID identity, `utc_now`, `normalize_label` |
| `workflow_capture/database.py` migrations 1–3 | Transactional forward-only migrations, `schema_migrations` checksums, refuse-newer-database |
| Evidence hash chain | Per-task append-only chain, `previous_hash` linkage, `verify_evidence_chains`, tamper detection in `doctor` |
| Internal vs external evidence separation | Caller-supplied `content_hash` rejected; typed external digest + algorithm + verification state; `legacy_unverified` honesty |
| `confirmations` state machine | `PREPARED → CONFIRMED → CONSUMED`, atomic consumption, exact payload-hash binding — retained for PERSONAL_EXPLICIT_CAPTURE |
| Lineage | `lineage` rows linking evidence → process; Raw vs Derived table separation; `derived_knowledge` has no write API |
| `similar_tasks` | Conservative normalized-task-type matching, disclosed `match_basis`, candidate-not-truth semantics |
| Read-back verification | Commit-time re-read + hash compare + consumption verification |
| Validation core | Actor/event/provenance/adoption enums, required-field checks, structured errors |
| CLI plumbing | JSON stdout/stderr, exit-code discipline, `doctor`/`migrate`/`show`/`similar` |
| `scripts/build_release.py`, `scripts/install.py` | Deterministic ZIP + SHA256SUMS; offline installer with self-check |
| Tests 1–20 | Entire v1.0.1 suite retained as regression (must pass unchanged) |

## 3. MODIFY — changed for v2

| Asset | Gap vs v2 target | v2 change |
|---|---|---|
| `SKILL.md` | Interactive terminal confirm is the only path — unsuitable as high-frequency enterprise UX | Rewrite: dual-mode capture. Enterprise mode = one mechanical pass (sanitize → validate → persist → read-back) under a valid harness grant. Personal mode = explicit confirmation. Fail-closed without authorization |
| `README.md` | Frames product as occasional explicit save | Reframe: enterprise-mandated low-burden task-path sedimentation; keep all boundary statements |
| `references/capture-contract.md` | Missing v2 fields: session identity, task timing, per-event timing/tool identity, decision events, human-intervention structure, AI context, business context | Contract v2: adds `capture_session_id`, `started_at`/`completed_at`, `business_context` (provenance-tagged, ref hashed), step-level `occurred_at`/`duration_ms`/`capability`/`intervention`, task-level `ai_context`; event type `decision`; unknown stays unknown |
| `workflow_capture/validation.py` | No session id, no timing fields, no scoring-field guard, no transcript-size guard, event types lack `decision` | Extend enums + optional-field validation; reject employee-scoring field names; reject oversized evidence excerpts (anti-transcript); provenance rules (`ai_inferred` requires confidence) |
| `workflow_capture/redaction.py` | Misses JWT / AWS / GitHub-token shapes | Add patterns; keep mechanism and finding reporting |
| `workflow_capture/database.py` | Schema v3 cannot hold session identity, capture mode/status, timing, business context | Migration 4 (new schema v4): tasks + `capture_session_id UNIQUE` (nullable), `capture_mode`, `capture_status`, `started_at`/`completed_at`, `business_context_ref_hash`, `business_context_json`, `authorization_json`; steps + `occurred_at`, `duration_ms`, `capability_json`, `intervention_json`; derived_knowledge + `sample_size`; honest legacy mapping |
| `workflow_capture/service.py` | Single SQLite path; no enterprise one-shot; no authorization; no idempotent session retry | Route all persistence through Storage Adapter; add `capture()` (enterprise one-shot with grant enforcement, idempotency, read-back, honest failure status); keep `prepare/confirm/commit` for personal mode |
| `workflow_capture/cli.py` | No `capture` command; no authorization surface | Add `capture` (enterprise), keep existing commands; new exit codes distinguishing authorization refusal (4) and capture-storage failure (5) from usage errors (2) and DB errors (3) |
| `references/data-model.md` | Documents v3 | Document v4: new columns, status taxonomy, seven future questions ↔ data mapping |
| `references/privacy-policy.md` | Confirmation-gate centric | Dual-mode privacy: enterprise authorization scope, minimization unchanged, no-transcript rule, retention delegated |
| `docs/SECURITY.md` | No authorization threat model | Add Enterprise Capture Authorization boundary, forgery resistance, fail-closed rules, honest attestation levels |
| `docs/ACCEPTANCE.md`, `docs/INSTALL.md`, `CHANGELOG.md`, `pyproject.toml`, `agents/openai.yaml` | v1 text/version | v2 updates; version 2.0.0 |

## 4. REMOVE — blocks high-frequency capture without adding truthfulness

| Asset / behavior | Why removed |
|---|---|
| Product-level rule "every record requires interactive human confirmation" | Replaced by Enterprise Capture Authorization. In enterprise mode, employee invocation under a valid harness grant is the approved entry; per-record terminal interaction adds burden, not truth (the confirmation state machine itself is **KEPT** for personal mode and as an audit-capable mechanism) |
| README quick-start presenting interactive confirm as *the* capture flow | Replaced by dual-mode quick start (enterprise `capture`, personal `prepare/confirm/commit`) |

Nothing else is removed. No v1.0.1 mechanism that protects truthfulness (sanitize, hash binding, read-back, consumption-once) is deleted; the personal mode keeps them all and enterprise mode keeps sanitize/validate/hash/read-back.

## 5. DELEGATE_TO_HARNESS — provided by enterprise environment, never built here

| Concern | v2 interface |
|---|---|
| Enterprise capture authorization fact | Grant JSON at `WORKFLOW_CAPTURE_AUTHORIZATION_FILE` (env-designated path), optional HMAC signature verified with `WORKFLOW_CAPTURE_AUTHORIZATION_KEY` (env-only secret). Never from candidate payload, CLI flags, or conversation. Missing/invalid/expired/out-of-scope → fail closed |
| Employee identity, SSO, org roles | Not collected. Optional confirmer identity/source (personal mode) and grant issuer/department scope stay harness-asserted |
| Enterprise storage (PostgreSQL/internal API/approved DB) | `ENTERPRISE_STORAGE_ADAPTER`: enterprise supplies a Python module implementing the Storage Adapter Contract (`WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE`); credentials never in this repo |
| Retention/deletion/encryption at rest/backup | Deployment policy; grant carries `retention_policy` reference, runtime records it, does not enforce deletion |
| Signed identity attestation beyond HMAC key distribution | Remains `PENDING_EXTERNAL_VALIDATION` (harness-native signed assertions) |

## 6. NOT_NEEDED — explicitly not built this round

| Candidate | Reason |
|---|---|
| Intent detection ("is this a business task?") | Company process already decides; invocation is the entry action |
| Path-optimization / BEST_KNOWN_PATH algorithm | Contract §6/§7: v2 only leaves sufficient data; insufficient-sample claims stay impossible (no write API) |
| Derived-knowledge write API / analytics engine | Raw vs Derived separation preserved; derived remains future/external with lineage contract |
| Employee scores/rankings/leaderboards | Forbidden by contract §12; validation mechanically rejects scoring fields |
| Enterprise admin console / monitoring dashboard / data lake | Not a platform (contract §2) |
| Real PostgreSQL connector in this repo | Enterprise adapter is deployment-supplied; contract test suite proves substitutability without shipping credentials or drivers |
| Passive/background capture, screen or session scraping | Forbidden (contract §2); static test asserts no network/background facilities |
| Automatic capture retry queue / outbox | Re-write policy is enterprise's (§10); runtime exposes idempotent re-invocation with the same `capture_session_id` instead |

## 7. Adversarial coverage plan (Phase 2)

All 18 contract attack scenarios map to executable tests or checks: unauthorized capture; forged/model-fabricated authorization; passive-monitoring surface scan; full-transcript leakage; credential leakage; duplicate task; retry duplicate; storage timeout; wrong read-back; task-success/capture-failure confusion; AI-inference-as-observation; employee scoring; insufficient-sample BEST PATH; derived-overwrites-raw; cross-task contamination; out-of-scope business context; stale model/skill version honesty; storage adapter failure. Each gets an evidence row in `evidence/v2.0.0-adversarial.md` with a four-value verdict (PASS / FAIL / PENDING_EXTERNAL_VALIDATION / NOT_INCLUDED_BY_DESIGN).

## 8. Release plan (Phase 3)

Full regression (v1 suite + v2 suite), clean-room install from the built v2.0.0 ZIP, fresh-harness simulation (empty environment, env-grant capture, personal PTY flow), deterministic release build, `git tag v2.0.0` on the exact final commit, GitHub Release with asset + SHA256SUMS, and read-only verification that v1.0.1 tag/release/assets are untouched.

---

Reconciliation complete. Construction (Phase 1) starts immediately per contract §16.
