# X4 Foresight — TODO / deferred work

Backlog of intentionally-deferred items. The core pipeline
(scan → resolve → DB → JSON) is complete and runnable via `x4_save_scanner.py`.

## Near-term, well-scoped

- [ ] **Deepen NPC intel — current order for station-sector NPC ships.**
      We already export the 297 NPC ships in player-station sectors (identity,
      role, faction, sector, mid-delivery destination). Add each ship's **current
      order** ("Attacking" / "Patrolling" / "Trading" / …) so threat reads are
      actionable — e.g. distinguish 51 Xenon fighters *attacking* vs passing
      through The Void.
      *How:* the NPC order-stream already runs for every NPC ship (it extracts
      DockAt `delivery_dest` in `ShipHandler.on_npc_order`). Extend it to also
      capture the default/active order label into a `ctx.npc_ship_orders` dict,
      then attach it in `db/write.py::_write_npc_ships` (+ an `order` column on
      the `npc_ships` table and the export row). No buffering, ~cheap.

- [ ] **Assemble `in_progress_deliveries`** in the export. We already have
      `ctx.delivery_dest_index` (ships mid-delivery); currently the export key is
      `[]`. Build the list (ship + ware + destination station).

- [ ] **NPC-ship homebase (Middleman `supplier` param)** for the resolver's
      Step 3. Small coverage gain on the inferred tail; the streaming extractor
      already walks NPC order params.

## Bigger pieces

- [ ] **Player event log + career stats — NEW data source, not yet parsed.**
      The save holds the player's in-game notification/event log AND career
      stats. Neither is extracted today. High value as a "recent events" feed for
      the AI advisor (reputation changes, mission updates, combat ALERTS, crew
      assignments, news). Discovered while investigating two civilian ships
      docked at the HQ — a `component="[0x…]"` ref in an `upkeep` entry is what
      tied a named-crew frigate and a diplomacy gift-ship to those hulls.

      WHERE (save_001.xml): a `<log>` element wrapping ~4,000 `<entry>` rows,
      immediately AFTER a `<stats>` block, near the trade economy log
      (~line 13,112,002). Find again via `grep -n '<entry .*category='` or locate
      the `<log>` that directly follows `</stats>`.

      ENTRY SHAPE:
          <entry time="106477.0" category="upkeep"
                 title="Assigned Individual … to Osprey Vanguard"
                 text="…" faction="{20203,601}" component="[0x205e2]"
                 interact="showonmap"/>
        - time      = absolute game_time_s → subtract scan game_time for "ago"
        - category  = news(353) · missions(318) · upkeep(288) · alerts(262) ·
                      diplomacy(17) · tips(7) · uncategorised(2786)
                      → `alerts` = combat/threat warnings (most actionable);
                        `upkeep` = crew/asset assignments; `missions`/`diplomacy`
                        = storyline.
        - title/text = human strings, but MAY contain language refs like
                       "{page,id}" (e.g. faction="{20203,601}") needing the lang
                       file to resolve.
        - component = links the event to a specific ship/station object_id —
                      lets us attach events to entities we already scan.

      PLAYER STATS block just before the <log> (cheap, grab too):
          <stats><stat id="trade_score" value="38448"/>
                 <stat id="trade_rank" value="16"/>
                 <stat id="fight_score" value="715"/>
                 <stat id="fight_rank" value="16"/> …</stats>

      Suggested: emit a `events` export section (recent N per category, lang refs
      resolved, time_ago_s computed) + a `player_stats` block.

- [ ] **UI wiring** (`ui/main_ui.py` → `ui.html`). Launch a scan from the UI
      and feed the dashboard the new JSON shape. Last piece for a complete UX.

- [ ] **TradeHandler — active trades + active auto-trades.** Currently stubbed;
      export keys `active_trades` / `active_auto_trades` are `[]`. Reads live
      `TradePerform` orders (player station ↔ NPC, and player ship NPC↔NPC).

- [ ] **Trends engine** (the big one — own project). The DB already accumulates
      per-scan history + a deduped trade ledger. Build `db/trends.py`
      (`compute_trends`) for empire trajectory, reputation crossings, station
      deltas, fleet changes, trade profit/volume windows, and a `changes[]`
      event list; surface in the export.

## Smaller / polish

- [x] **Diplomacy relations matrix view.** Done 2026-06-12 — final "Matrix"
      sub-tab on the Diplomacy strip: 21×21 tier-coloured grid over the
      `faction_relations` export key, sticky headers both axes, row-label
      click jumps to that faction's tab, symmetric-pair fallback for
      one-sided save entries.

- [ ] **`docked_at` marker on `npc_ships` export.** Visiting (non-player) ships
      docked at a player station are captured and shown in the display's Docked
      line, but in the JSON they look like any other NPC ship in the sector (no
      marker). Add a `docked_at` column (resolved player-station code) to the
      `npc_ships` table + export. Low priority — investigation showed the visiting
      ships at the HQ were player-associated story ships, not routine visitors.

- [ ] **Cluster names** — `scanner/handlers/sector.py` leaves `cluster_name`
      as a TODO (sector names resolve; cluster names don't yet).
- [ ] **Ship cargo contents** — `Ship.cargo_m3` / `cargo_max_m3` not extracted
      (needs a ware-volume table). Hull/shield are done; cargo load is not.
- [ ] **Station-docked NPC/civilian ships** — we extract player-owned docked
      ships from station subtrees; civilian visitors (e.g. 2 at GX HQ) are
      skipped. Revisit if their presence matters.
