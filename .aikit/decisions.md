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
