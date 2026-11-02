# Shooter decisions (append-only)

## ADR-001: Hitscan-only combat v1
Date: 2026-11-02
Status: accepted
Context: 60fps + determinism on CPU, no GPU projectiles yet.
Decision: All weapons hitscan via `keystone.physics.raycast`/`ray_aabb`; no ballistic projectiles, no sphere pushout for shots.
Consequences: Sim O(n) per pellet, deterministic; beams need quaternion work deferred to tracer yaw-only boxes.

## ADR-002: Shared mesh/material payloads for auto-instancing
Date: 2026-11-02
Status: accepted
Context: Renderer groups by `id(mesh)+id(material)` into 1 instanced draw.
Decision: 3 enemy + floor/wall + tracer/flash/pickup payloads shared; never clone Material per enemy. Enemies pooled (24 Nodes), tracers pooled (16).
Consequences: ≤40 draws, <20k tris worst case; per-enemy tint via emissive would break batching, so not done.

## ADR-003: Juice is presentation + capped logic
Date: 2026-11-02
Status: accepted
Context: Juice must never cost frame time or break `--verify-determinism`.
Decision: `ParticleSystem(max=256)` logic-only; muzzle flash 60ms + tracer 80ms pooled Nodes; hit-stop 2-tick freeze (in snapshot); kick decay 8/s (in snapshot); audio pre-synthesized, ≤8 voices.
Consequences: Hash stable; HUD `FX LIVE` from `particles.alive_count()`.

## ADR-004: Fixed-seed determinism v1
Date: 2026-11-02
Status: accepted
Context: `run_simulation` does not seed RNG; `run_log` seeds global only.
Decision: `Sim(seed=1)` fixed; own `random.Random`, never global/time. `log.seed` ignored v1 (same hash for any seed, still deterministic).
Consequences: `--verify-determinism` green; varying seeds need factory-arg support later.

## ADR-005: Engine boundary
Date: 2026-11-02
Status: accepted
Context: `test_boundary.py` forbids genre code in `keystone/`.
Decision: Game lives `projects/shooter/`, imports `keystone` only; zero `projects/keystone/**` edits.
Consequences: Engine gates stay green; balance via `shooter/data/*.json` only.

## ADR-006: Bot evidence roles and proxy labeling
Date: 2026-11-03
Status: accepted
Context: Stage 4 check showed `bot_log.json` (assault 60+540) scores 39 shots / 0 hits and dies on the default map, so it cannot carry the minute-one fun claim alone.
Decision: `bot_log.json` is the movement + determinism proof (replay hash `8319b113…`); `bot_strafe.json` (strafe_fire 300: 30 shots / 2 hits / hp 84 / replay hash `10f56c10…`) is the minute-one fun proof; `shot_stage4_min30proxy.*` stays labeled proxy until a true sustained run with frame-time graphs lands.
Consequences: No new capture conventions; claims cite the log that proves them.

## ADR-007: Full-length soak evidence and budget semantics
Date: 2026-11-03
Status: accepted
Context: The sustain slice needed a surviving bot and honest frame-time/budget numbers for 108,000 frames (30 sim-minutes).
Decision: `shooter/bot.py:kite_step` (pure feedback policy: face nearest, hold 6-12 m, fire when aimed; uses the shipped ammo economy — pulse, surge pickup, scatter/lance fallback) drives `scripts/soak.py`, which records `bot_soak.json` plus derived `soak_report.json` (per-600-frame wall series, wave events, death frame, peak budgets). `plan_batches.draw_calls` is the naive per-node count (51 at synthetic 24-enemy + 16-tracer load); the gate-relevant numbers are `batched_calls`/`instanced_calls` (6 at that load, 5 at the natural 16-alive peak), per the renderer's auto-instancing.
Consequences: Soak result — waves 1-4 cleared, wave 5 reached frame 2323, death frame 2988 (wave-5 swarm), 37 kills / 6550 score / 190 shots / 144 hits; mean sim-step 0.08-0.25 ms across 180 chunks (worst single step 24.3 ms, disclosed); replay hash `ba6419e0…` identical via driver and `--replay`.
