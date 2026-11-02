"""Full-length sustain soak: feedback bot, chunk timings, peak budget samples.

Drives ShooterGame with shooter.bot.kite_step (pure function of sim state),
records the CommandLog beside the existing bot_*.json trail, and captures a
per-600-frame wall-time series plus plan_batches samples at peak alive counts.
Writes bot_soak.json (canonical replay log) and soak_report.json (derived).

No balance or engine changes: ammo, spawns, and damage are the shipped tables.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "keystone"))

from keystone.batch import plan_batches  # noqa: E402
from keystone.input import ActionState  # noqa: E402
from keystone.math3d import Vec3  # noqa: E402
from keystone.replay import CommandLog, FIXED_STEP, stable_hash  # noqa: E402

from shooter.bot import kite_step  # noqa: E402
from shooter.game import ShooterGame  # noqa: E402
from shooter.sim import _Enemy  # noqa: E402

CHUNK = 600  # 10 s of sim per timing sample


def _peak24_budget() -> dict:
    """Synthetic max-load budget: 24 pooled enemies + full tracer ring, one sync."""
    game = ShooterGame()
    game.build_scene()
    sim = game.sim
    sim.spawn_queue = []
    sim.enemies = []
    kinds = ["mite", "brute", "wisp"]
    heights = {"mite": 0.5, "brute": 0.7, "wisp": 0.4}
    last = (0.0, 0.5, -2.0)
    for i in range(24):
        etype = kinds[i % 3]
        edef_hp = int(sim.enemy_defs[etype]["hp"])
        angle = math.tau * i / 24.0
        x, z = 10.0 * math.cos(angle), 8.0 + 10.0 * math.sin(angle)
        sim.enemies.append(
            _Enemy(etype=etype, pos=Vec3(x, heights[etype], z), hp=edef_hp, max_hp=edef_hp)
        )
        last = (x, 0.5, z)
    for _ in range(16):
        sim.tracers.append(
            {"x0": 0.0, "y0": 1.6, "z0": 8.0,
             "x1": last[0], "y1": last[1], "z1": last[2], "life": 0.08}
        )
    game.update(FIXED_STEP, ActionState())
    plan = plan_batches(game.scene)
    from keystone.gpu.instancing import plan_instanced

    inst = plan_instanced(game.scene)
    return {
        "alive": 24,
        "tracers": 16,
        "naive_draw_calls": int(plan["draw_calls"]),
        "batched_calls": int(plan["batched_calls"]),
        "instanced_calls": int(inst["instanced_calls"]),
        "triangles": int(plan["triangles"]),
    }


def main(
    frames: int = 108000,
    out_log: str = "bot_soak.json",
    out_report: str = "soak_report.json",
) -> None:
    game = ShooterGame()
    game.build_scene()
    log = CommandLog(seed=1)
    chunks: list[dict] = []
    chunk_wall = 0.0
    chunk_max = 0.0
    peak_alive = 0
    peak_budget: dict = {}
    wave_events: list[dict] = []
    death_frame: int | None = None
    last_wave = game.sim.wave
    t_all = time.perf_counter()
    for i in range(frames):
        action = kite_step(game.sim)
        log.record(action)
        tick_start = time.perf_counter()
        game.update(FIXED_STEP, action)
        step_wall = time.perf_counter() - tick_start
        chunk_wall += step_wall
        chunk_max = max(chunk_max, step_wall)
        alive = sum(1 for e in game.sim.enemies if e.alive)
        if alive > peak_alive:
            peak_alive = int(alive)
            plan = plan_batches(game.scene)
            from keystone.gpu.instancing import plan_instanced

            inst = plan_instanced(game.scene)
            peak_budget = {
                "alive": int(alive),
                "frame": int(i),
                "naive_draw_calls": int(plan["draw_calls"]),
                "batched_calls": int(plan["batched_calls"]),
                "instanced_calls": int(inst["instanced_calls"]),
                "triangles": int(plan["triangles"]),
            }
        if death_frame is None and not game.sim.alive:
            death_frame = int(i)
        if game.sim.wave != last_wave:
            wave_events.append(
                {
                    "frame": int(i),
                    "wave": int(game.sim.wave),
                    "kills": int(game.sim.kills),
                    "score": int(game.sim.score),
                    "hp": int(game.sim.hp),
                    "alive": bool(game.sim.alive),
                }
            )
            last_wave = game.sim.wave
        if (i + 1) % CHUNK == 0:
            chunks.append(
                {
                    "frames": [int(i + 1 - CHUNK), int(i + 1)],
                    "wall_ms": round(chunk_wall * 1000.0, 3),
                    "mean_step_ms": round(chunk_wall / CHUNK * 1000.0, 4),
                    "max_step_ms": round(chunk_max * 1000.0, 4),
                }
            )
            chunk_wall = 0.0
            chunk_max = 0.0
    wall_s = time.perf_counter() - t_all
    final = game.snapshot()
    peak24 = _peak24_budget()
    report = {
        "frames": int(frames),
        "step": FIXED_STEP,
        "seed": 1,
        "wall_s": round(wall_s, 3),
        "mean_step_ms": round(wall_s / frames * 1000.0, 4),
        "chunk_max_step_ms": max((c["max_step_ms"] for c in chunks), default=0.0),
        "chunks": chunks,
        "peak_alive": peak_alive,
        "peak_budget": peak_budget,
        "peak24_budget": peak24,
        "death_frame": death_frame,
        "wave_events": wave_events,
        "final": final,
        "hash": stable_hash(final),
    }
    log.save(Path(out_log))
    Path(out_report).write_text(
        __import__("json").dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(
        "soak frames=%d wall_s=%.2f mean_step_ms=%.4f wave=%d kills=%d score=%d hp=%d alive=%s hash=%s"
        % (
            frames, wall_s, wall_s / frames * 1000.0, final["wave"],
            final["kills"], final["score"], final["player"]["hp"],
            final["player"]["alive"], stable_hash(final),
        )
    )


if __name__ == "__main__":
    main(
        int(sys.argv[1]) if len(sys.argv) > 1 else 108000,
        sys.argv[2] if len(sys.argv) > 2 else "bot_soak.json",
        sys.argv[3] if len(sys.argv) > 3 else "soak_report.json",
    )
