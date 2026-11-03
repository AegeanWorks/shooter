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

## ADR-008: Wave-5 wisp cut for the sustain loop
Date: 2026-11-03
Status: accepted
Context: The frozen kite bot died at frame 2988 in a corner trap against 8 mites + 1 brute + 3 wisps; the 5.5-speed ranged wisp bleed was the dose-limiting pressure (screened 4→2→1 deaths at 2988→3354→3885 with early hp trajectory 100/100/88 intact each time).
Decision: `shooter/data/levels.json` wave 5 goes wisp 4→1 (mites 10, brutes 4 unchanged); waves 1-4, all weapons/enemies/player tables, and all bot code frozen.
Consequences: New best — `bot_soak2.json` / `soak_report2.json`: wave-5 entry still frame 2323 at hp 64, death frame 3884 in open combat (no corner trap), 38 kills / 6650 score / 190 shots / 145 hits; replay hash `ce8156ec…` identical via driver and `--replay`; suite still 11 passed; timing/budget unchanged (flat, green).

## ADR-009: Visual pass — HUD dedupe, floor/covers, tracer orientation (no balance change)
Date: 2026-11-03
Status: accepted
Context: Screenshot audit (960×540 headless `Engine.capture` PNG+JSON pairs) showed: duplicated WAVE/SCORE (engine status + game canvas), game HP panel under the engine help bar, flat gray floor (UV-stretched texture, `checker_scale=0`), covers sharing the wall material, and fire tracers mirrored front-to-back through the camera (yaw used the camera-forward `atan2(dx,-dz)` convention on a +z-length cube, yaw-only with no pitch). Proof driver: `scripts/capture.py` (seeded routes spawn/combat/burst/pickup/death; Engine stepped with `kite_step`, never CLI-idle).
Decision: `shooter/ui.py` owns WAVE/SCORE top-center + HP/ammo panel moved above the help bar (scale-aware) + red edge flash ≤30hp + translucent death tint; `status()` shortened to `HP - weapon ammo` (`|` has no bitmap glyph and rendered as `?`); floor `checker_scale=0.5`; one shared `material.cover` (warm tan, still a single payload — instancing intact); tracer yaw `atan2(dx,dz)` + pitch `-atan2(dy,hypot)` so the beam connects muzzle to hit; flash 0.22→0.10, tracer 0.05→0.02 wide; `juice.json` tracer 0.08→0.15 s / flash 0.06→0.10 s (presentation-only, not in snapshot); pickup spot + sim trigger both read `levels.json:pickup` (value kept at 0,-6 — moving it to 3,-6 broke kite's collection and cost a full wave: death 3884→2484 — reverted); pairwise enemy separation tried and reverted for the same sustain regression (kite needs the ball's clean away-vector; stacking at peak density kept as known limitation).
Consequences: Suite 13 passed (added kite-hold-distance + strafe-baseline locks); kite600 hash `098951ee` unchanged; kite6000 reproduces baseline exactly (death 3884, wave 5, 38 kills, pickup taken); `shot_fix_{spawn,combat,burst,pickup,death}.png+json` prove every touched view; no weapon/enemy/player table numbers changed.
