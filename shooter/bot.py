"""Headless bot scripts: move, shoot, kill. No window, deterministic."""

from __future__ import annotations

from keystone.input import ActionState


def idle(n: int) -> list[ActionState]:
    return [ActionState() for _ in range(n)]


def move_forward(n: int, sprint: bool = False) -> list[ActionState]:
    held = frozenset({"sprint"}) if sprint else frozenset()
    return [ActionState(forward=1.0, held=held) for _ in range(n)]


def look_spin(n: int, yaw_per_frame: float = 0.02) -> list[ActionState]:
    return [ActionState(look_yaw=yaw_per_frame) for _ in range(n)]


def fire_hold(n: int) -> list[ActionState]:
    """Hold fire (keyboard path) so auto weapons keep firing headless."""
    return [ActionState(held=frozenset({"fire"})) for _ in range(n)]


def fire_clicks(n: int) -> list[ActionState]:
    return [ActionState(pressed=frozenset({"fire"}), mouse_clicked=True) for _ in range(n)]


def assault(n_move: int = 60, n_fire: int = 240) -> list[ActionState]:
    """Walk forward then hold fire: minute-one fun proof (shots/hits/kills)."""
    script = move_forward(n_move)
    script.extend(fire_hold(n_fire))
    return script


def strafe_fire(n: int = 300) -> list[ActionState]:
    script: list[ActionState] = []
    for i in range(n):
        right = 1.0 if (i // 30) % 2 == 0 else -1.0
        script.append(ActionState(forward=0.6, right=right, held=frozenset({"fire"})))
    return script
