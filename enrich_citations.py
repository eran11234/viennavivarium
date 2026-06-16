#!/usr/bin/env python3
"""
Verify + enrich every citing work for the BVA corpus via OpenAlex.

For each BVA paper (by its OpenAlex work-id), fetch the works that cite it, with
authors, year, venue, topic, type, and a reconstructed abstract. Merge the
historiographic / species-match flags from the existing harvest. Resumable:
run repeatedly; each run processes papers until a time budget, then saves.

Output: legacy_data/citations_enriched.json
Run:    python3 enrich_citations.py      (repeat until it prints DONE)
"""
import os, re, json, csv, time, subprocess, urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "legacy_data", "citations_enriched.json")
MAILTO = "eran.witz@gmail.com"
TIME_BUDGET = 33          # seconds per invocation (stay under the shell limit)
SELECT = "id,doi,display_name,publication_year,authorships,primary_topic,abstract_inverted_index,type,cited_by_count"

def norm_doi(d):
    if not d: return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", str(d).strip().lower())

def reconstruct_abstract(inv):
    if not inv: return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    if not pos: return ""
    text = " ".join(pos[i] for i in sorted(pos))
    return re.sub(r"\s+", " ", text).strip()[:1600]

def fetch(url):
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "25", url],
                           capture_output=True, text=True)
        return json.loads(r.stdout) if r.stdout else None
    except Exception as e:
        print("  fetch error:", e); return None

def load_inputs():
    catalog = json.load(open(os.path.join(ROOT, "vivarium_site", "data", "catalog.json"), encoding="utf-8"))
    profiles = {int(p["id"]): p for p in json.load(open(os.path.join(ROOT, "legacy_data", "legacy_profiles.json"), encoding="utf-8"))}
    # per-citation flags from the harvest
    flags = {}
    with open(os.path.join(ROOT, "legacy_data", "legacy_citations.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            flags[(int(r["bva_id"]), norm_doi(r["citing_doi"]))] = dict(
                historiographic=(str(r.get("historiographic")).strip().lower() == "true"),
                species_match=r.get("species_match", ""), citing_topic=r.get("citing_topic", ""))
    return catalog, profiles, flags

def main():
    catalog, profiles, flags = load_inputs()
    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = [c for c in catalog
            if c.get("citations", 0) > 0 and str(c["id"]) not in out
            and profiles.get(c["id"], {}).get("wid")]
    todo.sort(key=lambda c: c["id"])
    start = time.time(); done_now = 0
    for c in todo:
        if time.time() - start > TIME_BUDGET:
            break
        pid = c["id"]; wid = profiles[pid]["wid"]
        url = (f"https://api.openalex.org/works?filter=cites:{wid}"
               f"&per-page=200&select={SELECT}&mailto={MAILTO}")
        data = fetch(url)
        if data is None:
            print(f"  paper {pid}: fetch failed, will retry next run"); continue
        works = []
        for w in data.get("results", []):
            doi = norm_doi(w.get("doi"))
            auth = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])][:8]
            pt = w.get("primary_topic") or {}
            topic = dict(name=(pt.get("display_name") or ""),
                         subfield=((pt.get("subfield") or {}).get("display_name") or ""),
                         field=((pt.get("field") or {}).get("display_name") or ""))
            fl = flags.get((pid, doi), {})
            works.append(dict(
                oa_id=(w.get("id") or "").replace("https://openalex.org/", ""),
                doi=doi, title=w.get("display_name") or "", year=w.get("publication_year"),
                authors=auth, type=w.get("type") or "", topic=topic,
                cited_by_count=w.get("cited_by_count"),
                historiographic=fl.get("historiographic", False),
                species_match=fl.get("species_match", ""),
                abstract=reconstruct_abstract(w.get("abstract_inverted_index"))))
        out[str(pid)] = dict(wid=wid, paper_title=c["title"], year=c["year"],
                             author=c["author"], organism=c.get("organism", ""),
                             cited_by_count=c.get("citations", 0),
                             fetched_count=len(works), works=works)
        done_now += 1
        time.sleep(0.25)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    total_papers = sum(1 for c in catalog if c.get("citations", 0) > 0)
    total_works = sum(len(v["works"]) for v in out.values())
    remaining = total_papers - len(out)
    print(f"this run: +{done_now} papers | enriched papers: {len(out)}/{total_papers} "
          f"| citing works captured: {total_works} | remaining papers: {remaining}")
    print("DONE" if remaining == 0 else "MORE (run again)")

if __name__ == "__main__":
    main()
