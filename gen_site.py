#!/usr/bin/env python3
"""
Generate the static site pages + assets for the BVA / Vienna Vivarium platform.
Reads site/data/*.json (produced by build_site.py) and writes HTML/CSS/JS,
copies figures, and copies the source PDFs for the translated papers.
Run AFTER build_site.py:  python3 gen_site.py
"""
import os, re, json, glob, shutil, subprocess, html

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "vivarium_site")
DATA = os.path.join(SITE, "data")
TRANS = os.path.join(ROOT, "translations_full")
FIGSRC = os.path.join(TRANS, "figures")
ARTICLES = os.path.join(ROOT, "articles")

# FULL_PDFS=1 (used by CI) bundles all 175 German originals and links every
# paper to its local PDF. Unset (local dev) bundles only the 7 translated papers
# and links the rest to their DOI, to keep local builds light.
FULL = os.environ.get("FULL_PDFS") == "1"

catalog = json.load(open(os.path.join(DATA, "catalog.json"), encoding="utf-8"))
legacy = json.load(open(os.path.join(DATA, "legacy.json"), encoding="utf-8"))
translations = json.load(open(os.path.join(DATA, "translations.json"), encoding="utf-8"))
tr_by_slug = {t["trans_slug"]: t for t in translations}

# Reader-facing context notes for papers that need framing before they are read
# (sexual orientation, intersex people, race, remains obtained from people who
# could not refuse). Rendered at the TOP of the reading page and the dossier, so
# a listed paper cannot be published without its note. See legacy_data/sensitivity.json.
_sensp = os.path.join(ROOT, "legacy_data", "sensitivity.json")
SENS = json.load(open(_sensp, encoding="utf-8")) if os.path.exists(_sensp) else {}
SENS = {k: v for k, v in SENS.items() if not k.startswith("_")}

def sens_html(pid, where):
    """The context block for one paper, or '' if it needs none."""
    s = SENS.get(str(pid))
    if not s or where not in (s.get("where") or ["read", "dossier"]):
        return ""
    paras = "".join("<p>%s</p>" % html.escape(p) for p in s.get("paras", []))
    cat = ('<span class="senscat">%s</span>' % html.escape(s["category"])) if s.get("category") else ""
    return ('<aside class="senswarn sev-%s" role="note" aria-label="Context note">'
            '<p class="sensh">%s%s</p>%s</aside>'
            % (html.escape(s.get("severity") or "medium"), cat,
               html.escape(s.get("heading") or "Before you read this"), paras))

# ---------------------------------------------------------------- assessment (September 2026 review)
# Where each paper's own claim stands today, how current research uses it, and what it offers a
# researcher now: legacy_data/assessment.json (built from a paper-by-paper reading under one rubric).
# This replaced the old statuses, the sleeping-beauty index and the legacy layers.
_asp = os.path.join(ROOT, "legacy_data", "assessment.json")
ASSESS = ({int(k): v for k, v in json.load(open(_asp, encoding="utf-8")).items() if not k.startswith("_")}
          if os.path.exists(_asp) else {})
STANDING = [   # key, full label, short label, definition
    ("established", "Established", "Established",
     "Later work confirmed this paper’s specific result, or explicitly credits it for a result that is now standard."),
    ("consistent", "Consistent with current knowledge", "Consistent",
     "The phenomenon it reports is accepted today, but this paper’s own result was never re-tested. It stands as an early instance."),
    ("revised", "Revised", "Revised",
     "The observation holds, at least in part, but its explanation, mechanism, scope or generality has changed."),
    ("unresolved", "Unresolved", "Unresolved",
     "A specific question the paper raised has not been settled: never re-tested with modern methods, or the evidence is mixed."),
    ("not_supported", "Not supported", "Not supported",
     "Later work contradicts the claim, it failed to replicate, or it rests on a framework now rejected."),
    ("no_claim", "No claim to assess", "No claim",
     "An obituary, a review, a methods paper or a pure description: nothing empirical to adjudicate."),
]
ST_LABEL = {k: l for k, l, _, _ in STANDING}
ST_SHORT = {k: s for k, _, s, _ in STANDING}
ST_DEF = {k: d for k, _, _, d in STANDING}
USE = [
    ("tested", "Tested or used today", "Current research re-tests the result or uses the paper’s data."),
    ("precedent", "Cited as a precedent",
     "Cited in scientific work since 1990, usually as an early description or as background, without re-testing it."),
    ("historians", "Cited by historians", "Cited since 1990 only in the history of science."),
    ("none", "Not cited since 1990", "No citing work since 1990 is recorded in OpenAlex."),
]
USE_LABEL = {k: l for k, l, _ in USE}
USE_DEF = {k: d for k, _, d in USE}
OFFERS = [("testable", "A testable question"), ("data", "Quantitative data"), ("method", "A reusable method"),
          ("organism", "An unusual system"), ("history", "Chiefly of historical interest")]
OFFER_LABEL = dict(OFFERS)
BASIS_LABEL = {"modern literature": "the modern literature", "citing works": "the works that cite it",
               "the paper's text": "the paper itself", "general knowledge": "general knowledge of the field"}


def st_chip(pid, full=False, href=None):
    """The standing chip for one paper ('' if it has no assessment)."""
    a = ASSESS.get(pid)
    if not a:
        return ""
    s = a["standing"]
    lab = ST_LABEL[s] if full else ST_SHORT[s]
    if href:
        return '<a class="stc stc-%s" href="%s" title="%s">%s</a>' % (s, href, html.escape(ST_DEF[s]), html.escape(lab))
    return '<span class="stc stc-%s" title="%s">%s</span>' % (s, html.escape(ST_DEF[s]), html.escape(lab))


def use_chip(pid):
    a = ASSESS.get(pid)
    if not a:
        return ""
    u = a["use"]
    return '<span class="usec usec-%s" title="%s">%s</span>' % (u, html.escape(USE_DEF[u]), html.escape(USE_LABEL[u]))


# the six big questions of the tour, reused as a filter on Discover
PROGRAMME_OF_PHENOMENON = {
    "regeneration": "regen", "heteromorphosis": "regen",
    "transplantation": "graft", "developmental_mechanics": "graft",
    "pigmentation": "colour", "color_change": "colour", "light_effects": "colour",
    "sex_determination": "sex",
    "inheritance_of_acquired": "heredity", "thermal_modification": "heredity",
    "salinity_osmotic": "heredity", "hybridization": "heredity",
    "growth": "growth", "morphology": "growth", "behavior": "growth", "gravity_effects": "growth",
}
# most specific first: a paper tagged both "regeneration" and "sex_determination" is about sex
PHENOMENON_PRIORITY = ["sex_determination", "inheritance_of_acquired", "hybridization", "pigmentation",
                       "color_change", "light_effects", "thermal_modification", "salinity_osmotic",
                       "heteromorphosis", "transplantation", "growth", "morphology", "gravity_effects",
                       "behavior", "regeneration", "developmental_mechanics"]


def programme_map():
    """paper id -> programme id, and the programmes (id, title) in tour order."""
    tp = os.path.join(ROOT, "legacy_data", "tour_tree.json")
    if not os.path.exists(tp):
        return {}, []
    TT = json.load(open(tp, encoding="utf-8"))
    assign = {int(k): v for k, v in TT.get("assign", {}).items()}
    out = {}
    for c in catalog:
        if c["id"] in assign:
            out[c["id"]] = assign[c["id"]]
            continue
        ph = c.get("phenomena") or []
        out[c["id"]] = next((PROGRAMME_OF_PHENOMENON[p] for p in PHENOMENON_PRIORITY if p in ph), "growth")
    return out, [(P["id"], P["title"]) for P in TT["programmes"]]

YEARS = [c["year"] for c in catalog]
STATS = dict(papers=len(catalog), trans=len(translations),
             y0=min(YEARS), y1=max(YEARS),
             authors=len({c["author"] for c in catalog}),
             redis=sum(1 for c in catalog if c["rediscovery"]))

NAV = [("index.html", "Home"), ("tour.html", "Tour"), ("catalog.html", "Catalog"),
       ("translations.html", "Translations"),
       ("rediscovery.html", "Discover"), ("authors.html", "Authors"),
       ("analytics.html", "Analytics"), ("about.html", "About")]

# ---------------------------------------------------------------- shell
SITE_URL = "https://eran11234.github.io/viennavivarium/"
import time as _time
BUILD_ID = _time.strftime("%Y%m%d%H%M")  # cache-buster for the stylesheet: GitHub Pages serves assets with max-age=600

# --- Get-involved form -------------------------------------------------------
# FORM_ENDPOINT: paste your Formspree form URL here (https://formspree.io/f/xxxxxxxx).
# While it is empty, the form falls back to opening the visitor's mail client addressed to CONTACT_EMAIL.
FORM_ENDPOINT = "https://formspree.io/f/xyeyjrpd"
CONTACT_EMAIL = "eran.witz@gmail.com"
SITE_DESC = ("The Biologische Versuchsanstalt (Vienna 'Vivarium') corpus in English: 175 papers from the "
             "institute's zoological department (1904–1930) with full translations, the German originals, "
             "and every paper read against today's science.")
FAVICON = ("data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' rx='12' fill='%2333485c'/%3E"
           "%3Ctext x='32' y='45' font-family='Georgia,serif' font-size='38' font-weight='bold' "
           "text-anchor='middle' fill='%23f3efe6'%3EV%3C/text%3E%3C/svg%3E")

# --- Downloadable snapshots --------------------------------------------------
# Rebuilt by CI on EVERY push (make_bundles.py) and uploaded to the "latest"
# release, so the Download page can never serve a snapshot older than the live
# site. Release assets rather than files in the Pages site: Pages has a ~1 GB
# soft limit and the site alone is already ~590 MB.
# The tag and filenames are fixed, so these URLs never need updating; the date
# below is stamped at build time and therefore always matches what CI uploaded.
SNAPSHOT_DATE = _time.strftime("%d %B %Y").lstrip("0")
REL_TAG = "latest"
REL_BASE = "https://github.com/eran11234/viennavivarium/releases/download/" + REL_TAG + "/"
REPO_ZIP = "https://github.com/eran11234/viennavivarium/archive/refs/heads/main.zip"
DOWNLOADS = [
    dict(key="site", size="~590 MB", primary=True,
         href=REL_BASE + "viennavivarium-site.zip",
         name="Complete offline site",
         lede="The whole website, working without an internet connection.",
         what=["All 175 English translations, with their figures",
               "All 175 German originals as PDFs",
               "The catalog, the guided tour, Discover and a dossier for every paper",
               "497 figure and plate scans"],
         how="Unzip and open <code>index.html</code>. Nothing to install, no server needed.",
         who="Best if you want to read, browse or keep the corpus."),
    dict(key="data", size="~8 MB", primary=False,
         href=REL_BASE + "viennavivarium-research-bundle.zip",
         name="Research bundle",
         lede="Every text and every data file, without the scans.",
         what=["All 175 translations as Markdown",
               "<code>catalog.csv</code> — one row per paper: where it stands, how it is cited today, citations by era, links",
               "The full working data: assessments, citations, methodology, biographies",
               "The original corpus spreadsheet"],
         how="Unzip and start with <code>catalog.csv</code>, or point a script at the folder.",
         who="Best for analysis, text mining, or handing the corpus to an AI."),
    dict(key="source", size="~560 MB", primary=False, href=REPO_ZIP,
         name="Source repository",
         lede="Everything the site is built from, plus the build scripts.",
         what=["The German PDFs and the translation sources",
               "<code>build_site.py</code> and <code>gen_site.py</code>",
               "The full revision history, if you clone rather than download"],
         how="Needs Python 3 and pandoc to render the site. "
             "<code>git clone https://github.com/eran11234/viennavivarium.git</code>",
         who="Best if you want to change something or run your own copy."),
]

def _title_trim(s, n=70):
    """Trim a long title at a word boundary for <title>/og:title."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return cut + "…"

def page(path, title, active, body, prefix="", head="", foot="", desc=None):
    nav = "".join(
        f'<a class="{"on" if active==h else ""}" href="{prefix}{href}">{h}</a>'
        for href, h in NAV)
    ttl = _title_trim(title)
    d = html.escape((desc or SITE_DESC).strip())
    # version every site script the same way as the stylesheet, so CSS and JS never mismatch after a deploy
    foot = re.sub(r'src="((?:\.\./)?(?:assets|data)/[^"?]+\.js)"', r'src="\1?v=' + BUILD_ID + '"', foot)
    url = SITE_URL + path
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(ttl)} · Vienna Vivarium in English</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Vienna Vivarium in English">
<meta property="og:title" content="{html.escape(ttl)}"><meta property="og:description" content="{d}"><meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="{FAVICON}">
<link rel="stylesheet" href="{prefix}assets/style.css?v={BUILD_ID}">{head}
</head><body>
<header class="site"><div class="wrap nav">
<a class="brand" href="{prefix}index.html"><span class="b1">Vienna Vivarium</span><span class="b2">the BVA corpus in English</span></a>
<nav>{nav}</nav><a class="getinv" href="{prefix}contribute.html"><span class="gi-dot"></span>Get involved</a></div></header>
<main class="wrap">{body}</main>
<footer class="site"><div class="wrap">
<p>Biologische Versuchsanstalt (the “Vivarium”), Vienna · {STATS['papers']} papers, {STATS['y0']}–{STATS['y1']} · {STATS['trans']} English translations.</p>
<p class="muted">An orientation platform for researchers. Translations and corpus analysis are scholarly working documents; cite the original alongside the translation. Corrections, collaborations and contributions are welcome — <a href="{prefix}contribute.html">get involved</a>.</p>
<p class="disclaimer"><b>Please note.</b> These papers are historical documents, reproduced for study, not as endorsements, and we are not responsible for their content. Some data may be wrong or harmful: early twentieth-century science sometimes used methods and arguments that would be considered unscientific or harmful today. The translations and assessments on this site may also contain errors.</p>
<p class="fdl"><a class="dlbtn" href="{prefix}download.html"><span class="dlarrow">&darr;</span> Download the whole corpus<small>translations, German originals and all the data — {SNAPSHOT_DATE}</small></a></p>
</div></footer>{foot}</body></html>"""
    with open(os.path.join(SITE, path), "w", encoding="utf-8") as f:
        f.write(doc)

# ---------------------------------------------------------------- home
def gen_index():
    feat = "".join(
        f'''<a class="tcard" href="papers/{t['page_slug']}.html">
        <div class="ty">{t['year']}</div>
        <div class="tt">{html.escape(t['title_en'])}</div>
        <div class="tm">{html.escape(t['author'])} · {html.escape(t['organism'] or '')}</div>
        {'<span class="badge wip">in progress</span>' if t['status']!='complete' else '<span class="badge done">full text</span>'}
        </a>'''
        for t in translations if t['status']=='complete')
    # live counts for the stats strip: curated people on the Authors page, and the assessments
    _ap = os.path.join(ROOT, "legacy_data", "authors.json")
    n_people = len(json.load(open(_ap, encoding="utf-8"))["people"]) if os.path.exists(_ap) else STATS["authors"]
    n_hold = sum(1 for v in ASSESS.values() if v["standing"] in ("established", "consistent"))
    n_open = sum(1 for v in ASSESS.values() if v.get("open"))
    # four programme covers for the featured panel (gen_tour writes assets/tree/prog-<id>-c.jpg later in the build)
    tour_imgs = "".join('<img src="assets/tree/prog-%s-c.jpg" alt="" loading="lazy">' % i
                        for i in ("regen", "colour", "graft", "heredity"))
    body = f"""
<section class="hero">
  <p class="kicker">An orientation platform for researchers</p>
  <h1>The Vienna Vivarium, in English</h1>
  <p class="lede">The Biologische Versuchsanstalt (1902–1945) was one of the first institutes for experimental biology. This platform opens the complete published output of its zoological department to English-language researchers: a searchable catalog of <strong>{STATS['papers']} papers</strong> ({STATS['y0']}–{STATS['y1']}), full English <strong>translations</strong> with figures, the German originals — and every paper <strong>assessed against later work</strong>: whether its own claim still stands, how current research uses it, and what it still offers a researcher.</p>
  <div class="cta">
    <a class="btn primary" href="catalog.html">Browse the catalog</a>
    <a class="btn" href="translations.html">Read translations</a>
    <a class="btn" href="rediscovery.html">Where each paper stands today</a>
  </div>
</section>
<a class="tourpanel" href="tour.html">
  <div class="tp-imgs">{tour_imgs}</div>
  <div class="tp-text">
    <p class="kicker">New here? Take the tour</p>
    <h2>From six big questions down to the papers</h2>
    <p>Start with what the institute wanted to know — how a body rebuilds what it has lost, where colour comes from, whether the environment reaches the next generation — then go inside to the researchers who chased each question and the papers they wrote, illustrated with their own plates.</p>
    <span class="tp-btn">Start the tour →</span>
  </div>
</a>
<figure class="heroimg">
  <img src="assets/img/vivarium-building.jpg" alt="The Biologische Versuchsanstalt building in the Vienna Prater, with VIVARIUM inscribed on the façade" loading="lazy">
  <figcaption>The Biologische Versuchsanstalt — the “Vivarium” — in the Vienna Prater. Built in 1873 as an aquarium-exhibition hall, it became, from 1902, the world's first private institute for experimental biology. The name <em>VIVARIUM</em> is still legible on the façade.</figcaption>
</figure>
<section class="stats">
  <div><b>{STATS['papers']}</b><span>papers cataloged</span></div>
  <div><b>{STATS['trans']}</b><span>English translations</span></div>
  <div><b>{n_people}</b><span>authors</span></div>
  <div><b>{n_hold}</b><span>results that still stand</span></div>
  <div><b>{n_open}</b><span>open questions worth testing</span></div>
</section>
<section>
  <h2>Featured translations</h2>
  <div class="tgrid">{feat}</div>
</section>
<section class="how">
  <h2>How to use this platform</h2>
  <p>The <a href="catalog.html">Catalog</a> is the map of the whole corpus — filter by author, organism, phenomenon, method, or where the paper stands today, and jump to a paper's English translation (where one exists) or its German original. The <a href="translations.html">Translations</a> are full reading pages with the original plates and a side-by-side view against the scanned German. <a href="rediscovery.html">Discover</a> sets every paper against later work: whether its own result was confirmed, is consistent with what is now known, was revised, is still unresolved or did not hold — and whether current research still uses it. Most papers are cited today, if at all, as history; Discover points to the few open questions and datasets still worth a researcher’s time. <a href="authors.html">Authors</a> gives the people behind the papers, the <a href="tour.html">Tour</a> walks from six big questions down to the papers, and <a href="analytics.html">Analytics</a> shows the shape of the institute's output over its four decades.</p>
</section>"""
    page("index.html", "Home", "Home", body)
    # Redirect stubs for pages whose URL changed (legacy_data/redirects.json: old -> new).
    # Paper URLs are built from the catalogue's author field, so correcting an author silently changes
    # the URL and breaks every old link (it happened four times: Burchhardt, Sato, Thomsen, de Hahn).
    # So every paper URL ever published is recorded in legacy_data/published_slugs.json (path -> paper id),
    # and any recorded path that no longer matches its paper's current page becomes a redirect automatically.
    _rp = os.path.join(ROOT, "legacy_data", "redirects.json")
    _pp = os.path.join(ROOT, "legacy_data", "published_slugs.json")
    _moved = json.load(open(_rp, encoding="utf-8")) if os.path.exists(_rp) else {}
    _pub = json.load(open(_pp, encoding="utf-8")) if os.path.exists(_pp) else {}
    _now = {t["id"]: "papers/%s.html" % t["page_slug"] for t in translations}
    _live = set(_now.values())
    for _old, _pid in _pub.items():
        if _pid in _now and _old != _now[_pid] and _old not in _moved:
            _moved[_old] = _now[_pid]
    # never let a redirect stub overwrite a page that is live today (e.g. after a translation is re-paired)
    _moved = {o: n for o, n in _moved.items() if o not in _live}
    try:   # remember today's URLs too (a no-op in CI, which does not commit)
        _pub.update({v: k for k, v in _now.items()})
        json.dump(dict(sorted(_pub.items())), open(_pp, "w", encoding="utf-8"), indent=1)
    except OSError:
        pass
    if _moved:
        for old, new in _moved.items():
            os.makedirs(os.path.dirname(os.path.join(SITE, old)) or SITE, exist_ok=True)
            depth = old.count("/"); pre = "../" * depth
            open(os.path.join(SITE, old), "w", encoding="utf-8").write(
                f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Moved</title>'
                f'<meta http-equiv="refresh" content="0; url={pre}{new}"><link rel="canonical" href="{SITE_URL}{new}">'
                f'</head><body><p>This page has moved to <a href="{pre}{new}">{new}</a>.</p></body></html>')
        print("redirects:", len(_moved))
    # GitHub Pages serves 404.html for any missing path
    page("404.html", "Page not found", "", """
<section class="hero"><p class="kicker">404</p><h1>That page isn’t here</h1>
<p class="lede">The address may have changed as the platform grew. Try the <a href="catalog.html">Catalog</a> to find a paper,
<a href="rediscovery.html">Discover</a> for its standing today, or the <a href="index.html">home page</a>.</p>
<div class="cta"><a class="btn primary" href="catalog.html">Browse the catalog</a><a class="btn" href="index.html">Home</a></div></section>""")

# ---------------------------------------------------------------- catalog
def gen_catalog():
    body = """
<h1>Catalog</h1>
<p class="lede">All papers in the corpus. Search and filter; <strong>click any row to open the paper’s dossier</strong> — where its claim stands, and every work that cites it — or use the Read column to open the translation or the German original.</p>
<section class="stlegend">
  <p><b>Where it stands</b> is each paper’s assessment against later work (September 2026, one paper at a time; see <a href="rediscovery.html#how">Discover</a>):
  <span class="stc stc-established">Established</span> <span class="stc stc-consistent">Consistent</span> <span class="stc stc-revised">Revised</span>
  <span class="stc stc-unresolved">Unresolved</span> <span class="stc stc-not_supported">Not supported</span> <span class="stc stc-no_claim">No claim</span>.
  <b>Cited since 1990</b> counts the works that cite the paper since 1990, scientific and historical; hover for how it is used.</p>
</section>
<div class="filters">
  <input id="q" type="search" placeholder="Search author, title, organism, claim…">
  <select id="phen"><option value="">Any phenomenon</option></select>
  <select id="method"><option value="">Any method</option></select>
  <select id="stand"><option value="">Wherever it stands</option>
    <option value="established">Established</option><option value="consistent">Consistent with current knowledge</option>
    <option value="revised">Revised</option><option value="unresolved">Unresolved</option>
    <option value="not_supported">Not supported</option><option value="no_claim">No claim to assess</option></select>
  <select id="use"><option value="">However it is used today</option>
    <option value="tested">Tested or used today</option><option value="precedent">Cited as a precedent</option>
    <option value="historians">Cited by historians</option><option value="none">Not cited since 1990</option></select>
  <select id="offer"><option value="">Anything it offers</option>
    <option value="testable">A testable question</option><option value="data">Quantitative data</option>
    <option value="method">A reusable method</option><option value="organism">An unusual system</option></select>
  <select id="sort"><option value="year">Sort: year ↑</option><option value="-year">year ↓</option><option value="-mod">most cited since 1990</option><option value="-cit">most cited overall</option><option value="stand">where it stands</option><option value="author">author</option><option value="method">method</option></select>
</div>
<p id="count" class="muted"></p>
<div class="tablewrap"><table id="cat"><thead><tr>
<th>Year</th><th>Author</th><th>Title</th><th>Organism</th><th>Method</th><th>Where it stands</th><th class="num">Cited since 1990</th><th>Read</th>
</tr></thead><tbody></tbody></table></div>
"""
    page("catalog.html", "Catalog", "Catalog", body,
         foot='<script src="data/site.js"></script><script src="data/methodology.js"></script><script src="data/catalog.js"></script><script src="data/assess.js"></script><script src="assets/catalog.js"></script>')

# ---------------------------------------------------------------- translations index
def gen_translations():
    cards = ""
    for t in translations:
        wip = t['status'] != 'complete'
        cards += f'''<a class="tcard big" href="papers/{t['page_slug']}.html">
        <div class="ty">{t['year']} · {html.escape(t['journal'])}</div>
        <div class="tt">{html.escape(t['title_en'])}</div>
        <div class="de">{html.escape(t['title_de'])}</div>
        <div class="tm">{html.escape(t['author'])}</div>
        <div class="meta">{'<span class="badge wip">in progress</span>' if wip else '<span class="badge done">full text</span>'}
        <span class="muted">{t['words']:,} words · {t['figs']} figures</span></div>
        </a>'''
    body = f"""
<h1>Translations</h1>
<p class="lede">Complete English renderings of {STATS['trans']} BVA papers, with the original plates and figures. Two are still being finalized (figures or full text pending) and are marked <em>in progress</em>. Each page links to the scanned German original and a side-by-side reader.</p>
<div class="tgrid">{cards}</div>"""
    page("translations.html", "Translations", "Translations", body)

# ---------------------------------------------------------------- legacy
def gen_legacy():
    """legacy.html (the legacy explorer) was retired in September 2026: its "legacy layers" measured whether
    a paper's organism is still studied, not the paper's legacy. Old links, including legacy.html?id=N,
    forward to that paper's dossier, or to Discover."""
    open(os.path.join(SITE, "legacy.html"), "w", encoding="utf-8").write(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Moved</title><meta name="robots" content="noindex">'
        '<script>var i=new URLSearchParams(location.search).get("id");'
        'location.replace(/^[0-9]+$/.test(i||"")?"dossier/"+i+".html":"rediscovery.html");</script>'
        '<meta http-equiv="refresh" content="1; url=rediscovery.html"></head>'
        '<body><p>This page has moved to <a href="rediscovery.html">Discover</a>.</p></body></html>')

# ---------------------------------------------------------------- analytics
def gen_analytics():
    body = """
<h1>Analytics</h1>
<p class="lede">The shape of the institute's output, where its claims stand today, and how it is cited.</p>
<div class="charts">
  <div class="chart"><h3>Publications per year</h3><canvas id="cYear"></canvas></div>
  <div class="chart"><h3>Where the papers’ claims stand today</h3><canvas id="cStand"></canvas></div>
  <div class="chart"><h3>Every citing work, by era</h3><canvas id="cEra"></canvas></div>
  <div class="chart"><h3>How current research uses the papers</h3><canvas id="cUse"></canvas></div>
  <div class="chart"><h3>Most prolific authors</h3><canvas id="cAuth"></canvas></div>
  <div class="chart"><h3>Most cited in science since 1990</h3><canvas id="cCit"></canvas></div>
</div>
<p class="note muted">Assessments from the September 2026 review — definitions on <a href="rediscovery.html#how">Discover</a>. Citing works via OpenAlex; “authors in this corpus” means citing works written by someone who also published in the series, so roughly the institute citing itself.</p>
"""
    page("analytics.html", "Analytics", "Analytics", body,
         head='<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>',
         foot='<script src="data/catalog.js"></script><script src="data/assess.js"></script><script src="assets/analytics.js"></script>')

# ---------------------------------------------------------------- about
def gen_about():
    body = f"""
<h1>About this platform</h1>
<div class="prose">
<h2>The institute</h2>
<p>The <strong>Biologische Versuchsanstalt</strong> (BVA, the “Vivarium”) was among the world's first institutions dedicated to experimental biology. In 1902 the zoologist <strong>Hans Przibram</strong> and the botanists <strong>Leopold von Portheim</strong> and <strong>Wilhelm Figdor</strong> bought the former aquarium of the 1873 World Exposition in Vienna's Prater and, from its official opening on 1 January 1903, ran it as a private research institute with their own money. It grew to four departments — zoological (Przibram), botanical (Figdor and Portheim), physico-chemical (Wolfgang Pauli Sr., 1907–1914) and physiological (Eugen Steinach, from 1913) — and in 1914 the founders donated it to the Imperial Academy of Sciences. Paul Kammerer, Paul Weiss, Leonore Brecher and the young Karl von Frisch all worked there; between 1920 and 1934, 39 of its 109 listed workers were women.</p>
<p>After the Anschluss of 1938 Przibram and Portheim were barred from their own institute and its Jewish staff dismissed. Przibram died in Theresienstadt in 1944; Leonore Brecher, Helene Jacobi, Martha Geiringer, Henny Burchardt and Heinrich Kun were murdered in the camps; the building burned in the last days of the war in 1945. The authoritative account is Gerd B. Müller (ed.), <em>Vivarium: Experimental, Quantitative, and Theoretical Biology at Vienna's Biologische Versuchsanstalt</em> (MIT Press, 2017), on which the institutional history here relies.</p>
<h2>What the corpus is</h2>
<p>From 1907 to 1925 the zoological department had its own section in Wilhelm Roux's <em>Archiv für Entwicklungsmechanik der Organismen</em>, the “Arbeiten der Zoologischen Abteilung der Biologischen Versuchsanstalt in Wien”; by 1930, when the institute's publications there stopped, <strong>175 articles</strong> had appeared — more than a tenth of the journal's output in those years. This platform contains that series <strong>in full</strong>: all {STATS['papers']} papers ({STATS['y0']}–{STATS['y1']}). It does not cover the botanical, physico-chemical or physiological departments' publications, which appeared elsewhere, nor Przibram's seven-volume <em>Experimental-Zoologie</em>.</p>
<h2>What this platform does</h2>
<p>It is an orientation layer for researchers who do not read German. It assembles, in one place: a searchable <strong>catalog</strong> of the series; full English <strong>translations</strong> with the original figures ({STATS['trans']} of {STATS['papers']}); the scanned German <strong>originals</strong>; the people behind the papers; and, on <strong>Discover</strong>, every paper assessed against later work: where its own claim stands today, how current research uses it, what it still offers a researcher, and every work that cites it.</p>
<h2>How the papers were assessed</h2>
<p>In September 2026 every paper was re-read from its full translation, together with every work that cites it (OpenAlex) and a search of the related modern literature (Consensus), and placed under one written rubric. <em>Established</em> means later work confirmed this paper’s own result, or explicitly credits it for a result now standard; <em>consistent</em> means the phenomenon is accepted but this paper’s result was never re-tested; <em>revised</em> means it holds only in part or for different reasons; <em>unresolved</em> means a specific point was never settled, and the dossier says how it could be tested; <em>not supported</em> means later work contradicts it, it failed to replicate, or it rests on a rejected framework. Where the more modest label was defensible, it was chosen. Separately, each paper records how it is cited today — most are cited, if at all, as history or as an early instance of something now known. These readings replaced an earlier scheme of “sleeping beauties” and “legacy layers”, which mistook general acceptance of a phenomenon for confirmation of a particular paper.</p>
<h2>How the translations were made</h2>
<p>Each German paper was OCR-corrected against the scanned source and translated in full, preserving numbered points, tables, and figure legends. Historical species names are kept as in the original, with modern equivalents noted (e.g. <em>Triton</em> → <em>Triturus</em>). Where an author's claims were later disputed — Kammerer's above all — the translation renders them exactly as stated, and says so; it reports the claims, it does not endorse them.</p>
<p><strong>On the plates.</strong> Text figures and plates are reproduced wherever they are present in the scanned original. In many cases they are not: the journal's lithographic plates were bound separately from the article offprints, so a paper's scan often ends with the plate <em>legends</em> but without the plates themselves. Those points are marked <em>“figure not reproduced”</em> in the running text, and the legends are always translated, so it is clear what is missing and where. Kammerer's 1909 monograph is the largest such case — its Plates XVI and XVII are absent from the source scan.</p>
<h2>How to cite</h2>
<p>Cite the original publication, noting the English translation and this platform as the access point, e.g.: <em>Author (Year), “Original German title,” Archiv für Entwicklungsmechanik …; English translation, Vienna Vivarium in English.</em></p>
<h2>Sources, data &amp; limits</h2>
<p>Citation data (who cites each paper today) derive from <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a>. The modern literature on each paper's questions was retrieved once, at build time, from the <a href="https://consensus.app" target="_blank" rel="noopener">Consensus</a> API (June 2026); it shows what later work says on each paper’s subject and does not cite the papers. The assessments are careful readings, not a consensus of the field, and a research aid rather than a settled historical judgment. Portraits on the Authors page are public-domain images via Wikimedia Commons, credited in place. Corpus metadata and the assessments are part of the project's ongoing analysis and should be treated as scholarly working material; corrections, collaborations and contributions are welcome — <a href="contribute.html">get involved</a>.</p>
</div>"""
    page("about.html", "About", "About", body)

# ---------------------------------------------------------------- get involved
def gen_contribute():
    """The always-reachable 'Get involved' page: an on-site form posting to Formspree
    (FORM_ENDPOINT); until that is configured it falls back to the visitor's mail client."""
    ways = [
        ("collab", "Research collaboration", "historians, biologists or philosophers of science who want to work with the corpus, co-author, or build on the Discover assessments"),
        ("translate", "Translate or check a translation", "German readers who can review, correct or improve a rendering"),
        ("context", "Add context, citations or corrections", "point to modern work that cites a paper, fix a fact, or extend a biography"),
        ("archive", "Share archives, images or family material", "descendants, archivists and institutions holding letters, photographs or documents"),
        ("support", "Support the project", "the platform is independent and unfunded; if you could help financially or with hosting, we would like to hear from you"),
        ("other", "Something else", "any other way you would like to be part of this"),
    ]
    opts = "".join(
        '<label class="ck"><input type="checkbox" name="ways" value="%s"><span>%s<small>%s</small></span></label>'
        % (k, html.escape(t), html.escape(d)) for k, t, d in ways)
    body = f"""
<div class="cwrap">
<section class="chero"><p class="kicker">Get involved</p>
<h1>Help bring the Vivarium back into the conversation</h1>
<p>This platform is the work of a small, independent project. Everything on it — {STATS['trans']} translations, {STATS['papers']} papers read against today's science, the biographies — can be improved by people who know something we don't. If you would like to collaborate, correct, add, or contribute in any other way, tell us a little about yourself below.</p></section>
<div class="cgrid">
<div class="cmain">
<form class="cform" id="cform" novalidate>
  <label for="f-name">Your name</label>
  <input type="text" id="f-name" name="name" autocomplete="name" required>
  <label for="f-email">Email</label>
  <input type="email" id="f-email" name="email" autocomplete="email" required>
  <label for="f-aff">Affiliation or background <span style="font-weight:400;color:var(--muted)">(optional)</span></label>
  <input type="text" id="f-aff" name="affiliation" placeholder="e.g. University of Vienna · historian of biology · descendant of a BVA researcher">
  <label>How would you like to be involved?</label>
  <div class="opt-row">{opts}</div>
  <label for="f-msg">Tell us more</label>
  <textarea id="f-msg" name="message" placeholder="What draws you to the project, what you could offer, or what you would like from us."></textarea>
  <div class="hp" aria-hidden="true"><label>Leave this empty<input type="text" name="_gotcha" tabindex="-1" autocomplete="off"></label></div>
  <input type="hidden" name="_subject" value="Vienna Vivarium — get involved">
  <button class="send" type="submit" id="fsend">Send</button>
  <p class="note" id="fnote"></p>
  <div class="err" id="ferr"></div>
</form>
<div class="done" id="fdone"><h3>Thank you.</h3><p>Your message is on its way. We read everything and will reply personally, usually within a few days.</p><p><a href="tour.html">Take the tour</a> · <a href="rediscovery.html">Open Discover</a> · <a href="catalog.html">Browse the catalog</a></p></div>
</div>
<aside class="caside">
  <div class="box"><h2>What helps most right now</h2><ul>
    <li><b>Modern citations we missed.</b> If a paper here is cited or used in work we haven't found, tell us — the assessments on Discover depend on it.</li>
    <li><b>The people.</b> Many of the {len(json.load(open(os.path.join(ROOT, "legacy_data", "authors.json"), encoding="utf-8"))["people"])} authors have only a line of biography. Dates, places, photographs, descendants.</li>
    <li><b>Translation checks.</b> Every rendering was made carefully, but a second German reader on any paper is welcome.</li>
    <li><b>Collaboration.</b> The corpus, the assessments and the citation data are open to joint research.</li>
  </ul></div>
  <div class="box donate"><h2>Supporting the project</h2><p>The platform runs without institutional funding. If you or your organisation would like to support it — financially, with hosting, or by helping it find an institutional home — tick <em>Support the project</em> and we will be in touch.</p></div>
  <div class="box"><h2>Prefer email?</h2><p>Write to <a id="cmail" href="#">the project</a> directly.</p></div>
</aside>
</div></div>"""
    js = r"""
(function(){
var EP=%s, MAIL=%s;
var f=document.getElementById('cform'),send=document.getElementById('fsend'),note=document.getElementById('fnote'),err=document.getElementById('ferr'),done=document.getElementById('fdone');
var cm=document.getElementById('cmail');cm.href='mailto:'+MAIL+'?subject='+encodeURIComponent('Vienna Vivarium — get involved');cm.textContent=MAIL;
note.textContent=EP?'Your details go only to the project; no newsletter, no sharing.':'This opens your email program with your details filled in.';
function vals(){var d=new FormData(f),ways=d.getAll('ways');return {name:d.get('name')||'',email:d.get('email')||'',affiliation:d.get('affiliation')||'',ways:ways,message:d.get('message')||'',gotcha:d.get('_gotcha')||''};}
function mailto(v){var body='Name: '+v.name+'\nEmail: '+v.email+'\nAffiliation: '+v.affiliation+'\nInvolvement: '+v.ways.join(', ')+'\n\n'+v.message;
  location.href='mailto:'+MAIL+'?subject='+encodeURIComponent('Vienna Vivarium — get involved')+'&body='+encodeURIComponent(body);}
f.addEventListener('submit',function(e){e.preventDefault();err.style.display='none';
  var v=vals();
  if(!v.name.trim()||!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.email)){err.textContent='Please give your name and a valid email address so we can reply.';err.style.display='block';return;}
  if(v.gotcha){return;}
  if(!EP){mailto(v);return;}
  send.disabled=true;send.textContent='Sending…';
  var fd=new FormData(f);fd.set('ways',v.ways.join(', '));
  fetch(EP,{method:'POST',body:fd,headers:{'Accept':'application/json'}}).then(function(r){
    if(r.ok){f.style.display='none';done.style.display='block';done.scrollIntoView({behavior:'smooth',block:'start'});}
    else{throw new Error('status '+r.status);}
  }).catch(function(){send.disabled=false;send.textContent='Send';
    err.innerHTML='Sending failed. <a href="#" id="fmail">Send it by email instead</a>.';err.style.display='block';
    document.getElementById('fmail').onclick=function(ev){ev.preventDefault();mailto(v);};});
});
})();
""" % (json.dumps(FORM_ENDPOINT), json.dumps(CONTACT_EMAIL))
    page("contribute.html", "Get involved", None, body, foot="<script>" + js + "</script>",
         desc="Collaborate with, correct, or contribute to the Vienna Vivarium project: research collaboration, translation checks, archives and family material, or support.")
    print("contribute.html:", "Formspree endpoint set" if FORM_ENDPOINT else "no endpoint yet — mailto fallback")


# ---------------------------------------------------------------- download
def gen_download():
    """Three dated snapshots of the corpus, served as GitHub Release assets."""
    def card(d):
        what = "".join("<li>%s</li>" % x for x in d["what"])
        return (
            '<section class="dlcard%s">'
            '<div class="dlhead"><h2>%s</h2><span class="dlsize">%s</span></div>'
            '<p class="dllede">%s</p>'
            '<ul class="dlwhat">%s</ul>'
            '<p class="dlhow">%s</p>'
            '<a class="dlget%s" href="%s"%s>&darr; Download</a>'
            '<p class="dlwho">%s</p>'
            '</section>'
            % (" prime" if d["primary"] else "", html.escape(d["name"]), html.escape(d["size"]),
               html.escape(d["lede"]), what, d["how"],
               " prime" if d["primary"] else "", d["href"],
               ' download' if d["href"].startswith(REL_BASE) else '',
               html.escape(d["who"])))
    body = f"""
<div class="dlwrap">
<p class="kicker">Take the whole thing with you</p>
<h1>Download the corpus</h1>
<p class="lede">Everything on this site can be downloaded and kept. The translations, the German
originals, the figures and the analysis are all here — nothing is held back behind the website.
Pick whichever shape suits what you want to do.</p>
<p class="dlsnap">Built <b>{SNAPSHOT_DATE}</b> · {STATS['papers']} papers · {STATS['trans']} translations ·
rebuilt automatically whenever the site changes ·
<a href="https://github.com/eran11234/viennavivarium/releases/tag/{REL_TAG}">all files on GitHub &rarr;</a></p>

<div class="dlgrid">{''.join(card(d) for d in DOWNLOADS)}</div>

<section class="dlnote">
  <h2>Before you use it</h2>
  <p><b>It is still a copy, not the live thing.</b> Both bundles are rebuilt automatically every time
  the site changes, so what you download matches what is published here — but once it is on your
  disk it stops tracking. Translations get corrected and verdicts revised; for anything you intend
  to quote or rely on, check the live page. Each zip carries a <code>README.txt</code> giving the
  date it was built.</p>
  <p><b>Cite the original alongside the translation.</b> Every reading page carries the full original
  reference and its DOI where one exists; <code>catalog.csv</code> in the research bundle carries
  them in a column.</p>
  <p><b>The verdicts are the project's own judgements</b>, not a settled consensus. Each paper was read
  against the current literature and placed on two axes — recognition and vindication — which are kept
  deliberately separate, because citation counts partly measure notoriety rather than correctness.
  Disagreement is useful; <a href="contribute.html">tell us</a>.</p>
  <p><b>Five papers carry a context note</b> — claims about sexual orientation, about race, and one
  anatomical study of a named intersex person whose body came from a penal institution. The translations
  are complete and unedited and the notes sit alongside them, not inside them. If you quote from those
  papers, please carry the context with the quotation.</p>
  <p><b>Rights.</b> The German originals were published 1904–1930 in <i>Archiv für Entwicklungsmechanik
  der Organismen</i>; their status varies by author and jurisdiction, and the scanned editions may carry
  their own terms. The translations and the analysis are this project's own work, and no reuse licence has
  been set for them yet — <a href="contribute.html">get in touch</a> before redistributing or republishing.</p>
</section>
</div>"""
    page("download.html", "Download", None, body,
         head="<style>" + DOWNLOAD_CSS + "</style>",
         desc=("Download the complete Vienna Vivarium corpus: 175 English translations, the German "
               "originals, figures and the full corpus analysis, as an offline site or a research bundle."))
    print("download.html:", len(DOWNLOADS), "bundles |", SNAPSHOT_DATE)

DOWNLOAD_CSS = r"""
.dlwrap{max-width:1040px}
.dlwrap .lede{max-width:72ch;font-size:16.5px;line-height:1.6}
.dlsnap{font-size:13.5px;color:var(--muted);border-top:1px solid var(--rule);padding-top:11px;margin:16px 0 22px}
.dlgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;align-items:start}
.dlcard{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:18px 19px 17px;display:flex;flex-direction:column;height:100%}
.dlcard.prime{border:1.5px solid #8a5a2b;background:#fdfaf5}
.dlhead{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px}
.dlhead h2{font-family:Georgia,serif;font-size:18.5px;margin:0;border:0;padding:0}
.dlsize{font-size:12px;font-weight:700;letter-spacing:.04em;color:#6b6459;background:var(--paper);border:1px solid var(--rule);border-radius:20px;padding:3px 10px;white-space:nowrap}
.dlcard.prime .dlsize{background:#8a5a2b;color:#fdfaf5;border-color:#8a5a2b}
.dllede{font-size:14.5px;color:#3c3833;margin:0 0 11px;line-height:1.5}
.dlwhat{margin:0 0 12px;padding-left:18px;font-size:13.5px;line-height:1.55;color:#4a463f}
.dlwhat li{margin-bottom:4px}
.dlhow{font-size:13px;color:var(--muted);line-height:1.55;margin:0 0 15px;padding-top:11px;border-top:1px solid var(--rule)}
.dlhow code,.dlnote code{background:var(--paper);border:1px solid var(--rule);border-radius:4px;padding:1px 5px;font-size:12.5px;word-break:break-all}
.dlget{margin-top:auto;display:block;text-align:center;background:var(--card);color:var(--ink);border:1px solid #cdc4b1;border-radius:8px;padding:10px 14px;font-size:14.5px;font-weight:600;text-decoration:none}
.dlget:hover{background:#fff;border-color:#8a5a2b;text-decoration:none}
.dlget.prime{background:#8a5a2b;color:#fdfaf5;border-color:#8a5a2b}
.dlget.prime:hover{background:#74491f;color:#fff}
.dlwho{font-size:12.5px;color:var(--muted);margin:9px 0 0;text-align:center;line-height:1.45}
.dlnote{margin-top:28px;background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:20px 24px 8px;max-width:80ch}
.dlnote h2{font-family:Georgia,serif;font-size:19px;margin:0 0 12px;border:0;padding:0}
.dlnote p{font-size:14.5px;line-height:1.62;color:#3c3833;margin:0 0 13px}
@media(max-width:900px){.dlgrid{grid-template-columns:1fr}.dlcard{height:auto}}
"""

# ---------------------------------------------------------------- reader (side-by-side)
def gen_reader():
    # Data-driven in-site reader: reader.html?id=<id>[&sxs=1].
    # Embeds the German PDF in the page with a download button; side-by-side
    # against the English translation when one exists.
    body = """
<div id="rhead"></div>
<div id="rview"></div>
<p id="rmiss" class="muted" style="display:none">Paper not found. <a href="catalog.html">Back to the catalog</a>.</p>
"""
    page("reader.html", "Reader", None, body,
         foot='<script src="data/catalog.js"></script><script src="data/assess.js"></script><script src="assets/reader.js"></script>')



def gen_authors():
    """A directory of the people behind the corpus: bios for the principal figures,
    a short line for every other contributor, each with their papers linked."""
    ap = os.path.join(ROOT, "legacy_data", "authors.json")
    A = json.load(open(ap, encoding="utf-8"))
    cat_by_id = {c["id"]: c for c in catalog}
    read_for = {t["id"]: t["page_slug"] for t in translations}

    def plink(pid):
        c = cat_by_id.get(pid)
        if not c:
            return ""
        href = ("papers/" + read_for[pid] + ".html") if pid in read_for else ("reader.html?id=%d" % pid)
        t = (c.get("title_en") or c.get("title") or "").strip()
        if len(t) > 52:
            t = t[:51].rstrip() + "…"
        return '<a class="pchip" href="%s">%s · %s</a>' % (href, c["year"], html.escape(t))

    def card(p, compact):
        chips = " ".join(plink(i) for i in p["papers"])
        yrs = ('<span class="ayears">%s</span>' % html.escape(p["years"])) if p.get("years") else ""
        role = ('<span class="arole">%s</span>' % html.escape(p["role"])) if p.get("role") else ""
        link = ('<a class="alink" href="%s" target="_blank" rel="noopener">more ↗</a>' % p["link"]) if p.get("link") else ""
        n = len(p["papers"])
        pic = ''
        if p.get("img"):
            pic = ('<figure class="aportrait"><img src="assets/%s" alt="Portrait of %s" loading="lazy">'
                   '<figcaption>%s</figcaption></figure>'
                   % (p["img"], html.escape(p["name"]), html.escape(p.get("img_credit", ""))))
        toggle = ('<span class="atoggle">%d %s <i class="chev">&rsaquo;</i></span>'
                  % (n, "papers" if n != 1 else "paper"))
        summary = ('<summary class="asum">' + pic
                   + '<div class="abody"><div class="ahead"><h2>%s</h2>%s%s</div>' % (html.escape(p["name"]), yrs, role)
                   + "".join('<p class="abio">%s</p>' % html.escape(_b.strip())
                             for _b in re.split(r"\n\s*\n", p["bio"]) if _b.strip())
                   + toggle + '</div></summary>')
        detail = ('<div class="adetail"><div class="apapers"><span class="lab">Wrote</span> %s</div>%s</div>'
                  % (chips, link))
        cls = "acard" + (" feat" if not compact else "") + (" haspic" if pic else "")
        return '<details class="%s" id="a-%s">%s%s</details>' % (cls, html.escape(p["key"]), summary, detail)

    feat = [p for p in A["people"] if p["featured"]]
    rest = [p for p in A["people"] if not p["featured"]]
    body = ('<p class="kicker">The people behind the corpus</p>'
            '<h1>Authors of the Vivarium</h1>'
            '<p class="lede">' + A["intro"] + '</p>'
            '<div class="astats"><div><b>%d</b><span>contributors</span></div>'
            '<div><b>%d</b><span>principal figures</span></div>'
            '<div><b>%d</b><span>papers, 1904–1930</span></div></div>'
            # counted, never read from A["stats"] — that field goes stale the moment
            # someone is added or promoted (it said 17 while 19 were featured)
            % (len(A["people"]), len(feat), STATS["papers"])
            + '<h2 class="asec">Principal figures</h2><div class="agrid feat">'
            + "".join(card(p, False) for p in feat) + '</div>'
            + '<h2 class="asec">Further contributors</h2>'
            + '<p class="muted" style="margin:0 0 12px;max-width:74ch">Assistants, visiting researchers and students who each left one or a few papers in the corpus.</p>'
            + '<div class="agrid">' + "".join(card(p, True) for p in rest) + '</div>')
    page("authors.html", "Authors", "Authors", body, head="<style>" + AUTHORS_CSS + "</style>")
    print("authors.html:", len(A["people"]), "people |", len(feat), "featured")


AUTHORS_CSS = r"""
.astats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0 6px}
.astats div{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:13px 14px}
.astats b{display:block;font-family:Georgia,serif;font-size:27px;line-height:1}
.astats span{font-size:12px;color:var(--muted)}
.asec{border-bottom:2px solid var(--rule);padding-bottom:7px;margin:34px 0 16px}
.agrid{display:grid;gap:14px}
.agrid.feat{grid-template-columns:repeat(auto-fill,minmax(330px,1fr))}
.agrid:not(.feat){grid-template-columns:repeat(auto-fill,minmax(290px,1fr))}
.acard{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:0;overflow:hidden}
.acard.feat{border-left:4px solid var(--accent)}
.acard[open]{box-shadow:0 3px 16px rgba(0,0,0,.08)}
.asum{padding:16px 17px;cursor:pointer;list-style:none;display:block}
.asum::-webkit-details-marker{display:none}.asum::marker{content:""}
.asum:hover{background:rgba(122,59,46,.04)}
.acard.haspic .asum{display:flex;gap:14px;align-items:flex-start}
.abody{flex:1;min-width:0}
.atoggle{display:inline-flex;align-items:center;gap:6px;margin-top:10px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);font-weight:700}
.chev{font-style:normal;font-size:16px;line-height:1;display:inline-block;transition:transform .2s}
.acard[open] .chev{transform:rotate(90deg)}
.adetail{padding:0 17px 15px;animation:adrop .25s ease}
@keyframes adrop{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
.aportrait{margin:0;flex:0 0 auto;width:88px}
.aportrait img{width:88px;height:108px;object-fit:cover;border-radius:9px;border:1px solid var(--rule);background:#efe9dd;filter:sepia(.12)}
.aportrait figcaption{font-size:8.5px;line-height:1.25;color:var(--muted);margin-top:3px;text-align:center}
@media(max-width:520px){.acard.haspic .asum{flex-direction:column}.aportrait,.aportrait img{width:78px}}
.ahead{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin-bottom:8px}
.ahead h2{font-family:Georgia,serif;font-size:19px;margin:0;border:0;padding:0}
.ayears{font-size:13px;color:var(--accent);font-weight:600}
.arole{font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);border-radius:5px;padding:1px 6px}
.abio{font-size:13.7px;line-height:1.58;color:#3c3833;margin:0 0 11px}
.apapers .lab{display:inline-block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-right:6px}
.apapers{font-size:0}
.pchip{display:inline-block;font-size:12.5px;border:1px solid var(--rule);border-radius:13px;padding:3px 10px;margin:3px 4px 0 0;background:var(--paper);color:var(--ink);line-height:1.3}
.pchip:hover{border-color:#cdc4b1;text-decoration:none;background:#fff}
.alink{display:inline-block;margin-top:11px;font-size:13px}
@media(max-width:640px){.astats{grid-template-columns:repeat(3,1fr)}.agrid.feat,.agrid:not(.feat){grid-template-columns:1fr}}
"""


DISCOVER_CSS = r"""
.dlede{max-width:80ch;font-size:16.5px;line-height:1.6}
.entries{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 10px}
.entry{text-align:left;font:inherit;cursor:pointer;background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:14px 15px 13px;
  display:flex;flex-direction:column;gap:4px;color:var(--ink);transition:border-color .2s,box-shadow .2s,transform .2s}
.entry:hover{border-color:#cfc5b1;box-shadow:0 6px 18px rgba(40,30,10,.08);transform:translateY(-1px)}
.entry.on{border-color:var(--accent2);box-shadow:inset 0 0 0 1px var(--accent2)}
.entry b{font-family:Georgia,serif;font-size:27px;line-height:1;color:var(--accent2)}
.entry .et{font-weight:600;font-size:15px;line-height:1.3}
.entry .ed{font-size:12.8px;line-height:1.45;color:var(--muted)}
.howto{margin:14px 0 6px;background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:4px 16px}
.howto summary{cursor:pointer;font-weight:600;font-size:14.5px;padding:10px 0;color:var(--accent2)}
.howto h3{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:14px 0 6px}
.deflist{list-style:none;padding:0;margin:0 0 6px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:7px 18px}
.deflist li{font-size:13.2px;line-height:1.5;color:#3c3833}
.deflist li .stc,.deflist li .usec{margin-right:6px}
.howto p{font-size:13.6px;line-height:1.6;color:#3c3833;max-width:92ch}
.explorer{margin:20px 0 8px}
.search{width:100%;font-size:15px;padding:11px 14px;border:1px solid var(--rule);border-radius:10px;background:var(--card);font-family:inherit}
.chipset{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:10px 0 0}
.chipset .lbl{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:4px;min-width:118px}
.fchip{font:inherit;font-size:12.5px;border:1px solid var(--rule);background:var(--card);border-radius:20px;padding:4px 11px;cursor:pointer;color:var(--ink)}
.fchip .cc{opacity:.55;font-size:11px;margin-left:4px}
.fchip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.exrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0 4px}
.exrow select{font-size:13.5px;padding:7px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--card);font-family:inherit}
.exrow .count{font-size:13px;color:var(--muted);margin-left:auto}
.exrow .reset{font-size:13px;background:none;border:0;color:var(--accent2);cursor:pointer;padding:0}
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin-top:8px}
.dc{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:6px}
.dc .dtop{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.dc h3{font-family:Georgia,serif;font-size:17px;margin:2px 0 0;line-height:1.28}
.dc h3 a{color:var(--ink)}
.dc .dm{font-size:12.5px;color:var(--muted);margin:0}
.dc .dm em{font-style:italic}
.dc .dv{font-size:14px;font-weight:600;line-height:1.4;margin:2px 0 0;color:#2f2c28}
.dc .dw{font-size:13.2px;line-height:1.55;color:#4a463f;margin:0}
.dc .dop{font-size:13px;line-height:1.5;margin:0;padding:7px 10px;background:#eef2f5;border-radius:8px;color:#2f3e4c}
.dc .doff{display:flex;flex-wrap:wrap;gap:5px}
.dc .dlk{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:4px}
.dc .dlk a{font-size:12.5px;border:1px solid var(--rule);border-radius:7px;padding:4px 10px;text-decoration:none;color:var(--ink)}
.dc .dlk a.go{background:var(--accent2);color:#fff;border-color:var(--accent2)}
.dc mark.hlt{font-weight:600}
@media(max-width:860px){.entries{grid-template-columns:repeat(2,1fr)}.chipset .lbl{min-width:0;width:100%}}
@media(max-width:560px){.entries{grid-template-columns:1fr}.dgrid{grid-template-columns:1fr}}
"""

DISCOVER_JS = r"""
(function(){
var D=window.DISCOVER, P=D.papers;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function hlEsc(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function hl(escaped,term){
  if(!term)return escaped;
  var t=String(term).trim(); if(t.length<2)return escaped;
  var parts=t.split(/\s+/).filter(function(x){return x.length>1;}).map(hlEsc);
  if(!parts.length)return escaped;
  var re=new RegExp('(?![^<]*>)(?![^&;]*;)('+parts.join('|')+')','gi');
  return escaped.replace(re,'<mark class="hlt">$1</mark>');
}
var ST={},US={},OF={},PG={};
D.standing.forEach(function(x){ST[x[0]]=x;});D.use.forEach(function(x){US[x[0]]=x;});
D.offers.forEach(function(x){OF[x[0]]=x;});D.progs.forEach(function(x){PG[x[0]]=x;});
var ORDER={};D.standing.forEach(function(x,i){ORDER[x[0]]=i;});
var ENTRY={open:function(p){return !!p.op;},hold:function(p){return p.s==='established'||p.s==='consistent';},
  fail:function(p){return p.s==='not_supported';},data:function(p){return p.o.indexOf('data')>=0;}};
var st={q:'',s:'all',u:'all',o:'all',p:'all',e:null,sort:'year'};
function useText(p){var u=US[p.u],t=u[1];
  if(p.u==='precedent')t+=' · '+p.c[3]+' since 1990';
  if(p.u==='historians')t+=' · '+p.c[4]+' since 1990';
  return t;}
function card(id){var p=P[id],Q=st.q.trim();
  var offs=p.o.map(function(o){return '<span class="oft oft-'+o+'">'+esc(OF[o][1])+'</span>';}).join('');
  var lk='<a class="go" href="dossier/'+id+'.html">Dossier →</a>';
  if(p.rd)lk+='<a href="papers/'+p.rd+'.html">English</a>';
  lk+='<a href="reader.html?id='+id+'">German</a>';
  return '<article class="dc"><div class="dtop"><span class="stc stc-'+p.s+'" title="'+esc(ST[p.s][3])+'">'+esc(ST[p.s][2])+'</span>'
   +'<span class="usec usec-'+p.u+'" title="'+esc(US[p.u][2])+'">'+esc(useText(p))+'</span>'
   +(p.sn?'<span class="oft oft-note" title="This paper carries a context note">◆ '+esc(p.sn)+'</span>':'')+'</div>'
   +'<h3><a href="dossier/'+id+'.html">'+hl(esc(p.t),Q)+'</a></h3>'
   +'<p class="dm">'+hl(esc(p.au),Q)+' · '+p.y+(p.org?' · <em>'+hl(esc(p.org),Q)+'</em>':'')+'</p>'
   +'<p class="dv">'+hl(esc(p.v),Q)+'</p><p class="dw">'+hl(esc(p.w),Q)+'</p>'
   +(p.op?'<p class="dop"><b>Open question.</b> '+esc(p.op)+'</p>':'')
   +(offs?'<div class="doff">'+offs+'</div>':'')
   +'<div class="dlk">'+lk+'</div></article>';}
function pass(p){var q=st.q.toLowerCase();
  if(st.e&&!ENTRY[st.e](p))return false;
  if(st.s!=='all'&&p.s!==st.s)return false;
  if(st.u!=='all'&&p.u!==st.u)return false;
  if(st.o!=='all'&&p.o.indexOf(st.o)<0)return false;
  if(st.p!=='all'&&p.prog!==st.p)return false;
  if(q){var hay=(p.t+' '+p.de+' '+p.au+' '+(p.org||'')+' '+p.v+' '+p.w+' '+(p.op||'')).toLowerCase();if(hay.indexOf(q)<0)return false;}
  return true;}
function counts(key){var m={};D.order.forEach(function(id){var p=P[id];
  var save=st[key];st[key]='all';if(pass(p)){var v=p[key];m[v]=(m[v]||0)+1;}st[key]=save;});return m;}
function chipset(el,key,defs,labelIdx){var m=counts(key),tot=0;Object.keys(m).forEach(function(k){tot+=m[k];});
  var h='<span class="lbl">'+el.getAttribute('data-label')+'</span><button class="fchip'+(st[key]==='all'?' on':'')+'" data-v="all">All<span class="cc">'+tot+'</span></button>';
  defs.forEach(function(d){if(!m[d[0]]&&st[key]!==d[0])return;
    h+='<button class="fchip'+(st[key]===d[0]?' on':'')+'" data-v="'+d[0]+'" title="'+esc(d[labelIdx+1]||'')+'">'+esc(d[labelIdx])+'<span class="cc">'+(m[d[0]]||0)+'</span></button>';});
  el.innerHTML=h;}
function render(){
  var list=D.order.filter(function(id){return pass(P[id]);});
  if(st.sort==='year')list.sort(function(a,b){return P[a].y-P[b].y||a-b;});
  else if(st.sort==='-year')list.sort(function(a,b){return P[b].y-P[a].y||a-b;});
  else if(st.sort==='cites')list.sort(function(a,b){return (P[b].c[3]+P[b].c[4])-(P[a].c[3]+P[a].c[4])||P[a].y-P[b].y;});
  else if(st.sort==='standing')list.sort(function(a,b){return ORDER[P[a].s]-ORDER[P[b].s]||P[a].y-P[b].y;});
  document.getElementById('grid').innerHTML=list.map(card).join('')||'<p class="muted">No paper matches these filters.</p>';
  document.getElementById('count').textContent=list.length+' of '+D.order.length+' papers';
  chipset(document.getElementById('fs'),'s',D.standing,2);
  chipset(document.getElementById('fu'),'u',D.use,1);
  document.querySelectorAll('.entry').forEach(function(b){b.classList.toggle('on',b.getAttribute('data-e')===st.e);});
}
function wire(id,key){document.getElementById(id).onclick=function(e){var b=e.target.closest('.fchip');if(!b)return;st[key]=b.getAttribute('data-v');render();};}
wire('fs','s');wire('fu','u');
var osel=document.getElementById('osel');osel.innerHTML='<option value="all">Anything it offers</option>'+D.offers.map(function(o){return '<option value="'+o[0]+'">'+esc(o[1])+'</option>';}).join('');
var psel=document.getElementById('psel');psel.innerHTML='<option value="all">All six questions</option>'+D.progs.map(function(o){return '<option value="'+o[0]+'">'+esc(o[1])+'</option>';}).join('');
osel.onchange=function(){st.o=osel.value;render();};psel.onchange=function(){st.p=psel.value;render();};
document.getElementById('sortsel').onchange=function(e){st.sort=e.target.value;render();};
document.getElementById('q').oninput=function(e){st.q=e.target.value;render();};
document.querySelectorAll('.entry').forEach(function(b){b.onclick=function(){var e=b.getAttribute('data-e');st.e=(st.e===e?null:e);
  if(st.e==='open')st.sort='standing';render();document.getElementById('explorer').scrollIntoView({behavior:'smooth',block:'start'});};});
document.getElementById('reset').onclick=function(){st={q:'',s:'all',u:'all',o:'all',p:'all',e:null,sort:'year'};
  document.getElementById('q').value='';osel.value='all';psel.value='all';document.getElementById('sortsel').value='year';render();};
var h=(location.hash||'').replace('#','');if(ENTRY[h])st.e=h;
if(h==='how'){var hw=document.getElementById('how');if(hw)hw.open=true;}
render();
})();
"""


def gen_discover():
    """Discover: where each paper's own claim stands today, how current research uses it and what it
    offers a researcher now, with four ways in. Replaces the old status/sleeping-beauty hub."""
    cat_by_id = {c["id"]: c for c in catalog}
    read_for = {t["id"]: t["page_slug"] for t in translations}
    prog_of, progs = programme_map()
    papers = {}
    for c in catalog:
        pid = c["id"]; a = ASSESS.get(pid)
        if not a:
            continue
        k = a.get("cites") or {}
        s = SENS.get(str(pid))
        papers[str(pid)] = dict(
            t=(c.get("title_en") or c.get("title") or ""), de=c.get("title") or "",
            au=c.get("author_full") or c.get("author") or "", y=c["year"], org=c.get("organism") or "",
            prog=prog_of.get(pid, ""), s=a["standing"], v=a["verdict"], w=a["why"],
            op=a.get("open") or "", o=a.get("offers") or [], u=a["use"],
            c=[k.get("to1945", 0), k.get("to1945_self", 0), k.get("mid", 0), k.get("modern_sci", 0),
               k.get("modern_hist", 0), k.get("total", 0)],
            rd=read_for.get(pid, ""), sn=(s or {}).get("category", ""))
    order = sorted((int(k) for k in papers), key=lambda i: (papers[str(i)]["y"], i))
    n = len(papers)
    cnt = lambda f: sum(1 for p in papers.values() if f(p))
    n_open = cnt(lambda p: p["op"]); n_hold = cnt(lambda p: p["s"] in ("established", "consistent"))
    n_fail = cnt(lambda p: p["s"] == "not_supported"); n_data = cnt(lambda p: "data" in p["o"])
    n_none = cnt(lambda p: p["u"] == "none")
    data = dict(papers=papers, order=order,
                standing=[[k, l, s, d] for k, l, s, d in STANDING],
                use=[[k, l, d] for k, l, d in USE], offers=[[k, l] for k, l in OFFERS],
                progs=[[i, t] for i, t in progs])
    os.makedirs(DATA, exist_ok=True)
    open(os.path.join(DATA, "discover.js"), "w", encoding="utf-8").write(
        "window.DISCOVER=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";")
    # slim cross-page index (Catalog, reader, analytics): id -> [standing, verdict, use, cites-by-era, offers]
    open(os.path.join(DATA, "assess.js"), "w", encoding="utf-8").write(
        "window.ASSESS=" + json.dumps({k: [p["s"], p["v"], p["u"], p["c"], p["o"]] for k, p in papers.items()},
                                      ensure_ascii=False, separators=(",", ":")) + ";")
    stand_li = "".join('<li><span class="stc stc-%s">%s</span>%s</li>' % (k, html.escape(l), html.escape(d))
                       for k, l, _, d in STANDING)
    use_li = "".join('<li><span class="usec usec-%s">%s</span>%s</li>' % (k, html.escape(l), html.escape(d))
                     for k, l, d in USE)
    off_li = "".join('<li><span class="oft oft-%s">%s</span></li>' % (k, html.escape(l)) for k, l in OFFERS)
    body = f"""
<p class="kicker">The corpus in the light of later work</p>
<h1>Discover</h1>
<p class="lede dlede">Each of the {n} papers was read in full and set against what later work did with it. Three things are recorded for every paper:
<b>where its own claim stands today</b>, <b>how current research uses it</b>, and <b>what it still offers a researcher</b>.
Most of these papers are cited today, if at all, as history or as an early instance of something now known;
{n_none} have not been cited since 1990. The useful questions are narrower: which specific results still stand, which did not, and which were never settled.</p>
<div class="entries" id="how-in">
  <button class="entry" data-e="open"><b>{n_open}</b><span class="et">Open questions worth testing</span><span class="ed">A specific point later work never settled, with a design that could settle it.</span></button>
  <button class="entry" data-e="hold"><b>{n_hold}</b><span class="et">Results that still stand</span><span class="ed">Established, or consistent with what is now known. Early instances, not necessarily the origin.</span></button>
  <button class="entry" data-e="fail"><b>{n_fail}</b><span class="et">Claims that did not hold</span><span class="ed">Contradicted, never replicated, or resting on a rejected framework.</span></button>
  <button class="entry" data-e="data"><b>{n_data}</b><span class="et">Data you could re-use</span><span class="ed">Measurement series or tables worth re-analysing.</span></button>
</div>
<details class="howto" id="how"><summary>How to read these assessments</summary>
<h3>Where the paper’s claim stands</h3><ul class="deflist">{stand_li}</ul>
<h3>How current research uses it</h3><ul class="deflist">{use_li}</ul>
<h3>What it offers now</h3><ul class="deflist">{off_li}</ul>
<p>Each paper was read from its full English translation together with every work that cites it (OpenAlex) and a search of the related modern literature, and judged under one written rubric: a paper is <em>established</em> only when later work confirmed its own specific result, and when a paper made two claims with different fates, its central claim decides and the other is named. Each assessment records what it rests on and how confident it is. They are careful readings, not a consensus of the field: treat them as a starting point and check the dossier’s evidence.</p>
<p>In September 2026 these assessments replaced an earlier scheme that labelled papers “sleeping beauties”, ranked them on an index of forgotten-yet-confirmed work, and graded “legacy layers”. That scheme read general acceptance of a phenomenon as confirmation of a particular paper, and read citation counts as present-day use; it has been withdrawn.</p>
</details>
<section class="explorer" id="explorer">
  <input id="q" class="search" type="search" placeholder="Search title, author, organism or claim…">
  <div class="chipset" id="fs" data-label="Where it stands"></div>
  <div class="chipset" id="fu" data-label="Used today"></div>
  <div class="exrow">
    <select id="psel"></select><select id="osel"></select>
    <select id="sortsel"><option value="year">Sort: year ↑</option><option value="-year">year ↓</option>
      <option value="standing">where it stands</option><option value="cites">most cited since 1990</option></select>
    <button class="reset" id="reset" type="button">Clear filters</button>
    <span id="count" class="count"></span>
  </div>
</section>
<div id="grid" class="dgrid"></div>"""
    page("rediscovery.html", "Discover", "Discover", body,
         head="<style>" + DISCOVER_CSS + "</style>",
         foot='<script src="data/discover.js"></script><script>' + DISCOVER_JS + '</script>',
         desc="Where each of the 175 Vivarium papers stands today: established, consistent, revised, unresolved "
              "or not supported; how current research uses it; and what it still offers a researcher.")
    print("discover:", n, "papers | open", n_open, "| hold", n_hold, "| not supported", n_fail, "| data", n_data)


DOSSIER_CSS = r"""
.dossier{max-width:840px}
.dossier .detitle{font-style:italic;color:var(--muted);margin:.1em 0 .3em;font-size:16px}
.dossier .byline{color:var(--muted);font-size:14px;margin:.2em 0 14px}
.dsec{margin:26px 0;padding-top:4px}
.dsec h2{font-family:Georgia,serif;font-size:21px;border-bottom:2px solid var(--rule);padding-bottom:6px;margin:0 0 12px}
.dsec h2 .cnt{font-family:-apple-system,sans-serif;font-size:13px;color:var(--muted);font-weight:400}
.standbox{background:var(--card);border:1px solid var(--rule);border-left:5px solid #9a9387;border-radius:12px;padding:16px 20px 14px}
.standbox.sb-established{border-left-color:#1d6e56}.standbox.sb-consistent{border-left-color:#4f7a74}
.standbox.sb-revised{border-left-color:#9a6a1f}.standbox.sb-unresolved{border-left-color:#33485c}
.standbox.sb-not_supported{border-left-color:#8a3a3a}
.standbox .lab{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:600;margin:0 0 7px}
.standbox .sthead{margin:0 0 6px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.standbox .stdef{font-size:12.5px;color:var(--muted)}
.standbox .stverdict{font-family:Georgia,serif;font-size:19px;line-height:1.35;margin:6px 0 8px;color:#211f1c}
.standbox .stwhy{font-size:15.5px;line-height:1.65;margin:0 0 10px}
.openbox{margin:12px 0 4px;padding:11px 14px;background:#eef2f5;border-radius:9px}
.openbox p{margin:0 0 6px;font-size:14.5px;line-height:1.6}.openbox p:last-child{margin:0}
.openbox b{color:#2f3e4c}
.offers{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 2px}
.stbasis{font-size:12.5px;color:var(--muted);margin:10px 0 0;padding-top:8px;border-top:1px dashed var(--rule)}
.usebox p{font-size:14.5px;line-height:1.6;margin:0 0 8px}
.usenote{padding:9px 12px;background:#edf5f1;border-left:3px solid #1d6e56;border-radius:0 8px 8px 0}
.eras{display:flex;height:22px;border-radius:6px;overflow:hidden;margin:12px 0 6px;background:#efe9dc}
.eras span{display:block;height:100%}
.era-self{background:#b9a57a}.era-early{background:#d8c9a3}.era-mid{background:#9fb1c0}.era-sci{background:#355e7d}.era-hist{background:#9a9387}
.eraleg{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;color:#4a463f}
.eraleg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.mgrid{display:grid;grid-template-columns:140px 1fr;gap:6px 14px;margin:0;font-size:14.5px;line-height:1.55}
.mgrid dt{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;padding-top:3px}
.mgrid dd{margin:0}
.mgrid dd.find{font-weight:600}
.summbox{margin:0 0 14px;padding:12px 14px;border-left:3px solid var(--accent2);background:#eef2f5;border-radius:0 8px 8px 0}
.summbox h3{margin:.1em 0 .4em;font-size:12.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--accent2)}
.summbox p{margin:0;font-size:14px;line-height:1.62}
.citelist{display:flex;flex-direction:column;gap:10px}
.citework{border:1px solid var(--rule);border-radius:9px;padding:10px 13px;background:var(--card)}
.citehd{margin:0;font-size:14px;line-height:1.5}
.citehd b{font-family:Georgia,serif}
.citenote{margin:6px 0 0;font-size:13.5px;line-height:1.6;color:#4a463f;padding-top:6px;border-top:1px dashed var(--rule)}
.histtag,.vertag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.02em;color:#fff;border-radius:20px;padding:1px 8px;vertical-align:1px}
.histtag{background:#9a9387}.vertag{background:#1d6e56}
.readnote{font-size:12.5px;color:var(--muted);line-height:1.55;margin:0 0 12px}
.facets{margin:0 0 10px;padding-left:20px;font-size:14px;line-height:1.5;color:#4a463f}
.conspaper{padding:10px 0;border-top:1px solid var(--rule)}
.conspaper:first-child{border-top:0}
.conslink{font-weight:600;font-size:14.5px;line-height:1.4}
.consmeta2{font-size:12px;color:var(--muted);margin:3px 0 4px}
.ptag{display:inline-block;background:var(--card);border:1px solid var(--rule);border-radius:5px;padding:0 6px;margin-left:5px;font-size:10.5px;text-transform:capitalize}
.constake{margin:3px 0 0;font-size:13.8px;line-height:1.55;color:#2f2c28}
@media(max-width:640px){.mgrid{grid-template-columns:1fr}.mgrid dt{padding-top:6px}}
"""

# papers whose catalogue record (organism or claim) was wrong when the related-literature search was run,
# so the retrieved literature is off-topic: the list is withheld rather than shown as if relevant
DOSSIER_NO_TOPICAL = {18, 58, 81, 83, 85, 87, 143, 155, 162, 167, 172, 175, 26, 27, 28, 31, 33}


def gen_dossier():
    """One page per paper: where its claim stands, how current research uses it, what it did,
    every work that cites it, and (where the search was on topic) the related modern literature."""
    def _ld(name):
        p = os.path.join(ROOT, "legacy_data", name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    DEEP = _ld("consensus_all.json")
    meth = _ld("methodology.json")
    ENR = _ld("citations_enriched.json")      # per paper -> works[]
    CNOTES = _ld("citation_notes.json")       # "<pid>:<oa_id>" -> prose note, mostly inferred from title/abstract
    CVER = set(_ld("citation_verified.json") or [])
    CTITLES = _ld("citation_titles.json")     # oa_id -> English title
    CSUMM = _ld("citation_summaries.json")    # pid -> summary of the citing works
    read_for = {t["id"]: t["page_slug"] for t in translations}
    os.makedirs(os.path.join(SITE, "dossier"), exist_ok=True)

    def _t(s):  # sources carry (sometimes doubly) encoded entities — fully decode, then escape once
        s = s or ""
        for _ in range(3):
            u = html.unescape(s)
            if u == s:
                break
            s = u
        return html.escape(s)

    def cited_by_html(pid_s):
        works = sorted((ENR.get(pid_s) or {}).get("works", []), key=lambda w: (w.get("year") or 0), reverse=True)
        summ = CSUMM.get(pid_s)
        n = len(works)
        if not works:
            return ('<section class="dsec"><h2>Every work that cites it</h2>'
                    '<p class="muted">No citing work is recorded in OpenAlex.</p></section>')
        sm = ('<div class="summbox"><h3>What the citing works do with it</h3><p>' + _t(summ) + '</p></div>') if summ else ''
        items = ""
        for w in works:
            a = w.get("authors") or []
            who = _t(a[0] if a else "") + (" et al." if len(a) > 1 else "")
            ttl = CTITLES.get(w.get("oa_id")) or w.get("title") or "(untitled)"
            doi = ('<a href="https://doi.org/%s" target="_blank" rel="noopener">doi ↗</a>' % w["doi"]) if w.get("doi") else ''
            key = "%s:%s" % (pid_s, w.get("oa_id"))
            tag = '<span class="histtag">history of science</span>' if w.get("historiographic") else ''
            ver = '<span class="vertag" title="Note written from the citing work’s full text">checked in the citing text</span>' if key in CVER else ''
            note = CNOTES.get(key)
            nt = ('<p class="citenote">' + _t(note) + '</p>') if note else ''
            yr = str(w.get("year") or "n.d.")
            if w.get("year_online"):
                yr += ' <span class="muted" title="OpenAlex lists the %s online date">(online %s)</span>' % (w["year_online"], w["year_online"])
            items += ('<div class="citework"><p class="citehd"><b>' + yr + '</b> · ' + who + ' — ' + _t(ttl)
                      + ' ' + doi + ' ' + tag + ' ' + ver + '</p>' + nt + '</div>')
        return ('<section class="dsec"><h2>Every work that cites it <span class="cnt">(%d in OpenAlex)</span></h2>' % n
                + sm + '<p class="readnote">The note under each work gives the likely reason it cites this paper. Most notes '
                'were reconstructed from the citing work’s title, topic and abstract, not from the citing sentence, which is '
                'rarely digitised for this literature; notes marked “checked in the citing text” were written from the citing '
                'work itself. Follow the DOI for the primary source.</p>'
                + '<div class="citelist">' + items + '</div></section>')

    def eras_html(c):
        tot = c.get("total", 0)
        if not tot:
            return '<p class="muted">No citing work is recorded in OpenAlex.</p>'
        segs = [("era-self", c.get("to1945_self", 0), "by 1945, by authors in this corpus"),
                ("era-early", c.get("to1945", 0) - c.get("to1945_self", 0), "by 1945, by others"),
                ("era-mid", c.get("mid", 0), "1946–1989"),
                ("era-sci", c.get("modern_sci", 0), "since 1990, scientific"),
                ("era-hist", c.get("modern_hist", 0), "since 1990, history of science")]
        dated = sum(v for _, v, _ in segs) or 1
        bar = "".join('<span class="%s" style="width:%.2f%%" title="%d %s"></span>' % (k, 100.0 * v / dated, v, lab)
                      for k, v, lab in segs if v)
        leg = "".join('<li><i class="%s"></i>%d %s</li>' % (k, v, lab) for k, v, lab in segs if v)
        return '<div class="eras" role="img" aria-label="Citing works by era">%s</div><ul class="eraleg">%s</ul>' % (bar, leg)

    def paper_html(r):
        bits = [str(r.get("year") or "")]
        au = html.escape(r.get("author") or "")
        if au:
            bits.append(au + (" +%d" % (r["n_authors"] - 1) if (r.get("n_authors") or 0) > 1 else ""))
        if r.get("journal"):
            bits.append(html.escape(r["journal"]))
        meta = " · ".join(x for x in bits if x)
        tags = ('<span class="ptag">' + html.escape(r["study_type"]) + '</span>') if r.get("study_type") else ""
        tk = ('<p class="constake">' + html.escape(r["takeaway"]) + '</p>') if r.get("takeaway") else ""
        u = r.get("url") or "#"
        return ('<div class="conspaper"><a class="conslink" href="' + html.escape(u) + '" target="_blank" rel="noopener">'
                + html.escape(r.get("title") or "(untitled)") + ' ↗</a><div class="consmeta2">' + meta + ' '
                + tags + '</div>' + tk + '</div>')

    n = 0
    for c in catalog:
        pid = c["id"]; pid_s = str(pid)
        a = ASSESS.get(pid)
        if not a:
            continue
        s = a["standing"]
        title_en = c.get("title_en") or c.get("title") or ""
        title_de = c.get("title") or ""
        org = c.get("organism") or ""
        read = ("../papers/" + read_for[pid] + ".html") if pid in read_for else None
        actions = '<a class="btn" href="../rediscovery.html">← Discover</a>'
        if read:
            actions += '<a class="btn primary" href="%s">Read the English translation</a>' % read
        actions += '<a class="btn" href="../reader.html?id=%d">German original</a>' % pid
        actions += '<a class="btn" href="../catalog.html?id=%d">Catalog entry</a>' % pid
        if c.get("doi"):
            actions += '<a class="btn" href="https://doi.org/%s" target="_blank" rel="noopener">DOI ↗</a>' % c["doi"]
        # --- where it stands
        openbox = ""
        if a.get("open"):
            openbox = ('<div class="openbox"><p><b>What is still open.</b> %s</p>%s</div>'
                       % (html.escape(a["open"]),
                          ('<p><b>How it could be tested.</b> %s</p>' % html.escape(a["test"])) if a.get("test") else ""))
        offers = "".join('<span class="oft oft-%s">%s</span>' % (o, html.escape(OFFER_LABEL[o])) for o in a.get("offers") or [])
        basis = ", ".join(BASIS_LABEL.get(b, b) for b in a.get("basis") or [])
        stand = f"""
  <section class="dsec standbox sb-{s}">
    <span class="lab">Where its claim stands today</span>
    <p class="sthead">{st_chip(pid, full=True)} <span class="stdef">{html.escape(ST_DEF[s])}</span></p>
    <p class="stverdict">{html.escape(a['verdict'])}</p>
    <p class="stwhy">{html.escape(a['why'])}</p>
    {openbox}
    {('<div class="offers">' + offers + '</div>') if offers else ''}
    <p class="stbasis">Assessed from {html.escape(basis)} · confidence: {html.escape(a.get('confidence') or '')} ·
      <a href="../rediscovery.html#how">how papers are assessed</a></p>
  </section>"""
        # --- how current research uses it
        k = a.get("cites") or {}
        un = ('<p class="usenote">%s</p>' % html.escape(a["use_note"])) if a.get("use_note") else ""
        use = f"""
  <section class="dsec usebox">
    <h2>How current research uses it</h2>
    <p>{use_chip(pid)} {html.escape(USE_DEF[a['use']])}</p>
    {un}
    {eras_html(k)}
  </section>"""
        # --- what the paper did (methodology record, corrected in the September 2026 review)
        m = meth.get(pid_s) or {}
        rows = [("Manipulation", "manipulation"), ("Design", "design"), ("Readout", "readout"),
                ("Quantification", "quantification"), ("Scale", "scale"), ("Sample", "n"), ("What it reported", "finding")]
        dl = "".join('<dt>%s</dt><dd%s>%s</dd>' % (lab, ' class="find"' if key == "finding" else "", html.escape(m[key]))
                     for lab, key in rows if m.get(key))
        tags = " ".join('<span class="badge">%s</span>' % html.escape(t) for t in (m.get("methods") or []))
        did = (f"""
  <section class="dsec">
    <h2>What the paper did</h2>
    {('<p style="margin:0 0 10px">' + ('<span class="badge mcl">' + html.escape(m.get('method')) + '</span> ' if m.get('method') else '') + tags + '</p>') if (m.get('method') or tags) else ''}
    <dl class="mgrid">{dl}</dl>
  </section>""" if dl else "")
        # --- related literature (topical, not citing)
        d = DEEP.get(pid_s) or {}
        res = sorted(d.get("results", []), key=lambda r: (r.get("year") or 0), reverse=True)
        topical = ""
        if res and pid not in DOSSIER_NO_TOPICAL:
            qs = "".join('<li>' + html.escape(f["q"]) + '</li>' for f in d.get("facets", []))
            topical = f"""
  <section class="dsec">
    <h2>Related modern literature <span class="cnt">({len(res)} papers, topical search)</span></h2>
    <p class="readnote">These papers do not cite this one. They were retrieved automatically in June 2026 from the
      <a href="https://consensus.app" target="_blank" rel="noopener">Consensus</a> search engine, with the questions below,
      to show what later work says on the paper’s subject; each takeaway is Consensus’s one-line summary.</p>
    <ul class="facets">{qs}</ul>
    <div class="conslist">{''.join(paper_html(r) for r in res)}</div>
  </section>"""
        body = f"""
<article class="dossier">
  <p class="kicker"><a href="../rediscovery.html">Discover</a> · {c.get('year')}{(' · <em>' + html.escape(org) + '</em>') if org else ''}</p>
  <h1>{html.escape(title_en)}</h1>
  {('<p class="detitle">' + html.escape(title_de) + '</p>') if title_de and title_de != title_en else ''}
  <p class="byline">{html.escape(c.get('author_full') or c.get('author') or '')} · {c.get('year')}</p>
  <div class="actionbar">{actions}</div>
  {sens_html(pid, "dossier")}
  {stand}
  {use}
  {did}
  {cited_by_html(pid_s)}
  {topical}
  <footer class="cite">Assessment: September 2026 review of the full corpus, one paper at a time, under a written rubric.
    Citations: OpenAlex. A research aid, not a settled historical judgment — corrections are welcome via
    <a href="../contribute.html">Get involved</a>.</footer>
</article>"""
        page(f"dossier/{pid}.html", title_en, "Discover", body,
             head="<style>" + DOSSIER_CSS + "</style>", prefix="../",
             desc=(f"{c.get('author_full') or c.get('author') or ''} ({c.get('year')}). {ST_LABEL[s]}: "
                   f"{a['verdict']}. {a['why']}")[:300])
        n += 1
    print("dossier pages:", n)


# ---------------------------------------------------------------- guided tour
TOUR_CSS = r"""
/* ---- the stage: full-bleed, dark, so the plates glow ---- */
main.wrap{max-width:none;padding:0}
footer.site{margin-top:0}
/* overflow-x:clip, NOT overflow:hidden: hidden would make the stage the sticky
   container and push the breadcrumb bar 62px down instead of pinning it */
.tstage{--ink:#ece6d8;--dim:#a8a192;--line:rgba(236,230,216,.14);--bg:#121418;--paper:#e9e0cb;
  position:relative;background:var(--bg);color:var(--ink);min-height:calc(100vh - 63px);overflow-x:clip}
.tstage a,.tstage a:hover{color:inherit;text-decoration:none}
.tcrumbs{position:sticky;top:63px;z-index:30;display:flex;flex-wrap:wrap;align-items:center;gap:4px 2px;
  padding:11px 22px;font:500 13.5px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:rgba(18,20,24,.9);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.tcrumbs button{all:unset;cursor:pointer;color:var(--dim);padding:3px 7px;border-radius:6px;transition:color .2s,background .2s}
.tcrumbs button:hover{color:var(--ink);background:rgba(236,230,216,.08)}
.tcrumbs button:focus-visible{outline:2px solid #cdb98a;outline-offset:1px}
.tcrumbs .sep{color:#5d584f;padding:0 1px}
.tcrumbs .here{color:var(--ink);padding:3px 7px;font-weight:600}

/* ---- overview: six questions as living cells ---- */
.tmap{position:relative;height:calc(100vh - 110px);min-height:600px;
  background:radial-gradient(ellipse 70% 80% at 66% 52%,#1d222a 0%,#15181d 55%,#121418 100%)}
.tmap svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.tmap-intro{position:absolute;left:34px;top:30px;bottom:24px;z-index:5;width:min(390px,32vw);display:flex;flex-direction:column;
  transition:opacity .45s}
.tmap-intro .k{font:600 11.5px/1.2 -apple-system,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:#cdb98a;margin:0 0 10px}
.tmap-intro h1{font:400 50px/1 Georgia,"Times New Roman",serif;margin:0 0 14px;color:#fff;letter-spacing:-.015em}
.tmap-intro .lead{font:15px/1.62 Georgia,serif;color:#cfc8b8;margin:0 0 20px}
.tlist{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px;overflow:auto}
.tlist button{all:unset;box-sizing:border-box;cursor:pointer;display:grid;grid-template-columns:12px 1fr auto;gap:2px 11px;align-items:baseline;
  width:100%;padding:9px 12px 10px 10px;border-radius:10px;transition:background .25s,transform .25s}
.tlist button:hover,.tlist button.on{background:rgba(236,230,216,.07);transform:translateX(4px)}
.tlist button:focus-visible{outline:2px solid #cdb98a}
.tlist .dot{width:10px;height:10px;border-radius:50%;background:var(--c);box-shadow:0 0 12px var(--c);align-self:center;grid-row:1/3}
.tlist b{font:400 17px/1.25 Georgia,serif;color:#fff}
.tlist i{font:italic 13.5px/1.4 Georgia,serif;color:#a9a293;grid-column:2}
.tlist .n{font:600 11px/1 -apple-system,sans-serif;letter-spacing:.08em;color:#8f887a;grid-column:3;grid-row:1}
.tmap-intro .hint{margin-top:auto;padding-top:14px;font:500 12.5px/1.45 -apple-system,sans-serif;color:#7f786b}
.tmap-intro .hint b{color:#cdb98a;font-weight:600}
.tmap.zoomed .tmap-intro{opacity:0;pointer-events:none}
.pg{transition:opacity .35s}
.pg.dim{opacity:.26}
.floater{animation:float var(--fd,9s) ease-in-out var(--fdel,0s) infinite alternate}
@keyframes float{from{transform:translate(0,-3px)}to{transform:translate(0,4px)}}
circle.disc{cursor:pointer;transition:fill-opacity .35s,stroke-width .35s}
.pg.hi circle.disc{fill-opacity:.26;stroke-width:2.4}
circle.ring{fill:none;stroke:rgba(236,230,216,.1);stroke-width:.8;pointer-events:none}
circle.leaf{cursor:pointer;stroke:rgba(10,11,14,.7);stroke-width:.8;transform-box:fill-box;transform-origin:center;
  transition:transform .28s cubic-bezier(.2,.8,.2,1),stroke .2s}
circle.leaf:hover{transform:scale(2.5);stroke:#fff;stroke-width:.5}
.tl-arc{font-family:Georgia,serif;fill:#f3ede0;letter-spacing:.01em;pointer-events:none;transition:opacity .4s}
.ttip{position:absolute;z-index:20;pointer-events:none;max-width:280px;padding:10px 13px;border-radius:10px;
  background:rgba(12,13,16,.95);border:1px solid var(--line);font:13px/1.45 -apple-system,sans-serif;color:#e8e2d4;
  opacity:0;transform:translateY(4px);transition:opacity .15s,transform .15s;box-shadow:0 12px 34px rgba(0,0,0,.55)}
.ttip.on{opacity:1;transform:none}
.ttip b{font:15px/1.3 Georgia,serif;display:block;color:#fff;margin:2px 0}
.ttip .y{color:#cdb98a;font-weight:600;font-size:12px;letter-spacing:.06em}

/* ---- portals ---- */
.tportal{position:relative;z-index:10;background:var(--bg);min-height:calc(100vh - 110px)}
.phero{position:relative;height:min(66vh,640px);min-height:420px;overflow:hidden;background:#0b0c0f;
  display:flex;align-items:center;justify-content:flex-end;padding-right:5.5%;box-sizing:border-box}
.phero .hbg{position:absolute;inset:-60px;width:calc(100% + 120px);height:calc(100% + 120px);object-fit:cover;
  filter:blur(28px) saturate(.75) brightness(.4);transform:scale(1.05)}
.phero .shade{position:absolute;inset:0;background:
  linear-gradient(180deg,rgba(18,20,24,0) 55%,rgba(18,20,24,.96) 100%),
  linear-gradient(90deg,rgba(18,20,24,.72) 0%,rgba(18,20,24,.2) 58%,rgba(18,20,24,0) 100%)}
.hplate{position:relative;z-index:2;transform:rotate(-1.2deg);max-width:44%;flex:0 1 auto;
  background:var(--paper);padding:12px;border-radius:3px;display:block;cursor:zoom-in;
  box-shadow:0 34px 80px rgba(0,0,0,.62),0 2px 0 rgba(255,255,255,.2) inset;animation:plate .9s cubic-bezier(.2,.8,.2,1) both .1s}
.hplate img{display:block;max-width:100%;object-fit:contain;mix-blend-mode:multiply}
@keyframes plate{from{opacity:0;transform:translateY(14px) rotate(1.5deg) scale(.96)}to{opacity:1;transform:rotate(-1.2deg)}}
.phero .htext{position:absolute;left:0;bottom:0;z-index:2;padding:0 34px 36px;max-width:min(52%,760px)}
.phero .medal{width:84px;height:84px;border-radius:50%;object-fit:cover;border:3px solid rgba(236,230,216,.85);
  box-shadow:0 10px 30px rgba(0,0,0,.5);filter:sepia(.35);margin:0 0 14px;display:block;background:#222}
.phero .kick{font:600 11.5px/1.3 -apple-system,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--acc,#cdb98a);margin:0 0 10px;
  filter:brightness(1.5) saturate(.8)}
.phero h1{font:400 clamp(32px,4.4vw,58px)/1.04 Georgia,serif;margin:0 0 12px;color:#fff;letter-spacing:-.015em;text-wrap:balance}
.phero .q{font:italic clamp(17px,1.8vw,21px)/1.38 Georgia,serif;color:#efe8d8;margin:0 0 12px;max-width:44ch}
.phero .intro{font:15.5px/1.62 Georgia,serif;color:#d6cfbf;margin:0;max-width:62ch}
.htext > *{animation:rise .8s cubic-bezier(.2,.8,.2,1) both}
.htext > *:nth-child(2){animation-delay:.07s}.htext > *:nth-child(3){animation-delay:.14s}
.htext > *:nth-child(4){animation-delay:.21s}.htext > *:nth-child(5){animation-delay:.28s}
@keyframes rise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
.caution{margin:22px 34px 0;padding:14px 18px;border-radius:11px;border:1px solid rgba(214,120,110,.35);
  border-left:4px solid #c9695e;background:rgba(138,58,58,.14);font:14.5px/1.6 -apple-system,sans-serif;color:#eadbd6;max-width:900px}
.caution b{color:#ffcfc6}

/* cards: every picture sits on the same paper, like a specimen card */
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(236px,1fr));gap:20px;padding:24px 34px 54px}
.psec{padding:6px 34px 0;margin:26px 0 0;font:600 11.5px/1.3 -apple-system,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}
.card{box-sizing:border-box;cursor:pointer;display:flex;flex-direction:column;border-radius:14px;overflow:hidden;
  background:#1b1e24;border:1px solid var(--line);
  transition:transform .4s cubic-bezier(.2,.8,.2,1),box-shadow .4s,border-color .4s;
  animation:rise .62s cubic-bezier(.2,.8,.2,1) both;animation-delay:calc(var(--i,0) * 42ms)}
.card:hover{transform:translateY(-6px);box-shadow:0 22px 50px rgba(0,0,0,.6);border-color:rgba(236,230,216,.34)}
.card:focus-visible{outline:2px solid #cdb98a;outline-offset:3px}
.card .cimg{position:relative;aspect-ratio:4/3;overflow:hidden;background:var(--paper)}
.card .cimg .pic{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;padding:12px;box-sizing:border-box;
  mix-blend-mode:multiply;transition:transform .9s cubic-bezier(.2,.8,.2,1)}
.card:hover .cimg .pic{transform:scale(1.05)}
.card .cimg .port{position:absolute;left:12px;bottom:10px;width:58px;height:58px;border-radius:50%;object-fit:cover;
  border:3px solid var(--paper);filter:sepia(.3);box-shadow:0 4px 14px rgba(0,0,0,.35)}
.card .cbody{padding:14px 16px 16px;display:flex;flex-direction:column;gap:6px;flex:1}
.card .cy{font:600 11px/1 -apple-system,sans-serif;letter-spacing:.12em;color:var(--acc,#cdb98a);filter:brightness(1.5) saturate(.8)}
.card .ct{font:17px/1.28 Georgia,serif;color:#fff;margin:0}
.card .cs{font:13.5px/1.5 -apple-system,sans-serif;color:var(--dim);margin:0;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.card .cmeta{margin-top:auto;display:flex;flex-wrap:wrap;gap:6px;padding-top:6px}
.chip{font:600 11px/1 -apple-system,sans-serif;letter-spacing:.02em;padding:5px 9px;border-radius:20px;background:rgba(236,230,216,.08);color:#d9d2c3;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
.chip.v{background:rgba(205,185,138,.14);color:#e7d6ab;white-space:normal;line-height:1.35}
.chip.st{color:#fff}
.chip.st-established{background:#2f8f71}.chip.st-consistent{background:#557f79}.chip.st-revised{background:#a8772a}
.chip.st-unresolved{background:#4c6883}.chip.st-not_supported{background:#a24a4a}.chip.st-no_claim{background:#6f6a61}
.art .why{font:15px/1.65 -apple-system,sans-serif;color:#cfc8b8;margin:-8px 0 24px;max-width:68ch}
.art .why .use{color:#9d968a}
.chip.note{background:rgba(201,105,94,.22);color:#ffc9c0}
.chip.note::before{content:"◆ ";font-size:9px}
.card.more .cimg{display:grid;grid-template-columns:repeat(3,1fr);gap:0}
.card.more .cimg img{width:100%;height:100%;object-fit:cover;mix-blend-mode:multiply}

/* article */
.art{padding:26px 34px 34px;max-width:980px}
.art .de{font:italic 16px/1.45 Georgia,serif;color:var(--dim);margin:0 0 8px}
.art .au{font:14px/1.5 -apple-system,sans-serif;color:#cfc8b8;margin:0 0 20px}
.art .note{margin:0 0 22px;padding:14px 18px;border-radius:11px;border:1px solid rgba(214,120,110,.35);border-left:4px solid #c9695e;
  background:rgba(138,58,58,.14);font:14.5px/1.6 -apple-system,sans-serif;color:#eadbd6}
.art .note .nh{font:700 11px/1 -apple-system,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#ff9f92;display:block;margin-bottom:7px}
.art .note a{color:#ffcfc6;text-decoration:underline}
.art .body{font:18px/1.72 Georgia,serif;color:#e4ddcd;margin:0 0 20px;max-width:68ch}
.art .verd{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 24px}
.art .verd .lab{font:600 11px -apple-system,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.art .acts{display:flex;flex-wrap:wrap;gap:10px}
.abtn{font:600 14px/1 -apple-system,sans-serif;padding:13px 18px;border-radius:9px;
  border:1px solid rgba(236,230,216,.28);color:#ece6d8;background:rgba(236,230,216,.04);transition:background .2s,border-color .2s,transform .2s}
.abtn:hover{background:rgba(236,230,216,.12);border-color:rgba(236,230,216,.6);transform:translateY(-1px)}
.abtn.pri{background:var(--acc,#8a5a2b);border-color:transparent;color:#fff}
.abtn.pri:hover{filter:brightness(1.15)}

/* the picture that flies between levels */
.tflip{position:fixed;z-index:60;pointer-events:none;background:#e9e0cb;overflow:hidden;
  box-shadow:0 30px 80px rgba(0,0,0,.55);will-change:left,top,width,height}
.tflip img{width:100%;height:100%;object-fit:contain;padding:4%;box-sizing:border-box;mix-blend-mode:multiply;display:block}

@media(max-width:980px){
  .tmap{height:auto;min-height:0;padding-bottom:10px}
  .tmap-intro{position:relative;left:0;top:0;bottom:auto;width:auto;padding:22px 20px 0}
  .tmap-intro h1{font-size:38px}
  .tmap-intro .lead{font-size:14.5px;margin-bottom:6px}
  .tlist,.tmap-intro .hint{display:none}
  .tmap svg{position:relative;height:78vh;min-height:460px}
  .phero{display:block;height:auto;min-height:0;padding:24px 0 0}
  .hplate{transform:rotate(-1deg);max-width:78%;width:max-content;margin:0 auto 18px;animation:none}
  .hplate img{max-height:none}
  .phero .htext{position:relative;max-width:none;padding:0 20px 26px}
  .pgrid{grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:12px;padding:18px 16px 40px}
  .card .cs{-webkit-line-clamp:3}
  .art,.psec{padding-left:18px;padding-right:18px}
  .caution{margin-left:16px;margin-right:16px}
  .tcrumbs{padding:9px 12px;font-size:12.5px}
}
@media(prefers-reduced-motion:reduce){
  .floater,.hplate,.card,.htext > *{animation:none!important}
  .card,.card .cimg .pic,circle.leaf{transition:none}
}
"""

TOUR_JS = r"""
(function(){
'use strict';
var T=window.TREE; if(!T||!window.d3){return;}
var RM=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
var TOUCH=window.matchMedia&&matchMedia('(hover: none)').matches;
function $(s,r){return (r||document).querySelector(s);}
function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
var mapEl=$('#tmap'), svgEl=$('#tsvg'), portal=$('#tportal'), crumbs=$('#tcrumbs'), tip=$('#ttip'), intro=$('#tmapintro');
var PROG={}; T.progs.forEach(function(p){PROG[p.id]=p;});
function P(id){return T.papers[String(id)];}
function sleep(ms){return new Promise(function(r){setTimeout(r,RM?0:ms);});}
function anim(el,frames,opts){
  if(RM||!el.animate){return Promise.resolve();}
  return new Promise(function(res){var a=el.animate(frames,opts);a.onfinish=res;a.oncancel=res;});}
var EASE='cubic-bezier(.2,.8,.2,1)';
function shortT(s,n){s=s||'';return s.length>n?s.slice(0,n-1).replace(/\s+\S*$/,'')+'…':s;}
// the site stylesheet sets smooth scrolling; the transitions need a real jump so they can measure where things land
function toTop(){window.scrollTo({top:0,left:0,behavior:'instant'});}

/* ================================================================ routing */
// a route is {p: programme, r: person key within it (or "_further"), a: paper id}
function parse(){var h=decodeURIComponent(location.hash.replace(/^#\/?/,'')).split('/').filter(Boolean);
  var rt={p:h[0]||null,r:h[1]||null,a:h[2]||null};
  if(rt.p&&!PROG[rt.p]) rt={p:null,r:null,a:null};
  if(rt.r&&rt.r!=='_further'&&!T.people[rt.p+'/'+rt.r]){rt.r=null;rt.a=null;}
  if(rt.a&&!P(rt.a)) rt.a=null;
  if(rt.a&&!rt.r) rt.a=null;
  return rt;}
function hashOf(rt){return '#/'+[rt.p,rt.r,rt.a].filter(Boolean).map(encodeURIComponent).join('/');}
function depth(rt){return rt.a?3:rt.r?2:rt.p?1:0;}
function same(a,b){return a.p===b.p&&a.r===b.r&&a.a===b.a;}
function isParent(a,b){return depth(a)===depth(b)-1&&(!a.p||a.p===b.p)&&(!a.r||a.r===b.r);}
var cur={p:null,r:null,a:null}, pending=null, busy=false, queued=false;
function go(rt,opts){pending=opts||{};var h=hashOf(rt);if(location.hash===h){route();}else{location.hash=h;}}
window.addEventListener('hashchange',route);

/* ================================================================ breadcrumbs */
function drawCrumbs(rt){
  var parts=[{label:T.root.title,rt:{p:null,r:null,a:null}}];
  if(rt.p) parts.push({label:PROG[rt.p].title,rt:{p:rt.p,r:null,a:null}});
  if(rt.r) parts.push({label:rt.r==='_further'?'Further contributors':T.people[rt.p+'/'+rt.r].name,rt:{p:rt.p,r:rt.r,a:null}});
  if(rt.a) parts.push({label:P(rt.a).year+' · '+shortT(P(rt.a).t,52),rt:rt});
  crumbs.innerHTML=parts.map(function(x,i){
    if(i===parts.length-1) return '<span class="here" aria-current="page">'+esc(x.label)+'</span>';
    return '<button type="button" data-h="'+esc(hashOf(x.rt))+'">'+esc(x.label)+'</button><span class="sep">›</span>';
  }).join('');}
crumbs.addEventListener('click',function(e){var b=e.target.closest('button[data-h]');if(b){location.hash=b.getAttribute('data-h');}});

/* ================================================================ the map: six cells */
var svg=d3.select(svgEl), world, defs, W=0, H=0, cells=[], view=null, entered=false;
function box(){var r=svgEl.getBoundingClientRect();return {w:r.width,h:r.height,wide:window.innerWidth>980};}
function layout(){
  var b=box(); W=b.w; H=b.h;
  var x0=b.wide?Math.min(470,W*0.35):8, y0=b.wide?20:8, aw=W-x0-14, ah=H-y0-14;
  var tot=d3.sum(T.progs,function(p){return p.n;}), fill=b.wide?0.5:0.54;
  for(var attempt=0;attempt<8;attempt++){
    var k=Math.sqrt(fill*aw*ah/(Math.PI*tot));
    var ns=T.progs.map(function(p,i){var a=-Math.PI/2+i/T.progs.length*2*Math.PI;
      return {id:p.id,r:k*Math.sqrt(p.n),x:x0+aw/2+Math.cos(a)*aw*0.24,y:y0+ah/2+Math.sin(a)*ah*0.24};});
    var sim=d3.forceSimulation(ns).stop()
      .force('c',d3.forceCollide(function(d){return d.r+26;}).strength(1).iterations(4))
      .force('x',d3.forceX(x0+aw/2).strength(0.05)).force('y',d3.forceY(y0+ah/2).strength(0.09));
    for(var t=0;t<360;t++){sim.tick();ns.forEach(function(d){
      d.x=Math.max(x0+d.r+6,Math.min(x0+aw-d.r-6,d.x));d.y=Math.max(y0+d.r+28,Math.min(y0+ah-d.r-6,d.y));});}
    var bad=false;
    for(var i=0;i<ns.length;i++)for(var j=i+1;j<ns.length;j++){
      if(Math.hypot(ns[i].x-ns[j].x,ns[i].y-ns[j].y)<ns[i].r+ns[j].r+20) bad=true;}
    if(!bad) return ns;
    fill*=0.88;
  }
  return ns;}
function inner(pr,R){
  var kids=pr.people.map(function(k){return {key:k,kids:T.people[k].papers.map(function(id){return {id:id,pers:k};})};});
  if(pr.further.length) kids.push({key:pr.id+'/_further',kids:pr.further.map(function(id){return {id:id,pers:pr.id+'/_further'};})});
  var h=d3.hierarchy({kids:kids},function(d){return d.kids;}).sum(function(d){return d.kids?0:1;})
    .sort(function(a,b){return b.value-a.value;});
  return d3.pack().size([2*R,2*R]).padding(function(d){return d.depth===0?Math.max(4,R*0.04):1.1;})(h);}
function arc(cx,cy,r){ // an arc over the top of a circle, for its title to ride on
  var a0=-Math.PI*0.94, a1=-Math.PI*0.06;
  return 'M'+(cx+r*Math.cos(a0))+','+(cy+r*Math.sin(a0))+' A'+r+','+r+' 0 0,1 '+(cx+r*Math.cos(a1))+','+(cy+r*Math.sin(a1));}
function buildMap(){
  var ns=layout(); cells=ns;
  svg.attr('viewBox','0 0 '+W+' '+H); svg.selectAll('*').remove();
  defs=svg.append('defs');
  world=svg.append('g').attr('class','world');
  var seen={};
  ns.forEach(function(n,ci){
    var pr=PROG[n.id]; n.pack=inner(pr,n.r);
    var outer=world.append('g').attr('class','pg').attr('data-p',n.id).attr('transform','translate('+(n.x-n.r)+','+(n.y-n.r)+')');
    var g=outer.append('g').attr('class','floater').style('--fd',(7+ci*1.3)+'s').style('--fdel',(-ci*1.7)+'s');
    g.append('circle').attr('class','disc').attr('cx',n.r).attr('cy',n.r).attr('r',n.r)
      .attr('fill',pr.accent).attr('fill-opacity',0.14).attr('stroke',pr.accent).attr('stroke-width',1.5)
      .attr('tabindex',0).attr('role','button').attr('aria-label',pr.title+' — '+pr.n+' papers')
      .on('mouseenter',function(e){hl(n.id,true);showTip('<b>'+esc(pr.title)+'</b>'+esc(pr.q),e);})
      .on('mousemove',moveTip).on('mouseleave',function(){hl(n.id,false);hideTip();})
      .on('click',function(e){e.stopPropagation();enterProg(n.id);})
      .on('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();enterProg(n.id);}});
    n.pack.children&&n.pack.children.forEach(function(c){
      g.append('circle').attr('class','ring').attr('cx',c.x).attr('cy',c.y).attr('r',c.r);});
    n.pack.leaves().forEach(function(l){
      var id=l.data.id, p=P(id), pat='pi'+id+'-'+n.id;
      if(!seen[pat]){seen[pat]=1;
        var pt=defs.append('pattern').attr('id',pat).attr('patternContentUnits','objectBoundingBox').attr('width',1).attr('height',1);
        pt.append('rect').attr('width',1).attr('height',1).attr('fill','#e9e0cb');
        pt.append('image').attr('href',p.img.b).attr('width',1).attr('height',1).attr('preserveAspectRatio','xMidYMid slice')
          .style('mix-blend-mode','multiply');
        // documents (papers with no figure) take their programme's colour, so the real pictures stand out
        if(p.kind==='titlepage') pt.append('rect').attr('width',1).attr('height',1).attr('fill',pr.accent).attr('fill-opacity',0.62);}
      g.append('circle').attr('class','leaf').attr('cx',l.x).attr('cy',l.y).attr('r',l.r).attr('fill','url(#'+pat+')')
        .datum({id:id,pers:l.data.pers,prog:n.id,x:l.x,y:l.y,r:l.r,cell:n})
        .style('pointer-events',TOUCH?'none':null)
        .on('mouseenter',function(e,d){d3.select(this.parentNode.parentNode).raise();d3.select(this).raise();hl(n.id,true);
          showTip('<span class="y">'+p.year+'</span><b>'+esc(shortT(p.t,96))+'</b>'+esc(p.au)+
            (p.sens?'<br><span style="color:#ffb3a8">◆ '+esc(p.sens.c)+' — context note</span>':''),e);})
        .on('mousemove',moveTip).on('mouseleave',function(){hl(n.id,false);hideTip();})
        .on('click',function(e,d){e.stopPropagation();hideTip();var k=d.pers.split('/');
          go({p:n.id,r:k[1],a:String(id)},{fromLeaf:d});});});
    // the title rides the rim, so it never covers a picture
    var fs=Math.max(12,Math.min(20,(n.r*Math.PI*0.88)/(pr.title.length*0.56)));
    defs.append('path').attr('id','arc-'+n.id).attr('d',arc(n.r,n.r,n.r+fs*0.55));
    g.append('text').attr('class','tl-arc').style('font-size',fs+'px').append('textPath')
      .attr('href','#arc-'+n.id).attr('startOffset','50%').attr('text-anchor','middle').text(pr.title);
  });
  svg.on('click',null);
  view=[W/2,H/2,Math.min(W,H)]; zoomTo(view);
  if(!entered&&!RM){entered=true;entrance();}
}
function zoomTo(v){ // v = [world x at centre, world y at centre, world size spanning min(W,H)]
  view=v; var k=Math.min(W,H)/v[2];
  world.attr('transform','translate('+(W/2-v[0]*k)+','+(H/2-v[1]*k)+') scale('+k+')');
  mapEl.classList.toggle('zoomed',k>1.05);}
function zoomView(t,dur){
  var i=d3.interpolateZoom(view,t);
  if(RM||!dur){zoomTo(t);return Promise.resolve();}
  return new Promise(function(res){svg.transition().duration(dur).ease(d3.easeCubicInOut)
    .tween('zoom',function(){return function(x){zoomTo(i(x));};}).on('end',res).on('interrupt',res);});}
function entrance(){
  world.selectAll('circle.disc').each(function(){var r=+this.getAttribute('r');
    d3.select(this).attr('r',0).transition().duration(900).ease(d3.easeBackOut.overshoot(1.2)).attr('r',r);});
  world.selectAll('circle.ring').attr('opacity',0).transition().delay(500).duration(700).attr('opacity',1);
  world.selectAll('circle.leaf').each(function(){var r=+this.getAttribute('r');
    d3.select(this).attr('r',0).transition().delay(380+Math.random()*1100).duration(560).ease(d3.easeBackOut.overshoot(1.6)).attr('r',r);});
  world.selectAll('text.tl-arc').attr('opacity',0).transition().delay(700).duration(800).attr('opacity',1);}
function hl(id,on){
  world.selectAll('g.pg').classed('dim',function(){return on&&this.getAttribute('data-p')!==id;})
    .classed('hi',function(){return on&&this.getAttribute('data-p')===id;});
  $$('.tlist button').forEach(function(b){b.classList.toggle('on',on&&b.getAttribute('data-p')===id);});}
function showTip(h,e){tip.innerHTML=h;tip.classList.add('on');moveTip(e);}
function hideTip(){tip.classList.remove('on');}
function moveTip(e){var r=mapEl.getBoundingClientRect();var x=e.clientX-r.left+18,y=e.clientY-r.top+16;
  if(x+290>r.width) x=e.clientX-r.left-296; if(y+120>r.height) y=e.clientY-r.top-110;
  tip.style.left=x+'px';tip.style.top=y+'px';}
function screenOf(n,leaf){ // where a cell (or a paper inside it) is on screen now
  var k=Math.min(W,H)/view[2], s=svgEl.getBoundingClientRect(), tx=W/2-view[0]*k, ty=H/2-view[1]*k;
  var wx=leaf?(n.x-n.r+leaf.x):n.x, wy=leaf?(n.y-n.r+leaf.y):n.y, wr=leaf?leaf.r:n.r;
  return {x:s.left+tx+wx*k, y:s.top+ty+wy*k, r:wr*k};}
function enterProg(id){hideTip();hl(id,false);go({p:id,r:null,a:null},{fromCell:id});}
function drawIntro(){
  intro.innerHTML='<p class="k">'+esc(T.root.place)+'</p><h1>'+esc(T.root.title)+'</h1><p class="lead">'+esc(T.root.intro)+'</p>'+
    '<ol class="tlist">'+T.progs.map(function(p){return '<li><button type="button" data-p="'+p.id+'" style="--c:'+p.accent+'">'+
      '<span class="dot"></span><b>'+esc(p.title)+'</b><span class="n">'+p.n+'</span><i>'+esc(p.q)+'</i></button></li>';}).join('')+'</ol>'+
    '<p class="hint">'+(TOUCH?'<b>Tap a circle</b> to go inside.':'Every dot is a paper — <b>hover</b> to see it, <b>click</b> a circle or a question to go inside.')+'</p>';
  $$('.tlist button').forEach(function(b){var id=b.getAttribute('data-p');
    b.addEventListener('mouseenter',function(){hl(id,true);});b.addEventListener('mouseleave',function(){hl(id,false);});
    b.addEventListener('focus',function(){hl(id,true);});b.addEventListener('blur',function(){hl(id,false);});
    b.addEventListener('click',function(){enterProg(id);});});}
var rs=null;
window.addEventListener('resize',function(){clearTimeout(rs);rs=setTimeout(function(){if(!mapEl.hidden)buildMap();else sizePlates();},180);});

/* ================================================================ portals */
function img(p,sz){return p&&p.img?p.img[sz]:'';}
// re-fit the plate to the viewport as it is NOW: on a phone the first paint can report a viewport
// twice the real height, and rotating the device changes it again
function sizePlates(){var im=$('.hplate img',portal);if(!im||!im.dataset.pw) return;
  var z=plateSize(+im.dataset.pw,+im.dataset.ph); if(z){im.style.width=z.w+'px';im.style.height=z.h+'px';}}
window.addEventListener('load',sizePlates);
// the plate's exact pixel size, known before the image downloads, so animations can land on it
function plateSize(pw,ph){
  if(!pw||!ph) return null;
  var wide=window.innerWidth>980, hw=portal.clientWidth||window.innerWidth;
  var maxW=(wide?hw*0.44:hw*0.78)-24, maxH=wide?Math.min(window.innerHeight*0.66,640)*0.78:window.innerHeight*0.44;
  var k=Math.min(maxW/pw,maxH/ph,1.6);
  return {w:Math.round(pw*k),h:Math.round(ph*k)};}
function heroHTML(o){
  return '<header class="phero" style="--acc:'+o.acc+'">'+
    '<img class="hbg" src="'+esc(o.bg)+'" alt="">'+'<div class="shade"></div>'+
    (o.plate?'<a class="hplate" href="'+esc(o.plate)+'" target="_blank" rel="noopener" title="Open the full image"><img src="'+esc(o.plate)+'" alt="'+esc(o.alt||'')+'"'+
      (function(){var z=plateSize(o.pw,o.ph);return z?' data-pw="'+o.pw+'" data-ph="'+o.ph+'" width="'+z.w+'" height="'+z.h+'" style="width:'+z.w+'px;height:'+z.h+'px"':'';})()+'></a>':'')+
    '<div class="htext">'+(o.medal?'<img class="medal" src="'+esc(o.medal)+'" alt="Portrait of '+esc(o.title)+'">':'')+
    '<p class="kick">'+o.kick+'</p><h1>'+esc(o.title)+'</h1>'+
    (o.q?'<p class="q">'+esc(o.q)+'</p>':'')+(o.intro?'<p class="intro">'+esc(o.intro)+'</p>':'')+'</div></header>';}
function paperCard(id,rt,i){
  var p=P(id), chips='';
  if(p.sens) chips+='<span class="chip note" title="'+esc(p.sens.s)+'">'+esc(p.sens.c)+'</span>';
  if(p.s) chips+='<span class="chip st st-'+p.s+'">'+esc(p.sl)+'</span>';
  return '<a class="card" style="--i:'+i+'" href="'+hashOf(rt)+'" data-id="'+id+'">'+
    '<div class="cimg"><img class="pic" src="'+esc(img(p,'c'))+'" alt="" loading="lazy"></div>'+
    '<div class="cbody"><span class="cy">'+p.year+'</span><h3 class="ct">'+esc(shortT(p.t,110))+'</h3>'+
    '<p class="cs">'+esc(p.au)+'</p><div class="cmeta">'+chips+'</div></div></a>';}
function personCard(k,pr,i){
  var r=T.people[k], n=r.papers.length, sub=r.blurb||[r.years,r.role].filter(Boolean).join(' · ');
  return '<a class="card" style="--i:'+i+'" href="'+hashOf({p:pr.id,r:r.key,a:null})+'">'+
    '<div class="cimg"><img class="pic" src="'+esc(r.img?r.img.c:'')+'" alt="" loading="lazy">'+
    (r.portrait?'<img class="port" src="'+esc(r.portrait)+'" alt="">':'')+'</div>'+
    '<div class="cbody"><span class="cy">'+n+' PAPER'+(n===1?'':'S')+(r.years?' · '+esc(r.years):'')+'</span>'+
    '<h3 class="ct">'+esc(r.name)+'</h3><p class="cs">'+esc(sub)+'</p></div></a>';}
function furtherCard(pr,i){
  var ims=pr.further.slice(0,6).map(function(id){return '<img src="'+esc(img(P(id),'b'))+'" alt="" loading="lazy">';}).join('');
  return '<a class="card more" style="--i:'+i+'" href="'+hashOf({p:pr.id,r:'_further',a:null})+'">'+
    '<div class="cimg">'+ims+'</div><div class="cbody"><span class="cy">'+pr.further.length+' PAPERS · '+pr.furtherPeople.length+' PEOPLE</span>'+
    '<h3 class="ct">Further contributors</h3><p class="cs">Assistants, visitors and students who each left a single paper on this question.</p></div></a>';}
function renderProg(pr){
  var cards=pr.people.map(function(k,i){return personCard(k,pr,i);}).join('');
  if(pr.further.length) cards+=furtherCard(pr,pr.people.length);
  return heroHTML({acc:pr.accent,bg:pr.img.c,plate:pr.img.d,pw:pr.img.w,ph:pr.img.h,alt:'A figure from one of the papers',
      kick:pr.n+' papers · '+pr.y0+'–'+pr.y1+' · '+pr.people.length+' researchers',title:pr.title,q:pr.q,intro:pr.intro})+
    (pr.caution?'<div class="caution"><b>Before you go further.</b> Some papers in this programme make claims about human sexuality, intersex people and race that are false and did real harm. Each carries a context note — marked ◆ on its card and shown in full before the paper.</div>':'')+
    '<p class="psec">The researchers</p><div class="pgrid">'+cards+'</div>';}
function renderPerson(pr,rk){
  var ids,name,sub,plate,medal,kick,bg,pw,ph;
  if(rk==='_further'){ids=pr.further;name='Further contributors';
    sub='Assistants, visitors and students who each left a single paper on '+pr.title.toLowerCase()+'.';
    var f=ids.map(P).filter(function(p){return p.kind!=='titlepage';})[0]||P(ids[0]);
    plate=img(f,'d');bg=img(f,'c');pw=f.img.w;ph=f.img.h;kick=esc(pr.title)+' · '+ids.length+' papers';}
  else{var r=T.people[pr.id+'/'+rk];ids=r.papers;name=r.name;sub=r.blurb;plate=r.img?r.img.d:'';bg=r.img?r.img.c:'';medal=r.portrait;
    pw=r.img&&r.img.w;ph=r.img&&r.img.h;
    kick=esc(pr.title)+' · '+ids.length+' paper'+(ids.length===1?'':'s')+(r.years?' · '+esc(r.years):'');}
  var cards=ids.map(function(id,i){return paperCard(id,{p:pr.id,r:rk,a:String(id)},i);}).join('');
  return heroHTML({acc:pr.accent,bg:bg,plate:plate,pw:pw,ph:ph,kick:kick,title:name,intro:sub,medal:medal})+
    '<p class="psec">'+(rk==='_further'?'Their papers':'Papers on this question')+'</p><div class="pgrid">'+cards+'</div>';}
function renderArticle(pr,rk,aid){
  var p=P(aid);
  var note=p.sens?'<div class="note"><span class="nh">◆ '+esc(p.sens.c)+' — read this first</span>'+esc(p.sens.s)+
      ' The full note is at the top of the '+(p.read?'<a href="'+esc(p.read)+'">reading page</a>':'reading page')+'.</div>':'';
  var acts='';
  if(p.read) acts+='<a class="abtn pri" href="'+esc(p.read)+'">Read the English translation →</a>';
  if(p.dos) acts+='<a class="abtn" href="'+esc(p.dos)+'">Where it stands, and who cites it</a>';
  acts+='<a class="abtn" href="'+esc(p.pdf)+'">The German original</a>';
  var sib=(rk==='_further'?pr.further:T.people[pr.id+'/'+rk].papers).filter(function(x){return String(x)!==String(aid);});
  var who=rk==='_further'?'this group':T.people[pr.id+'/'+rk].name;
  return heroHTML({acc:pr.accent,bg:img(p,'c'),plate:img(p,'d'),pw:p.img.w,ph:p.img.h,alt:p.kind==='titlepage'?'The paper\'s title page':'A figure from the paper',
      kick:p.year+' · '+esc(pr.title),title:p.t})+
    '<div class="art" style="--acc:'+pr.accent+'">'+(p.de&&p.de!==p.t?'<p class="de">'+esc(p.de)+'</p>':'')+
    '<p class="au">'+esc(p.au)+'</p>'+note+(p.text?'<p class="body">'+esc(p.text)+'</p>':'')+
    (p.s?'<div class="verd"><span class="lab">Today</span><span class="chip st st-'+p.s+'">'+esc(p.sl)+'</span><span class="chip v">'+esc(p.v)+'</span></div>':'')+
    (p.w?'<p class="why">'+esc(p.w)+(p.ul?' <span class="use">'+esc(p.ul)+'.</span>':'')+'</p>':'')+
    '<div class="acts">'+acts+'</div></div>'+
    (sib.length?'<p class="psec">More from '+esc(who)+'</p><div class="pgrid">'+
      sib.map(function(id,i){return paperCard(id,{p:pr.id,r:rk,a:String(id)},i);}).join('')+'</div>':'');}
function renderPortal(rt){
  var pr=PROG[rt.p];
  portal.style.setProperty('--acc',pr.accent);
  portal.innerHTML=rt.a?renderArticle(pr,rt.r,rt.a):rt.r?renderPerson(pr,rt.r):renderProg(pr);
  sizePlates(); requestAnimationFrame(sizePlates);
  document.title=(rt.a?P(rt.a).t:rt.r?(rt.r==='_further'?'Further contributors':T.people[rt.p+'/'+rt.r].name):pr.title)+' · Tour · Vienna Vivarium in English';}
portal.addEventListener('click',function(e){
  var a=e.target.closest('a.card');if(!a||e.metaKey||e.ctrlKey||e.shiftKey||e.button!==0) return;
  pending={src:a.querySelector('.cimg')};});

/* ================================================================ transitions */
function plateRect(){var h=$('.hplate',portal);return h?h.getBoundingClientRect():null;}
function plateSrc(){var i=$('.hplate img',portal);return i?(i.currentSrc||i.src):'';}
function fly(url,from,to,dur,r0,r1){
  if(RM) return Promise.resolve(null);
  var d=document.createElement('div');d.className='tflip';d.innerHTML='<img alt="" src="'+esc(url)+'">';
  var f={left:from.left+'px',top:from.top+'px',width:from.width+'px',height:from.height+'px',borderRadius:r0||'14px'};
  Object.keys(f).forEach(function(k){d.style[k]=f[k];});
  document.body.appendChild(d);
  return anim(d,[f,{left:to.left+'px',top:to.top+'px',width:to.width+'px',height:to.height+'px',borderRadius:r1||'3px'}],
              {duration:dur||720,easing:EASE,fill:'forwards'}).then(function(){return d;});}
function showMap(){mapEl.hidden=false;portal.hidden=true;portal.innerHTML='';portal.removeAttribute('style');
  var b=box(); if(!world||Math.abs(b.w-W)>2||Math.abs(b.h-H)>2) buildMap();}
function showPortal(){mapEl.hidden=true;portal.hidden=false;}
function overlay(){var top=crumbs.getBoundingClientRect().bottom;
  Object.assign(portal.style,{position:'fixed',left:'0',right:'0',top:top+'px',bottom:'0',overflow:'hidden',zIndex:'40'});return top;}
function unoverlay(){['position','left','right','top','bottom','overflow','zIndex'].forEach(function(k){portal.style[k]='';});}
async function mapToPortal(rt,o){
  var s;
  if(o.fromCell){var n=cells.find(function(c){return c.id===o.fromCell;});
    await zoomView([n.x,n.y,2*n.r*1.1],760); s=screenOf(n);}
  else{s=screenOf(o.fromLeaf.cell,o.fromLeaf);}
  renderPortal(rt); portal.hidden=false; var top=overlay();
  var cx=s.x, cy=s.y-top, R=Math.hypot(Math.max(cx,innerWidth-cx),Math.max(cy,innerHeight-top-cy))+8;
  await anim(portal,[{clipPath:'circle('+Math.max(5,s.r)+'px at '+cx+'px '+cy+'px)'},{clipPath:'circle('+R+'px at '+cx+'px '+cy+'px)'}],
             {duration:o.fromCell?700:860,easing:EASE});
  unoverlay(); mapEl.hidden=true; toTop();}
async function portalToMap(fromP){
  toTop();
  mapEl.hidden=false; var b=box(); if(!world||Math.abs(b.w-W)>2||Math.abs(b.h-H)>2) buildMap();
  var n=cells.find(function(c){return c.id===fromP;});
  zoomTo([n.x,n.y,2*n.r*1.1]);
  var s=screenOf(n), top=overlay();
  var cx=s.x, cy=s.y-top, R=Math.hypot(Math.max(cx,innerWidth-cx),Math.max(cy,innerHeight-top-cy))+8;
  await anim(portal,[{clipPath:'circle('+R+'px at '+cx+'px '+cy+'px)'},{clipPath:'circle('+s.r+'px at '+cx+'px '+cy+'px)'}],
             {duration:560,easing:'cubic-bezier(.6,0,.4,1)'});
  portal.hidden=true;portal.innerHTML='';portal.removeAttribute('style');
  await zoomView([W/2,H/2,Math.min(W,H)],820);}
async function deeper(rt,srcBox){
  // the clicked card's picture lifts off and becomes the plate on the next level
  var from=srcBox&&srcBox.getBoundingClientRect(); var si=srcBox&&$('.pic',srcBox); var url=si&&(si.currentSrc||si.src);
  await anim(portal,[{opacity:1},{opacity:0}],{duration:230,easing:'ease-out'});
  renderPortal(rt); portal.style.opacity='0'; toTop();
  var pl=$('.hplate',portal);
  if(pl) pl.style.animation='none';
  var to=plateRect();
  if(from&&to&&url&&from.width>0){
    if(pl) pl.style.visibility='hidden';
    portal.style.transition='opacity .45s'; portal.style.opacity='1';
    var d=await fly(url,from,to,760,'0px','3px');
    if(pl) pl.style.visibility='';
    if(d) anim(d,[{opacity:1},{opacity:0}],{duration:200}).then(function(){d.remove();});
    portal.style.transition='';
  }else{portal.style.opacity='';await anim(portal,[{opacity:0},{opacity:1}],{duration:320});}}
async function shallower(rt,child){
  // back up a level: the plate shrinks back into the card it came from
  if(scrollY>40){window.scrollTo({top:0,behavior:RM?'auto':'smooth'});await sleep(320);}
  var from=plateRect(), url=plateSrc();
  await anim(portal,[{opacity:1},{opacity:0}],{duration:200});
  renderPortal(rt); portal.style.opacity='0';
  var sel=child.a?'a.card[data-id="'+child.a+'"]':'a.card[href="'+hashOf({p:child.p,r:child.r,a:null})+'"]';
  var card=$(sel,portal); if(card) card.scrollIntoView({block:'center',behavior:'instant'});
  var ci=card&&$('.cimg',card), to=ci&&ci.getBoundingClientRect();
  portal.style.opacity='';
  if(from&&to&&url){ci.style.visibility='hidden';
    var d=await fly(url,from,to,640,'3px','0px'); ci.style.visibility=''; if(d) d.remove();}}
async function crossfade(rt){
  await anim(portal,[{opacity:1},{opacity:0}],{duration:180});
  renderPortal(rt); toTop();
  await anim(portal,[{opacity:0},{opacity:1}],{duration:320});}

/* ================================================================ router */
async function route(){
  if(busy){queued=true;return;}
  var rt=parse(), prev=cur, o=pending||{}; pending=null;
  if(same(rt,prev)&&(depth(rt)===0?!mapEl.hidden:!portal.hidden)) return;
  busy=true; drawCrumbs(rt); hideTip();
  try{
    if(depth(rt)===0){
      if(depth(prev)>0&&!portal.hidden&&!RM) await portalToMap(prev.p);
      else{showMap();zoomTo([W/2,H/2,Math.min(W,H)]);}
      document.title='Tour · Vienna Vivarium in English';
    }else if(!mapEl.hidden&&(o.fromCell||o.fromLeaf)&&!RM){await mapToPortal(rt,o);}
    else if(portal.hidden){renderPortal(rt);showPortal();toTop();}
    else if(o.src){await deeper(rt,o.src);}
    else if(isParent(rt,prev)){await shallower(rt,prev);}
    else{await crossfade(rt);}
  }catch(err){renderPortal(rt);showPortal();if(window.console)console.error(err);}
  finally{cur=rt;busy=false;if(queued){queued=false;pending=null;route();}}}
document.addEventListener('keydown',function(e){
  if(e.key!=='Escape'||depth(cur)===0) return;
  var up={p:cur.p,r:cur.r,a:null}; if(!cur.a){if(cur.r)up.r=null;else up.p=null;} location.hash=hashOf(up);});

// first paint
var start=parse(); cur=start; drawCrumbs(start); drawIntro(); buildMap();
if(depth(start)>0){renderPortal(start);showPortal();}
})();
"""


# ---------------------------------------------------------------- guided tour (hierarchical)
# Institute -> six research programmes -> the researchers who pursued each -> their articles.
# Content: legacy_data/tour_tree.json (programmes, intros, per-programme researcher blurbs,
# assignment overrides, picture choices). Pictures: legacy_data/tour_src/<id>.jpg, chosen by
# locating the figure region on each page (text masked out) and reviewed by eye.
# The overview is a zoomable circle-pack; entering a programme opens "picture portals".



def _smart_square(im, side):
    """Square crop centred on the detail (edge energy), not the geometric middle."""
    from PIL import Image, ImageFilter
    im = im.convert("RGB"); w, h = im.size; s = min(w, h)
    if w != h:
        small = im.copy(); small.thumbnail((160, 160))
        e = small.convert("L").filter(ImageFilter.FIND_EDGES); px = e.load()
        sw, sh = small.size; ss = min(sw, sh)
        if sw > sh:
            cols = [sum(px[x, y] for y in range(sh)) for x in range(sw)]
            x0 = max(range(sw - ss + 1), key=lambda i: sum(cols[i:i + ss]))
            x = int(x0 * w / sw); im = im.crop((x, 0, x + s, s))
        else:
            rows = [sum(px[x, y] for x in range(sw)) for y in range(sh)]
            y0 = max(range(sh - ss + 1), key=lambda i: sum(rows[i:i + ss]))
            y = int(y0 * h / sh); im = im.crop((0, y, s, y + s))
    return im.resize((side, side), Image.LANCZOS)


def gen_tour():
    from PIL import Image
    tp = os.path.join(ROOT, "legacy_data", "tour_tree.json")
    if not os.path.exists(tp):
        return
    TT = json.load(open(tp, encoding="utf-8"))

    def ld(name):
        p = os.path.join(ROOT, "legacy_data", name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    SENS = ld("sensitivity.json")
    METH = ld("methodology.json")
    AUTH = json.load(open(os.path.join(ROOT, "legacy_data", "authors.json"), encoding="utf-8"))["people"]
    cat_by_id = {c["id"]: c for c in catalog}
    read_for = {t["id"]: t["page_slug"] for t in translations}
    slug_of = {t["id"]: t["trans_slug"] for t in translations}

    out = os.path.join(SITE, "assets", "tree"); os.makedirs(out, exist_ok=True)
    srcdir = os.path.join(ROOT, "legacy_data", "tour_src")

    def cut(pid, key=None):
        """b = 180px square (bubbles), c = 560px card, d = 1200px detail/hero."""
        key = key or "p%s" % pid
        src = os.path.join(srcdir, "%s.jpg" % pid)
        if not os.path.exists(src):
            return None
        im = Image.open(src).convert("RGB")
        _smart_square(im, 180).save(os.path.join(out, key + "-b.jpg"), "JPEG", quality=78, optimize=True)
        c = im.copy(); c.thumbnail((560, 700), Image.LANCZOS)
        c.save(os.path.join(out, key + "-c.jpg"), "JPEG", quality=80, optimize=True, progressive=True)
        d = im.copy(); d.thumbnail((1200, 1200), Image.LANCZOS)
        d.save(os.path.join(out, key + "-d.jpg"), "JPEG", quality=82, optimize=True, progressive=True)
        return {"b": "assets/tree/%s-b.jpg" % key, "c": "assets/tree/%s-c.jpg" % key,
                "d": "assets/tree/%s-d.jpg" % key, "w": d.size[0], "h": d.size[1]}

    # ---- papers -> programmes
    assign = {int(k): v for k, v in TT.get("assign", {}).items()}
    pics = TT.get("pictures", {})

    def programme_of(c):
        if c["id"] in assign:
            return assign[c["id"]]
        ph = c.get("phenomena") or []
        for p in PHENOMENON_PRIORITY:
            if p in ph:
                return PROGRAMME_OF_PHENOMENON[p]
        return "growth"

    papers = {}
    for c in catalog:
        pid = c["id"]; ps = str(pid)
        img = cut(pid)
        # what the paper reported (methodology record, checked against the paper in the September 2026
        # review) and where it stands today (the assessment) — no narrative that could outrun the evidence
        text = (METH.get(ps) or {}).get("finding") or ""
        asg = ASSESS.get(pid) or {}
        s = SENS.get(ps)
        pk = (pics.get(ps) or {}).get("kind", "titlepage")
        papers[ps] = dict(
            id=pid, year=c["year"], t=c.get("title_en") or c.get("title") or "",
            de=c.get("title") or "", au=c.get("author_full") or c.get("author") or "",
            img=img, kind=pk, text=text,
            s=asg.get("standing") or "", sl=ST_LABEL.get(asg.get("standing"), ""),
            v=asg.get("verdict") or "", w=asg.get("why") or "", ul=USE_LABEL.get(asg.get("use"), ""),
            sens=({"c": s["category"], "s": s.get("short", ""), "sev": s.get("severity", "medium")} if s else None),
            read=("papers/%s.html" % read_for[pid]) if pid in read_for else None,
            dos=("dossier/%d.html" % pid) if asg else None,
            pdf="reader.html?id=%d" % pid,
            prog=programme_of(c))

    # ---- researchers within each programme
    blurbs = TT.get("blurbs", {})
    progs = []
    people = {}
    for P in TT["programmes"]:
        pid_list = [int(k) for k, v in papers.items() if v["prog"] == P["id"]]
        pset = set(pid_list)
        principal, further_people = [], []
        for person in AUTH:
            mine = sorted([i for i in person["papers"] if i in pset], key=lambda i: cat_by_id[i]["year"])
            if not mine:
                continue
            key = "%s/%s" % (P["id"], person["key"])
            is_principal = len(mine) >= 2 or person.get("featured") or person["key"] in blurbs.get(P["id"], {})
            # the person's picture: portrait if we have one, else their strongest figure here
            fig = sorted(mine, key=lambda i: (papers[str(i)]["kind"] == "titlepage",
                                              -((pics.get(str(i)) or {}).get("score") or 0)))[0]
            rec = dict(key=person["key"], name=person["name"], years=person.get("years", ""),
                       role=person.get("role", ""), blurb=blurbs.get(P["id"], {}).get(person["key"], ""),
                       portrait=("assets/" + person["img"]) if person.get("img") else None,
                       img=papers[str(fig)]["img"], papers=mine)
            people[key] = rec
            (principal if is_principal else further_people).append(key)
        principal.sort(key=lambda k: (-len(people[k]["papers"]), people[k]["name"]))
        further_people.sort(key=lambda k: people[k]["name"])
        further = sorted({i for k in further_people for i in people[k]["papers"]},
                         key=lambda i: cat_by_id[i]["year"])
        yrs = [cat_by_id[i]["year"] for i in pid_list]
        cov = cut(P["cover"], key="prog-%s" % P["id"])   # c = blurred backdrop + homepage, d = the plate
        progs.append(dict(id=P["id"], title=P["title"], q=P["question"], intro=P["intro"],
                          accent=P.get("accent", "#8a5a2b"), caution=bool(P.get("caution")),
                          n=len(pid_list), y0=min(yrs), y1=max(yrs), img=cov,
                          people=principal, further=further, furtherPeople=further_people))

    R = TT["root"]
    data = dict(root=dict(title=R["title"], place=R["place"], intro=R["intro"], n=STATS["papers"]),
                progs=progs, people=people, papers=papers)
    open(os.path.join(DATA, "tree.js"), "w", encoding="utf-8").write(
        "window.TREE=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";")

    body = ('<div class="tstage" id="tstage">'
            '<nav class="tcrumbs" id="tcrumbs" aria-label="Where you are in the tour"></nav>'
            '<div class="tmap" id="tmap">'
            '<div class="tmap-intro" id="tmapintro"></div>'
            '<svg id="tsvg" role="img" aria-label="The corpus as nested circles: six research programmes, their researchers and their papers"></svg>'
            '<div class="ttip" id="ttip" role="tooltip"></div>'
            '</div>'
            '<div class="tportal" id="tportal" hidden></div>'
            '</div>'
            '<noscript><p style="padding:20px">The tour needs JavaScript. '
            'The same material is in the <a href="catalog.html">catalog</a> and on the '
            '<a href="authors.html">authors</a> page.</p></noscript>')
    page("tour.html", "Tour", "Tour", body,
         head="<style>" + TOUR_CSS + "</style>",
         foot='<script src="assets/d3.v7.min.js"></script><script src="data/tree.js"></script>'
              '<script>' + TOUR_JS + '</script>',
         desc="A guided tour of the Vienna Vivarium: from six big questions down to the researchers "
              "who pursued them and the papers they wrote, with the figures from the papers.")
    n_img = sum(1 for v in papers.values() if v["kind"] != "titlepage")
    print("tour.html: %d programmes | %d researcher nodes | %d papers (%d with a figure) " %
          (len(progs), len(people), len(papers), n_img))


def gen_citations():
    """Emit the slim per-paper citing-works list (for bubbles) + the composed paragraphs."""
    enr_path = os.path.join(ROOT, "legacy_data", "citations_enriched.json")
    notes_path = os.path.join(ROOT, "legacy_data", "citation_notes.json")
    titles_path = os.path.join(ROOT, "legacy_data", "citation_titles.json")
    titles = json.load(open(titles_path, encoding="utf-8")) if os.path.exists(titles_path) else {}
    cits = {}
    if os.path.exists(enr_path):
        enr = json.load(open(enr_path, encoding="utf-8"))
        for pid, v in enr.items():
            arr = []
            for w in v["works"]:
                a = w["authors"]
                aname = (a[0] if a else "") + (" et al." if len(a) > 1 else "")
                rec = dict(k=w["oa_id"], d=w["doi"], y=w["year"], a=aname,
                           t=w["title"], s=w["topic"].get("subfield", ""),
                           h=1 if w["historiographic"] else 0, m=w["species_match"])
                et = titles.get(w["oa_id"])
                if et:
                    rec["et"] = et
                arr.append(rec)
            arr.sort(key=lambda x: (x["h"], -(x["y"] or 0)))
            cits[pid] = arr
    notes = json.load(open(notes_path, encoding="utf-8")) if os.path.exists(notes_path) else {}
    ver_path = os.path.join(ROOT, "legacy_data", "citation_verified.json")
    verified = json.load(open(ver_path, encoding="utf-8")) if os.path.exists(ver_path) else []
    ver_map = {k: 1 for k in verified}
    os.makedirs(DATA, exist_ok=True)
    open(os.path.join(DATA, "citations.js"), "w", encoding="utf-8").write(
        "window.CITATIONS=" + json.dumps(cits, ensure_ascii=False) + ";")
    open(os.path.join(DATA, "notes.js"), "w", encoding="utf-8").write(
        "window.NOTES=" + json.dumps(notes, ensure_ascii=False) + ";\n"
        "window.VERIFIED=" + json.dumps(ver_map, ensure_ascii=False) + ";")
    sum_path = os.path.join(ROOT, "legacy_data", "citation_summaries.json")
    summaries = json.load(open(sum_path, encoding="utf-8")) if os.path.exists(sum_path) else {}
    open(os.path.join(DATA, "summaries.js"), "w", encoding="utf-8").write(
        "window.SUMMARIES=" + json.dumps(summaries, ensure_ascii=False) + ";")
    print("citations.js:", sum(len(v) for v in cits.values()), "works | notes:", len(notes),
          "| verified:", len(verified), "| summaries:", len(summaries))

def gen_methodology():
    """Emit per-paper methodology: auto cluster for all 175 + full structured records where written."""
    auto = json.load(open(os.path.join(ROOT, "legacy_data", "methodology_auto.json"), encoding="utf-8")) if os.path.exists(os.path.join(ROOT, "legacy_data", "methodology_auto.json")) else {}
    full = json.load(open(os.path.join(ROOT, "legacy_data", "methodology.json"), encoding="utf-8")) if os.path.exists(os.path.join(ROOT, "legacy_data", "methodology.json")) else {}
    meth = {}
    for pid, rec in auto.items():
        meth[pid] = {"cluster": rec.get("cluster", ""), "tags": rec.get("tags", [])}
    for pid, rec in full.items():
        meth.setdefault(pid, {})
        meth[pid]["cluster"] = rec.get("method") or meth[pid].get("cluster", "")
        meth[pid]["full"] = rec
    os.makedirs(DATA, exist_ok=True)
    open(os.path.join(DATA, "methodology.js"), "w", encoding="utf-8").write(
        "window.METH=" + json.dumps(meth, ensure_ascii=False) + ";")
    print("methodology.js:", len(meth), "papers |", sum(1 for v in meth.values() if v.get("full")), "full summaries")

# ---------------------------------------------------------------- reading pages
def render_md(slug):
    mdpath = os.path.join(TRANS, slug + "_FULL.md")
    txt = open(mdpath, encoding="utf-8").read()
    lines = txt.split("\n")
    # drop the first markdown H1 (we render our own title)
    for i, ln in enumerate(lines):
        if ln.strip():
            if ln.startswith("# "):
                lines[i] = ""
            break
    txt = "\n".join(lines)
    out = subprocess.run(["pandoc", "-f", "markdown", "-t", "html5", "--no-highlight"],
                         input=txt, capture_output=True, text=True)
    frag = out.stdout
    frag = frag.replace('src="figures/', 'src="../figures/')
    frag = re.sub(r'\s*style="width:[^"]*"', '', frag)
    frag = re.sub(r'\swidth="\d+"', '', frag)
    toc = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', frag)
    return frag, toc

def gen_reading_pages():
    os.makedirs(os.path.join(SITE, "papers"), exist_ok=True)
    _ti = os.path.join(ROOT, "legacy_data", "translation_issues.json")
    TR_NOTES = {k: v["public_note"] for k, v in (json.load(open(_ti, encoding="utf-8")) if os.path.exists(_ti) else {}).items()
                if isinstance(v, dict) and v.get("public_note")}
    cat_by_id = {c["id"]: c for c in catalog}
    _sp = os.path.join(ROOT, "legacy_data", "citation_summaries.json")
    SUMM = json.load(open(_sp, encoding="utf-8")) if os.path.exists(_sp) else {}
    # cross-link indices: paper -> author cards, and organism groupings for "related papers"
    _AUTH = json.load(open(os.path.join(ROOT, "legacy_data", "authors.json"), encoding="utf-8"))
    pid2auth = {}
    for _p in _AUTH["people"]:
        for _pid in _p.get("papers", []):
            pid2auth.setdefault(_pid, []).append((_p["key"], _p["name"]))
    read_for = {tt["id"]: tt["page_slug"] for tt in translations}
    # a few catalog rows have a wrong organism (fixed only via rediscovery.json org_override);
    # leave those out of the organism grouping so they neither pollute nor get a wrong "related" list
    _rp = os.path.join(ROOT, "legacy_data", "rediscovery.json")
    _bad_org = set()
    if os.path.exists(_rp):
        _bad_org = {int(k) for k in json.load(open(_rp, encoding="utf-8")).get("org_override", {})}
    genus_idx, taxon_idx = {}, {}
    for _c in catalog:
        if _c["id"] in _bad_org:
            continue
        _g = (_c.get("genus") or "").strip().lower()
        _x = (_c.get("taxon") or "").strip().lower()
        if _g:
            genus_idx.setdefault(_g, []).append(_c["id"])
        if _x:
            taxon_idx.setdefault(_x, []).append(_c["id"])
    for t in translations:
        slug = t["trans_slug"]; ps = t["page_slug"]
        frag, toc = render_md(slug)
        c = cat_by_id[t["id"]]
        lg = legacy.get(str(t["id"]), {})
        toc_html = "".join(f'<a href="#{i}">{re.sub("<.*?>","",txt)}</a>' for i, txt in toc) if toc else ""
        doi = t["doi"]
        doi_a = f'<a href="https://doi.org/{doi}">{doi}</a>' if doi else "—"
        wip = t["status"] != "complete"
        pid = t["id"]
        pdf_rel = f"../pdfs/{t['pdf']}"
        reader_sxs = f"../reader.html?id={pid}&sxs=1"
        reader_one = f"../reader.html?id={pid}"
        notice = '<div class="notice">This translation is still being finalized (figures or full text in progress).</div>' if wip else ""
        if TR_NOTES.get(slug):     # a known problem with this translation, stated before the text
            notice += '<div class="notice">%s</div>' % html.escape(TR_NOTES[slug])
        # (Legacy panel removed — its content now lives in the Discover dossier.)
        # connections panel: author bio(s), this paper's rediscovery card, related papers (same organism)
        auth_links = "".join(
            '<a class="cnchip" href="../authors.html#a-%s">%s &rarr;</a>' % (html.escape(k), html.escape(nm))
            for k, nm in pid2auth.get(pid, []))
        redis_link = ('<p class="ck">Today</p>'
                      '<a class="cnredis" href="../dossier/%d.html">Where it stands, and who cites it &rarr;</a>' % pid
                      ) if pid in ASSESS else ""
        _g = (c.get("genus") or "").strip().lower()
        _x = (c.get("taxon") or "").strip().lower()
        _seen = {pid}; _rel = []; _from_genus = 0
        if pid not in _bad_org:
            for _rid in genus_idx.get(_g, []):
                if _rid not in _seen:
                    _seen.add(_rid); _rel.append(_rid)
            _from_genus = len(_rel)
            if len(_rel) < 4:
                for _rid in taxon_idx.get(_x, []):
                    if _rid not in _seen:
                        _seen.add(_rid); _rel.append(_rid)
            _rel.sort(key=lambda r: (0 if r in read_for else 1, cat_by_id[r].get("year") or 0))
            _rel = _rel[:6]

        def _rlink(rid):
            rc = cat_by_id[rid]
            href = (read_for[rid] + ".html") if rid in read_for else ("../reader.html?id=%d" % rid)
            tt = (rc.get("title_en") or rc.get("title") or "").strip()
            if len(tt) > 46:
                tt = tt[:45].rstrip() + "…"
            return '<a class="cnchip" href="%s">%s &middot; %s</a>' % (href, rc.get("year"), html.escape(tt))
        rel_html = "".join(_rlink(r) for r in _rel)
        _org_label = (c.get("genus") if _from_genus else (c.get("taxon") or "the corpus"))
        connect = ('<section class="connect"><h2>Connections</h2>'
                   + (('<p class="ck">Author</p>' + auth_links) if auth_links else '')
                   + redis_link
                   + (('<p class="ck">More on %s</p>%s' % (html.escape(_org_label), rel_html)) if rel_html else '')
                   + '</section>')
        _pid = c["id"]
        _as = ASSESS.get(_pid) or {}
        _doss_btn = ('<a class="btn" href="../dossier/%d.html">Where it stands today</a>' % _pid) if _as else ''
        _doss_chip = st_chip(_pid, href="../dossier/%d.html" % _pid)
        _doss_line = ('<p class="dverdline"><b>Today:</b> %s <a href="../dossier/%d.html">why, and who cites it →</a></p>'
                      % (html.escape(_as["verdict"]), _pid)) if _as else ''
        body = f"""
<article class="reading">
  <p class="kicker"><a href="../catalog.html">Catalog</a> · BVA · {t['year']}</p>
  <h1>{html.escape(t['title_en'])}</h1>
  <p class="detitle">{html.escape(t['title_de'])}</p>
  <p class="byline">{html.escape(t['author'])} · {html.escape(t['journal'])} · DOI {doi_a}</p>
  <div class="badges">{_doss_chip} {('<span class=badge org>'+html.escape(c['organism'])+'</span>') if c['organism'] else ''} {'<span class="badge wip">in progress</span>' if wip else '<span class="badge done">full text</span>'}</div>
  {_doss_line}
  {sens_html(pid, "read")}
  <div class="actionbar">
    <a class="btn primary" href="{reader_sxs}">⇆ Read German side-by-side</a>
    <a class="btn" href="{reader_one}">German reader</a>
    {_doss_btn}
    <a class="btn" href="{pdf_rel}" download>↓ Download PDF</a>
    {('<a class="btn" href="https://doi.org/'+doi+'" target="_blank">DOI ↗</a>') if doi else ''}
  </div>
  {notice}
  <div class="cols">
    <div class="text">{frag}</div>
    <aside class="toc">{('<div class=tocbox><p>On this page</p>'+toc_html+'</div>') if toc_html else ''}{connect}</aside>
  </div>
  <footer class="cite">Cite: {html.escape(t['author'])} ({t['year']}), “{html.escape(t['title_de'])},” {html.escape(t['journal'])}. English translation, Vienna Vivarium in English.</footer>
</article>"""
        page(f"papers/{ps}.html", t["title_en"], "Translations", body, prefix="../",
             desc=(f"English translation of {t['author']} ({t['year']}), “{t['title_de']}” — "
                   f"Biologische Versuchsanstalt, Vienna. With original figures and the German scan side by side.")[:300])

# ---------------------------------------------------------------- assets / copy
def _cp(src, dst):
    """Copy only if missing (mounted FS may forbid unlink/overwrite)."""
    if os.path.exists(dst):
        return
    try:
        shutil.copyfile(src, dst)
    except Exception as e:
        print("  skip", os.path.basename(dst), e)

def copy_assets():
    if os.path.isdir(FIGSRC):
        for d in sorted(glob.glob(os.path.join(FIGSRC, "*"))):
            if not os.path.isdir(d):
                continue
            out = os.path.join(SITE, "figures", os.path.basename(d))
            os.makedirs(out, exist_ok=True)
            for f in glob.glob(os.path.join(d, "*")):
                _cp(f, os.path.join(out, os.path.basename(f)))
    pdir = os.path.join(SITE, "pdfs"); os.makedirs(pdir, exist_ok=True)
    pdfs = sorted({c["pdf"] for c in catalog if c["pdf"]}) if FULL else sorted({t["pdf"] for t in translations})
    for fn in pdfs:
        _cp(os.path.join(ARTICLES, fn), os.path.join(pdir, fn))
    # site imagery (historical photos / map) committed under legacy_data/img
    # vendored libraries (served locally so the offline download works without a network)
    vend = os.path.join(ROOT, "legacy_data", "vendor", "d3.v7.9.0.min.js")
    if os.path.exists(vend):
        os.makedirs(os.path.join(SITE, "assets"), exist_ok=True)
        shutil.copyfile(vend, os.path.join(SITE, "assets", "d3.v7.min.js"))
    imgsrc = os.path.join(ROOT, "legacy_data", "img")
    if os.path.isdir(imgsrc):
        for root, _dirs, files in os.walk(imgsrc):
            rel = os.path.relpath(root, imgsrc)
            outd = os.path.join(SITE, "assets", "img") if rel == "." else os.path.join(SITE, "assets", "img", rel)
            os.makedirs(outd, exist_ok=True)
            for f in files:
                _cp(os.path.join(root, f), os.path.join(outd, f))

def write_css():
    css = r""":root{--paper:#f7f4ee;--card:#fffdf9;--ink:#211f1c;--muted:#6f6a61;--rule:#e4ddce;
--accent:#7a3b2e;--accent2:#355e7d;--link:#355e7d;--l1:#1d6e56;--l2:#355e7d;--l3:#9a6a1f;--l4:#9a9387;}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}
a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}
h1{font-family:Georgia,"Times New Roman",serif;font-weight:600;font-size:34px;line-height:1.15;margin:.2em 0 .4em}
h2{font-family:Georgia,serif;font-weight:600;font-size:23px;margin:1.6em 0 .5em}
h3{font-size:16px;margin:.2em 0 .6em}
.muted{color:var(--muted)}
header.site{position:sticky;top:0;z-index:20;background:rgba(247,244,238,.95);backdrop-filter:blur(6px);border-bottom:1px solid var(--rule)}
.nav{display:flex;align-items:center;justify-content:space-between;height:62px}
.brand{display:flex;flex-direction:column;line-height:1.1}
.brand .b1{font-family:Georgia,serif;font-weight:600;font-size:19px;color:var(--ink)}
.brand .b2{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
nav a{margin-left:18px;font-size:14.5px;color:var(--ink)}
nav a.on{color:var(--accent);font-weight:600}
.getinv{display:inline-flex;align-items:center;gap:7px;margin-left:22px;background:#33485c;color:#fff;font-size:13.5px;font-weight:600;padding:8px 14px;border-radius:20px;text-decoration:none;white-space:nowrap;flex:0 0 auto;box-shadow:0 2px 8px rgba(29,39,51,.18);transition:background .2s,transform .2s}
.getinv:hover{background:#1d2733;text-decoration:none;transform:translateY(-1px)}
.getinv .gi-dot{width:8px;height:8px;border-radius:50%;background:#cdb98a;box-shadow:0 0 0 0 rgba(205,185,138,.6);animation:gipulse 2.4s ease-out infinite}
@keyframes gipulse{0%{box-shadow:0 0 0 0 rgba(205,185,138,.6)}70%{box-shadow:0 0 0 7px rgba(205,185,138,0)}100%{box-shadow:0 0 0 0 rgba(205,185,138,0)}}
@media(prefers-reduced-motion:reduce){.getinv .gi-dot{animation:none}}
@media(max-width:860px){.getinv{margin-left:10px;padding:7px 11px;font-size:12.5px}}
/* contribute page */
.cwrap{max-width:900px}
.chero{background:linear-gradient(135deg,#1d2733,#33485c);border-radius:18px;padding:30px 32px 28px;color:#f3efe6;position:relative;overflow:hidden;margin-top:10px}
.chero::after{content:"✦";position:absolute;right:10px;top:-30px;font-size:160px;opacity:.06}
.chero .kicker{color:#cdb98a}.chero h1{color:#fff;font-family:Georgia,serif;font-size:34px;margin:.1em 0 .3em;line-height:1.15}
.chero p{color:#dfe6ee;font-size:16px;line-height:1.6;max-width:70ch;margin:0}
.cgrid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:26px;margin-top:22px;align-items:start}
.cform{background:var(--card);border:1px solid var(--rule);border-radius:16px;padding:22px 24px}
.cform label{display:block;font-size:13px;font-weight:600;letter-spacing:.02em;color:#3c3833;margin:14px 0 6px}
.cform label:first-child{margin-top:0}
.cform input[type=text],.cform input[type=email],.cform textarea{width:100%;box-sizing:border-box;font:inherit;font-size:15px;padding:10px 12px;border:1px solid var(--rule);border-radius:9px;background:var(--paper);color:var(--ink)}
.cform input:focus,.cform textarea:focus{outline:none;border-color:#33485c;box-shadow:0 0 0 3px rgba(51,72,92,.15)}
.cform textarea{min-height:130px;resize:vertical}
.cform .opt-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.cform .ck{display:flex;gap:9px;align-items:flex-start;font-size:14px;font-weight:400;padding:9px 11px;border:1px solid var(--rule);border-radius:9px;background:var(--paper);cursor:pointer;margin:0;letter-spacing:0;line-height:1.4;color:var(--ink)}
.cform .ck:has(input:checked){border-color:#33485c;background:#eef2f5}
.cform .ck input{margin-top:3px;flex:0 0 auto}
.cform .ck small{display:block;color:var(--muted);font-size:12px;margin-top:1px}
.cform .hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
.cform .send{margin-top:18px;background:#33485c;color:#fff;font:inherit;font-weight:700;font-size:15px;padding:12px 20px;border:0;border-radius:10px;cursor:pointer}
.cform .send:hover{background:#1d2733}.cform .send:disabled{opacity:.6;cursor:default}
.cform .note{font-size:12.5px;color:var(--muted);margin:10px 0 0;line-height:1.5}
.cmain .done{display:none;background:#eef5f1;border:1px solid #cfe3d8;border-radius:12px;padding:18px 20px;font-size:15px;line-height:1.6}
.cmain .done h3{margin:0 0 6px;font-family:Georgia,serif;font-size:20px}
.cform .err{display:none;background:#fbf2dd;border:1px solid #e7d4ac;border-radius:10px;padding:12px 14px;font-size:14px;margin-top:12px;line-height:1.5}
.caside .box{background:var(--card);border:1px solid var(--rule);border-radius:14px;padding:18px 20px;margin-bottom:14px}
.caside h2{font-family:Georgia,serif;font-size:18px;margin:0 0 8px;border:0}
.caside p,.caside li{font-size:14px;line-height:1.6;color:#3c3833;margin:0 0 8px}
.caside ul{padding-left:18px;margin:0}
.caside .box.donate{border-left:4px solid #cdb98a}
@media(max-width:760px){.cgrid{grid-template-columns:1fr}.cform .opt-row{grid-template-columns:1fr}.chero h1{font-size:27px}}
footer.site{margin-top:60px;border-top:1px solid var(--rule);padding:26px 0;font-size:13.5px;color:var(--muted)}
footer.site p{margin:.3em 0}
/* footer download button (target: download.html) */
.fdl{margin-top:18px !important}
.dlbtn{display:inline-flex;align-items:baseline;gap:9px;flex-wrap:wrap;background:var(--card);border:1px solid #cdc4b1;border-radius:9px;padding:11px 18px;color:var(--ink);font-size:14.5px;font-weight:600;text-decoration:none}
.dlbtn:hover{background:#fff;border-color:#8a5a2b;text-decoration:none}
.dlbtn .dlarrow{font-weight:700;color:#8a5a2b}
.dlbtn small{font-weight:400;font-size:12.5px;color:var(--muted)}
@media(max-width:600px){.dlbtn{width:100%;justify-content:center;text-align:center}}
.hero{padding:30px 0 8px}
.heroimg{margin:26px 0 4px}
.heroimg img{width:100%;height:auto;display:block;border:1px solid var(--rule);border-radius:10px;filter:sepia(.18) contrast(1.02)}
.heroimg figcaption{font-size:13px;color:var(--muted);line-height:1.55;margin:9px 2px 0;max-width:76ch}
.kicker{font-size:12.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
.lede{font-size:18px;color:#3c3833;max-width:62ch}
.cta{margin:22px 0 6px;display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-block;padding:9px 16px;border:1px solid var(--rule);border-radius:8px;background:var(--card);color:var(--ink);font-size:14.5px;cursor:pointer}
.btn:hover{border-color:#cdc4b1;text-decoration:none}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.primary:hover{background:#683224}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:34px 0}
.tourpanel{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:0;margin:26px 0 8px;border-radius:18px;overflow:hidden;background:linear-gradient(135deg,#1d2733,#33485c);color:#f3efe6;text-decoration:none;box-shadow:0 18px 44px rgba(29,39,51,.22);transition:transform .35s cubic-bezier(.2,.8,.2,1),box-shadow .35s}
.tourpanel:hover{transform:translateY(-3px);box-shadow:0 26px 54px rgba(29,39,51,.3);text-decoration:none}
.tp-imgs{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:4px;align-content:center}
.tp-imgs img{width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;object-position:center top;display:block;border-radius:8px;filter:saturate(.9) contrast(1.02);transition:transform .8s ease}
.tourpanel:hover .tp-imgs img{transform:scale(1.04)}
.tp-text{padding:30px 32px 28px;display:flex;flex-direction:column;justify-content:center}
.tp-text .kicker{color:#cdb98a;margin:0 0 4px}
.tp-text h2{color:#fff;font-family:Georgia,serif;font-size:31px;margin:0 0 10px;line-height:1.15;border:0}
.tp-text p{color:#dfe6ee;font-size:15.5px;line-height:1.6;margin:0 0 18px}
.tp-btn{align-self:flex-start;background:#cdb98a;color:#26313d;font-weight:700;font-size:14.5px;padding:10px 18px;border-radius:9px}
.tourpanel:hover .tp-btn{background:#fff}
@media(max-width:760px){.tourpanel{grid-template-columns:1fr}.tp-imgs img:nth-child(n+3){display:none}.tp-imgs img{aspect-ratio:3/2}.tp-text{padding:22px 20px}.tp-text h2{font-size:25px}}
.stats div{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:16px}
.stats b{display:block;font-family:Georgia,serif;font-size:30px}
.stats span{font-size:13px;color:var(--muted)}
.tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px;margin:14px 0}
.tcard{display:block;background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:16px;color:var(--ink)}
.tcard:hover{border-color:#cdc4b1;text-decoration:none;transform:translateY(-1px)}
.tcard .ty{font-size:12.5px;color:var(--muted);margin-bottom:6px}
.tcard .tt{font-family:Georgia,serif;font-size:17px;line-height:1.25;margin-bottom:6px}
.tcard .de{font-style:italic;color:var(--muted);font-size:13.5px;margin:4px 0}
.tcard .tm{font-size:13.5px;color:#4a463f}
.tcard .meta{margin-top:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{display:inline-block;font-size:11.5px;padding:2px 9px;border-radius:20px;border:1px solid var(--rule);color:var(--muted);background:var(--paper)}
.badge.done{color:#1d6e56;border-color:#bcdccb;background:#edf7f1}
.badge.wip{color:#9a6a1f;border-color:#e7d4ac;background:#fbf2dd}
.badge.redis{color:#7a3b2e;border-color:#e6c6bb;background:#f8ebe6}
.badge.org{font-style:italic}
.badge.l1{color:#fff;background:var(--l1);border-color:var(--l1)}
.badge.l2{color:#fff;background:var(--l2);border-color:var(--l2)}
.badge.l3{color:#fff;background:var(--l3);border-color:var(--l3)}
.badge.l4{color:#fff;background:var(--l4);border-color:var(--l4)}
.how p{max-width:70ch}
/* filters + table */
.filters{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.filters input[type=search],.filters select{padding:8px 11px;border:1px solid var(--rule);border-radius:8px;background:var(--card);font-size:14px}
.filters #q{flex:1;min-width:220px}
.chk{display:flex;align-items:center;gap:6px;font-size:14px;color:#4a463f}
.tablewrap{border:1px solid var(--rule);border-radius:10px;background:var(--card)}
table#cat{border-collapse:collapse;width:100%;font-size:13.5px}
#cat th,#cat td{text-align:left;padding:8px 9px;border-bottom:1px solid var(--rule);vertical-align:top}
#cat th{position:sticky;top:62px;z-index:5;background:var(--card);font-size:12.5px;letter-spacing:.03em;text-transform:uppercase;color:var(--muted);cursor:default;box-shadow:0 1px 0 var(--rule)}
#cat td.num,#cat th.num{text-align:right}
#cat tr:hover td{background:#fbf8f2}
#cat tbody tr{cursor:pointer}
#cat .ti{font-weight:500}#cat .de{color:var(--muted);font-style:italic;font-size:13px}
#cat td.today{max-width:200px;min-width:150px}
#cat td:last-child{min-width:96px}
#cat td:nth-child(2){min-width:104px;max-width:160px}
#cat td:last-child{white-space:nowrap}
.cstat{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.02em;padding:2px 8px;border-radius:20px;text-decoration:none;white-space:nowrap}
.cstat:hover{text-decoration:none;filter:brightness(1.12)}
.cst-sb{background:#33485c;color:#f3efe6}.cst-qc{background:#2e6f6a;color:#fff}.cst-ll{background:#1d6e56;color:#fff}
.cst-st{background:#9a6a1f;color:#fff}.cst-cl{background:#8a3a3a;color:#fff}.cst-rr{background:#9a9387;color:#fff}
#cat .csbi{display:inline-block;font-size:10px;font-weight:700;color:#33485c;margin-left:4px}
#cat .cverd{font-size:11.5px;color:var(--muted);line-height:1.35;margin-top:3px}
.dosslink{font-weight:600;color:var(--accent2)}
/* search-term highlighting in result lists */
mark.hlt{background:#fde9a9;color:inherit;border-radius:3px;padding:0 1px;font-weight:600;box-decoration-break:clone;-webkit-box-decoration-break:clone}
#cat .cverd mark.hlt,.dcardx .ck mark.hlt{font-weight:600}
@media(prefers-contrast:more){mark.hlt{background:#ffd54a;outline:1px solid #a8801a}}
#cat tr.hit td{background:#fdf6e0;box-shadow:inset 3px 0 0 var(--accent2)}
.dscta{display:flex;gap:18px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:16px 0 6px;padding:15px 18px;border-radius:12px;background:linear-gradient(135deg,#1d2733,#33485c);color:#f3efe6;position:relative;overflow:hidden}
.dscta::after{content:"☾";position:absolute;right:6px;top:-34px;font-size:120px;opacity:.07}
.dsctatext{flex:1 1 460px;position:relative;z-index:2}
.dscta h2{font-family:Georgia,serif;font-size:19px;margin:0 0 5px;color:#fff;border:0}
.dscta p{font-size:13.8px;line-height:1.6;margin:0 0 10px;color:#dfe6ee;max-width:82ch}
.dscta p b{color:#cdb98a}
.dsctaleg{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:5px 14px}
.dsctaleg li{font-size:12px;color:#b9c6d3;line-height:1.5}
.dsctabtn{position:relative;z-index:2;flex:0 0 auto;background:#cdb98a;color:#26313d;font-weight:700;font-size:14px;padding:10px 18px;border-radius:9px;text-decoration:none;white-space:nowrap}
.dsctabtn:hover{background:#fff;text-decoration:none}
.badge.dverd{background:#33485c;color:#f3efe6;border-color:#33485c}
.dverdline{font-size:14px;line-height:1.55;margin:8px 0 0;padding:8px 12px;border-left:3px solid #33485c;background:#f4f1ea;border-radius:0 8px 8px 0;color:#3c3833}
.dverdline b{color:#33485c}
@media(max-width:680px){.dscta{flex-direction:column;align-items:flex-start}}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#d8cfbe;margin-right:5px;vertical-align:middle}
.dot.on{background:var(--accent)}
.rd{font-size:11px;color:var(--accent)}
/* legacy */
.legacy{display:flex;flex-direction:column;gap:10px}
.litem{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.litem .h{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.litem .ti{font-family:Georgia,serif;font-size:16px}
.litem .sub{font-size:13px;color:var(--muted);margin-top:3px}
.litem details{margin-top:8px}.litem summary{cursor:pointer;font-size:13.5px;color:var(--link)}
.litem .cites{margin:8px 0 0;padding-left:18px;font-size:13px}
.litem .cites li{margin:3px 0}
.kv{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:#4a463f;margin-top:6px}
td.meth{font-size:12.5px;color:#4a463f}
.mfull{color:var(--accent);font-size:9px;vertical-align:middle}
.methbox{border:1px solid var(--rule);border-radius:10px;background:var(--card);padding:14px 16px;margin:14px 0}
.methbox h3{margin:0 0 6px;font-size:15px}
.badge.mcl{background:#ece8f6;border-color:#d2c9ec;color:#4a3f72}
.mgrid{display:grid;grid-template-columns:130px 1fr;gap:5px 12px;margin:8px 0;font-size:13.5px}
.mgrid dt{color:var(--muted);font-weight:600}
.mgrid dd{margin:0;color:#3c3833}
.mfind{font-size:13.5px;margin:8px 0}
@media(max-width:600px){.mgrid{grid-template-columns:1fr}.mgrid dt{margin-top:6px}}
/* charts */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:14px}
.chart{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.chart canvas{max-height:280px}
.note{margin-top:18px}
/* reading */
.reading{padding-top:10px}
.reading .detitle{font-style:italic;color:var(--muted);font-size:18px;margin:-6px 0 8px}
.reading .byline{font-size:14px;color:#4a463f;margin:6px 0}
.reading .badges{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.actionbar{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 6px}
.notice{background:#fbf2dd;border:1px solid #e7d4ac;color:#7a5a1c;border-radius:8px;padding:10px 14px;font-size:14px;margin:12px 0}
/* reader-facing context note (sensitivity.json) — top of reading page + dossier */
.senswarn{background:#fbf6ef;border:1px solid #d9c7ae;border-left:5px solid #8a5a2b;border-radius:10px;padding:15px 20px 6px;margin:18px 0 6px;max-width:74ch;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.senswarn.sev-high{background:#fbf3ee;border-left-color:#8a3a3a;border-color:#dcc0b4}
.senswarn .sensh{margin:0 0 9px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#8a5a2b}
.senswarn.sev-high .sensh{color:#8a3a3a}
.senswarn .senscat{display:inline-block;background:#8a5a2b;color:#fbf6ef;border-radius:4px;padding:2px 8px;margin-right:9px;letter-spacing:.05em}
.senswarn.sev-high .senscat{background:#8a3a3a}
.senswarn p{margin:0 0 11px;font-size:14.5px;line-height:1.62;color:#3c3833}
@media(max-width:600px){.senswarn{padding:13px 15px 4px}.senswarn p{font-size:14px}}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:34px;margin-top:18px}
.text{font-family:Georgia,"Times New Roman",serif;font-size:17px;line-height:1.72;max-width:70ch}
.text h2{font-size:21px;margin-top:1.5em}.text h3{font-size:17px}
.text img{max-width:100%;height:auto;display:block;margin:14px auto;border:1px solid var(--rule);background:#fff;padding:4px}
.text table{border-collapse:collapse;margin:14px 0;font-size:14px;display:block;overflow-x:auto;max-width:100%;width:max-content}
.text th,.text td{border:1px solid var(--rule);padding:5px 9px}
.text blockquote{border-left:3px solid var(--rule);margin:14px 0;padding:4px 16px;color:#534e46;background:#fbf8f2}
.toc{align-self:start;position:static}
.text pre{overflow-x:auto;max-width:100%;background:#fbf8f2;border:1px solid var(--rule);border-radius:8px;padding:10px 12px;font-size:13px;line-height:1.45}
.tocbox{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:12px 14px;font-family:-apple-system,sans-serif;font-size:13.5px;margin-bottom:14px}
.tocbox p{margin:0 0 6px;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.tocbox a{display:block;padding:2px 0;color:#4a463f}
.legacypanel{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;font-family:-apple-system,sans-serif}
.legacypanel h2{font-family:-apple-system,sans-serif;font-size:14px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:0 0 10px}
.lstats{display:flex;gap:14px;margin-bottom:10px}
.lstats b{display:block;font-family:Georgia,serif;font-size:22px}
.lstats span{font-size:11.5px;color:var(--muted)}
.cites{font-size:13px;padding-left:16px}.cites li{margin:4px 0}
.connect{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;margin-top:14px;font-family:-apple-system,sans-serif}
.connect h2{font-family:-apple-system,sans-serif;font-size:14px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:0 0 6px}
.connect .ck{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);font-weight:600;margin:11px 0 5px}
.cnchip{display:inline-block;font-size:12.5px;border:1px solid var(--rule);border-radius:13px;padding:3px 10px;margin:0 4px 5px 0;background:var(--paper);color:var(--ink);line-height:1.3}
.cnchip:hover{border-color:#cdc4b1;text-decoration:none;background:#fff}
.cnredis{display:inline-block;font-size:13px;color:var(--accent);font-weight:600}
.cite{margin-top:24px;border-top:1px solid var(--rule);padding-top:12px;font-size:13px;color:var(--muted)}
.prose{max-width:72ch}.prose p{margin:.7em 0}
.rsingle iframe{width:100%;height:82vh;border:1px solid var(--rule);border-radius:8px;background:#fff}
.rpanes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.rpanes .rp{position:relative}
.rpanes iframe{width:100%;height:82vh;border:1px solid var(--rule);border-radius:8px;background:#fff}
.rlbl{position:absolute;top:6px;left:6px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:var(--paper);border:1px solid var(--rule);border-radius:6px;padding:2px 8px;z-index:2}
.layers{margin:8px 0 26px}
.laycards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:14px 0}
.laycard{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px}
.laycard b{display:block;margin:8px 0 4px;font-size:15px}
.laycard p{font-size:13.5px;color:#4a463f;margin:0}
/* where a paper stands (assessment) and how it is used today */
.stc{display:inline-block;font:600 11px/1.25 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;letter-spacing:.02em;padding:3px 10px;border-radius:20px;color:#fff;white-space:nowrap;text-decoration:none;vertical-align:1px}
a.stc:hover{text-decoration:none;filter:brightness(1.12)}
.stc-established{background:#1d6e56}.stc-consistent{background:#4f7a74}.stc-revised{background:#9a6a1f}
.stc-unresolved{background:#33485c}.stc-not_supported{background:#8a3a3a}.stc-no_claim{background:#9a9387}
.usec{display:inline-block;font:600 11px/1.25 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:2px 9px;border-radius:20px;border:1px solid #cfc7b6;color:#5b5446;background:var(--card);white-space:nowrap}
.usec-tested{border-color:#1d6e56;color:#1d6e56}.usec-precedent{border-color:#7d93a5;color:#34526a}
.usec-historians{border-color:#c2ab7c;color:#7a6437}.usec-none{color:#8a857c}
.oft{display:inline-block;font-size:11px;line-height:1.3;padding:2px 8px;border-radius:5px;background:#f1ece2;color:#5b5446;border:1px solid #e3dccd}
.oft-testable{background:#eef2f5;color:#2f3e4c;border-color:#d3dde6}.oft-data{background:#eef5f1;color:#1d5a47;border-color:#cfe2d8}
.oft-note{background:#f8ebe6;color:#7a3b2e;border-color:#e6c6bb}
.stlegend{margin:14px 0 8px;padding:11px 14px;background:var(--card);border:1px solid var(--rule);border-radius:10px}
.stlegend p{margin:0;font-size:13.5px;line-height:1.9;color:#3c3833}
#cat td.today .stc{margin-bottom:2px}
#cat td.num .usec{min-width:34px;text-align:center}
footer.site .disclaimer{font-size:12.5px;line-height:1.55;color:#6f6a61;border-left:3px solid #d8cfbe;padding:2px 0 2px 11px;margin:12px 0;max-width:100ch}
footer.site .disclaimer b{color:#4a463f}
@media(max-width:860px){.cols{grid-template-columns:1fr}.toc{position:static}.charts{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.rpanes{grid-template-columns:1fr}nav a{margin-left:12px}.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}#cat th{position:static}}
"""
    os.makedirs(os.path.join(SITE, "assets"), exist_ok=True)
    open(os.path.join(SITE, "assets", "style.css"), "w", encoding="utf-8").write(css)

def write_js():
    catalog_js = r"""
(function(){
var D=window.CATALOG||[],AS=window.ASSESS||{};
var q=document.getElementById('q'),phen=document.getElementById('phen'),method=document.getElementById('method'),
 stand=document.getElementById('stand'),use=document.getElementById('use'),offer=document.getElementById('offer'),
 sort=document.getElementById('sort'),tb=document.querySelector('#cat tbody'),count=document.getElementById('count');
var SL={established:'Established',consistent:'Consistent',revised:'Revised',unresolved:'Unresolved',not_supported:'Not supported',no_claim:'No claim'};
var SO={established:0,consistent:1,revised:2,unresolved:3,not_supported:4,no_claim:5};
var UL={tested:'Tested or used today',precedent:'Cited as a precedent',historians:'Cited by historians',none:'Not cited since 1990'};
function A(c){return AS[c.id]||null;}
function modern(c){var a=A(c);return a?(a[3][3]+a[3][4]):0;}
var ph={};D.forEach(function(c){(c.phenomena||[]).forEach(function(p){ph[p]=(ph[p]||0)+1})});
Object.keys(ph).sort().forEach(function(p){var o=document.createElement('option');o.value=p;o.textContent=p.replace(/_/g,' ')+' ('+ph[p]+')';phen.appendChild(o)});
var METH=window.METH||{};
var MLAB={"Regeneration & restitution":"Regeneration","Transplantation & grafting":"Transplantation","Endocrine & sex manipulation":"Endocrine/sex","Inheritance & breeding":"Inheritance","Colour change & pigment":"Colour change","Environmental modification":"Environment","Quantitative growth & biometry":"Growth/biometry","Developmental mechanics (egg/embryo)":"Dev. mechanics","Functional physiology & behaviour":"Physiology","Morphology, histology & biochemistry":"Morphology"};
function mcl(c){var m=METH[c.id];return m?(m.cluster||''):'';}
var ms={};D.forEach(function(c){var m=mcl(c);if(m)ms[m]=(ms[m]||0)+1;});
Object.keys(ms).sort().forEach(function(k){var o=document.createElement('option');o.value=k;o.textContent=(MLAB[k]||k)+' ('+ms[k]+')';method.appendChild(o);});
function esc(s){return (s||'').replace(/[&<>"]/g,function(m){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]})}
function hlEsc(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function hl(escaped,term){
  if(!term)return escaped;
  var t=String(term).trim(); if(t.length<2)return escaped;
  var parts=t.split(/\s+/).filter(function(x){return x.length>1;}).map(hlEsc);
  if(!parts.length)return escaped;
  var re=new RegExp('(?![^<]*>)(?![^&;]*;)('+parts.join('|')+')','gi');
  return escaped.replace(re,'<mark class="hlt">$1</mark>');
}
function row(c){
 var a=A(c),Q=(q.value||'').trim();
 var read=c.has_translation?('<a href="papers/'+c.slug+'.html"><span class="dot on"></span>English</a><br><a href="reader.html?id='+c.id+'">German</a>')
                           :('<a href="reader.html?id='+c.id+'">Read original</a>');
 var today='—',m=modern(c),cit='—';
 if(a){today='<a class="stc stc-'+a[0]+'" href="dossier/'+c.id+'.html">'+SL[a[0]]+'</a><div class="cverd">'+hl(esc(a[1]),Q)+'</div>';
   cit='<span class="usec usec-'+a[2]+'" title="'+UL[a[2]]+'">'+(m||'—')+'</span>';}
 return '<tr class="crow" data-id="'+c.id+'"><td>'+c.year+'</td><td>'+hl(esc(c.author).replace(/([\/;,])\s*/g,'$1​'),Q)+'</td>'+
 '<td><div class="ti">'+hl(esc(c.title_en||c.title),Q)+'</div>'+((c.title&&c.title!==c.title_en)?'<div class="de">('+hl(esc(c.title),Q)+')</div>':'')+'</td>'+
 '<td><em>'+hl(esc(c.organism),Q)+'</em></td>'+
 '<td class="meth">'+esc(MLAB[mcl(c)]||mcl(c)||'—')+'</td>'+
 '<td class="today">'+today+'</td><td class="num">'+cit+'</td><td>'+read+'</td></tr>';
}
function apply(){
 var t=(q.value||'').toLowerCase(),P=phen.value,M=method.value,S=stand.value,U=use.value,O=offer.value;
 var r=D.filter(function(c){
  var a=A(c);
  if(P&&(c.phenomena||[]).indexOf(P)<0)return false;
  if(M&&mcl(c)!==M)return false;
  if(S&&(!a||a[0]!==S))return false;
  if(U&&(!a||a[2]!==U))return false;
  if(O&&(!a||a[4].indexOf(O)<0))return false;
  if(t){var hay=(c.author+' '+(c.author_full||'')+' '+c.title+' '+(c.title_en||'')+' '+(c.organism||'')+' '+(a?a[1]:'')).toLowerCase();if(hay.indexOf(t)<0)return false;}
  return true;});
 var s=sort.value;
 r.sort(function(a,b){
  if(s==='year')return a.year-b.year||a.id-b.id;
  if(s==='-year')return b.year-a.year||a.id-b.id;
  if(s==='-mod')return modern(b)-modern(a)||a.year-b.year;
  if(s==='-cit')return (b.citations||0)-(a.citations||0);
  if(s==='stand'){var x=A(a),y=A(b);return ((x?SO[x[0]]:9)-(y?SO[y[0]]:9))||a.year-b.year;}
  if(s==='author')return a.author.localeCompare(b.author);
  if(s==='method')return (mcl(a)||'~').localeCompare(mcl(b)||'~')||a.year-b.year;
  return 0;});
 tb.innerHTML=r.map(row).join('');
 count.textContent=r.length+' of '+D.length+' papers';
}
[q,phen,method,sort].forEach(function(e){e.addEventListener('input',apply)});
[stand,use,offer].forEach(function(e){e.addEventListener('change',apply)});
tb.addEventListener('click',function(e){if(e.target.closest('a'))return;var tr=e.target.closest('tr');if(tr&&tr.dataset.id)location.href='dossier/'+tr.dataset.id+'.html';});
apply();
// deep link from Discover / a dossier: catalog.html?id=N — scroll to the row and flag it
(function(){
 var pid=new URLSearchParams(location.search).get('id');
 if(!pid)return;
 var tr=tb.querySelector('tr[data-id="'+pid+'"]');
 if(!tr)return;
 tr.classList.add('hit');
 tr.scrollIntoView({block:'center'});
})();
})();
"""
    analytics_js = r"""
(function(){
var D=window.CATALOG||[],AS=window.ASSESS||{};
var mut='#6f6a61',grid='#e4ddce';
Chart.defaults.font.family='-apple-system,Segoe UI,Roboto,sans-serif';Chart.defaults.color=mut;
function years(){var m={};D.forEach(function(c){m[c.year]=(m[c.year]||0)+1});
 var ys=[];for(var y=1902;y<=1945;y++)ys.push(y);return{labels:ys,data:ys.map(function(y){return m[y]||0})};}
var yr=years();
new Chart(cYear,{type:'bar',data:{labels:yr.labels,datasets:[{data:yr.data,backgroundColor:'#7a3b2e'}]},
 options:{plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:12}},y:{grid:{color:grid},ticks:{precision:0}}}}});
var ids=Object.keys(AS);
var SK=['established','consistent','revised','unresolved','not_supported','no_claim'];
var sc={};ids.forEach(function(k){sc[AS[k][0]]=(sc[AS[k][0]]||0)+1;});
new Chart(cStand,{type:'doughnut',data:{labels:['Established','Consistent with current knowledge','Revised','Unresolved','Not supported','No claim to assess'],
 datasets:[{data:SK.map(function(k){return sc[k]||0}),backgroundColor:['#1d6e56','#4f7a74','#9a6a1f','#33485c','#8a3a3a','#b8b1a4']}]},
 options:{plugins:{legend:{position:'right'}}}});
var e=[0,0,0,0,0];ids.forEach(function(k){var c=AS[k][3];e[0]+=c[1];e[1]+=c[0]-c[1];e[2]+=c[2];e[3]+=c[3];e[4]+=c[4];});
new Chart(cEra,{type:'bar',data:{labels:['By 1945 · authors in this corpus','By 1945 · others','1946–1989','Since 1990 · science','Since 1990 · history of science'],
 datasets:[{data:e,backgroundColor:['#b9a57a','#d8c9a3','#9fb1c0','#355e7d','#9a9387']}]},
 options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{grid:{color:grid},ticks:{precision:0}},y:{grid:{display:false}}}}});
var UK=['tested','precedent','historians','none'];
var uc={};ids.forEach(function(k){uc[AS[k][2]]=(uc[AS[k][2]]||0)+1;});
new Chart(cUse,{type:'bar',data:{labels:['Tested or used today','Cited as a precedent','Cited by historians','Not cited since 1990'],
 datasets:[{data:UK.map(function(k){return uc[k]||0}),backgroundColor:['#1d6e56','#355e7d','#b9a57a','#d8cfbe']}]},
 options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{grid:{color:grid},ticks:{precision:0}},y:{grid:{display:false}}}}});
var am={};D.forEach(function(c){am[c.author]=(am[c.author]||0)+1});
var top=Object.keys(am).map(function(k){return[k,am[k]]}).sort(function(a,b){return b[1]-a[1]}).slice(0,12);
new Chart(cAuth,{type:'bar',data:{labels:top.map(function(x){return x[0]}),datasets:[{data:top.map(function(x){return x[1]}),backgroundColor:'#355e7d'}]},
 options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{grid:{color:grid},ticks:{precision:0}},y:{grid:{display:false}}}}});
var cc=D.filter(function(c){return AS[c.id]&&AS[c.id][3][3]>0;}).sort(function(a,b){return AS[b.id][3][3]-AS[a.id][3][3]}).slice(0,12);
new Chart(cCit,{type:'bar',data:{labels:cc.map(function(c){return c.author+' '+c.year}),datasets:[{data:cc.map(function(c){return AS[c.id][3][3]}),backgroundColor:'#355e7d'}]},
 options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{afterLabel:function(i){return (cc[i.dataIndex].title_en||cc[i.dataIndex].title||'').slice(0,70)}}}},scales:{x:{grid:{color:grid},ticks:{precision:0}},y:{grid:{display:false}}}}});
})();
"""
    reader_js = r"""
(function(){
var P=new URLSearchParams(location.search), id=parseInt(P.get('id'),10), sxs=P.get('sxs')==='1';
var C=(window.CATALOG||[]).filter(function(c){return c.id===id})[0];
var head=document.getElementById('rhead'), view=document.getElementById('rview');
if(!C){document.getElementById('rmiss').style.display='block';return;}
function esc(s){return (s||'').replace(/[&<>"]/g,function(m){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]})}
var pdf='pdfs/'+encodeURIComponent(C.pdf||'');
document.title=(C.author+' '+C.year)+' · Vienna Vivarium';
var en=C.has_translation?('papers/'+C.slug+'.html'):null;
var doi=C.doi?('<a href="https://doi.org/'+C.doi+'" target="_blank">'+C.doi+'</a>'):'';
var acts='<a class="btn primary" href="'+pdf+'" download>↓ Download PDF</a>';
if(en){acts+='<a class="btn" href="'+en+'">Read English translation</a>';
 acts+= sxs?('<a class="btn" href="reader.html?id='+id+'">Single view</a>')
          :('<a class="btn" href="reader.html?id='+id+'&sxs=1">⇆ Side-by-side English</a>');}
if((window.ASSESS||{})[id])acts+='<a class="btn" href="dossier/'+id+'.html">Where it stands today</a>';
if(doi)acts+='<a class="btn" href="https://doi.org/'+C.doi+'" target="_blank">DOI ↗</a>';
var ttl=C.title_en||C.title;
head.innerHTML='<p class="kicker"><a href="catalog.html">Catalog</a> · BVA · '+C.year+'</p>'+
 '<h1 style="margin-bottom:4px">'+esc(ttl)+'</h1>'+
 ((C.title&&C.title!==C.title_en)?'<p class="detitle" style="font-style:italic;color:var(--muted);margin:0 0 6px">('+esc(C.title)+')</p>':'')+
 '<p class="byline">'+esc(C.author_full||C.author)+' · '+C.year+(doi?' · DOI '+doi:'')+(C.organism?' · <em>'+esc(C.organism)+'</em>':'')+'</p>'+
 '<div class="actionbar">'+acts+'</div>';
if(sxs&&en){
 view.innerHTML='<div class="rpanes"><div class="rp"><span class="rlbl">German original</span><iframe src="'+pdf+'#view=FitH" title="German original PDF"></iframe></div>'+
  '<div class="rp"><span class="rlbl">English translation</span><iframe src="'+en+'" title="English translation"></iframe></div></div>';
}else{
 view.innerHTML='<div class="rsingle"><iframe src="'+pdf+'#view=FitH" title="German original PDF"></iframe></div>';
}
})();
"""
    a = os.path.join(SITE, "assets")
    open(os.path.join(a, "catalog.js"), "w").write(catalog_js)
    open(os.path.join(a, "analytics.js"), "w").write(analytics_js)
    open(os.path.join(a, "reader.js"), "w").write(reader_js)

def main():
    os.makedirs(DATA, exist_ok=True)
    write_css(); write_js()
    open(os.path.join(DATA, "site.js"), "w").write("window.SITE=" + json.dumps({"fullPdfs": FULL}) + ";")
    open(os.path.join(SITE, ".nojekyll"), "w").write("")
    gen_index(); gen_catalog(); gen_translations(); gen_legacy(); gen_analytics(); gen_about(); gen_reader(); gen_contribute(); gen_download()
    gen_citations(); gen_methodology(); gen_discover(); gen_dossier(); gen_authors(); gen_reading_pages(); copy_assets()
    gen_tour()  # after copy_assets: it thumbnails figures/portraits that copy_assets puts in place
    print("Generated site at", SITE, "| FULL_PDFS =", FULL)
    print("pages:", sorted(os.path.basename(p) for p in glob.glob(os.path.join(SITE, "*.html"))))
    print("reading pages:", len(glob.glob(os.path.join(SITE, "papers", "*.html"))))
    print("figures:", len(glob.glob(os.path.join(SITE, "figures", "*", "*"))))
    print("pdfs:", len(glob.glob(os.path.join(SITE, "pdfs", "*.pdf"))))

if __name__ == "__main__":
    main()
