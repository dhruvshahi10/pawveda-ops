"""Daily numbers, straight from Instagram, so the weekly review no longer depends on Business Suite's
reach column (which Meta has announced it is removing). Writes metrics/<date>.json and metrics/latest.json."""
from common import load, save, now, log, graph, GraphError, IG_ID, DRY, IST

REEL = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions",
        "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
FEED = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions"]


def fetch(mid, metrics):
    out = {}
    try:
        res = graph("GET", f"{mid}/insights", {"metric": ",".join(metrics)})
        for d in res.get("data", []):
            v = d.get("values", [{}])[0].get("value") if d.get("values") else d.get("total_value", {}).get("value")
            out[d["name"]] = v
        return out
    except GraphError as e:                    # one unsupported metric fails the whole call: fall back one by one
        for m in metrics:
            try:
                res = graph("GET", f"{mid}/insights", {"metric": m})
                d = res.get("data", [{}])[0]
                out[m] = d.get("values", [{}])[0].get("value") if d.get("values") else d.get("total_value", {}).get("value")
            except GraphError:
                out[m] = None
        return out


def main():
    if DRY:
        log("DRY RUN: insights idle")
        return
    acct = graph("GET", "me", {"fields": "username,followers_count,follows_count,media_count"})
    media = graph("GET", f"{IG_ID}/media", {"fields": "id,caption,media_type,media_product_type,permalink,timestamp", "limit": 50}).get("data", [])
    rows = []
    for m in media:
        is_reel = m.get("media_product_type") == "REELS"
        r = {"media_id": m["id"], "permalink": m.get("permalink"), "timestamp": m.get("timestamp"),
             "type": "reel" if is_reel else m.get("media_type", "").lower(),
             "hook": (m.get("caption") or "").split("\n")[0][:120]}
        r.update(fetch(m["id"], REEL if is_reel else FEED))
        rows.append(r)
    day = now().astimezone(IST).strftime("%Y-%m-%d")
    snap = {"read_at": now().isoformat(), "account": acct, "posts": rows}
    save(f"metrics/{day}.json", snap)
    save("metrics/latest.json", snap)
    log("insights saved:", len(rows), "posts, followers", acct.get("followers_count"))


if __name__ == "__main__":
    main()
