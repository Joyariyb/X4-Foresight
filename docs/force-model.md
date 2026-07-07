# Force model

How the military advisor turns fitted loadouts into a verdict about who wins a
fight, and into a single number for whether a force is massing over time. The
maths lives in [`db/advisors/force.py`](../db/advisors/force.py); the rules that
consume it live in [`db/advisors/military.py`](../db/advisors/military.py). This
page is the *why* behind the formulas — update it when the model changes, not
when a threshold is retuned.

## Why loadouts, not counts or credits

Ship counts lie: one Xenon K outweighs twenty fighters. Credits lie too, in the
opposite direction: a 90 m hull with no guns costs a fortune and threatens
nothing, while a 5 m torpedo boat is a real danger. So every number below is
derived from the **actual fitted equipment** in the save (`ship_equipment` rows
resolved to real damage / shield / range stats), never from hull tallies or
price.

Two honesty limits are baked in and should never be presented away: pilot skill,
mods, ammo and X4's simplified out-of-sector combat are all unmodelled, and a
fleet is treated as one merged pool even though individual ships lose shields at
different moments. That is why every verdict is a coarse **band**, never a win
percentage.

## Per-ship, per-side inputs

`ship_power()` reduces one ship to four numbers; `sector_forces()` sums them per
side into a *profile*. Everything downstream reads just these:

```
dₕ = dps_hull      damage/s that lands on hull
dₛ = dps_shield    damage/s that lands on shields
eₕ = ehp_hull      hull hit points   (effective HP)
eₛ = ehp_shield    shield hit points (effective HP)
```

`eHP` = effective hit points = the damage a pool can absorb before it is gone.
A force's total durability is `eₕ + eₛ` (hull + shields). Shields regenerate and
absorb first; hull is what actually has to reach zero to kill the ship.

## 1 · Time to kill

`ttk_seconds(attacker A, defender D)` — how long A's sustained DPS needs to grind
D's shield pool, then its hull pool (shields first, mirroring X4):

```
                eₛ(D)     eₕ(D)
TTK(A, D)  =    ─────  +  ─────
                dₛ(A)     dₕ(A)
```

with two edge rules:

- a term contributes **0** when that pool is empty;
- the whole result is **∞** when the defender still has a pool the attacker has
  no matching DPS for — i.e. *can't break through*.

## 2 · Run it both ways

```
t_they = TTK(hostile, player)     time for them to kill us
t_we   = TTK(player, hostile)     time for us to kill them
```

Whoever kills faster (smaller TTK) is winning.

## 3 · Verdict

Band the two TTKs, with a deliberately wide dead-band `k = 2`
(`OUTMATCHED_RATIO`) — a narrower band would claim precision the model doesn't
have:

```
                 ⎧ Undefended   if n(player) = 0
                 ⎪ Contested    if a side is all-unassessed (no loadout data)
                 ⎪ Outmatched   if t_we   = ∞           (we can never crack them)
V(t_they, t_we) =⎨ Covered      if t_they = ∞           (they can never crack us)
                 ⎪ Outmatched   if t_we   > k · t_they
                 ⎪ Covered      if t_they > k · t_we
                 ⎩ Contested    otherwise
```

Equivalently, when both TTKs are finite and nonzero, the single ratio
`ρ = t_we / t_they` decides it: `ρ > k` → Outmatched, `ρ < 1/k` → Covered,
otherwise Contested.

**Missing data degrades toward the middle, never toward reassurance.** A side
with no captured loadouts reads as zero DPS, which without the `all-unassessed`
guard would score a completely unknown fleet as harmless ("Covered"). The same
reasoning stops a partially-unassessed hostile force from earning "Covered".

## 4 · Build-up strength

The verdict answers "who wins this fight". A different question — "is a force
massing?" — needs a single scalar you can trend across scans. That is
`combat_strength()`:

```
F = dₕ + dₛ                     firepower
H = eₕ ,  S = eₛ                durability axes (hull, shield eHP)

strength = √( F · (H + S) )
```

Geometric, not additive, for two reasons: the axes are different units (dmg/s vs
HP), so a sum is meaningless; and a product **zeroes on a missing axis**, which
is the behaviour we want — no firepower ⇒ no offensive threat ⇒ strength 0,
however much hull the force carries. The square root keeps the index in the same
magnitude as its inputs and linear in fleet size, so "firepower doubled" reads
as "strength doubled".

This is the domain's single strength measure: the build-up rule and any future
rule that needs one number derive it here, so they can never disagree about who
is stronger. It shares the same profile inputs as the TTK duel — the two just
summarise them for different questions.

### The build-up trigger

`buildup_findings()` walks `combat_strength` across the last `BUILDUP_WINDOW = 4`
scans for each player-station sector with hostiles, takes the trailing run of
scans with real strength (a zero breaks the run — it means no coverage / no
loadouts that scan, not "grew from nothing"), and fires when the run is long
enough, strictly rising, and has grown by at least `BUILDUP_GROWTH`:

```
        strength(latest)
  g  =  ────────────────   ≥ 2   ∧   rising every scan   ∧   run ≥ 3 scans
        strength(oldest)
```

A passing raid arrives, fights and leaves, so it cannot stay monotonically
rising across four snapshots; sustained growth is staging. Unlike every other
military rule this one is **not** distance-gated — the threat to a station
doesn't lessen because the player flew away, and a warning that flickered with
the player's position would defeat the point. The finding reports per-axis
growth (firepower, hull) so the card can say *what* is massing, not just that
something is.

## Where each piece surfaces

| Question | Function | Shown in |
| --- | --- | --- |
| Who wins this fight? | `ttk_seconds` → `_verdict` | Hostile Presence card (verdict band + colour) |
| What can't my guns track? | `tracking_factor` / `dps_anti_small` | Tracking Mismatch card |
| Am I out-reached? | `max_range_m` | Outranged card |
| Is a force massing? | `combat_strength` → `buildup_findings` | Force Build-Up card + Trends → Recent Changes |
