#!/usr/bin/env python3
"""Conwai run analysis tool.

Usage:
    python tools/analyze.py                    # full report
    python tools/analyze.py --agent Joshua     # single agent timeline
    python tools/analyze.py --compare          # A/B group comparison
    python tools/analyze.py --agent Joshua --tick 120  # single tick trace
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path("data")


def connect():
    ev = sqlite3.connect(DATA / "events.db")
    st = sqlite3.connect(DATA / "state.db")
    return ev, st


def get_groups(ev):
    groups = {}
    for entity, data in ev.execute(
        "SELECT entity, data FROM events WHERE type='ab_group'"
    ).fetchall():
        groups[entity] = json.loads(data)["group"]
    return groups


def get_tick():
    p = DATA / "tick"
    return int(p.read_text().strip()) if p.exists() else 0


def get_agent_state(st, entity):
    state = {}
    for comp, data in st.execute(
        "SELECT component, data FROM components WHERE entity=?", (entity,)
    ).fetchall():
        state[comp] = json.loads(data)
    return state


def get_all_agents(st, groups):
    agents = {}
    entities = set()
    for (entity,) in st.execute(
        "SELECT DISTINCT entity FROM components WHERE component='agent_info'"
    ).fetchall():
        entities.add(entity)
    for entity in sorted(entities):
        agents[entity] = get_agent_state(st, entity)
        agents[entity]["_group"] = groups.get(entity, "none")
    return agents


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def report_overview(ev, st):
    tick = get_tick()
    groups = get_groups(ev)
    total = ev.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    day = tick // 24 + 1
    hour = 8 + tick % 24

    print(f"=== CONWAI RUN ANALYSIS ===")
    print(f"Tick: {tick} (Day {day}, {hour}:00)  Events: {total}")
    if groups:
        grp_counts = defaultdict(int)
        for g in groups.values():
            grp_counts[g] += 1
        print(f"Groups: {dict(grp_counts)}")
    print()

    # Event types
    print("--- EVENTS ---")
    for t, c in ev.execute(
        "SELECT type, COUNT(*) FROM events GROUP BY type ORDER BY COUNT(*) DESC"
    ).fetchall():
        print(f"  {t}: {c}")
    print()

    # Agent state
    agents = get_all_agents(st, groups)
    print("--- AGENTS ---")
    print(
        f"  {'':3s} {'handle':12s} {'role':15s} {'coins':>5s} {'F':>4s} {'W':>4s} "
        f"{'B':>4s} {'hun':>4s} {'thi':>4s}"
    )
    for handle, a in sorted(agents.items()):
        grp = a["_group"][:3].upper()
        info = a.get("agent_info", {})
        eco = a.get("economy", {})
        inv = a.get("inventory", {})
        hun = a.get("hunger", {})
        print(
            f"  [{grp}] {handle:12s} {info.get('role','?'):15s} "
            f"{int(eco.get('coins',0)):>5d} "
            f"{inv.get('flour',0):>4d} {inv.get('water',0):>4d} "
            f"{inv.get('bread',0):>4d} "
            f"{hun.get('hunger',0):>4d} {hun.get('thirst',0):>4d}"
        )
    print()

    # Deaths
    deaths = ev.execute(
        "SELECT entity, data FROM events WHERE type='agent_died'"
    ).fetchall()
    if deaths:
        print(f"--- DEATHS ({len(deaths)}) ---")
        for entity, data in deaths:
            d = json.loads(data)
            print(f"  {d.get('handle', entity)}: {d.get('cause', '?')}")
        print()


def report_compare(ev, st):
    groups = get_groups(ev)
    if not groups:
        print("No A/B groups found.")
        return

    tick = get_tick()
    grp_names = sorted(set(groups.values()))
    agents_by_grp = defaultdict(list)
    for entity, grp in groups.items():
        agents_by_grp[grp].append(entity)

    print("=== A/B COMPARISON ===\n")

    # Actions per group
    print("--- ACTIONS PER AGENT ---")
    action_types = [
        "forage", "bake", "trade", "offer", "accept",
        "send_message", "post_to_board", "entity_destroyed",
    ]
    header = f"  {'action':20s}"
    for g in grp_names:
        header += f" {g:>12s}"
    print(header)

    for atype in action_types:
        line = f"  {atype:20s}"
        for g in grp_names:
            agents = agents_by_grp[g]
            cnt = ev.execute(
                f"SELECT COUNT(*) FROM events WHERE type=? AND entity IN ({','.join('?' * len(agents))})",
                [atype] + agents,
            ).fetchone()[0]
            n = len(agents)
            line += f" {cnt/n:>12.1f}"
        print(line)
    print()

    # Trade efficiency
    print("--- TRADE EFFICIENCY ---")
    for g in grp_names:
        agents = agents_by_grp[g]
        trades = ev.execute(
            f"SELECT COUNT(*) FROM events WHERE type='trade' AND entity IN ({','.join('?' * len(agents))})",
            agents,
        ).fetchone()[0]
        offers = ev.execute(
            f"SELECT COUNT(*) FROM events WHERE type='offer' AND entity IN ({','.join('?' * len(agents))})",
            agents,
        ).fetchone()[0]
        ratio = trades / offers if offers > 0 else 0
        print(f"  {g}: {trades} trades / {offers} offers = {ratio:.2f}")
    print()

    # Reciprocity
    print("--- DM RECIPROCITY ---")
    for g in grp_names:
        agents = set(agents_by_grp[g])
        # Get all DM pairs where sender is in this group
        pairs = ev.execute(
            f"""SELECT entity, REPLACE(json_extract(data, '$.to'), '@', '') as receiver, COUNT(*)
                FROM events WHERE type='send_message'
                AND entity IN ({','.join('?' * len(agents))})
                GROUP BY entity, receiver""",
            list(agents),
        ).fetchall()
        total_pairs = len(pairs)
        reciprocal = 0
        pair_counts = {(s, r): c for s, r, c in pairs}
        for (s, r), c in pair_counts.items():
            if (r, s) in pair_counts:
                reciprocal += 1
        pct = reciprocal / total_pairs * 100 if total_pairs > 0 else 0
        print(f"  {g}: {reciprocal}/{total_pairs} reciprocal ({pct:.1f}%)")
    print()

    # Wealth comparison
    print("--- CURRENT WEALTH ---")
    all_agents = get_all_agents(st, groups)
    header = f"  {'metric':20s}"
    for g in grp_names:
        header += f" {g:>12s}"
    print(header)

    for metric, path in [
        ("avg coins", ("economy", "coins")),
        ("avg flour", ("inventory", "flour")),
        ("avg water", ("inventory", "water")),
        ("avg bread", ("inventory", "bread")),
        ("avg hunger", ("hunger", "hunger")),
        ("min bread", None),
        ("zero bread", None),
    ]:
        line = f"  {metric:20s}"
        for g in grp_names:
            agents = [
                all_agents[h] for h in agents_by_grp[g] if h in all_agents
            ]
            if metric == "min bread":
                val = min(
                    (a.get("inventory", {}).get("bread", 0) for a in agents),
                    default=0,
                )
                line += f" {val:>12d}"
            elif metric == "zero bread":
                val = sum(
                    1
                    for a in agents
                    if a.get("inventory", {}).get("bread", 0) == 0
                )
                line += f" {val:>12d}"
            else:
                comp, field = path
                vals = [a.get(comp, {}).get(field, 0) for a in agents]
                avg = sum(vals) / len(vals) if vals else 0
                line += f" {avg:>12.1f}"
        print(line)
    print()

    # Reflection quality
    log_path = DATA / "sim.log"
    if log_path.exists():
        log_text = log_path.read_text()
        print("--- REFLECTION QUALITY ---")
        positive_words = re.compile(
            r"effective|success|proved|resolved|leverag|reliab|maintain|"
            r"convert|balanced|stabiliz|sustain|worked|improved",
            re.IGNORECASE,
        )
        negative_words = re.compile(
            r"failed|failure|shortage|crisis|unable|ineffect|starvation|"
            r"depleted|useless|expired",
            re.IGNORECASE,
        )

        for g in grp_names:
            agents = agents_by_grp[g]
            pattern = "|".join(re.escape(a) for a in agents)
            insights = [
                line
                for line in log_text.splitlines()
                if "insight:" in line and re.search(f"@({pattern})", line)
            ]
            pos = sum(1 for l in insights if positive_words.search(l))
            neg = sum(1 for l in insights if negative_words.search(l))
            total = len(insights)
            pos_pct = pos / total * 100 if total > 0 else 0
            neg_pct = neg / total * 100 if total > 0 else 0
            print(
                f"  {g}: {total} reflections, "
                f"{pos} solution ({pos_pct:.0f}%), "
                f"{neg} problem ({neg_pct:.0f}%)"
            )
        print()

    # Elections
    votes = ev.execute(
        "SELECT entity, json_extract(data, '$.candidate') FROM events WHERE type='vote'"
    ).fetchall()
    if votes:
        print("--- ELECTIONS ---")
        vote_counts = defaultdict(int)
        for _, candidate in votes:
            candidate = candidate.lstrip("@")
            vote_counts[candidate] += 1
        for candidate, count in sorted(
            vote_counts.items(), key=lambda x: -x[1]
        ):
            grp = groups.get(candidate, "?")[:3].upper()
            print(f"  [{grp}] {candidate}: {count} votes")
        print()


def report_agent_timeline(ev, st, agent, tick_filter=None):
    groups = get_groups(ev)
    grp = groups.get(agent, "none")
    state = get_agent_state(st, agent)
    info = state.get("agent_info", {})
    eco = state.get("economy", {})
    inv = state.get("inventory", {})
    hun = state.get("hunger", {})
    mem = state.get("agent_memory", {})

    print(f"=== AGENT TIMELINE: {agent} ===")
    print(f"Group: {grp}, Role: {info.get('role', '?')}")
    print(
        f"Current: coins={int(eco.get('coins',0))}, "
        f"F={inv.get('flour',0)}, W={inv.get('water',0)}, "
        f"B={inv.get('bread',0)}, hunger={hun.get('hunger',0)}"
    )
    print(f"Soul: {(mem.get('soul') or 'none')[:100]}")
    print(f"Strategy: {(mem.get('strategy') or 'none')[:200]}")
    print(f"Journal: {(mem.get('memory') or 'none')[:200]}")
    print()

    # All events for this agent, chronologically
    events = ev.execute(
        "SELECT t, type, data FROM events WHERE entity=? AND type NOT IN ('ab_group','entity_spawned') ORDER BY t",
        (agent,),
    ).fetchall()

    if not events:
        print("  No events found.")
        return

    # Group by approximate tick (events within 1 second are same tick)
    ticks = []
    current_tick_events = []
    last_t = events[0][0]
    for t, typ, data in events:
        if t - last_t > 2:  # new tick
            if current_tick_events:
                ticks.append(current_tick_events)
            current_tick_events = []
        current_tick_events.append((t, typ, data))
        last_t = t
    if current_tick_events:
        ticks.append(current_tick_events)

    # Log file data for this agent
    log_path = DATA / "sim.log"
    log_lines = []
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                if f"[{agent}]" in line or f"[@{agent}]" in line:
                    log_lines.append(line.strip())

    # Index log lines by approximate content
    recall_lines = [l for l in log_lines if "recall:" in l]
    importance_lines = [l for l in log_lines if "importance:" in l]
    insight_lines = [l for l in log_lines if "insight:" in l]
    focal_lines = [l for l in log_lines if "focal question:" in l]
    strategy_lines = [l for l in log_lines if "morning" in l.lower() or "strategy" in l.lower()]
    reasoning_lines = [l for l in log_lines if "tok)" in l]

    print(f"--- SUMMARY ---")
    print(f"  Total events: {len(events)}")
    print(f"  Ticks with activity: {len(ticks)}")
    print(f"  Recalls logged: {len(recall_lines)}")
    print(f"  Importance scores: {len(importance_lines)}")
    print(f"  Reflections generated: {len(insight_lines)}")
    print(f"  Focal questions: {len(focal_lines)}")
    print()

    # Action breakdown
    action_counts = defaultdict(int)
    for _, typ, _ in events:
        action_counts[typ] += 1
    print("--- ACTIONS ---")
    for typ, cnt in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {typ}: {cnt}")
    print()

    # Trade partners
    trades = [
        json.loads(data)
        for _, typ, data in events
        if typ == "trade"
    ]
    if trades:
        print("--- TRADE PARTNERS ---")
        partner_counts = defaultdict(int)
        for t in trades:
            partner_counts[t.get("with", "?")] += 1
        for partner, cnt in sorted(
            partner_counts.items(), key=lambda x: -x[1]
        ):
            pg = groups.get(partner, "?")[:3].upper()
            print(f"  [{pg}] {partner}: {cnt} trades")
        print()

    # Reflections
    if insight_lines:
        print("--- ALL REFLECTIONS ---")
        for line in insight_lines:
            insight = line.split("insight: ", 1)[1] if "insight: " in line else line
            print(f"  {insight[:140]}")
        print()

    # Focal questions
    if focal_lines:
        print("--- ALL FOCAL QUESTIONS ---")
        for line in focal_lines:
            q = line.split("focal question: ", 1)[1] if "focal question: " in line else line
            print(f"  {q[:140]}")
        print()

    # Recent reasoning (last 10)
    if reasoning_lines:
        print("--- RECENT REASONING (last 10) ---")
        for line in reasoning_lines[-10:]:
            print(f"  {line[:200]}")
        print()

    # If tick_filter specified, show that specific tick in detail
    if tick_filter is not None:
        print(f"\n--- TICK {tick_filter} DETAIL ---")
        # Find events near this tick
        # We need to map tick number to timestamp
        # Use the log file timestamps and match
        tick_day = tick_filter // 24 + 1
        tick_hour = 8 + tick_filter % 24
        time_str = f"Day {tick_day}, {tick_hour}:00"

        # Find recalls for this tick
        tick_recalls = [l for l in recall_lines if time_str in l or f"Day {tick_day}," in l]
        if tick_recalls:
            print("  Recalled:")
            for l in tick_recalls[:10]:
                # Extract just the content and score
                match = re.search(r'recall: "(.*?)".*?\((.*?)\)', l)
                if match:
                    print(f"    {match.group(1)[:80]} ({match.group(2)})")

        # Find reasoning for this tick
        tick_reasoning = [l for l in reasoning_lines if time_str in l]
        if tick_reasoning:
            print("  Reasoning:")
            for l in tick_reasoning:
                print(f"    {l[:200]}")


def main():
    parser = argparse.ArgumentParser(description="Analyze conwai run")
    parser.add_argument("--agent", help="Show timeline for specific agent")
    parser.add_argument("--tick", type=int, help="Show detail for specific tick (use with --agent)")
    parser.add_argument("--compare", action="store_true", help="A/B group comparison")
    args = parser.parse_args()

    ev, st = connect()

    if args.agent:
        report_agent_timeline(ev, st, args.agent, tick_filter=args.tick)
    elif args.compare:
        report_compare(ev, st)
    else:
        report_overview(ev, st)
        report_compare(ev, st)

    ev.close()
    st.close()


if __name__ == "__main__":
    main()
