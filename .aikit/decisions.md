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

## ADR-010: Stage 0 triage — keep fix evidence, drop duplicates and stray logs
Date: 2026-11-03
Status: accepted
Context: Dirty tree held `shot_check_*` vs `shot_fix_*` pairs for all 5 routes, a truncated 6000-frame `soak_report.json` overwriting the 108000-frame full evidence, stray `600`/`600.bak` 6000-frame CommandLogs, and `__pycache__` dirs.
Decision: Keep `shot_fix_*` (ADR-009 cited proof; PNG bytes identical to `shot_check_*`, scene/stats/ui equal, only image path + top hash differ so `check` adds no proof) and commit it; delete `shot_check_*` duplicates; restore committed 108000-frame `soak_report.json` (death 2988, hash `ba6419e0…`); delete `600`/`600.bak` (duplicate stray logs; canonical logs stay `bot_soak.json`/`bot_soak2.json`) and `__pycache__` dirs.
Consequences: Tree clean except the landed `shot_fix_*` evidence; shooter 13 passed, keystone green, `--verify-determinism` 600 ok.

## ADR-011: Engine upgrade adoption — explicit renderer flags, outcome signal, kite reference
Date: 2026-11-03
Status: accepted
Context: Keystone added deterministic shadows/sRGB/post/bloom (all default-on) plus seeded `keystone.playtest`. Shooter inherited all four implicitly (`Scene` defaults) with no proof, and `snapshot()` had `score` but no `outcome`, so `validate_fairness` could only return `unknown`.
Decision: `shooter/data/grade.json` owns the four renderer flags as DATA; `shooter/game.py:build_scene` sets each `Scene.*.enabled` explicitly from it. `shooter/data/levels.json` gains `win_wave: 2`; `shooter/sim.py:snapshot` emits `outcome` (`lose` dead / `win` wave>=win_wave / `ongoing`). `bot_kite600.json` (kite 600 ActionStates, wave 2 / 9 kills / win) is the scripted reference DATA. `scripts/capture.py` gains `--no-*` toggles + profiler print (`draws/tris/inst/shadow_calls/map/flags`).
Consequences: Combat on-state profiler `draws=7 tris=810 inst=4 shadow_calls=17 map=1024 S1C1P1B1`, sim `18 shots/16 hits/4 kills/wave 2/hp 100` identical across all toggles (renderer never touches sim). Before/after luma: sRGB 35.57 vs 33.38, shadows 35.57 vs 35.36, post 35.57 vs 34.82, bloom 35.57 vs 34.89 — all change pixels, all kept (draws 7/40, tris 810/80000). Bots: random60 `unknown/no_reference_solution` hash `56a2f562…`, greedy300 `unknown` (score 0, random-equivalent) hash `027ea639…`, scripted kite `fair/witnessed_win:reference:181` hash `13cfa9be…` (`--expect-hash` pinned, exit 0). Death stays deterministic pinned `lose` via `test_player_can_die`, not a fair-blocker. Suite 16 passed.

## ADR-012: Sustain drift is engine-caused — no game re-tune (Stage 4 finding)
Date: 2026-11-04
Status: accepted
Context: Stage 4 re-ran the full 108000-frame sustain to temp on current code: death 2232, wave 4, 30 kills / 4750 score, hash `a6370ef2…` (mean 0.177ms, chunk_max 85.7ms, peak_alive 6) vs committed `soak_report2.json` baseline death 3884, wave 5, 38 kills / 6650 score, hash `ce8156ec…`. Wave timings diverge early (wave 3 at 717 vs 708, wave 4 at 1410 vs 1323). A `HEAD~1` baseline-code worktree on the same current engine reproduces death 2232 with identical wave events (hash `0a18b90b…`, outcome field being the only game diff), proving the drift is not from this stage's game changes (snapshot-only `outcome` + additive `win_wave` + same-True renderer flags cannot touch `step()`).
Decision: No game table changes to chase the drift — `weapons/enemies/levels` balance stays frozen per ADR-008, committed soak reports stay as historical baseline. Engine-side follow-up (physics: slopes step-up / platform carry / particle AABB / waves pushout, all landed after the sustain baseline) follows the engine prompt, never a game fork.
Consequences: Renderer adoption, fair kite verdict, and minute-one strafe lock stand; full-length sustain proof is blocked pending the engine prompt. Repro: `python scripts/soak.py 6000 <tmp-log> <tmp-rep>` (or 108000) on current code vs `soak_report2.json` — expect death 2232, not 3884.
Mechanism (bisected 2026-11-04, temp `probe.py`/`tracedump.py`, worktrees removed): last-good engine `9b4e8d5`/`3384d8a` reproduce death 3884 with baseline wave timings (180/708/1323/2323); first-bad is `2db2a78` slopes step-up (`keystone/character.py`). First divergence frame 507 at the center-cover corner (-1.17,-1.35): x -1.1709 vs -1.2211, y/z/combat identical. `_try_step_up` fires exactly 2× per 600 kite frames, 100% success. Root defect: on a wall-slide (one axis blocked, other free) it retries the FULL frame displacement from the raised position, so the free axis is applied a SECOND time (double slide); the flat-ground settle passes the rise/limit checks trivially. The commit's "defaults preserve steps" claim holds only for sims that never wall-slide. Suggested engine correction: retry only the blocked axis (or residual amounts). Game impact contained: divergence starts at frame 507, after the wave-2 win (~181) and the 300-frame strafe proof — fair verdict and minute-one evidence unaffected, re-verified green on engine HEAD `1218468` (suite 16/16).

## ADR-013: Engagement loop — variable rewards, honest near-miss, voluntary overdrive (Stage 2 revision)
Date: 2026-11-04
Status: accepted
Context: Stage 1 audit found 1.5 of 5 pillars (weak autonomy, partial competence-fairness) with variable reward, near-miss, and push-your-luck missing. Stage 2 verified the plan against CyberPulse decisions (`rewards.py` 70/20/10, `puzzles.py` near-miss, `engine.py:overdrive/break_combo/extraction_risk`, ADR-015 separate world RNG, ADR-019 one-shot SURGE cap + terminal guards) and shooter call sites (`sim.py` single RNG, `_switch` surge-away allowed, hitscan `ray_aabb`, `snapshot()->stable_hash`, `bot.py:kite_step`, `scripts/soak.py`). Ten Stage 1 assumptions were wrong (jackpot density, magnitude-vs-timing conflation, graze geometry unbuilt, almost-lost mislabeled, HP-cost ungrounded, surge tradeoff false, streak underspecified, single-stream RNG perturbation, bot return-rate claim, `aikit.py check` registration gap).
Decision: Port principles, not code, per Stage 2 §6: NEW `shooter/data/engagement.json` (schema 1: reward 0.85/0.12/×2.0/cache 0.03/+12/8s; streak +0.10 cap 0.50 break-on-hurt; near-miss ≤0.10 once/wave +6 reserve; overdrive 30 reserve/8s/×2; surge_lock true). `sim.py`: separate `reward_rng = Random(seed^0x9E3779B9)` for all engagement rolls; per-kill partition standard/critical/cache with streak bonus and overdrive doubling; single almost-won detector (post-hit survivor ≤10%) with one capped bonus per wave; CLUTCH flavor-only (never counted); voluntary `pressed=="overdrive"` with `overdrive_preview()` refusals (dead/already-on/surge-active/insufficient-ammo), 8s timer, any `hurt` breaks streak + timer; switching away from surge forfeits `surge_t`; snapshot gains `streak/best_streak/overdrive_t/rewards/near_miss/clutch/caches`. `game.py` exposes `overdrive` button; `ui.py` STREAK/OVERDRIVE/SURGE-LOCKED/NEAR-MISS lines (presentation-only); `bot.py:overdrive_step` measurement policy (kite + press when preview ok and streak≥3). Tests: NEW `tests/test_engagement.py` (12 tests: DATA validity, stream separation, 5000-roll partition, kill accounting, cap/break, near-miss honesty + cap, clutch exclusion, overdrive preview/cost/break/doubling, cache drop/pickup/expiry, surge forfeit, determinism + rewards==kills).
Consequences: Suite 28 passed (16 existing + 12 new); fair `witnessed_win` and strafe 30/2/84 pins hold; `--verify-determinism` green. Scripted proof (seeds 1-20, kite 600f): all reach wave 2, mean 8.4 kills / 1676 score / 0.35 near-miss; reward hist 0.875/0.089/0.036 over 168 kills vs stated 0.85/0.12/0.03. Overdrive policy (seeds 1-5): 3 presses/600f, scores 2390-3290 (+~60% vs kite baseline) with streak intact. Kite 6000f seed 1: wave 5, 43 kills / 9800, death tick 3577 (vs 2232 current-engine no-engagement baseline — extra cache ammo extends the run; trajectory otherwise unchanged). Ethics line holds: no HP costs, no currency, no fake near-misses (counter excludes clutch/low-HP warnings), no countdowns/logins; overdrive 8s capped, always breakable, surge lock disclosed in HUD. `aikit.py check shooter` still unregistered (pre-existing gap, out of scope). No `weapons/enemies/levels` balance touched; no engine files touched.

## ADR-014: Verification state on combined heads (game 9504b46 + engine f653b64)
Date: 2026-11-04
Status: accepted
Context: Peer engagement work (ADR-013) and engine swarm/batch fixes landed while sustain was blocked. Re-verified everything on combined current heads rather than assuming prior pins hold.
Decision: Keep `bot_kite600.json` as the CommandLog replay artifact; engine `load_actions` now rejects CommandLog-shaped files as `--script` (use `--replay` for audits, derive `{"actions": [...]}` to temp for CLI playtests — no committed duplicate). Pins re-captured, all verdicts hold: kite scripted `fair/witnessed_win:reference:181` hash `e5cfaf0e…` (same positions, score 610 vs 550 from variable rewards), random60 `unknown` hash `62cb2ed9…`, greedy300 `unknown` score 0 hash `993bb68a…`, 108k sustain death 3576 wave 5 / 43 kills / 9800 hash `ec703aa7…` (mean 0.0877ms, chunk_max 23.1ms, peak 7). Suite 28/28 green; keystone suite exit 0 on `f653b64`.
Consequences: The 2232→3576 sustain move is game-side (engagement caches/overdrive), not an engine fix — the `_try_step_up` double-slide defect stands and full-baseline proof (3884) still waits on the engine prompt. Minute-one strafe lock and fair verdict unaffected. Repro commands unchanged (outputs to temp).

## ADR-015: Wave-1 audit fixes — cache pickup, surge forfeit, mixer cap, test honesty
Date: 2026-11-04
Status: accepted
Context: Audit wave 1 (newest 10 commits) re-verified every finding with a repro before fixing. Three bugs were verified true; two nits and one vacuous test were code-evident.
Decision: (1) Cache pickup uses direct `aabb_overlap`, not the shared `TriggerTracker` — edge-triggering one shared "cache" name stranded all but one overlapping drop per frame (repro: two overlapping caches in wave 1 granted +12 once, second stranded until TTL expiry; after fix both grant same frame, +24). Surge pickup keeps the tracker (single volume, verified working). (2) Surge forfeit also zeroes `ammo["surge"]` — no input path switches back (slot1-3 only), so leftover rounds sat unreachable in the snapshot, and a programmatic re-select with ammo but no timer would arm a permanent timer-less gun (now the guard blocks it). (3) Voice cap uses public `Mixer.clear()` instead of `mixer._voices.pop(0)` — engine never drains voices, so the cap is load-bearing against unbounded growth; post-update invariant `voice_count <= 8` preserved. (4) `test_reward_stream_separate_and_reseedable` drops the `or True` tautology for real advance/reseed assertions. (5) Dead code removed: duplicate `yaw = pi` assignment, `if True` filter in `_sync_scene`.
Consequences: Suite 28/28 green; strafe 30/2/84 and kite determinism pins unchanged; no weapon/enemy/level DATA touched; no engine files touched. Left as-is (verified harmless): duplicated reload `elif` (unreachable with shipped DATA — only surge has `reload_s == 0` and surge reserve is always 0 — but load-bearing for modded tables), duplicated `_eng()` fallback defaults.

## ADR-016: Wave-2 audit — oldest history, dependency audit, docs drift, coverage
Date: 2026-11-04
Status: accepted
Context: Oldest commit (8854d3b: movement, hitscan, 3 enemies, capped juice) re-verified — all still present and pinned by tests (move/sprint/fire/hit/kill/die/score/determinism/budget). Dependency sweep: shooter + scripts + tests import stdlib and `keystone.*` only (no direct third-party deps); no packaging manifest needed (plugin loads via `--game` module path + `conftest.py` sys.path; suite green proves it).
Decision: (1) Tighten `_switch("surge")` guard to timer-only (`surge_t <= 0` blocks): the Wave-1 ammo fix exposed that a never-picked-up re-select (timer 0, ammo 0) armed a dead-end weapon — no fire, no reload, recoverable only via slots. No live caller switches to surge (pickup sets the timer directly), so behavior is unchanged except the dead end is now refused. Pinned by `test_surge_forfeit_relinquishes_ammo` (forfeit + never-taken paths). (2) Fix README drift: tree now lists `engagement.json`/`grade.json`/`test_engagement.py`/`test_audit.py`/`soak.py`/`capture.py`/evidence files; Controls rewritten to the actual live Engine map (E jump, one shot per click, slots/reload/overdrive headless-only). (3) FILED engine-side (out of scope here, ADR-005): Engine builds a plain `InputMap()` with defaults and offers no per-game bindings hook, so `fire/reload/slot1-3/overdrive/jump` action names can never arrive live — verified by code read (`app.py:57`, `input.py` defaults contain none of them). `tests/test_audit.py::test_live_input_limits_documented` pins the current boundary as a tripwire: it fails if the engine grows the hook, prompting a README update. (4) Coverage pins added (`tests/test_audit.py`, 6 tests): overlapping-cache same-frame pickup, surge forfeit + guard, voice-cap bound (12 forced voices trim to <= 8), overdrive policy press/refuse paths, HUD smoke incl. low-hp/death paths.
Consequences: Suite 34/34 green. No DATA or engine files touched. Live slots/reload/overdrive stay headless-only until the engine prompt lands a bindings hook.
