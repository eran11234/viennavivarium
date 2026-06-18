#!/usr/bin/env python3
"""
Step 2 — turn the REAL passages (contexts.jsonl) into one-sentence notes.

For every work with status 'ok' it sends ONLY the extracted snippet(s) to the Claude
API and asks for a 1-2 sentence note on how the citing work uses the BVA paper. The
model is told to reply exactly 'SKIP' if the snippet does not actually reference the
BVA work — so nothing is invented. Output: verified_notes.json  {key: note}.

Needs your own key:  export ANTHROPIC_API_KEY=sk-ant-...   (the script never prints it)
If you'd rather not use the API, skip this script — contexts.jsonl already holds the
raw passages and they can be written up by hand or in a Claude Code session.
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CTX  = os.path.join(HERE, "contexts.jsonl")
OUT  = os.path.join(HERE, "verified_notes.json")
ENR  = os.path.join(ROOT, "legacy_data", "citations_enriched.json")
CAT  = os.path.join(ROOT, "vivarium_site", "data", "catalog.json")
MODEL = os.environ.get("VERIFY_MODEL", "claude-3-5-haiku-latest")

PROMPT = """You are annotating how a later work cites an early-20th-century paper from the Vienna Biologische Versuchsanstalt (BVA).

THE BVA PAPER (the one being cited):
  {bva}

THE CITING WORK:
  {citing}

The exact sentence(s) from the citing work that mention the BVA author, verbatim:
  {snips}

Write ONE or TWO plain sentences describing what the citing work does with the BVA paper and why it cites it, grounded ONLY in the sentence(s) above. Be specific and faithful to the text; do not add facts that are not in the snippet. Do not start with "This paper".

Reply with exactly "SKIP" (nothing else) if the sentence(s) are NOT a genuine in-text use of the BVA paper — e.g. they are only a bibliography/reference-list entry (like "Przibram, H.: ..." or a journal/volume/pages line), a page header, a download/access/metadata line, or just a coincidental surname match with no statement about the work."""

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first (export ANTHROPIC_API_KEY=...). Aborting."); sys.exit(1)
    import anthropic
    client = anthropic.Anthropic()

    cat = {str(p["id"]): p for p in json.load(open(CAT, encoding="utf-8"))} if os.path.exists(CAT) else {}
    enr = json.load(open(ENR, encoding="utf-8"))
    wmeta = {}
    for pid, rec in enr.items():
        for w in rec.get("works", []):
            wmeta[f"{pid}:{w['oa_id']}"] = w

    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    rows = [json.loads(l) for l in open(CTX, encoding="utf-8")]
    todo = [r for r in rows if r["status"] == "ok" and r["key"] not in out]
    print(f"{len(todo)} passages to write up (already written: {len(out)}).")

    for i, r in enumerate(todo, 1):
        key = r["key"]; pid = key.split(":")[0]; cp = cat.get(pid, {})
        w = wmeta.get(key, {})
        bva = f"{cp.get('author','?')} ({cp.get('year','?')}). {cp.get('title_en') or cp.get('title','?')}"
        citing = f"{(w.get('authors') or ['?'])[0]} ({w.get('year','?')}). {w.get('title','?')}"
        snips = "\n  ".join('"' + s + '"' for s in r["snippets"])
        if r.get("src") == "ocr":
            snips = ("(These sentence(s) come from OCR of a scanned page and may contain "
                     "transcription errors. If too garbled to be sure of the meaning, reply SKIP.)\n  "
                     + snips)
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=180, temperature=0.2,
                messages=[{"role": "user",
                           "content": PROMPT.format(bva=bva, citing=citing, snips=snips)}])
            note = msg.content[0].text.strip()
        except Exception as e:
            print("  API error on", key, str(e)[:80]); time.sleep(5); continue
        if note and note.upper() != "SKIP":
            out[key] = note
        print(f"[{i}/{len(todo)}] {key} -> {'SKIP' if note.upper()=='SKIP' else note[:70]}")
        if i % 20 == 0:
            json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Wrote {len(out)} verified notes -> {OUT}")

if __name__ == "__main__":
    main()
