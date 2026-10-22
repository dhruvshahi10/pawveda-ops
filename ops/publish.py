"""The publisher. Runs every 5 minutes from GitHub Actions.

Posts at most one queue entry per run: the earliest whose slot has arrived, whose status is
"scheduled" (the house sets "cut" or "hold" from Dhruv's Review Room decisions), and which has not
already been published. Every post carries the AI-generated label. Nothing else is ever posted.
"""
import sys, time
import requests
from common import load, save, now, parse, log, graph, media_url, GraphError, IG_ID, DRY

LATE_LIMIT_H = 6        # a slot missed by more than this is marked "missed" for the house to re-slot
MAX_FAILS = 3


def wait_ready(cid, label):
    for _ in range(30):              # up to ~5 min, as Meta recommends
        st = graph("GET", cid, {"fields": "status_code,status"})
        code = st.get("status_code")
        if code in ("FINISHED", "PUBLISHED"):
            return
        if code in ("ERROR", "EXPIRED"):
            raise GraphError(f"{label} container {code}: {st.get('status','')}")
        time.sleep(10)
    raise GraphError(f"{label} container never finished processing")


def reachable(url):
    try:
        r = requests.head(url, timeout=30, allow_redirects=True)
        return r.status_code == 200
    except requests.RequestException:
        return False


def build(e):
    kind, files = e["kind"], e["media"]
    for f in files:
        if not reachable(media_url(f)):
            raise GraphError(f"media not reachable yet: {media_url(f)}")
    if kind == "image":
        body = {"image_url": media_url(files[0]), "caption": e["caption"], "is_ai_generated": True}
        if e.get("alt"):
            body["alt_text"] = e["alt"][0][:1000]
        cid = graph("POST", f"{IG_ID}/media", json_body=body)["id"]
        wait_ready(cid, "image")
        return cid
    if kind == "carousel":
        kids = []
        for i, f in enumerate(files):
            body = {"image_url": media_url(f), "is_carousel_item": True}
            alts = e.get("alt") or []
            if i < len(alts) and alts[i]:
                body["alt_text"] = alts[i][:1000]
            try:
                kid = graph("POST", f"{IG_ID}/media", json_body=body)["id"]
            except GraphError as err:
                if "alt_text" in body and "alt" in str(err).lower():
                    body.pop("alt_text")
                    kid = graph("POST", f"{IG_ID}/media", json_body=body)["id"]
                else:
                    raise
            kids.append(kid)
        for k in kids:
            wait_ready(k, "carousel item")
        cid = graph("POST", f"{IG_ID}/media", json_body={
            "media_type": "CAROUSEL", "children": ",".join(kids),
            "caption": e["caption"], "is_ai_generated": True})["id"]
        wait_ready(cid, "carousel")
        return cid
    if kind in ("reel", "story_video"):
        body = {"media_type": "REELS" if kind == "reel" else "STORIES",
                "video_url": media_url(files[0]), "is_ai_generated": True}
        if kind == "reel":
            body["caption"] = e["caption"]
            if e.get("trial"):
                body["trial_params"] = {"graduation_strategy": "SS_PERFORMANCE"}
        try:
            cid = graph("POST", f"{IG_ID}/media", json_body=body)["id"]
        except GraphError as err:
            if "trial_params" in body:      # not eligible for Trial Reels: post as a normal reel
                log("trial reel refused, posting as a normal reel:", err)
                body.pop("trial_params")
                e["trial_fallback"] = str(err)[:200]
                cid = graph("POST", f"{IG_ID}/media", json_body=body)["id"]
            else:
                raise
        wait_ready(cid, kind)
        return cid
    raise GraphError(f"unknown kind {kind}")


def bio_has_link():
    """True when the Instagram bio's website field is set. Captions that point at the bio only
    keep that line when this is true; otherwise the line is swapped back (06-BUILD-STATUS rule:
    never claim a link that does not exist)."""
    try:
        return bool((graph("GET", IG_ID, {"fields": "website"}) or {}).get("website", "").strip())
    except Exception as err:
        log("could not read bio website, posting without the bio line:", str(err)[:120])
        return False


def apply_waitlist_swap(e):
    sw = e.get("waitlist_swap")
    if not sw or sw.get("with", "") not in e["caption"]:
        return
    if not bio_has_link():
        e["caption"] = e["caption"].replace(sw["with"], sw.get("without", ""))
        log("bio has no link: posted without the waitlist line:", e["id"])


def main():
    queue = load("queue/schedule.json", [])
    pub = load("state/published.json", {})
    fails = load("state/failures.json", {})
    t = now()
    changed = False

    for e in queue:
        if e["status"] == "scheduled" and e["id"] not in pub and (t - parse(e["slot"])).total_seconds() > LATE_LIMIT_H * 3600:
            e["status"] = "missed"
            log("missed slot, left for the house to re-slot:", e["id"])
            changed = True

    due = sorted([e for e in queue if e["status"] == "scheduled" and e["id"] not in pub and parse(e["slot"]) <= t],
                 key=lambda e: e["slot"])
    if not due:
        log("nothing due")
        if changed:
            save("queue/schedule.json", queue)
        return
    e = due[0]
    log("due:", e["id"], e["kind"], e["slot"])
    if DRY:
        log("DRY RUN: would publish", e["id"], [media_url(f) for f in e["media"]])
        return
    apply_waitlist_swap(e)
    try:
        cid = build(e)
        mid = graph("POST", f"{IG_ID}/media_publish", json_body={"creation_id": cid})["id"]
        info = {}
        try:
            info = graph("GET", mid, {"fields": "permalink,timestamp,media_type,media_product_type"})
        except GraphError:
            pass
        rec = {"media_id": mid, "published_at": t.isoformat(), "slot": e["slot"], "kind": e["kind"],
               "permalink": info.get("permalink"), "trial": bool(e.get("trial")) and not e.get("trial_fallback")}
        if e.get("first_comment"):
            try:
                c = graph("POST", f"{mid}/comments", json_body={"message": e["first_comment"]})
                rec["first_comment_id"] = c.get("id")
            except GraphError as err:
                rec["first_comment_error"] = str(err)[:200]
        pub[e["id"]] = rec
        e["status"] = "published"
        save("state/published.json", pub)
        save("queue/schedule.json", queue)
        log("PUBLISHED", e["id"], rec.get("permalink"))
    except GraphError as err:
        n = fails.get(e["id"], {}).get("count", 0) + 1
        fails[e["id"]] = {"count": n, "last": str(err)[:400], "at": t.isoformat()}
        if n >= MAX_FAILS:
            e["status"] = "failed"
            save("queue/schedule.json", queue)
        save("state/failures.json", fails)
        log("FAILED", e["id"], n, err)
        sys.exit(0 if n < MAX_FAILS else 1)


if __name__ == "__main__":
    main()
