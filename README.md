# pawveda-ops

The always-on half of the PawVeda content house. It does three things and nothing else:

1. **Publishes** posts from `queue/schedule.json` at their slot, through Instagram's official API, with the
   AI-generated label on every post. Only entries with `"status": "scheduled"` are posted. The house sets
   `"cut"` or `"hold"` from Dhruv's Review Room decisions; the veto window is 12 hours before the slot.
2. **Answers comments** on PawVeda's posts. Safe ones (thanks, praise, "which dog is this") get a reply in
   PawVeda's voice. Anything about symptoms, food, medicine, dosage or emergencies is **never answered
   here**: it is held in `state/held.json` with a draft for Dhruv. Replies he approves go out from
   `queue/outbox.json`.
3. **Reads insights** daily into `metrics/`.

It never likes, follows, comments on other accounts, or scrolls. That is against Instagram's terms.

## Why this repo is public

Instagram's API fetches post media from a public URL. This repo holds only the publisher code and the
media of posts that are about to be public anyway, served through jsDelivr. Tokens and keys live only in
**Settings → Secrets and variables → Actions**, never in files.

## Secrets

| Secret | What |
|---|---|
| `IG_TOKEN` | Long-lived Instagram token from the Meta app dashboard (valid 60 days; expires around 19 Dec 2026 if made on 19-20 Oct) |
| `IG_USER_ID` | The `user_id` from `GET https://graph.instagram.com/v25.0/me?fields=user_id,username` |
| `ANTHROPIC_API_KEY` | For the comment desk (Claude Haiku). Without it every comment is held instead of answered |

## Running it by hand

Actions → **house** → Run workflow. Tick *dry run* to see what would happen without posting.

## Files

| Path | Written by | What |
|---|---|---|
| `queue/schedule.json` | the house | Every post: slot (IST), media, caption, alt text, first comment, status |
| `queue/outbox.json` | the house | Replies Dhruv approved, waiting to be sent |
| `state/published.json` | publisher | What actually went out, with media ids and links |
| `state/held.json` | comment desk | Comments waiting for Dhruv |
| `state/comments.json` | comment desk | Every comment seen and what was done with it |
| `metrics/` | daily job | Reach, views, saves, shares, watch time per post; followers |
