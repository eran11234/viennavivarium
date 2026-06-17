# Source-verifying the citation notes (overnight, on your Mac)

This harness rewrites the "how it cites" notes from the **actual citing passage**, read
through **your own logged-in Chrome**. You start it; it runs unattended and checkpoints.
It never sees your password (you log in yourself), and it is deliberately slow so it does
not get your library access blocked.

## ⚠️ Read before running
- Pulling thousands of full texts through institutional access is the kind of **bulk
  downloading that publisher and library terms of service prohibit**. Done too fast it can
  get **your university's whole IP range throttled or blocked**. The fetch script defaults
  to **25–45 s between requests** and **stops itself** after 8 straight failures. **Do not
  lower the delays.** At this rate ~2,000 works takes **several nights** — that is correct,
  not a bug. If unsure, check your library's acceptable-use policy first.
- It only reads pages (no bulk PDF downloads).
- Most pre-1960 German papers are **image-only scans** with no text layer, so they will come
  back `scan_or_empty` / `no_passage` — those keep their existing (clearly disclosed) note.
  Realistically this verifies the **modern + digitized subset** (~a quarter to a third).

## One-time setup
```bash
cd tools/verify
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Each run
**1. Start a dedicated Chrome with remote debugging and log into your library in it.**
(Use a separate profile dir so it doesn't touch your everyday Chrome.)
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/bva-verify-chrome" &
```
In that window: sign into your university library / proxy, and **confirm you can open a
paywalled article** (e.g. https://onlinelibrary.wiley.com/doi/10.1002/jez.b.22845 — you
should see the full text, not a paywall). Leave the window open. Keep the Mac awake
(`caffeinate -d` in another terminal, or disable sleep).

**2. Fetch the real passages (this is the long, overnight part).**
```bash
source .venv/bin/activate
python3 1_fetch_contexts.py        # resumable; Ctrl-C safe; `touch STOP` to stop cleanly
```
Writes `contexts.jsonl` (one line per work: status + the extracted sentence(s)).
Re-running skips works already attempted. To do a short test run first:
`MAX_FETCH=15 python3 1_fetch_contexts.py`.

**3. Write the notes from those passages (uses the Claude API — your key).**
```bash
export ANTHROPIC_API_KEY=sk-ant-...      # your own key; the script never prints it
python3 2_write_notes.py                 # snippet -> 1-2 sentence note; 'SKIP' if not a real cite
```
Writes `verified_notes.json`. (Prefer to write them yourself / in a Claude Code session?
Skip this step — `contexts.jsonl` already has the raw passages.)

**4. Merge into the site and rebuild, then deploy.**
```bash
python3 3_merge.py                       # updates citation_notes.json + citation_verified.json, runs gen_site.py
cd ../.. && git add legacy_data/citation_notes.json legacy_data/citation_verified.json \
  && git commit -m "Source-verified citation notes (batch)" && git push
```
Verified notes show a green **"✓ verified from source"** badge on the dossier and map.

## Files
- `bva_targets.json` — per-paper author surname(s) + year to search for (precomputed).
- `1_fetch_contexts.py` → `contexts.jsonl`
- `2_write_notes.py` → `verified_notes.json`
- `3_merge.py` → updates the two `legacy_data/*` files + rebuilds
- `STOP` — create this file to stop the fetcher cleanly between requests.

## Tuning
- `MIN_DELAY` / `MAX_DELAY` (seconds, default 25/45) — politeness. Leave them high.
- `MAX_FETCH` (default 0 = all) — cap a single run.
- `CDP_URL` (default http://localhost:9222).
- `VERIFY_MODEL` (default claude-3-5-haiku-latest).
