#!/usr/bin/env python3
"""
Build the two downloadable bundles from an already-built site.

Run AFTER build_site.py and gen_site.py:
    python3 build_site.py && python3 gen_site.py && python3 make_bundles.py

Produces, in dist/:
    viennavivarium-site.zip              the whole browsable site, ~590 MB
    viennavivarium-research-bundle.zip   translations + data + catalog.csv, ~8 MB

CI runs this on every push and uploads both to the "latest" GitHub release, so
the Download page never serves a snapshot older than the live site. That matters:
the bundles once sat four hours behind a correction pass, still carrying material
the site had already fixed, with nothing to tell a reader.

The README templates live in legacy_data/bundle_readme_*.txt and carry a
{{BUILD_DATE}} placeholder stamped at build time.
"""
import os, re, csv, json, glob, shutil, zipfile, datetime, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "vivarium_site")
DIST = os.path.join(ROOT, "dist")
DATE = datetime.date.today().isoformat()                       # 2026-09-22
NICE = datetime.date.today().strftime("%d %B %Y").lstrip("0")  # 22 September 2026

# Files that must never ship inside a bundle. vivarium_site/ is gitignored, so it
# accumulates local-only leftovers that never appear on the live site — a stale
# README.md from an earlier build nearly shipped once.
SKIP_NAMES = {".DS_Store", "README.md"}
# already-compressed: storing beats deflating, and turns minutes into seconds
STORE_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip"}


def _readme(which):
    p = os.path.join(ROOT, "legacy_data", "bundle_readme_%s.txt" % which)
    return open(p, encoding="utf-8").read().replace("{{BUILD_DATE}}", NICE)


def _zip(src_dir, out_path, top, skip_names=(), level=1):
    n = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as z:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
            for f in sorted(files):
                if f in skip_names:
                    continue
                p = os.path.join(root, f)
                arc = os.path.join(top, os.path.relpath(p, src_dir))
                ct = (zipfile.ZIP_STORED if os.path.splitext(f)[1].lower() in STORE_EXT
                      else zipfile.ZIP_DEFLATED)
                z.write(p, arc, compress_type=ct)
                n += 1
    return n, os.path.getsize(out_path)


def write_catalog_csv(path):
    """One row per paper: the practical entry point into the research bundle."""
    cat = json.load(open(os.path.join(SITE, "data", "catalog.json"), encoding="utf-8"))
    tr = {t["id"]: t for t in json.load(open(os.path.join(SITE, "data", "translations.json"), encoding="utf-8"))}

    def ld(name):
        p = os.path.join(ROOT, "legacy_data", name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    A, S, SENS = ld("consensus_all.json"), ld("consensus_synthesis.json"), ld("sensitivity.json")
    B = "https://eran11234.github.io/viennavivarium/"

    rows = []
    for c in sorted(cat, key=lambda x: x["id"]):
        i = c["id"]; s = str(i)
        a = A.get(s) or {}; y = S.get(s) or {}; t = tr.get(i) or {}
        rows.append(dict(
            id=i, year=c.get("year"), author=c.get("author"),
            title_en=c.get("title_en") or "", title_de=c.get("title") or "",
            journal=c.get("journal") or "", doi=c.get("doi") or "",
            organism=c.get("organism") or "", genus=c.get("genus") or "", taxon=c.get("taxon") or "",
            citations=c.get("citations"), legacy_layer=c.get("layer"),
            discover_status=a.get("status") or "", sleeping_beauty=bool(a.get("sleeping")),
            sbi=a.get("sbi") if a.get("sleeping") else "", verdict=y.get("verdict") or "",
            modern_papers_read=a.get("n_unique") or "", modern_since_2015=a.get("recent") or "",
            context_note=(SENS.get(s) or {}).get("category", ""),
            translation_file=(t.get("trans_slug", "") + "_FULL.md") if t else "",
            reading_page=(B + "papers/" + t["page_slug"] + ".html") if t.get("page_slug") else "",
            dossier_page=(B + "dossier/%d.html" % i) if a else "",
            pdf_file=c.get("pdf") or ""))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return rows


def build_research_bundle():
    top = "viennavivarium-data-%s" % DATE
    # Stage in a temp dir, never under the repo: on a mounted filesystem the
    # cleanup unlink is refused ("Operation not permitted") and the build dies
    # after the zip is already written.
    tmp = tempfile.mkdtemp(prefix="vv-bundle-")
    stage = os.path.join(tmp, top)
    for sub in ("translations", "data", "site-data"):
        os.makedirs(os.path.join(stage, sub), exist_ok=True)

    for f in glob.glob(os.path.join(ROOT, "translations_full", "*.md")):
        shutil.copyfile(f, os.path.join(stage, "translations", os.path.basename(f)))
    for f in glob.glob(os.path.join(ROOT, "legacy_data", "*.json")) + \
             glob.glob(os.path.join(ROOT, "legacy_data", "*.csv")):
        b = os.path.basename(f)
        if b.startswith("_batch_"):          # internal scratch, never shipped
            continue
        shutil.copyfile(f, os.path.join(stage, "data", b))
    for f in glob.glob(os.path.join(SITE, "data", "*.json")):
        shutil.copyfile(f, os.path.join(stage, "site-data", os.path.basename(f)))
    xlsx = os.path.join(ROOT, "BVA Corpus Analysis.xlsx")
    if os.path.exists(xlsx):
        shutil.copyfile(xlsx, os.path.join(stage, os.path.basename(xlsx)))

    rows = write_catalog_csv(os.path.join(stage, "catalog.csv"))
    open(os.path.join(stage, "README.txt"), "w", encoding="utf-8").write(_readme("data"))

    out = os.path.join(DIST, "viennavivarium-research-bundle.zip")
    n, size = _zip(stage, out, top, level=9)
    shutil.rmtree(tmp, ignore_errors=True)
    noted = sum(1 for r in rows if r["context_note"])
    noverd = [r["id"] for r in rows if not r["verdict"]]
    print("research bundle: %d files, %.1f MB  (%d papers, %d with a context note, "
          "no verdict for ids %s)" % (n, size / 1e6, len(rows), noted, noverd))
    return out


def build_site_bundle():
    top = "viennavivarium-site-%s" % DATE
    open(os.path.join(SITE, "README.txt"), "w", encoding="utf-8").write(_readme("site"))
    out = os.path.join(DIST, "viennavivarium-site.zip")
    n, size = _zip(SITE, out, top, skip_names=SKIP_NAMES)
    print("site bundle    : %d files, %.0f MB" % (n, size / 1e6))
    return out


def main():
    if not os.path.isdir(SITE):
        raise SystemExit("vivarium_site/ not found — run build_site.py and gen_site.py first")
    os.makedirs(DIST, exist_ok=True)
    build_research_bundle()
    build_site_bundle()
    print("bundles written to", DIST, "| snapshot", NICE)


if __name__ == "__main__":
    main()
