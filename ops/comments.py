"""The comment desk. Runs every 5 minutes after the publisher.

For every new comment on PawVeda's recent posts:
  - health, food-safety, medicine, dosage or emergency  -> never answered here; held for Dhruv with a draft
  - spam, links, self-promotion, abuse                  -> ignored (logged)
  - everything else (thanks, praise, "which dog", simple questions about PawVeda) -> answered in voice
A keyword screen runs BEFORE the model, so a health question is held even if the model would answer it.
Replies Dhruv approves in the Review Room arrive in queue/outbox.json and are sent from here.
"""
import json, os, re
import requests
from common import load, save, now, log, graph, GraphError, IG_ID, DRY

KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("REPLY_MODEL", "claude-haiku-5-5")
MAX_REPLIES_PER_RUN = 15
LOOKBACK_POSTS = 30

HEALTH = re.compile(r"""\b(vomit\w*|puk\w*|diarr\w*|loose\s*motion\w*|blood\w*|bleed\w*|letharg\w*|seiz\w*|
 collaps\w*|breath\w*|panting|limp\w*|swell\w*|swollen|fever|temperature|sick|ill(ness)?|pain|hurt\w*|injur\w*|wound|
 itch\w*|rash|tick(s)?|flea(s)?|worm\w*|infect\w*|lump|tumou?r|cancer|vaccin\w*|rabies|parvo|distemper|lepto\w*|
 medicine|medic\w*|tablet|pill|dose|dosage|mg\b|syrup|paracetamol|crocin|dolo|combiflam|ibuprofen|antibiotic\w*|
 vet\b|vets\b|doctor|emergenc\w*|poison\w*|toxic|ate\b|eaten|swallow\w*|chocolate|grape\w*|kishmish|raisin\w*|onion\w*|
 garlic|xylitol|laddoo|ladoo|mithai|milk|dahi|curd|roti|chapati|rice|bone(s)?|food|diet|not\s+eating|won'?t\s+eat|
 pregnan\w*|heat|neuter\w*|spay\w*|scared|panic\w*|anxi\w*|shak\w*|trembl\w*|hiding|cracker\w*|firework\w*|
 bimar|beemar|ulti|dast|khoon|dawai|dawa|bukhar|khana\s+nahi)\b""", re.I | re.X)
LINKY = re.compile(r"(https?://|www\.|\.com\b|dm\s+(me|us)\s+for|promo|followers|collab\s+with\s+us)", re.I)
BANNED_OUT = re.compile(r"\b(owner|fur\s*baby|pawsome|paw-some|unleash|revolutionary|game-?changing|cutting-edge|seamless|"
                        r"diagnos\w*|cure\w*|treat(ment)?|prescri\w*|guarantee\w*|dose|dosage|mg)\b", re.I)

SYSTEM = """You answer Instagram comments for PawVeda, pet health intelligence for Indian dog and cat parents.
Voice: a knowledgeable friend texting another friend. Calm, warm, specific, brief. Indian by default; Hindi only where it is the
natural word. The pet is the protagonist. Never say: owner (say pet parent), fur baby, pawsome, unleash, revolutionary,
game-changing, cutting-edge, seamless, diagnosis, cure, treatment, prescribe, guarantee. No hashtags. No links. At most one
emoji and only if it carries meaning. Never more than two short sentences. Never invent a fact about PawVeda: if asked
about features, pricing, launch dates or availability, say the team will share it here and on the profile, nothing more.
Never give health, food-safety, medicine or emergency advice of any kind.

Decide one action:
- "reply": thanks, praise, greetings, tagging a friend, "which dog is this", reactions, simple non-health questions.
- "hold": ANY mention of symptoms, illness, injury, behaviour worries, food a pet ate or might eat, medicine, dosage,
  vets, emergencies, or anything you are unsure about. Also complaints, partnership or press requests.
- "ignore": spam, links, self-promotion, abuse, bots.
For "hold" on a health topic, still write a draft for a human to approve: warm, no advice, and end with the substance of
"PawVeda helps you decide when to see a vet. It doesn't replace one. If this is happening right now, a vet is the right call."
Return only JSON: {"action": "reply"|"hold"|"ignore", "category": "<one or two words>", "reply": "<text or empty>"}"""


def ask_model(comment, post_caption):
    if not KEY:
        return None
    body = {"model": MODEL, "max_tokens": 300, "system": SYSTEM,
            "messages": [{"role": "user", "content": f"Post caption (first lines): {post_caption[:400]}\n\nComment by a viewer: {comment}"}]}
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=60,
                          headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except (requests.RequestException, ValueError) as e:
        log("model call failed:", e)
        return None


def safe_reply(text):
    if not text or len(text) > 280 or BANNED_OUT.search(text) or LINKY.search(text) or "#" in text:
        return False
    emoji = sum(1 for ch in text if ord(ch) > 0x2600)
    return emoji <= 1


def send_outbox(state):
    outbox = load("queue/outbox.json", [])
    sent_any = False
    for item in outbox:
        if item.get("sent_at") or not item.get("message") or not item.get("comment_id"):
            continue
        try:
            r = graph("POST", f"{item['comment_id']}/replies", json_body={"message": item["message"]})
            item["sent_at"] = now().isoformat()
            item["reply_id"] = r.get("id")
            state["replied"][item["comment_id"]] = {"by": "dhruv-approved", "at": item["sent_at"], "text": item["message"]}
            sent_any = True
            log("sent approved reply to", item["comment_id"])
        except GraphError as e:
            item["error"] = str(e)[:200]
            log("outbox send failed", item["comment_id"], e)
    if sent_any or any(i.get("error") for i in outbox):
        save("queue/outbox.json", outbox)


def main():
    if DRY:
        log("DRY RUN: comment desk idle (no IG_TOKEN)")
        return
    state = load("state/comments.json", {"seen": {}, "replied": {}})
    held = load("state/held.json", [])
    me = graph("GET", "me", {"fields": "user_id,username"})
    my_name = (me.get("username") or "").lower()

    send_outbox(state)

    media = graph("GET", f"{IG_ID}/media", {"fields": "id,caption,permalink,timestamp", "limit": LOOKBACK_POSTS}).get("data", [])
    replies_sent = 0
    for m in media:
        try:
            cs = graph("GET", f"{m['id']}/comments",
                       {"fields": "id,text,username,timestamp,replies{id,username,text}", "limit": 50}).get("data", [])
        except GraphError as e:
            log("comments read failed", m["id"], e)
            continue
        for c in cs:
            cid = c["id"]
            if cid in state["seen"] or (c.get("username") or "").lower() == my_name:
                continue
            ours = [r for r in (c.get("replies") or {}).get("data", []) if (r.get("username") or "").lower() == my_name]
            text = c.get("text") or ""
            entry = {"comment_id": cid, "media_id": m["id"], "permalink": m.get("permalink"), "username": c.get("username"),
                     "text": text, "at": c.get("timestamp")}
            if ours:
                state["seen"][cid] = "already-replied"
                continue
            if LINKY.search(text):
                state["seen"][cid] = "ignored-link"
                continue
            decision = ask_model(text, m.get("caption") or "")
            health = bool(HEALTH.search(text))
            if health or not decision or decision.get("action") == "hold":
                entry["draft"] = (decision or {}).get("reply", "")
                entry["category"] = "health" if health else (decision or {}).get("category", "unsure")
                entry["status"] = "held"
                held.append(entry)
                state["seen"][cid] = "held"
                log("held for Dhruv:", cid, entry["category"])
                continue
            if decision.get("action") == "ignore":
                state["seen"][cid] = "ignored"
                continue
            reply = (decision.get("reply") or "").strip()
            if not safe_reply(reply) or replies_sent >= MAX_REPLIES_PER_RUN:
                entry.update({"draft": reply, "category": "failed-guardrail" if replies_sent < MAX_REPLIES_PER_RUN else "rate-cap", "status": "held"})
                held.append(entry)
                state["seen"][cid] = "held"
                continue
            try:
                r = graph("POST", f"{cid}/replies", json_body={"message": reply})
                state["seen"][cid] = "replied"
                state["replied"][cid] = {"by": "auto", "at": now().isoformat(), "text": reply, "reply_id": r.get("id"), "comment": text}
                replies_sent += 1
                log("auto-replied", cid)
            except GraphError as e:
                log("reply failed", cid, e)
    save("state/comments.json", state)
    save("state/held.json", held)


if __name__ == "__main__":
    main()
