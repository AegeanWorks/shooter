"""Shooter HUD: crosshair, HP, ammo, score. Presentation-only, never sim."""

from __future__ import annotations


def draw_shooter(canvas, hud, sim) -> None:
    w, h = int(hud.width), int(hud.height)
    cx, cy = w // 2, h // 2
    white = (0.95, 0.95, 0.97, 1.0)
    dim = (0.55, 0.60, 0.68, 1.0)
    accent = (1.0, 0.62, 0.20, 1.0)
    danger = (1.0, 0.30, 0.30, 1.0)
    panel_c = (0.03, 0.04, 0.06, 0.72)

    # crosshair (expands on hit)
    gap = 8 if float(getattr(sim, "hitmark_t", 0.0)) <= 0.0 else 12
    col = accent if float(getattr(sim, "hitmark_t", 0.0)) > 0.0 else white
    canvas.rect(cx - gap - 8, cy - 1, 8, 2, col)
    canvas.rect(cx + gap, cy - 1, 8, 2, col)
    canvas.rect(cx - 1, cy - gap - 8, 2, 8, col)
    canvas.rect(cx - 1, cy + gap, 2, 8, col)
    canvas.rect(cx - 1, cy - 1, 2, 2, col)

    # engine help lives bottom-left (overlay.py); keep the game panel above it.
    # overlay scale/help math mirrored here so panels never overlap.
    scale = 2 if (w >= 620 and h >= 360) else 1
    if w >= 620:
        help_h = (9 * scale) * 2 + 6 * scale
        panel_y = h - 64 - (help_h + (12 if scale == 2 else 6))
    else:
        panel_y = h - 64
    # bottom-left status panel (HP/ammo only; wave/score stays top-center,
    # engine status() carries the same short HP/ammo line — no duplication)
    canvas.rect(12, panel_y, 300, 52, panel_c)
    hp = int(getattr(sim, "hp", 100))
    hp_col = danger if hp <= 30 else white
    canvas.text(20, panel_y + 8, f"HP {hp}", hp_col, 2)
    canvas.text(20, panel_y + 28, f"{str(getattr(sim, 'weapon', 'pulse')).upper()} "
               f"{int(sim.ammo.get(sim.weapon, 0))}/{int(sim.reserve.get(sim.weapon, 0))}", dim, 2)
    # low-hp edge warning (translucent, presentation-only)
    if hp <= 30 and bool(getattr(sim, "alive", True)):
        edge = (1.0, 0.15, 0.15, 0.28)
        canvas.rect(0, 0, w, 6, edge)
        canvas.rect(0, h - 6, w, 6, edge)
        canvas.rect(0, 0, 6, h, edge)
        canvas.rect(w - 6, 0, 6, h, edge)
    # top-center wave/score/streak (single source; engine status() omits these)
    canvas.text(cx - 90, 34, f"WAVE {int(getattr(sim, 'wave', 1))}  "
               f"SCORE {int(getattr(sim, 'score', 0))}", white, 2)
    streak = int(getattr(sim, "streak", 0))
    od_t = float(getattr(sim, "overdrive_t", 0.0))
    if streak > 0:
        canvas.text(cx - 90, 52, f"STREAK x{streak}", accent, 2)
    if od_t > 0.0:
        canvas.text(cx - 90, 68, f"OVERDRIVE {od_t:.1f}s x2", accent, 2)
    elif str(getattr(sim, "weapon", "")) == "surge" and float(getattr(sim, "surge_t", 0.0)) > 0.0:
        canvas.text(cx - 90, 68, f"SURGE {float(getattr(sim, 'surge_t', 0.0)):.1f}s - switching drops it", dim, 2)
    if int(getattr(sim, "near_miss", 0)) > 0:
        canvas.text(cx - 90, 84, f"NEAR-MISS {int(getattr(sim, 'near_miss', 0))}", dim, 2)
    if not bool(getattr(sim, "alive", True)):
        canvas.rect(0, 0, w, h, (0.45, 0.02, 0.02, 0.28))
        canvas.text(cx - 70, cy - 60, "YOU DIED", danger, 4)
