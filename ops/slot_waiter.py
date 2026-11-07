"""Slot waiter: makes a post go out within about a minute of its slot.

GitHub honours the house workflow's schedules only every 1-5 hours, so a 13:00 post could go out
at 16:13 (5 Nov: 193 min late). This script runs from its own workflow (slot-waiter.yml). When a
post is due within the next WINDOW_H hours, it sleeps until the slot and then dispatches the house
workflow, which re-reads the queue itself, so a cut or hold made while this was waiting still wins.
It never posts anything and never edits the queue.

Prints one of:  none | dispatch-now <id> | wait <seconds> <id>
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW_H = 5.5          # the job's timeout is 350 min; a waiter never sleeps longer than this
OVERDUE_H = 6           # publish.py marks a slot missed after 6 h; past that there is nothing to do


def load(path, default):
    p = os.path.join(ROOT, path)
    return json.load(open(p)) if os.path.exists(p) else default


def decide(queue, published, t):
    pending = [e for e in queue if e.get("status") == "scheduled" and e["id"] not in published]
    for e in pending:
        e["_slot"] = datetime.fromisoformat(e["slot"])
    overdue = [e for e in pending if timedelta(0) <= t - e["_slot"] <= timedelta(hours=OVERDUE_H)]
    if overdue:
        return ("dispatch-now", min(overdue, key=lambda e: e["_slot"])["id"], 0)
    soon = [e for e in pending if timedelta(0) < e["_slot"] - t <= timedelta(hours=WINDOW_H)]
    if soon:
        e = min(soon, key=lambda e: e["_slot"])
        return ("wait", e["id"], int((e["_slot"] - t).total_seconds()) + 20)
    return ("none", None, 0)


if __name__ == "__main__":
    t = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc)
    action, pid, secs = decide(load("queue/schedule.json", []), load("state/published.json", {}), t)
    print(action if action == "none" else (f"dispatch-now {pid}" if action == "dispatch-now" else f"wait {secs} {pid}"))
