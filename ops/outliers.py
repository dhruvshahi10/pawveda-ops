#!/usr/bin/env python3
"""outliers.py - rank PawVeda's own reels by how far each beat the account's median reach.

Idea taken from ig-viral in Jakeschincariol/instagram-agent-skill (MIT, vendored in
ops/vendor (hooks.json + LICENSE)): raw numbers are not evidence; the multiple over the
account's own baseline is. Above 3x is a signal, under 1.5x is a normal day.

Usage
  python3 ops/outliers.py metrics/latest.json [--since 2026-10-20] [--md out.md]

Each reel also gets the hook pattern from the vendored hooks.json (26 patterns, matched in the
upstream classify_order) so the weekly review can see which kinds of opening beat the median.
"Unmatched" is a result too: most of our openings are scenes, not creator formulas.
"""
import argparse, json, os, re, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "vendor", "hooks.json")


def classify(text, hooks):
    by_id = {h["id"]: h for h in hooks["hooks"]}
    for i in hooks.get("classify_order", list(by_id)):
        h = by_id.get(i)
        if h and h.get("match") and re.search(h["match"], text or "", re.I):
            return h["name"]
    return "Unmatched"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metrics")
    ap.add_argument("--since", default="2026-10-20")
    ap.add_argument("--md")
    a = ap.parse_args()
    data = json.load(open(a.metrics))
    hooks = json.load(open(HOOKS))
    reels = [p for p in data.get("posts", []) if p.get("type") == "reel" and p.get("timestamp", "")[:10] >= a.since]
    if not reels:
        sys.exit("no reels in range")
    med = statistics.median(p.get("reach", 0) for p in reels)
    rows = []
    for p in reels:
        r = p.get("reach", 0)
        mult = r / med if med else 0
        band = "SIGNAL" if mult >= 3 else ("above" if mult >= 1.5 else ("normal" if mult >= 0.67 else "below"))
        rows.append(dict(date=p["timestamp"][:10], reach=r, mult=round(mult, 2), band=band,
                         shares=p.get("shares", 0), saves=p.get("saved", 0), comments=p.get("comments", 0),
                         watch_s=round((p.get("ig_reels_avg_watch_time") or 0) / 1000, 1),
                         pattern=classify(p.get("hook", ""), hooks), hook=(p.get("hook") or "")[:90], link=p.get("permalink", "")))
    rows.sort(key=lambda x: -x["mult"])
    lines = [f"# Reel outliers since {a.since}", "",
             f"{len(rows)} reels · median reach {med:g} · read {data.get('read_at', '?')[:16]} UTC", "",
             "| Multiple | Band | Reach | Shares | Saves | Watch s | Pattern | Date | Opening |",
             "|---|---|---|---|---|---|---|---|---|"]
    for x in rows:
        lines.append(f"| {x['mult']}x | {x['band']} | {x['reach']} | {x['shares']} | {x['saves']} | {x['watch_s']} | {x['pattern']} | {x['date']} | {x['hook']} |")
    by_pat = {}
    for x in rows:
        by_pat.setdefault(x["pattern"], []).append(x["mult"])
    lines += ["", "| Pattern | Reels | Median multiple |", "|---|---|---|"]
    for k, v in sorted(by_pat.items(), key=lambda kv: -statistics.median(kv[1])):
        lines.append(f"| {k} | {len(v)} | {statistics.median(v):.2f}x |")
    out = "\n".join(lines) + "\n"
    if a.md:
        open(a.md, "w").write(out)
    print(out)


if __name__ == "__main__":
    main()
