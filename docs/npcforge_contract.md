# NPCForge Contract

NPCForge is a headless subsystem that never writes directly to the database.

## Loop

1. `Observation` is built by the engine from world state and recent context.
2. `policy.py` returns `NPCOutput`:
   - `dialogue`
   - `intent`
   - `candidate_actions`
   - `state_updates`
   - optional `memory_update`
3. Engine applies bounded updates transactionally:
   - mood decay toward baseline
   - affinity/trust/respect clamps
   - memory summary and pinned memories
4. Engine compiles candidate actions:
   - executable safe actions (for now: NPC move, availability change)
   - flavor-only actions (logged, no world mutation)
5. Engine emits events for observability:
   - `NPC_SPOKE`
   - `NPC_STATE_UPDATED`
   - `NPC_TICK`
   - `FLAVOR_ONLY`

## Boundaries

- Deterministic engine remains source of truth.
- No arc progression from planner ticks.
- No off-screen key NPC deaths from planner ticks.
- Planner tick actions are tagged with `["npc_tick"]`.

## Relationship Signals

State tracks:

- `affinity_by_player` in `[-100, 100]`
- `trust_by_player` in `[0, 100]`
- `respect_by_player` in `[0, 100]`
- per-player `bond_flags` and `grudge_flags`
- per-player greeting stage `0..3`
- interaction timestamps and short-term memory
