#!/usr/bin/env python3
"""
Build the BVA / Vienna Vivarium English orientation platform (static site).

Reads the existing project data (corpus xlsx, legacy_profiles.json,
paper_legacy_summary.csv, the 7 translation markdown files + figures, and the
175 source PDFs in articles/) and generates a self-contained static website in
BVA/site/ — framework-free HTML/CSS/JS that opens by double-click and deploys
to any free static host.

Run:  python3 build_site.py
"""
import os, re, json, csv, html, glob, shutil, subprocess, unicodedata
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "vivarium_site")
DATA = os.path.join(SITE, "data")
ARTICLES = os.path.join(ROOT, "articles")
TRANS = os.path.join(ROOT, "translations_full")
FIGSRC = os.path.join(TRANS, "figures")

# ---------- helpers ----------
def norm(s):
    """Normalize text for fuzzy matching: strip diacritics, lowercase, alnum tokens."""
    if not s: return ""
    s = html.unescape(str(s))
    s = s.replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    return s

def tokens(s):
    return set(t for t in re.split(r"[^a-z0-9]+", norm(s)) if len(t) > 2)

def surname(author):
    a = norm(author)
    a = re.sub(r"\(.*?\)", " ", a)            # drop "(riga)"
    parts = [p for p in re.split(r"[\s/,-]+", a) if p]
    return parts[-1] if parts else a

def clean(s):
    return html.unescape(str(s)).strip() if s is not None else ""

def layer_num(s):
    m = re.search(r"(\d)", str(s) or "")
    return int(m.group(1)) if m else None

# ---------- load sources ----------
def load_summary():
    rows = {}
    with open(os.path.join(ROOT, "legacy_data", "paper_legacy_summary.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[int(r["id"])] = r
    return rows

def load_profiles():
    with open(os.path.join(ROOT, "legacy_data", "legacy_profiles.json"), encoding="utf-8") as f:
        data = json.load(f)
    return {int(p["id"]): p for p in data}

def load_data_sheet():
    """xlsx 'Data' sheet: cleaner German titles + author(full) + rationale."""
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(ROOT, "BVA Corpus Analysis.xlsx"), read_only=True)
    ws = wb["Data"]
    out = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        year, author, author_full, title, citations, layer, rationale = row[:7]
        if year is None: continue
        out.append(dict(year=year, author=clean(author), author_full=clean(author_full),
                        title=clean(title), citations=citations, layer=clean(layer),
                        rationale=clean(rationale)))
    return out

# ---------- PDF index ----------
def pdf_index():
    files = [os.path.basename(p) for p in glob.glob(os.path.join(ARTICLES, "*.pdf"))]
    idx = []
    for fn in files:
        m = re.match(r"(\d{4})_([^_]+)_(.*?)(?:__[a-z0-9]+)?\.pdf$", fn)
        if not m:
            idx.append((None, "", fn, tokens(fn))); continue
        yr, auth, titlepart = m.group(1), m.group(2), m.group(3)
        idx.append((int(yr), norm(auth), fn, tokens(titlepart)))
    return idx

def match_pdf(year, author, title, idx, used):
    cand = [e for e in idx if e[0] == year]
    if not cand: cand = idx
    sn = surname(author)
    ttok = tokens(title)
    best, best_score = None, 0.0
    for yr, auth, fn, ftok in cand:
        if not ttok or not ftok: continue
        overlap = len(ttok & ftok) / max(1, min(len(ttok), len(ftok)))
        score = overlap + (0.25 if sn and sn in auth else 0) + (0.15 if yr == year else 0)
        if fn in used: score -= 0.5
        if score > best_score:
            best, best_score = fn, score
    return (best, round(best_score, 2)) if best_score >= 0.45 else (None, round(best_score, 2))

def assign_pdfs(summary, ds_match, idx, trans_for_id):
    """Unique global assignment: each paper -> exactly one source PDF (bijection)."""
    assigned, used = {}, set()
    for pid, slug in trans_for_id.items():       # translated papers: verified mapping first
        assigned[pid] = TRANS_PDF[slug]; used.add(TRANS_PDF[slug])
    def info(s):
        ds = ds_match(int(s["year"]), clean(s["author"]), s["title"])
        return tokens(ds.get("title") or clean(s["title"])), surname(clean(s["author"])), int(s["year"])
    pairs = []
    for pid, s in summary.items():
        if pid in assigned: continue
        ttok, sn, year = info(s)
        if not ttok: continue
        for yr, auth, fn, ftok in idx:
            if fn in used or not ftok: continue
            overlap = len(ttok & ftok) / max(1, min(len(ttok), len(ftok)))
            score = overlap + (0.25 if sn and sn in auth else 0) + (0.30 if yr == year else 0)
            if score >= 0.40:
                pairs.append((score, pid, fn))
    pairs.sort(key=lambda x: x[0], reverse=True)       # greedy by best score, unique
    for score, pid, fn in pairs:
        if pid in assigned or fn in used: continue
        assigned[pid] = fn; used.add(fn)
    rem = [e for e in idx if e[2] not in used]          # complete the bijection
    for pid, s in summary.items():
        if pid in assigned: continue
        ttok, sn, year = info(s)
        best_i, best_sc = -1, -1.0
        for i, (yr, auth, fn, ftok) in enumerate(rem):
            ov = (len(ttok & ftok) / max(1, min(len(ttok), len(ftok)))) if ttok and ftok else 0
            sc = ov + (0.30 if yr == year else 0) + (0.25 if sn and sn in auth else 0)
            if sc > best_sc: best_sc, best_i = sc, i
        if best_i >= 0:
            assigned[pid] = rem[best_i][2]; used.add(rem[best_i][2]); rem.pop(best_i)
    return assigned

# ---------- translation metadata ----------
# Confirmed slug -> source PDF (verified by DOI / fileOnDisk / title)
TRANS_PDF = {
 "01_Przibram_1924_Amphibian-embryo": "1924_Przibram_Die-virtuelle-und-reelle-Lage-des-Amphibienembryos-nach-naturlichen-un.pdf",
 "02_Steinach_1916_Puberty-glands": "1916_Steinach_Pubertatsdrusen-und-Zwitterbildung.pdf",
 "03_Weiss_1925_Limb-skeleton": "1925_Weiss_Unabhangigkeit-der-Extremitatenregeneration-vom-Skelett-bei-Triton-cri.pdf",
 "04_Przibram-Megusar_1912_Sphodromantis-growth": "1912_PrzibramMegusar_Wachstumsmessungen-an-Sphodromantis-bioculata-Burm.pdf",
 "05_Kammerer_1909_Alytes-inheritance": "1909_Kammerer_Vererbung-erzwungener-Fortpflanzungsanpassungen.pdf",
 "06_Hadzi_1906_Hydra": "1906_Hadzi_Vorversuche-zur-Biologie-von-Hydra.pdf",
 "07_Przibram_1921_Form-velocity": "1921_Przibram_Form-und-Geschwindigkeit-Ein-Beitrag-zur-allgemeinen-Morphologie-Die-N.pdf",
 "08_Kammerer_1904_Salamandra": "1904_Kammerer_Beitrag-zur-Erkenntnis-der-Verwandtschaftsverhaltnisse-von-Salamandra.pdf",
 "09_Megusar_1912_Crustacean-colour": "1912_Megusar_Experimente-uber-den-Farbwechsel-der-Crustaceen.pdf",
 "10_Brecher_1921_Pieris-pupal-colours": "1921_Brecher_Die-Puppenfarbungen-des-Kohlweißlings-Pieris-brassicae-L-Sechster-Teil.pdf",
 "11_Przibram_1921_Triple-formation": "1921_Przibram_Die-Bruch-Dreifachbildung-im-Tierreiche.pdf",
 "12_Weiss_1924_Transplanted-limb-function": "1924_Weiss_Die-Funktion-transplantierter-Amphibienextremitaten.pdf",
 "13_Weiss_1926_Whole-regenerate-half": "1926_Weiss_Ganzregenerate-aus-Halbem-Extremitatenquerschnitt.pdf",
 "14_PrzibramBrecher_1919_Causes-of-colouration": "1919_PrzibramBrecher_Ursachen-tierischer-Farbkleidung.pdf",
 "15_Kammerer_1907_Reproductive-adaptations-II": "1907_Kammerer_Vererbung-erzwungener-Fortpflanzungsanpassungen.pdf",
 "16_Abolin_1925_Fish-colour-chemicals": "1925_Abolin_Beeinflussung-des-Fischfarbwechsels-durch-Chemikalien.pdf",
 "17_Uhlenhuth_1913_Salamander-eye-metamorphosis": "1913_Uhlenhuth_Die-synchrone-Metamorphose-transplantierter-Salamanderaugen.pdf",
 "18_Weiss_1927_Blastem-potency": "1927_Weiss_Potenzprufung-am-Regenerationsblastem.pdf",
 "19_Steinach_1920_Hermaphrodite-glands": "1920_Steinach_Kunstliche-und-naturliche-Zwitterdrusen-und-ihre-analogen-Wirkungen.pdf",
 "20_Uhlenhuth_1912_Amphibian-eye-transplant": "1912_Uhlenhuth_Die-Transplantation-des-Amphibienauges.pdf",
 "21_Kurz_1912_Triton-leg-potencies": "1912_Kurz_Die-beinbildenden-Potenzen-entwickelter-Tritonen.pdf",
}
# authoritative German titles for translated papers (corpus titles can be mismatched)
TRANS_DE = {
 "01_Przibram_1924_Amphibian-embryo": "Die virtuelle und reelle Lage des Amphibienembryos nach natürlichen und künstlichen Marken am Ei des Bergmolches (Triton alpestris)",
 "02_Steinach_1916_Puberty-glands": "Pubertätsdrüsen und Zwitterbildung",
}
# English titles for translations not covered by _args.json
TRANS_EN = {
 "08_Kammerer_1904_Salamandra": "A Contribution to the Knowledge of the Relationships of Salamandra atra and maculosa",
 "09_Megusar_1912_Crustacean-colour": "Experiments on the Colour Change of the Crustaceans",
 "10_Brecher_1921_Pieris-pupal-colours": "The Pupal Colourations of the Cabbage White, Pieris brassicae L. (VI: The Chemism of Colour Adaptation)",
 "11_Przibram_1921_Triple-formation": "Triple-Formation at a Break in the Animal Kingdom",
 "12_Weiss_1924_Transplanted-limb-function": "The Function of Transplanted Amphibian Limbs",
 "13_Weiss_1926_Whole-regenerate-half": "Whole-Regenerates from a Half Limb Cross-Section",
 "14_PrzibramBrecher_1919_Causes-of-colouration": "Causes of Animal Colouration. I. Preliminary Experiments on Extracts",
 "15_Kammerer_1907_Reproductive-adaptations-II": "Inheritance of Enforced Reproductive Adaptations. I & II: Offspring of the Late-Born Salamandra maculosa and the Early-Born Salamandra atra",
 "16_Abolin_1925_Fish-colour-chemicals": "Influencing the Colour Change of Fishes by Chemicals (I: Infundin and Adrenalin on the Melano- and Xanthophores of the Minnow)",
 "17_Uhlenhuth_1913_Salamander-eye-metamorphosis": "The Synchronous Metamorphosis of Transplanted Salamander Eyes",
 "18_Weiss_1927_Blastem-potency": "Potency-Testing on the Regeneration Blastema (I: Limb-Formation from Tail-Blastema in the Limb-Field in Triton)",
 "19_Steinach_1920_Hermaphrodite-glands": "Artificial and Natural Hermaphrodite Glands and Their Analogous Effects",
 "20_Uhlenhuth_1912_Amphibian-eye-transplant": "The Transplantation of the Amphibian Eye",
 "21_Kurz_1912_Triton-leg-potencies": "The Leg-Forming Potencies of Developed Newts (Triton)",
}
# slug -> (year, surname-ish) for catalog matching
TRANS_KEY = {
 "01_Przibram_1924_Amphibian-embryo": (1924, "przibram", "virtuelle reelle lage amphibienembryos"),
 "02_Steinach_1916_Puberty-glands": (1916, "steinach", "pubertatsdrusen zwitterbildung"),
 "03_Weiss_1925_Limb-skeleton": (1925, "weiss", "unabhangigkeit extremitatenregeneration skelett triton"),
 "04_Przibram-Megusar_1912_Sphodromantis-growth": (1912, "megusar", "wachstumsmessungen sphodromantis bioculata"),
 "05_Kammerer_1909_Alytes-inheritance": (1909, "kammerer", "vererbung erzwungener fortpflanzungsanpassungen"),
 "06_Hadzi_1906_Hydra": (1906, "hadzi", "vorversuche biologie hydra"),
 "07_Przibram_1921_Form-velocity": (1921, "przibram", "form geschwindigkeit morphologie"),
 "08_Kammerer_1904_Salamandra": (1904, "kammerer", "verwandtschaftsverhaltnisse salamandra atra maculosa"),
 "09_Megusar_1912_Crustacean-colour": (1912, "megusar", "experimente farbwechsel crustaceen"),
 "10_Brecher_1921_Pieris-pupal-colours": (1921, "brecher", "puppenfarbungen kohlweisslings pieris brassicae"),
 "11_Przibram_1921_Triple-formation": (1921, "przibram", "bruch dreifachbildung tierreiche"),
 "12_Weiss_1924_Transplanted-limb-function": (1924, "weiss", "funktion transplantierter amphibienextremitaten"),
 "13_Weiss_1926_Whole-regenerate-half": (1926, "weiss", "ganzregenerate halbem extremitatenquerschnitt"),
 "14_PrzibramBrecher_1919_Causes-of-colouration": (1919, "przibram", "ursachen tierischer farbkleidung"),
 "15_Kammerer_1907_Reproductive-adaptations-II": (1907, "kammerer", "vererbung erzwungener fortpflanzungsanpassungen"),
 "16_Abolin_1925_Fish-colour-chemicals": (1925, "abolin", "beeinflussung fischfarbwechsels chemikalien"),
 "17_Uhlenhuth_1913_Salamander-eye-metamorphosis": (1913, "uhlenhuth", "synchrone metamorphose transplantierter salamanderaugen"),
 "18_Weiss_1927_Blastem-potency": (1927, "weiss", "potenzprufung regenerationsblastem"),
 "19_Steinach_1920_Hermaphrodite-glands": (1920, "steinach", "kunstliche naturliche zwitterdrusen analogen wirkungen"),
 "20_Uhlenhuth_1912_Amphibian-eye-transplant": (1912, "uhlenhuth", "transplantation amphibienauges"),
 "21_Kurz_1912_Triton-leg-potencies": (1912, "kurz", "beinbildenden potenzen entwickelter tritonen"),
}

def load_trans_meta():
    meta = {}
    p = os.path.join(TRANS, "_work", "_meta.json")
    if os.path.exists(p):
        meta.update(json.load(open(p, encoding="utf-8")))
    args = {}
    p = os.path.join(TRANS, "_work", "_args.json")
    if os.path.exists(p):
        a = json.load(open(p, encoding="utf-8"))
        args = a.get("papers", {})
    # word counts + figure counts from the md
    out = {}
    for slug in TRANS_PDF:
        md = os.path.join(TRANS, slug + "_FULL.md")
        words, figs, title_en = 0, 0, ""
        if os.path.exists(md):
            txt = open(md, encoding="utf-8").read()
            words = len(re.findall(r"\w+", txt))
            figs = len(re.findall(r"!\[", txt))
        title_en = (args.get(slug, {}) or {}).get("title_en", "")
        out[slug] = dict(meta=meta.get(slug, {}), title_en=title_en, words=words, figs=figs)
    # hardcode title_en / status for 01,02 (not in _args) and gaps
    out["01_Przibram_1924_Amphibian-embryo"]["title_en"] = "The Virtual and Real Position of the Amphibian Embryo, from Natural and Artificial Marks on the Egg of the Alpine Newt (Triton alpestris)"
    out["02_Steinach_1916_Puberty-glands"]["title_en"] = "Puberty Glands and Hermaphrodite Formation"
    for slug, t in TRANS_EN.items():
        if slug in out:
            out[slug]["title_en"] = t
    return out

# ---------- build catalog ----------
def build():
    os.makedirs(DATA, exist_ok=True)
    summary = load_summary()
    profiles = load_profiles()
    datasheet = load_data_sheet()
    idx = pdf_index()
    tmeta = load_trans_meta()

    # index data-sheet rows by (year, surname) for clean titles + author_full + rationale
    ds_by_key = defaultdict(list)
    for d in datasheet:
        ds_by_key[(d["year"], surname(d["author"]))].append(d)

    def ds_match(year, author, title):
        cands = ds_by_key.get((year, surname(author)), [])
        if not cands: return {}
        if len(cands) == 1: return cands[0]
        tt = tokens(title)
        return max(cands, key=lambda d: len(tokens(d["title"]) & tt))

    # which catalog id is each translation?
    trans_for_id = {}
    for slug, (yr, sn, ttl) in TRANS_KEY.items():
        best_id, best = None, 0
        for pid, s in summary.items():
            if int(s["year"]) != yr: continue
            sc = len(tokens(ttl) & tokens(s["title"])) + (1 if sn in norm(s["author"]) else 0)
            if sc > best: best, best_id = sc, pid
        if best_id: trans_for_id[best_id] = slug

    assigned = assign_pdfs(summary, ds_match, idx, trans_for_id)
    catalog, legacy = [], {}
    mapped = 0
    for pid in sorted(summary):
        s = summary[pid]; pr = profiles.get(pid, {})
        year = int(s["year"]); author = clean(s["author"])
        ds = ds_match(year, author, s["title"])
        title_de = ds.get("title") or clean(pr.get("title")) or clean(s["title"])
        author_full = ds.get("author_full") or author
        organism = clean(s.get("organism")) or clean(pr.get("organism"))
        phenomena = pr.get("phenomena") or [p.strip() for p in (s.get("phenomena") or "").split(",") if p.strip()]
        layer = layer_num(s.get("layer")) or layer_num(ds.get("layer"))
        conv = clean(s.get("convergence_axis"))
        doi = clean(s.get("doi")) or clean(pr.get("doi"))
        cited = int(s.get("cited_by_count") or pr.get("cited_by_count") or 0)
        n_par = int(s.get("n_parallels") or 0)
        same_uncited = int(s.get("n_parallel_same_organism_uncited") or 0)
        same_cites = int(s.get("n_same_organism_citations") or 0)
        rediscovery = bool(same_uncited > 0 and same_cites == 0)
        slug = trans_for_id.get(pid)
        pdf = assigned.get(pid)
        if pdf:
            mapped += 1
        if slug:                       # prefer the translation's authoritative German title
            mt = ((tmeta.get(slug, {}) or {}).get("meta") or {}).get("title") or TRANS_DE.get(slug)
            if mt:
                title_de = mt

        rec = dict(
            id=pid, year=year, author=author, author_full=author_full,
            title=title_de, organism=organism, genus=clean(pr.get("genus")),
            modern=clean(pr.get("modern")), taxon=clean(pr.get("taxon")),
            phenomena=phenomena, layer=layer, convergence=conv, doi=doi,
            citations=cited, n_parallels=n_par, rediscovery=rediscovery,
            pdf=pdf, has_translation=bool(slug),
            slug=(slug.split("_")[0] + "-" + re.sub(r"[^a-z0-9]+","-",norm(author)) + "-" + str(year)) if slug else None,
            trans_slug=slug,
            title_en=(tmeta.get(slug, {}).get("title_en") if slug else None),
            rationale=ds.get("rationale", ""),
        )
        catalog.append(rec)

        # legacy detail (cap citations to keep payload sane)
        cites = []
        for c in (pr.get("citations") or [])[:30]:
            cites.append(dict(doi=clean(c.get("doi")), year=c.get("year"),
                              author=clean(c.get("author")), title=clean(c.get("title"))))
        legacy[pid] = dict(cited_by_count=cited, citations=cites, n_parallels=n_par,
                           parallels_total_estimate=s.get("parallels_total_estimate"),
                           convergence=conv, modern=clean(pr.get("modern")),
                           genus=clean(pr.get("genus")), rediscovery=rediscovery,
                           layer=layer, top_parallel_dois=clean(s.get("top_parallel_dois")))

    # write data as JS globals (works from file://) + json copies
    with open(os.path.join(DATA, "catalog.js"), "w", encoding="utf-8") as f:
        f.write("window.CATALOG=" + json.dumps(catalog, ensure_ascii=False) + ";")
    with open(os.path.join(DATA, "legacy.js"), "w", encoding="utf-8") as f:
        f.write("window.LEGACY=" + json.dumps(legacy, ensure_ascii=False) + ";")
    with open(os.path.join(DATA, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)

    # ----- translations index -----
    JOURNAL_OVERRIDE = {
      "01_Przibram_1924_Amphibian-embryo": "Archiv f. mikroskopische Anatomie u. Entwicklungsmechanik 102 (1924)",
      "02_Steinach_1916_Puberty-glands": "Archiv f. Entwicklungsmechanik 42 (1916)",
    }
    INPROG = {"05_Kammerer_1909_Alytes-inheritance", "07_Przibram_1921_Form-velocity"}
    by_trans = {c["trans_slug"]: c for c in catalog if c["trans_slug"]}
    translations = []
    for slug, c in by_trans.items():
        tm = tmeta.get(slug, {}); m = tm.get("meta", {})
        vol = m.get("volume")
        journal = JOURNAL_OVERRIDE.get(slug) or (
            f"Archiv f. Entwicklungsmechanik {vol} ({c['year']})" if vol
            else f"Archiv f. Entwicklungsmechanik der Organismen ({c['year']})")
        translations.append(dict(
            trans_slug=slug, page_slug=c["slug"], id=c["id"],
            title_en=tm.get("title_en") or c.get("title_en") or "",
            title_de=c["title"], author=c["author_full"] or c["author"],
            year=c["year"], journal=journal, doi=c["doi"], pdf=c["pdf"],
            organism=c["organism"], words=tm.get("words", 0), figs=tm.get("figs", 0),
            status=("in-progress" if slug in INPROG else "complete"),
        ))
    translations.sort(key=lambda t: t["trans_slug"])
    with open(os.path.join(DATA, "legacy.json"), "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)
    with open(os.path.join(DATA, "translations.json"), "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=1)

    # report
    tr = [c for c in catalog if c["has_translation"]]
    print(f"catalog papers : {len(catalog)}")
    print(f"pdf mapped     : {mapped}/{len(catalog)}")
    print(f"translations   : {len(tr)} -> ids {[c['id'] for c in tr]}")
    print(f"rediscovery    : {sum(1 for c in catalog if c['rediscovery'])}")
    print(f"layers         : " + ", ".join(f"L{n}={sum(1 for c in catalog if c['layer']==n)}" for n in [1,2,3,4]))
    miss = [c['id'] for c in catalog if not c['pdf']]
    print(f"missing pdf ids: {miss[:20]}{' ...' if len(miss)>20 else ''}")
    for c in tr:
        print(f"  trans id={c['id']} {c['year']} {c['author']:18.18} pdf={'OK' if c['pdf'] else 'MISSING'}  slug={c['trans_slug']}")
    return catalog, legacy, tmeta, trans_for_id

if __name__ == "__main__":
    build()
