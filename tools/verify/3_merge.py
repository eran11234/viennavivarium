#!/usr/bin/env python3
"""
Step 3 — fold the verified notes into the site data, then rebuild.

Updates legacy_data/citation_notes.json (note text) and legacy_data/citation_verified.json
(the list of source-verified keys, which drives the green "verified from source" badge),
then runs gen_site.py. Commit & push with your normal deploy flow afterwards.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
NOTES = os.path.join(ROOT, "legacy_data", "citation_notes.json")
VER   = os.path.join(ROOT, "legacy_data", "citation_verified.json")
VN    = os.path.join(HERE, "verified_notes.json")

def main():
    if not os.path.exists(VN):
        print("No verified_notes.json yet — run 2_write_notes.py first."); sys.exit(1)
    vnotes = json.load(open(VN, encoding="utf-8"))
    notes = json.load(open(NOTES, encoding="utf-8")) if os.path.exists(NOTES) else {}
    verified = set(json.load(open(VER, encoding="utf-8"))) if os.path.exists(VER) else set()

    n_new = sum(1 for k in vnotes if k not in verified)
    notes.update(vnotes)
    verified |= set(vnotes.keys())

    json.dump(notes, open(NOTES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sorted(verified), open(VER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Merged {len(vnotes)} verified notes ({n_new} newly verified). "
          f"Total verified: {len(verified)}.")

    print("Rebuilding site ...")
    subprocess.run([sys.executable, "gen_site.py"], cwd=ROOT, check=True)
    print("Done. Now commit & push:")
    print("  git add legacy_data/citation_notes.json legacy_data/citation_verified.json")
    print("  git commit -m 'Source-verified citation notes (batch)'")
    print("  git push")

if __name__ == "__main__":
    main()
