"""Run by the scheduled Claude house session (not by GitHub Actions).

The session exports two Review Room collections with the ArtifactData tool, saves them as JSON, and runs:

    python ops/house_sync.py reviews.json replies.json > sync-result.json

Input files are the 'list' results for the collections "reviews" and "replies": either a list of
{"id": ..., "data": {...}} objects or a {doc_id: data} map. This script then:
  - applies Dhruv's decisions to queue/schedule.json (cut -> "cut"; needs edit -> "hold"; a cut he reverses goes back
    to "scheduled" if its slot is still ahead). It never re-schedules a "needs edit" hold: the house does that after
    making the edit.
  - moves replies he approved into queue/outbox.json for the publisher to send
  - prints the held comments that are not yet in the Review Room, for the session to write there
"""
import json, sys
from common import load, save, now, parse


def docs(path):
    raw = json.load(open(path))
    if isinstance(raw, dict) and "documents" in raw:
        raw = raw["documents"]
    if isinstance(raw, list):
        return {d.get("id") or d.get("doc_id"): (d.get("data") or d) for d in raw}
    return raw


def main(reviews_path, replies_path):
    reviews, replies = docs(reviews_path), docs(replies_path)
    queue = load("queue/schedule.json", [])
    pub = load("state/published.json", {})
    outbox = load("queue/outbox.json", [])
    held = load("state/held.json", [])
    t = now()
    changes = []

    for e in queue:
        if e["id"] in pub or e["status"] in ("published", "failed"):
            continue
        key = "stories" if e["kind"] == "story_video" else f"day-{int(e['day']):02d}"
        r = reviews.get(key) or {}
        d, note = r.get("decision"), (r.get("note") or "").strip()
        if d == "cut" and e["status"] != "cut":
            e["status"] = "cut"; e["cut_at"] = t.isoformat()
            changes.append(f"CUT {e['id']}")
        elif d == "edit" and e["status"] != "hold":
            e["status"] = "hold"; e["hold_reason"] = f"Dhruv asked for an edit: {note or '(no note)'}"
            e["edit_note"] = note; e["edit_requested_at"] = r.get("at")
            changes.append(f"HOLD for edit {e['id']}: {note}")
        elif d == "edit" and e["status"] == "hold" and note and note != e.get("edit_note"):
            e["edit_note"] = note; e["hold_reason"] = f"Dhruv asked for an edit: {note}"
            changes.append(f"EDIT NOTE updated {e['id']}: {note}")
        elif d in (None, "approve") and e["status"] == "cut" and parse(e["slot"]) > t:
            e["status"] = "scheduled"; e.pop("cut_at", None)
            changes.append(f"UN-CUT {e['id']}")

    queued = {o["comment_id"] for o in outbox}
    for cid, r in replies.items():
        if r.get("status") == "approved" and r.get("final") and cid not in queued:
            outbox.append({"comment_id": cid, "message": r["final"].strip(), "approved_at": r.get("decided_at") or t.isoformat()})
            changes.append(f"REPLY approved {cid}")

    to_push = []
    for h in held:
        cid = h.get("comment_id")
        if h.get("status") == "held" and not h.get("synced") and cid not in replies:
            to_push.append({"comment_id": cid, "username": h.get("username"), "text": h.get("text"), "permalink": h.get("permalink"),
                            "draft": h.get("draft") or "", "category": h.get("category"), "at": h.get("at"), "status": "held"})
            h["synced"] = True
    save("queue/schedule.json", queue)
    save("queue/outbox.json", outbox)
    save("state/held.json", held)
    print(json.dumps({"changes": changes, "push_to_review_room": to_push,
                      "next_up": [{"id": e["id"], "slot": e["slot"], "status": e["status"]} for e in queue
                                  if e["status"] in ("scheduled", "hold", "missed") and e["id"] not in pub][:5]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
