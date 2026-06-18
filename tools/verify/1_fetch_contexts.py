#!/usr/bin/env python3
"""
Step 1 — fetch the REAL citing passages, overnight, from your own logged-in Chrome.

It connects (over the Chrome DevTools Protocol) to a Chrome you started yourself and
logged into your university library. It never sees your password. For each citing
work it opens the DOI, reads the rendered page, and pulls the sentence(s) that
mention the cited BVA author — so a note can later be written from the real text.

SAFETY / TERMS OF USE — READ THIS:
  Pulling thousands of full texts through institutional access is the kind of bulk
  downloading that publisher AND library terms of service forbid, and it can get your
  university's whole IP range throttled or blocked. This script is therefore SLOW BY
  DESIGN (default ~25-45 s between requests, randomized) and stops itself if it looks
  like it is being blocked. Do NOT lower the delays to "finish in one night". Check
  your library's acceptable-use policy first. At the polite default, ~2000 works takes
  several nights — that is intentional and correct.

Resumable: every attempt is appended to contexts.jsonl; re-running skips done keys.
Ctrl-C safe. Create a file named STOP in this folder to make it exit cleanly.
"""
import json, os, re, time, random, sys, datetime
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ENR  = os.path.join(ROOT, "legacy_data", "citations_enriched.json")
TARG = os.path.join(HERE, "bva_targets.json")
OUT  = os.path.join(HERE, "contexts.jsonl")
DONE = os.path.join(HERE, "citation_notes_existing.json")  # optional, to skip already-verified

CDP_URL   = os.environ.get("CDP_URL", "http://localhost:9222")
MIN_DELAY = float(os.environ.get("MIN_DELAY", "25"))   # seconds between requests (polite!)
MAX_DELAY = float(os.environ.get("MAX_DELAY", "45"))
MAX_FETCH = int(os.environ.get("MAX_FETCH", "0"))      # 0 = no cap this run
NAV_TIMEOUT = 45000

def log(*a):
    print(datetime.datetime.now().strftime("%H:%M:%S"), *a, flush=True)

def sentences(text):
    text = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+", text)

def sanitize(s):
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"[A-Za-z0-9_]{22,}", "", s)   # strip long tokens (ids, cookies)
    return s.strip()[:400]

REF_CHROME = re.compile(
    r"google scholar|download pdf|cite this article|published:|crossref|pubmed|"
    r"view article|save article|sign in|institutional|subscribe|reprints|"
    r"volume\s+\d+|pages?\s+\d|article\s+number|metrics|^\s*doi|©", re.I)
VERBS = re.compile(r"\b(showed|found|reported|cited|describe|demonstrat|observ|suggest|"
                   r"claim|confirm|accord|noted|propos|studie|investigat|postulat|"
                   r"replicat|invalidat|attention|hypothes)\w*", re.I)

def looks_like_reflist(s):
    """True for bibliography entries / page chrome rather than an in-text citation."""
    if REF_CHROME.search(s):
        return True
    if re.match(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+,\s*[A-Z]\.", s):  # 'Przibram, H.: ...'
        return True
    if len(re.findall(r"[a-zäöüß]{3,}", s)) < 4:               # too few prose words
        return True
    return False

def fold(s):
    import unicodedata
    s = s.replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()

def extract(body, surnames, year):
    fsur = [fold(sn) for sn in surnames]
    cand = []
    for sent in sentences(body):
        if not any(sn in fold(sent) for sn in fsur):   # diacritic/ß-insensitive (Weiß=Weiss)
            continue
        s = sanitize(sent)
        if not s or looks_like_reflist(s):
            continue
        score = 0
        for y in (year, year - 1, year + 1):
            if re.search(r"\(\s*" + str(y), s):    # in-text "(1921"
                score += 2
            elif str(y) in s:
                score += 1
        if VERBS.search(s):                        # reads like prose about the work
            score += 1
        cand.append((score, s))
    cand.sort(key=lambda h: -h[0])
    seen, out = set(), []
    for _, s in cand:
        if s and s not in seen:
            seen.add(s); out.append(s)
        if len(out) >= 5:
            break
    return out

def classify(body):
    low = body.lower()
    if len(body) < 600:
        return "scan_or_empty"
    if re.search(r"(introduction|references|materials and methods|results|discussion|abstract)", low):
        if re.search(r"(get access|buy article|purchase pdf|sign in to read|institutional login required)", low) \
           and not re.search(r"(references|acknowledg)", low):
            return "paywalled"
        return "fulltext"
    if re.search(r"(get access|buy article|purchase|log in via|subscribe)", low):
        return "paywalled"
    return "thin"

def main():
    enr = json.load(open(ENR, encoding="utf-8"))
    targ = json.load(open(TARG, encoding="utf-8"))
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            try: done.add(json.loads(line)["key"])
            except Exception: pass
    # optionally skip keys that are already source-verified
    skip_verified = set()
    vpath = os.path.join(ROOT, "legacy_data", "citation_verified.json")
    if os.path.exists(vpath):
        skip_verified = set(json.load(open(vpath, encoding="utf-8")))

    jobs = []
    for pid, rec in enr.items():
        tg = targ.get(str(pid))
        if not tg: continue
        for w in rec.get("works", []):
            key = f"{pid}:{w['oa_id']}"
            if not w.get("doi"): continue
            if key in done or key in skip_verified: continue
            jobs.append((key, pid, w["doi"], tg["surnames"], tg["year"], w.get("year")))
    log(f"{len(jobs)} works to attempt (already done: {len(done)}).  Delay {MIN_DELAY}-{MAX_DELAY}s.")
    if not jobs:
        log("Nothing to do."); return

    with sync_playwright() as p:
        log(f"Connecting to your Chrome at {CDP_URL} ...")
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.set_default_navigation_timeout(NAV_TIMEOUT)

        n_block = 0; n_done = 0
        out = open(OUT, "a", encoding="utf-8")
        for (key, pid, doi, surnames, byear, wyear) in jobs:
            if os.path.exists(os.path.join(HERE, "STOP")):
                log("STOP file found — exiting cleanly."); break
            status, snippets = "error", []
            try:
                page.goto("https://doi.org/" + doi, wait_until="domcontentloaded")
                try: page.wait_for_load_state("networkidle", timeout=12000)
                except Exception: pass
                body = page.inner_text("body")
                status = classify(body)
                if status == "fulltext":
                    snippets = extract(body, surnames, byear)
                    if not snippets:
                        status = "no_passage"
                    else:
                        status = "ok"
            except Exception as e:
                status = "error"; snippets = [str(e)[:120]]
            rec = dict(key=key, pid=pid, doi=doi, status=status,
                       surnames=surnames, year=byear, snippets=snippets,
                       ts=datetime.datetime.now().isoformat(timespec="seconds"))
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            n_done += 1
            log(f"[{n_done}] {key}  {status}  ({len(snippets)} snip)")
            # crude block-detection: many consecutive paywalls/errors => back off / stop
            if status in ("paywalled", "error", "scan_or_empty"):
                n_block += 1
            else:
                n_block = 0
            if n_block >= 8:
                log("8 consecutive failures — possible rate-limit/block or session expired. "
                    "Stopping to protect your library access. Re-check your login and rerun later.")
                break
            if MAX_FETCH and n_done >= MAX_FETCH:
                log(f"Reached MAX_FETCH={MAX_FETCH} for this run."); break
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        out.close()
        log(f"Done this run: {n_done} attempted. contexts.jsonl updated.")

if __name__ == "__main__":
    main()
