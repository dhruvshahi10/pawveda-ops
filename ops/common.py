"""Shared helpers for the PawVeda publisher. No secrets live in this repo:
IG_TOKEN, IG_USER_ID and ANTHROPIC_API_KEY come from GitHub Actions secrets."""
import json, os, time, datetime as dt
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH = "https://graph.instagram.com/v25.0"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TOKEN = os.environ.get("IG_TOKEN", "").strip()
IG_ID = os.environ.get("IG_USER_ID", "").strip()
DRY = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes") or not TOKEN


def path(*p):
    return os.path.join(ROOT, *p)


def load(rel, default):
    try:
        with open(path(rel), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(rel, data):
    os.makedirs(os.path.dirname(path(rel)), exist_ok=True)
    with open(path(rel), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def log(*a):
    print(now().astimezone(IST).strftime("%d %b %H:%M IST"), *a, flush=True)


class GraphError(Exception):
    pass


def graph(method, endpoint, params=None, json_body=None, retries=2):
    """Call graph.instagram.com. Raises GraphError with Meta's message on failure."""
    if DRY:
        raise GraphError("dry run: no IG_TOKEN set")
    url = endpoint if endpoint.startswith("http") else f"{GRAPH}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, params=params, json=json_body, headers=headers, timeout=60)
        except requests.RequestException as e:
            last = str(e)
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code < 400:
            return r.json() if r.content else {}
        try:
            err = r.json().get("error", {})
            last = f"{r.status_code} {err.get('type','')} {err.get('code','')}: {err.get('message', r.text)[:300]}"
            transient = err.get("is_transient") or r.status_code >= 500
        except ValueError:
            last, transient = f"{r.status_code}: {r.text[:300]}", r.status_code >= 500
        if not transient:
            break
        time.sleep(5 * (attempt + 1))
    raise GraphError(last)


def media_url(rel):
    """Public URL Instagram fetches media from. Default: jsDelivr serving this public repo at the
    commit being run, so the URL never points at a stale cache."""
    base = os.environ.get("MEDIA_BASE", "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "dhruvshahi10/pawveda-ops")
        sha = os.environ.get("MEDIA_SHA", "")
        if not sha:
            # pin to the last commit that touched media/: it is old enough for jsDelivr to have cached it,
            # and the files never change after that commit. A brand-new commit SHA 404s for a while.
            try:
                import subprocess
                sha = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", "media"], text=True, timeout=20).strip()
            except Exception:
                sha = ""
        sha = sha or os.environ.get("GITHUB_SHA", "main")
        base = f"https://cdn.jsdelivr.net/gh/{repo}@{sha}"
    return f"{base}/{rel.lstrip('/')}"
