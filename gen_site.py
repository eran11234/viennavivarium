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
               "The catalog, the guided tour, the Discover hub and all 172 dossiers",
               "497 figure and plate scans"],
         how="Unzip and open <code>index.html</code>. Nothing to install, no server needed.",
         who="Best if you want to read, browse or keep the corpus."),
    dict(key="data", size="~8 MB", primary=False,
         href=REL_BASE + "viennavivarium-research-bundle.zip",
         name="Research bundle",
         lede="Every text and every data file, without the scans.",
         what=["All 175 translations as Markdown",
               "<code>catalog.csv</code> — one row per paper, with verdicts, citations and links",
               "The full working data: verdicts, citations, methodology, syntheses, biographies",
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
<p class="fdl"><a class="dlbtn" href="{prefix}download.html"><span class="dlarrow">&darr;</span> Download the whole corpus<small>translations, German originals and all the data — {SNAPSHOT_DATE}</small></a></p>
</div></footer>{foot}</body></html>"""
    with open(os.path.join(SITE, path), "w", encoding="utf-8") as f:
        f.write(doc)

def layer_badge(n):
    if not n: return '<span class="badge l0">unranked</span>'
    return f'<span class="badge l{n}">legacy layer {n}</span>'

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
    # live counts for the stats strip: curated people on the Authors page, and the
    # strict sleeping-beauty set from the Discover re-evaluation
    _ap = os.path.join(ROOT, "legacy_data", "authors.json")
    n_people = len(json.load(open(_ap, encoding="utf-8"))["people"]) if os.path.exists(_ap) else STATS["authors"]
    _cp = os.path.join(ROOT, "legacy_data", "consensus_all.json")
    _CA = json.load(open(_cp, encoding="utf-8")) if os.path.exists(_cp) else {}
    n_sleep = sum(1 for v in _CA.values() if v.get("sleeping"))
    n_confirmed = sum(1 for v in _CA.values() if v.get("status") in ("Sleeping Beauty", "Quiet Classic", "Living Legacy"))
    # four programme covers for the featured panel (gen_tour writes assets/tree/prog-<id>-c.jpg later in the build)
    tour_imgs = "".join('<img src="assets/tree/prog-%s-c.jpg" alt="" loading="lazy">' % i
                        for i in ("regen", "colour", "graft", "heredity"))
    body = f"""
<section class="hero">
  <p class="kicker">An orientation platform for researchers</p>
  <h1>The Vienna Vivarium, in English</h1>
  <p class="lede">The Biologische Versuchsanstalt (1902–1945) was one of the first institutes for experimental biology. This platform opens the complete published output of its zoological department to English-language researchers: a searchable catalog of <strong>{STATS['papers']} papers</strong> ({STATS['y0']}–{STATS['y1']}), full English <strong>translations</strong> with figures, the German originals — and every paper <strong>read against today's science</strong>, to show which of these forgotten results the field has since rediscovered.</p>
  <div class="cta">
    <a class="btn primary" href="catalog.html">Browse the catalog</a>
    <a class="btn" href="translations.html">Read translations</a>
    <a class="btn" href="rediscovery.html">☾ Discover what held up</a>
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
  <div><b>{n_confirmed}</b><span>results confirmed by today's science</span></div>
  <div><b>{n_sleep}</b><span>sleeping beauties</span></div>
</section>
<section>
  <h2>Featured translations</h2>
  <div class="tgrid">{feat}</div>
</section>
<section class="how">
  <h2>How to use this platform</h2>
  <p>The <a href="catalog.html">Catalog</a> is the map of the whole corpus — filter by author, organism, phenomenon, method, or today's verdict, and jump to a paper's English translation (where one exists) or its German original. The <a href="translations.html">Translations</a> are full reading pages with the original plates and a side-by-side view against the scanned German. <a href="rediscovery.html">Discover</a> sets every paper against the current literature: which results became textbook science, which are still contested, and which <em>sleeping beauties</em> the field has rediscovered without ever citing them. <a href="authors.html">Authors</a> gives the people behind the papers, the <a href="tour.html">Tour</a> walks from six big questions down to the papers, and <a href="analytics.html">Analytics</a> shows the shape of the institute's output over its four decades.</p>
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
    for _old, _pid in _pub.items():
        if _pid in _now and _old != _now[_pid] and _old not in _moved:
            _moved[_old] = _now[_pid]
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
<p class="lede">All papers in the corpus. Search and filter; <strong>click any row to see the modern works that cite it</strong>, or use the Read column to open the translation or German original.</p>
<section class="dscta">
  <div class="dsctatext">
    <h2>☾ Every paper, judged against today's science</h2>
    <p>The <b>Today</b> column carries each paper's verdict from <b>Discover</b>, where all 174 were read against the current literature and placed on two axes — how much modern science <em>remembers</em> them, and whether their ideas <em>held up</em>. Click any chip or <b>☾ Dossier</b> to open that paper's full dossier.</p>
    <ul class="dsctaleg">
      <li><span class="cstat cst-sb">Sleeping Beauty</span> forgotten, yet confirmed</li>
      <li><span class="cstat cst-qc">Quiet Classic</span> lightly cited, but vindicated</li>
      <li><span class="cstat cst-ll">Living Legacy</span> well cited, and it held up</li>
      <li><span class="cstat cst-st">Stirring</span> alive but unsettled</li>
      <li><span class="cstat cst-cl">Contested Legacy</span> famous, but refuted</li>
      <li><span class="cstat cst-rr">Rightly Rested</span> forgotten, and it did not hold</li>
    </ul>
  </div>
  <a class="dsctabtn" href="rediscovery.html">Open Discover →</a>
</section>
<div class="filters">
  <input id="q" type="search" placeholder="Search author, title, organism…">
  <select id="layer"><option value="">Any legacy layer</option><option>1</option><option>2</option><option>3</option><option>4</option></select>
  <select id="phen"><option value="">Any phenomenon</option></select>
  <select id="method"><option value="">Any method</option></select>
  <select id="status"><option value="">Any verdict today</option>
    <option>Sleeping Beauty</option><option>Quiet Classic</option><option>Living Legacy</option>
    <option>Stirring</option><option>Contested Legacy</option><option>Rightly Rested</option></select>
  <label class="chk"><input type="checkbox" id="tonly"> Translated only</label>
  <label class="chk"><input type="checkbox" id="ronly"> ☾ Sleeping beauties</label>
  <select id="sort"><option value="year">Sort: year ↑</option><option value="-year">year ↓</option><option value="-cit">most cited</option><option value="-sbi">sleeping-beauty index</option><option value="author">author</option><option value="method">method</option></select>
</div>
<p id="count" class="muted"></p>
<div class="tablewrap"><table id="cat"><thead><tr>
<th>Year</th><th>Author</th><th>Title</th><th>Organism</th><th>Method</th><th>Legacy</th><th class="num">Cited</th><th>Today</th><th>Read</th>
</tr></thead><tbody></tbody></table></div>
"""
    page("catalog.html", "Catalog", "Catalog", body,
         foot='<script src="data/site.js"></script><script src="data/methodology.js"></script><script src="data/catalog.js"></script><script src="data/discidx.js"></script><script src="assets/catalog.js"></script>')

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
    body = """
<h1>Legacy explorer</h1>
<p class="lede">For each paper: who cites it in modern science, and whether its organism is still actively studied. <strong>Rediscovery targets</strong> are papers whose organism is alive in today's literature but whose original BVA work goes uncited — candidates for renewed attention.</p>
<p class="muted" style="font-size:13px;line-height:1.55;border-left:3px solid var(--rule);padding:2px 0 2px 12px;margin:0 0 14px">The short note beside each citing work describes the <em>likely</em> reason it cites the BVA original, reconstructed from that work's title, topic and (where available) abstract — not from the citing sentence itself, which is seldom digitised for this 1900–1940 literature. Read the notes as orientation; follow each DOI for the primary source.</p>

<section class="layers">
  <h2>What the four legacy layers mean</h2>
  <p>Every paper is graded by how deeply modern science still engages its actual work — judged from the present-day papers that cite it, with purely historical mentions set aside. The depth runs from the same organism still under study down to nothing but the bare logic of experiment surviving.</p>
  <div class="laycards">
    <div class="laycard"><span class="badge l1">Layer 1</span><b>Same genus, still studied</b><p>Modern work still studies the very genus the BVA paper worked on — the deepest continuity. <span class="muted">22 papers · 13%</span></p></div>
    <div class="laycard"><span class="badge l2">Layer 2</span><b>Same taxon, different genus</b><p>The technique or question travelled to a related animal: the same broad group (amphibians, beetles, crustaceans, mammals) but a different genus. The BVA's best-cited work lives here. <span class="muted">70 papers · 40%</span></p></div>
    <div class="laycard"><span class="badge l3">Layer 3</span><b>Same phenomenon, unrelated organism</b><p>Modern work pursues the same phenomenon — regeneration, transplantation, colour change, inheritance, sex determination — but in an unrelated organism. <span class="muted">37 papers · 21%</span></p></div>
    <div class="laycard"><span class="badge l4">Layer 4</span><b>Only the experimental logic survives</b><p>Engagement exists, but shares only the abstract form of “perturb and observe,” not the species, taxon, or phenomenon. <span class="muted">41 papers · 23%</span></p></div>
  </div>
  <p class="muted">A further 5 papers have no indexed modern citations at all. Depth is judged from OpenAlex citation data, excluding history-of-science (“historiographic”) mentions.</p>
</section>

<div class="filters">
  <input id="q" type="search" placeholder="Search author, title, organism…">
  <select id="conv"><option value="">Any convergence axis</option></select>
  <select id="layer"><option value="">Any legacy layer</option><option>1</option><option>2</option><option>3</option><option>4</option></select>
  <label class="chk"><input type="checkbox" id="ronly" checked> Rediscovery targets only</label>
</div>
<p id="count" class="muted"></p>
<div id="list" class="legacy"></div>
"""
    page("legacy.html", "Legacy", "Legacy", body,
         foot='<script src="data/catalog.js"></script><script src="data/legacy.js"></script><script src="data/citations.js"></script><script src="data/notes.js"></script><script src="data/summaries.js"></script><script src="data/methodology.js"></script><script src="data/discidx.js"></script><script src="assets/legacy.js"></script>')

# ---------------------------------------------------------------- analytics
def gen_analytics():
    body = """
<h1>Analytics</h1>
<p class="lede">The shape of the institute's output, and how it lands in modern science.</p>
<div class="charts">
  <div class="chart"><h3>Publications per year</h3><canvas id="cYear"></canvas></div>
  <div class="chart"><h3>Legacy-layer distribution</h3><canvas id="cLayer"></canvas></div>
  <div class="chart"><h3>Most prolific authors</h3><canvas id="cAuth"></canvas></div>
  <div class="chart"><h3>Most-cited papers today</h3><canvas id="cCit"></canvas></div>
</div>
<p class="note muted">Legacy layers run from 1 (modern work still engages the same genus) to 4 (only the abstract logic of experiment survives) — see the <a href="legacy.html">Legacy</a> page for full definitions. Citation counts via OpenAlex.</p>
"""
    page("analytics.html", "Analytics", "Analytics", body,
         head='<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>',
         foot='<script src="data/catalog.js"></script><script src="assets/analytics.js"></script>')

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
<p>It is an orientation layer for researchers who do not read German. It assembles, in one place: a searchable <strong>catalog</strong> of the series; full English <strong>translations</strong> with the original figures ({STATS['trans']} of {STATS['papers']}); the scanned German <strong>originals</strong>; the people behind the papers; and, on <strong>Discover</strong>, every paper read against the current literature — a summary of the state of the art, a verdict on whether the paper's claim held up, the modern works that actually cite it, and a ranked search for <em>sleeping beauties</em>: results the field has since confirmed without ever citing their Viennese origin.</p>
<h2>How the translations were made</h2>
<p>Each German paper was OCR-corrected against the scanned source and translated in full, preserving numbered points, tables, and figure legends. Historical species names are kept as in the original, with modern equivalents noted (e.g. <em>Triton</em> → <em>Triturus</em>). Where an author's claims were later disputed — Kammerer's above all — the translation renders them exactly as stated, and says so; it reports the claims, it does not endorse them.</p>
<p><strong>On the plates.</strong> Text figures and plates are reproduced wherever they are present in the scanned original. In many cases they are not: the journal's lithographic plates were bound separately from the article offprints, so a paper's scan often ends with the plate <em>legends</em> but without the plates themselves. Those points are marked <em>“figure not reproduced”</em> in the running text, and the legends are always translated, so it is clear what is missing and where. Kammerer's 1909 monograph is the largest such case — its Plates XVI and XVII are absent from the source scan.</p>
<h2>How to cite</h2>
<p>Cite the original publication, noting the English translation and this platform as the access point, e.g.: <em>Author (Year), “Original German title,” Archiv für Entwicklungsmechanik …; English translation, Vienna Vivarium in English.</em></p>
<h2>Sources, data &amp; limits</h2>
<p>Citation data (who cites each paper today) derive from <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a>. The modern literature on each paper's questions was retrieved once, at build time, from the <a href="https://consensus.app" target="_blank" rel="noopener">Consensus</a> API (June 2026); the state-of-the-art summaries, verdicts and sleeping-beauty index were written and computed from that retrieval and are a research aid, not a settled historiographic judgment. Portraits on the Authors page are public-domain images via Wikimedia Commons, credited in place. Corpus metadata, legacy layers and convergence axes are part of the project's ongoing analysis and should be treated as scholarly working material; corrections, collaborations and contributions are welcome — <a href="contribute.html">get involved</a>.</p>
</div>"""
    page("about.html", "About", "About", body)

# ---------------------------------------------------------------- get involved
def gen_contribute():
    """The always-reachable 'Get involved' page: an on-site form posting to Formspree
    (FORM_ENDPOINT); until that is configured it falls back to the visitor's mail client."""
    ways = [
        ("collab", "Research collaboration", "historians, biologists or philosophers of science who want to work with the corpus, co-author, or build on the Discover verdicts"),
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
    <li><b>Modern citations we missed.</b> If a paper here is cited or used in work we haven't found, tell us — the verdicts on Discover depend on it.</li>
    <li><b>The people.</b> Many of the {len(json.load(open(os.path.join(ROOT, "legacy_data", "authors.json"), encoding="utf-8"))["people"])} authors have only a line of biography. Dates, places, photographs, descendants.</li>
    <li><b>Translation checks.</b> Every rendering was made carefully, but a second German reader on any paper is welcome.</li>
    <li><b>Collaboration.</b> The corpus, the verdicts and the citation data are open to joint research.</li>
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
         foot='<script src="data/catalog.js"></script><script src="data/discidx.js"></script><script src="assets/reader.js"></script>')

# ---------------------------------------------------------------- legacy map
REDISC_CSS = r"""
.rstats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:22px 0 8px}
.rstats div{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:13px 14px}
.rstats b{display:block;font-family:Georgia,serif;font-size:27px;line-height:1}
.rstats span{font-size:12px;color:var(--muted)}
.qbanner{display:flex;gap:12px;align-items:flex-start;background:#f1ece1;border:1px solid var(--rule);border-left:4px solid var(--accent2);border-radius:10px;padding:12px 15px;margin:14px 0;font-size:14px;line-height:1.5}
.qbanner .qi{font-size:21px;color:var(--accent2);line-height:1}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:20px 0 6px}
.chip{border:1px solid var(--rule);background:var(--card);border-radius:20px;padding:6px 13px;font-size:13.5px;color:var(--ink);cursor:pointer}
.chip:hover{border-color:#cdc4b1}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.zchk{display:inline-flex;align-items:center;gap:7px;font-size:13.5px;color:var(--muted);margin:4px 0 10px;cursor:pointer}
.gsec{margin:26px 0 8px}
.ghead{border-bottom:2px solid var(--rule);padding-bottom:8px;margin-bottom:14px}
.ghead h2{margin:.1em 0 .15em}
.gmod{font-size:12.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
.gblurb{font-size:14.5px;color:#46423b;max-width:74ch;margin:0}
.dcard{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:16px 17px;margin:12px 0}
.dcard.flash{box-shadow:0 0 0 3px rgba(122,59,46,.4);transition:box-shadow .3s}
.dc-h{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}
.dc-h h3{font-family:Georgia,serif;font-size:18px;line-height:1.25;margin:0 0 3px}
.dc-de{font-style:italic;color:var(--muted);font-size:12.5px;margin:1px 0 4px}
.dc-meta{font-size:13.5px;color:var(--muted);margin:0}
.dc-meta .now{color:var(--accent2)}
.dc-badges{display:flex;flex-direction:column;gap:5px;align-items:flex-end;flex-shrink:0;text-align:right}
.lb{font-size:11px;padding:2px 7px;border-radius:5px;color:#fff;white-space:nowrap}
.lb.l1{background:var(--l1)}.lb.l2{background:var(--l2)}.lb.l3{background:var(--l3)}.lb.l4{background:var(--l4)}
.clab{font-size:11px;color:var(--muted);max-width:150px}
.gap{margin:12px 0 10px}
.gapbar{height:7px;background:#ece6da;border-radius:4px;overflow:hidden}
.gapbar span{display:block;height:100%;background:linear-gradient(90deg,#9a6a1f,#7a3b2e)}
.gaptxt{font-size:13px;color:#46423b;margin:6px 0 0}
.gaptxt b{font-family:Georgia,serif}.gaptxt b.z{color:var(--accent)}
.ztag{color:var(--accent);font-weight:600;font-size:12px}
.dcard.zero{border-color:#d9b8ac;background:#fdf6f3}
.whatsnew{font-size:14.5px;line-height:1.55;margin:10px 0 0}
.openend{font-size:14px;line-height:1.55;margin:10px 0 0;background:#f3efe6;border-radius:8px;padding:9px 12px}
.citetag{display:inline-block;margin-left:8px;font-size:10.5px;letter-spacing:.04em;text-transform:uppercase;font-weight:600;padding:1px 7px;border-radius:10px;white-space:nowrap;vertical-align:middle}
.citetag.wake{background:#1d6e56;color:#fff}
.citetag.dorm{background:#e6ddcb;color:#6f6a61}
.citesumm{font-size:13.5px;line-height:1.55;margin:8px 0 0;background:#eef2f5;border-left:3px solid var(--accent2);border-radius:6px;padding:8px 12px}
.citesumm .lab{color:var(--accent2)}
.lab{display:inline-block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-right:7px}
.openend .lab{color:var(--accent2)}
.dc-links{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:13px}
.tlink{font-size:13px;border:1px solid var(--rule);border-radius:7px;padding:5px 10px;background:var(--paper);color:var(--ink)}
.tlink:hover{border-color:#cdc4b1;text-decoration:none}
.qedbtn{font-size:13px;border:1px solid var(--accent2);color:#fff;background:var(--accent2);border-radius:7px;padding:5px 11px;cursor:pointer;text-decoration:none;display:inline-block}
a.qedbtn{margin-left:6px}
.dc-links .qedbtn.ghost{margin-left:auto}
.qedbtn:hover{background:#2b4d68;text-decoration:none}
.qedbtn.ghost{background:transparent;color:var(--accent2)}
.qedbtn.ghost:hover{background:#eef2f5}
.qedout{display:none;margin-top:11px;font-size:13.5px;line-height:1.5;border-left:3px solid var(--accent2);padding:9px 12px;background:#eef2f5;border-radius:6px}
.qpend b{color:var(--accent2)}
.cons .consq{margin:0 0 2px;font-size:13.5px}
.cons .consmeta{margin:0 0 10px;font-size:12px;color:var(--muted);font-weight:600;letter-spacing:.02em}
.conspaper{padding:8px 0;border-top:1px solid #dde4ea}
.conspaper:first-of-type{border-top:0}
.conslink{font-weight:600;font-size:13.5px;line-height:1.35;display:inline-block}
.consmeta2{font-size:11.5px;color:var(--muted);margin:2px 0 3px}
.ptag{display:inline-block;background:#fff;border:1px solid var(--rule);border-radius:5px;padding:0 6px;margin-left:5px;font-size:10.5px;text-transform:capitalize}
.constake{margin:3px 0 0;font-size:13px;line-height:1.5;color:#2f2c28}
.consfoot{margin:9px 0 0;font-size:11.5px;color:var(--muted);font-style:italic}
.ubh{margin-top:40px}
.ubintro{max-width:74ch}
.ubcard{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:17px 18px;margin:13px 0}
.ubcard h3{font-family:Georgia,serif;font-size:19px;margin:0 0 6px}
.ubq{font-size:15px;color:#3c3833;font-weight:500;margin:0 0 10px}
.ubquote{margin:0;border-left:3px solid var(--accent);padding:4px 0 4px 14px;font-style:italic;color:#46423b;font-size:14px}
.ubquote cite{display:block;font-style:normal;font-size:12px;color:var(--muted);margin-top:6px}
.ubquote .conf{color:#9a6a1f}
.ubquote .de{display:none;margin-top:8px;color:#5a554c}
.degerman{display:inline-block;margin-left:8px;font-size:11px;border:1px solid var(--rule);border-radius:5px;background:var(--paper);color:var(--muted);padding:1px 7px;cursor:pointer;font-style:normal}
.ubmod{font-size:14px;line-height:1.55;margin:11px 0 0}
.ublinks{font-size:13px;color:var(--muted);margin:10px 0 0}
.pchip{display:inline-block;border:1px solid var(--rule);border-radius:14px;padding:2px 9px;margin:2px 3px 0 0;font-size:12.5px;background:var(--paper)}
.obit{font-size:13px;border-top:1px solid var(--rule);margin-top:30px;padding-top:14px}
@media(max-width:680px){.rstats{grid-template-columns:repeat(2,1fr)}.dc-h{flex-direction:column}.dc-badges{flex-direction:row;align-items:flex-start;text-align:left}.qedbtn{margin-left:0}}
"""

REDISC_JS = r"""
(function(){
var R=window.REDISCOVERY, MG=R.stats.maxgap||63;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

function links(c){var L=[];
  if(c.read)L.push('<a class="tlink" href="'+c.read+'">Read translation</a>');
  if(c.pdf)L.push('<a class="tlink" href="pdfs/'+encodeURIComponent(c.pdf)+'" download>German PDF</a>');
  L.push('<a class="tlink" href="legacy.html">Who cites it ↗</a>');
  if(c.doi)L.push('<a class="tlink" href="https://doi.org/'+c.doi+'" target="_blank" rel="noopener">DOI ↗</a>');
  return L.join('');}
function cardHTML(pid){var c=R.cards[pid]; if(!c)return '';
  var pct=Math.max(4,Math.round(c.gap/MG*100)), zero=c.citations===0;
  var now=(c.modern&&c.modern!=='—'&&c.modern!==c.organism)?' <span class="now">→ today <em>'+esc(c.modern)+'</em></span>':'';
  return '<article id="card-'+pid+'" class="dcard'+(zero?' zero':'')+'" data-cit="'+c.citations+'">'
   +'<div class="dc-h"><div><h3>'+esc(c.title)+'</h3>'
   +((c.title_de&&c.title_de!==c.title)?'<p class="dc-de">('+esc(c.title_de)+')</p>':'')
   +'<p class="dc-meta">'+esc(c.author)+' · '+c.year+(c.organism?' · <em>'+esc(c.organism)+'</em>':'')+now+'</p></div>'
   +'<div class="dc-badges">'+(c.layer?'<span class="lb l'+c.layer+'">Layer '+c.layer+'</span>':'')
   +(c.cluster?'<span class="clab">'+esc(c.cluster)+'</span>':'')+'</div></div>'
   +'<div class="gap"><div class="gapbar"><span style="width:'+pct+'%"></span></div>'
   +'<p class="gaptxt"><b>'+c.gap+'</b> modern works study this animal · <b class="'+(zero?'z':'')+'">'+c.citations+'</b> cite the original'
   +(zero?' <span class="ztag">none yet</span>':'')+'</p></div>'
   +'<p class="whatsnew"><span class="lab">What’s new</span>'+esc(c.whats_new)+'</p>'
   +'<div class="openend"><span class="lab">Still open today?</span>'+esc(c.open_end)
   +(c.ncite?'<span class="citetag'+(c.recent?' wake':' dorm')+'">'+(c.recent?'re-cited '+c.lastcite+' · waking':'last cited '+c.lastcite+' · dormant')+'</span>':'<span class="citetag dorm">never cited</span>')
   +'</div>'
   +(c.cite_summary?'<div class="citesumm"><span class="lab">How it’s cited today</span>'+esc(c.cite_summary)+'</div>':'')
   +'<div class="dc-links">'+links(c)
   +(c.consensus?'<button class="qedbtn ghost" onclick="qedAnalyze('+pid+')">☾ Quick peek</button>':'')
   +'<a class="qedbtn" href="dossier/'+pid+'.html">☾ Deep dive'+(c.consensus?(' · '+c.consensus.n+' papers'):'')+' →</a></div>'
   +'<div class="qedout" id="qed-'+pid+'"></div></article>';}
function groupHTML(g){return '<section class="gsec" data-k="'+g.key+'"><div class="ghead"><h2>'+esc(g.title)+'</h2>'
   +'<p class="gmod">'+esc(g.modern)+'</p><p class="gblurb">'+esc(g.blurb)+'</p></div>'
   +g.papers.slice().sort(function(a,b){return (R.cards[b]?R.cards[b].gap:0)-(R.cards[a]?R.cards[a].gap:0);}).map(cardHTML).join('')+'</section>';}

document.getElementById('chips').innerHTML='<button class="chip on" data-k="all">All ‹'+R.stats.targets+'›</button>'
  +R.groups.map(function(g){return '<button class="chip" data-k="'+g.key+'">'+esc(g.title)+' ‹'+g.papers.length+'›</button>';}).join('');
document.getElementById('groups').innerHTML=R.groups.map(groupHTML).join('');

document.getElementById('unfinished').innerHTML=R.unfinished.map(function(u){
  var ch=(u.papers||[]).map(function(id){var c=R.cards[id];return c?'<a class="pchip" href="#card-'+id+'" onclick="return jump('+id+')">'+esc(c.author)+' '+c.year+'</a>':'';}).join('');
  return '<section class="ubcard"><h3>'+esc(u.title)+'</h3><p class="ubq">'+esc(u.question)+'</p>'
   +'<blockquote class="ubquote">“'+esc(u.quote_en)+'”'
   +'<button class="degerman" onclick="var d=this.parentNode.querySelector(\'.de\');d.style.display=d.style.display===\'block\'?\'none\':\'block\';">original German</button>'
   +'<span class="de">„'+esc(u.quote_de)+'“</span>'
   +'<cite>— '+esc(u.source)+' · <span class="conf">'+esc(u.confidence)+'</span></cite></blockquote>'
   +'<p class="ubmod"><span class="lab">Where it went</span>'+esc(u.modern)+'</p>'
   +(ch?'<p class="ublinks">In the walk-through: '+ch+'</p>':'')+'</section>';
}).join('');

if(R.obituary){document.querySelector('.obit').innerHTML='A 40th paper, '+esc(R.obituary.author)+' ('+R.obituary.year+'), “'+esc(R.obituary.title)+',” was flagged by the same algorithm but is an obituary (of the BVA researcher Franz Megusar), not a discovery — so it is left out of the walk-through above.';}

var zchk=document.getElementById('zonly');
function applyZero(){var on=zchk.checked;
  document.querySelectorAll('.dcard').forEach(function(c){c.style.display=(on&&c.dataset.cit!=='0')?'none':'';});}
function setFilter(k){
  document.querySelectorAll('#chips .chip').forEach(function(b){b.classList.toggle('on',b.dataset.k===k);});
  document.querySelectorAll('.gsec').forEach(function(s){s.style.display=(k==='all'||s.dataset.k===k)?'':'none';});
  applyZero();}
document.getElementById('chips').addEventListener('click',function(e){var b=e.target.closest('.chip');if(b)setFilter(b.dataset.k);});
zchk.addEventListener('change',applyZero);

window.jump=function(id){setFilter('all');zchk.checked=false;applyZero();var el=document.getElementById('card-'+id);
  if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.add('flash');setTimeout(function(){el.classList.remove('flash');},1600);}return false;};

window.qedAnalyze=function(id){var out=document.getElementById('qed-'+id),c=R.cards[id];
  if(out.style.display==='block'){out.style.display='none';return;}
  out.style.display='block';
  var cn=c.consensus;
  if(!cn||!cn.papers||!cn.papers.length){out.innerHTML='<div class="qpend">No Consensus results recorded for this question.</div>';return;}
  var h='<div class="cons"><p class="consq">Question put to <b>Consensus</b>: <em>“'+esc(cn.query)+'”</em></p>'
    +'<p class="consmeta">'+cn.n+' papers found · '+cn.recent+' published since 2015'+(cn.latest?(' · most recent '+cn.latest):'')+'</p>';
  h+=cn.papers.map(function(p){
    var meta=[p.year,(p.author?(esc(p.author)+(p.others>0?(' +'+p.others):'')):''),(p.journal?esc(p.journal):'')].filter(Boolean).join(' · ');
    var tags=(p.study?'<span class="ptag">'+esc(p.study)+'</span>':'')+((p.cites!=null)?'<span class="ptag">'+p.cites+' cites</span>':'');
    return '<div class="conspaper"><a class="conslink" href="'+p.url+'" target="_blank" rel="noopener">'+esc(p.title)+' ↗</a>'
      +'<div class="consmeta2">'+meta+' '+tags+'</div>'
      +(p.takeaway?'<p class="constake">'+esc(p.takeaway)+'</p>':'')+'</div>';}).join('');
  h+='<p class="consfoot">Modern literature retrieved via the <a href="https://consensus.app" target="_blank" rel="noopener">Consensus</a> API for this paper’s open question. Takeaways are Consensus’s one-line summaries of each citing study.</p></div>';
  out.innerHTML=h;};
})();
"""


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


def gen_rediscovery():
    """Interactive walk-through of the 40 rediscovery targets, grouped by living model
    system, with per-paper open ends, a monograph-mined 'unfinished business' synthesis,
    and a (placeholder) Q.E.D. Science analysis button wired for later activation."""
    rp = os.path.join(ROOT, "legacy_data", "rediscovery.json")
    R = json.load(open(rp, encoding="utf-8"))
    cat_by_id = {c["id"]: c for c in catalog}
    read_for = {t["id"]: t["page_slug"] for t in translations}
    org_ov = {int(k): v for k, v in R.get("org_override", {}).items()}
    mpath = os.path.join(ROOT, "legacy_data", "methodology.json")
    meth = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {}
    _sp = os.path.join(ROOT, "legacy_data", "citation_summaries.json")
    SUMM = json.load(open(_sp, encoding="utf-8")) if os.path.exists(_sp) else {}
    _ep = os.path.join(ROOT, "legacy_data", "citations_enriched.json")
    ENR = json.load(open(_ep, encoding="utf-8")) if os.path.exists(_ep) else {}
    _consp = os.path.join(ROOT, "legacy_data", "consensus.json")
    CONS = json.load(open(_consp, encoding="utf-8")) if os.path.exists(_consp) else {}

    def consensus_for(pid):
        cn = CONS.get(str(pid))
        if not cn or not cn.get("results"):
            return None
        rs = [r for r in cn["results"] if r.get("title")][:5]
        if not rs:
            return None
        yrs = [r.get("year") for r in rs if r.get("year")]
        return dict(
            query=cn.get("query"), n=cn.get("n_results", len(rs)),
            latest=(max(yrs) if yrs else None),
            recent=sum(1 for y in yrs if y and y >= 2015),
            papers=[dict(title=r.get("title"), author=r.get("author"),
                         others=max(0, (r.get("n_authors") or 1) - 1), year=r.get("year"),
                         journal=r.get("journal"), study=r.get("study_type"),
                         cites=r.get("citations"), takeaway=r.get("takeaway"), url=r.get("url"))
                    for r in rs])

    def citeyears(pid):
        ys = sorted(w.get("year") for w in ENR.get(str(pid), {}).get("works", []) if w.get("year"))
        return ys

    def card(pid):
        c = cat_by_id[pid]
        cur = R["cards"][str(pid)]
        org, modern = org_ov.get(pid, (c.get("organism"), c.get("modern")))
        ys = citeyears(pid)
        last = ys[-1] if ys else None
        return dict(
            cite_summary=SUMM.get(str(pid)),
            lastcite=last, recent=bool(last and last >= 2010), ncite=len(ys),
            id=pid, title=(c.get("title_en") or c.get("title") or "").replace("�", "ä"),
            title_de=(c.get("title") or "").replace("�", "ä"),
            author=c.get("author"), year=c.get("year"),
            organism=org, modern=modern, taxon=c.get("taxon"),
            cluster=(meth.get(str(pid), {}) or {}).get("method", ""), layer=c.get("layer"),
            citations=c.get("citations", 0), gap=c.get("n_parallels", 0),
            whats_new=cur[0], open_end=cur[1],
            read=("papers/" + read_for[pid] + ".html") if pid in read_for else None,
            pdf=c.get("pdf"), doi=c.get("doi"), consensus=consensus_for(pid))

    cards = {}
    for g in R["groups"]:
        for pid in g["papers"]:
            cards[str(pid)] = card(pid)
    maxgap = max((c["gap"] for c in cards.values()), default=63)
    zero = sum(1 for c in cards.values() if c["citations"] == 0)
    cons_total = sum(c["consensus"]["n"] for c in cards.values() if c.get("consensus"))
    cons_npapers = sum(1 for c in cards.values() if c.get("consensus"))
    ob = cat_by_id.get(R.get("obituary"))
    obit = dict(id=ob["id"], author=ob["author"], year=ob["year"],
                title=(ob.get("title") or "").replace("�", "ä")) if ob else None
    data = dict(intro=R["intro"], qed=R["qed"], groups=R["groups"], cards=cards,
                unfinished=R["unfinished"], obituary=obit,
                stats=dict(targets=len(cards), systems=len(R["groups"]),
                           zero=zero, programs=len(R["unfinished"]), maxgap=maxgap,
                           cons_total=cons_total, cons_npapers=cons_npapers))
    os.makedirs(DATA, exist_ok=True)
    open(os.path.join(DATA, "rediscovery.js"), "w", encoding="utf-8").write(
        "window.REDISCOVERY=" + json.dumps(data, ensure_ascii=False) + ";")

    body = ('<p class="kicker">Rediscovery targets</p>'
        '<h1>Forty discoveries waiting to be re-cited</h1>'
        '<p class="lede">' + R["intro"] + '</p>'
        '<div class="rstats">'
        '<div><b>' + str(len(cards)) + '</b><span>rediscovery targets</span></div>'
        '<div><b>' + str(len(R["groups"])) + '</b><span>living model systems</span></div>'
        '<div><b>' + str(zero) + '</b><span>with zero modern citations</span></div>'
        '<div><b>' + str(len(R["unfinished"])) + '</b><span>unfinished programs</span></div>'
        '<div><b>' + str(cons_total) + '</b><span>modern papers via Consensus</span></div>'
        '</div>'
        '<div class="qbanner"><span class="qi">☾</span><div><b>Is it still open — or a sleeping beauty?</b> '
        'For each paper, the “Still open today?” line asks whether the question it touches remains unresolved, or '
        'whether the paper is a <em>sleeping beauty</em> — a forgotten early answer to something science is still asking. '
        'A green <span class="citetag wake" style="margin:0">re-cited · waking</span> tag means modern work (2010 on) has begun citing it again; a grey '
        '<span class="citetag dorm" style="margin:0">dormant</span> tag means it has gone quiet. '
        'Now wired live: the <b>☾ What today\'s research says</b> button on each card opens the modern literature on that '
        'paper\'s open question — <b>' + str(cons_total) + ' papers</b> across the ' + str(cons_npapers) + ' targets, retrieved from the <b>Consensus</b> API with each study\'s one-line takeaway.</div></div>'
        '<p class="muted" style="font-size:13.5px;line-height:1.55;max-width:76ch;margin:8px 0 0">On each card the bar reads <b>how many modern works study this animal</b> against <b>how many cite the BVA original</b> — the wider the gap, the more orphaned the work. Where modern science <em>does</em> engage a paper, a “How it’s cited today” note summarises that reception; <b>Who cites it ↗</b> opens the full, paper-by-paper citation list on the Legacy page.</p>'
        '<div id="chips" class="chips"></div>'
        '<label class="zchk"><input type="checkbox" id="zonly"> Show only the targets nobody cites yet ('
        + str(zero) + ')</label>'
        '<div id="groups"></div>'
        '<h2 class="ubh">The institute’s unfinished business</h2>'
        '<p class="muted ubintro">Beyond the single papers, the Vivarium opened whole research programs it never '
        'closed. These six are drawn from Przibram’s own monographs — each with the original passage and a note '
        'on where the question went.</p>'
        '<div id="unfinished"></div>'
        '<section style="margin-top:34px;padding:14px 16px;border:1px solid var(--rule);border-left:4px solid var(--accent2);border-radius:10px;background:#f1ece1">'
        '<h3 style="margin:.1em 0 .4em">Powered by Consensus</h3>'
        '<p class="muted" style="font-size:13.5px;line-height:1.6;max-width:80ch;margin:0">'
        'Each paper&rsquo;s open question was put to the <a href="https://consensus.app" target="_blank" rel="noopener">Consensus</a> '
        'developer API (<code>GET /v1/quick_search</code>), which returns ranked, peer-reviewed papers with a one-line takeaway for each. '
        'The results were fetched once <b>at build time</b> and baked into this page, so there is no per-visitor cost and the API key '
        'never sits in this static site&rsquo;s JavaScript. The takeaways shown are Consensus&rsquo;s own summaries of each study; '
        'follow any title to read it on Consensus. Verdicts reflect the literature as retrieved in June 2026 and are a research aid, not a settled answer.</p></section>'
        '<p class="obit muted"></p>')

    page("rediscovery.html", "Rediscover", "Rediscover", body,
         head="<style>" + REDISC_CSS + "</style>",
         foot='<script src="data/summaries.js"></script><script src="data/rediscovery.js"></script><script>' + REDISC_JS + '</script>')
    print("rediscovery.html:", len(cards), "cards |", len(R["groups"]), "groups |",
          len(R["unfinished"]), "programs | zero-cite:", zero)


DISCOVER_CSS = r"""
.dlede{max-width:78ch;font-size:16.5px;line-height:1.6}
.ledenote{display:block;margin-top:9px;font-size:14px;color:var(--muted)}
.sbwrap{margin:22px 0 8px;background:linear-gradient(135deg,#1d2733,#33485c);border-radius:16px;padding:18px 20px 20px;color:#f3efe6;position:relative;overflow:hidden}
.sbwrap::after{content:"☾";position:absolute;right:-10px;top:-26px;font-size:150px;opacity:.07}
.sbhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;position:relative;z-index:2}
.sbeyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#cdb98a;font-weight:600}
.sbnav button{background:rgba(255,255,255,.12);color:#fff;border:0;border-radius:8px;width:34px;height:30px;font-size:15px;cursor:pointer;margin-left:6px}
.sbnav button:hover{background:rgba(255,255,255,.25)}
.carousel{position:relative;z-index:2;min-height:166px}
.cslide{display:none;animation:cfade .6s ease}
.cslide.on{display:block}
@keyframes cfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.cverdict{display:inline-block;background:#cdb98a;color:#26313d;font-size:11.5px;font-weight:700;letter-spacing:.03em;padding:3px 11px;border-radius:20px}
.cslide h3{font-family:Georgia,serif;font-size:23px;margin:9px 0 3px;color:#fff;line-height:1.2}
.cmeta{font-size:13px;color:#b9c6d3;margin:0 0 8px}
.cmeta em{color:#e7dcc4;font-style:normal}
.ctoday{font-size:14.5px;line-height:1.55;color:#eee;max-width:80ch;margin:0 0 12px}
.ctoday b{color:#cdb98a;font-weight:700}
.cgo{display:inline-block;background:#fff;color:#26313d;font-weight:600;font-size:13px;padding:6px 13px;border-radius:8px;text-decoration:none}
.cgo:hover{background:#cdb98a;text-decoration:none}
.sbdots{display:flex;flex-wrap:wrap;gap:5px;margin-top:13px;position:relative;z-index:2}
.sbdots i{width:7px;height:7px;border-radius:50%;background:rgba(255,255,255,.3);cursor:pointer}
.sbdots i.on{background:#cdb98a;transform:scale(1.3)}
.explorer{margin:26px 0 8px}
.search{width:100%;font-size:15px;padding:11px 14px;border:1px solid var(--rule);border-radius:10px;background:var(--card);font-family:inherit}
.exrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:11px 0}
.exrow select{font-size:13.5px;padding:7px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--card);font-family:inherit}
.count{font-size:13px;color:var(--muted);margin-left:auto}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:11px 0}
.chip{font-size:12.5px;border:1px solid var(--rule);background:var(--card);border-radius:20px;padding:5px 13px;cursor:pointer;color:var(--ink)}
.chip.on{background:var(--accent2);color:#fff;border-color:var(--accent2)}
.chip .cc{opacity:.6;font-size:11px;margin-left:3px}
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;margin-top:6px}
.dcardx{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:15px 16px;display:flex;flex-direction:column}
.dcardx .stat{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:2px 9px;border-radius:20px;align-self:flex-start;margin-bottom:7px}
.st-sb{background:#33485c;color:#f3efe6}.st-qc{background:#2e6f6a;color:#fff}.st-ll{background:#1d6e56;color:#fff}.st-st{background:#9a6a1f;color:#fff}.st-cl{background:#8a3a3a;color:#fff}.st-rr{background:#9a9387;color:#fff}
.csbi{display:inline-block;margin-left:8px;background:rgba(255,255,255,.14);color:#e7dcc4;font-size:11px;font-weight:700;letter-spacing:.02em;padding:3px 10px;border-radius:20px}
.taxnote{margin:18px 0 4px;background:var(--card);border:1px solid var(--rule);border-left:4px solid #33485c;border-radius:10px;padding:13px 16px}
.taxnote p{font-size:13.8px;line-height:1.6;margin:0 0 9px;max-width:84ch;color:#3c3833}
.taxleg{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:6px 16px}
.taxleg li{font-size:12.5px;color:var(--muted);line-height:1.5}
.taxleg .stat{display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;margin-right:5px}
.synbadge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.02em;color:var(--accent);border:1px solid var(--accent);border-radius:20px;padding:1px 8px;margin-left:6px}
.dcardx h3{font-family:Georgia,serif;font-size:17px;margin:0 0 3px;line-height:1.25}
.dcardx .cm{font-size:12.5px;color:var(--muted);margin:0 0 8px}
.dcardx .cm em{font-style:italic}
.dcardx .ck{font-size:13px;line-height:1.5;color:#3c3833;margin:0 0 10px;flex:1}
.dcardx .cn{font-size:11.5px;color:var(--accent2);font-weight:600;margin:0 0 9px}
.dcardx .lk{display:flex;gap:8px;flex-wrap:wrap}
.dcardx .lk a{font-size:12.5px;border:1px solid var(--rule);border-radius:7px;padding:4px 10px;text-decoration:none;color:var(--ink)}
.dcardx .lk a.go{background:var(--accent2);color:#fff;border-color:var(--accent2)}
.dcardx .lk a:hover{border-color:#cdc4b1}
@media(max-width:680px){.rstats{grid-template-columns:repeat(2,1fr)}.dgrid{grid-template-columns:1fr}}
"""

DISCOVER_JS = r"""
(function(){
var D=window.DISCOVER, P=D.papers;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
// --- search-term highlighting: applied to ALREADY-ESCAPED html, so it can never break markup ---
function hlEsc(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function hl(escaped,term){
  if(!term)return escaped;
  var t=String(term).trim(); if(t.length<2)return escaped;
  var parts=t.split(/\s+/).filter(function(x){return x.length>1;}).map(hlEsc);
  if(!parts.length)return escaped;
  var re=new RegExp('(?![^<]*>)(?![^&;]*;)('+parts.join('|')+')','gi');
  return escaped.replace(re,'<mark class="hlt">$1</mark>');
}
var SC={'Sleeping Beauty':'st-sb','Quiet Classic':'st-qc','Living Legacy':'st-ll','Stirring':'st-st','Contested Legacy':'st-cl','Rightly Rested':'st-rr'};
// ---------- sleeping-beauty carousel ----------
var sb=D.sleeping, ci=0, timer=null, playing=true;
function slide(pid){var p=P[pid];var now=(p.org&&p.org!=='—')?('<span class="cmeta"> </span>'):'';
  var today=p.ft?('<p class="ctoday"><b>Today'+(p.fy?(' ('+p.fy+')'):'')+':</b> '+esc(p.ft)+'</p>'):(p.hook?('<p class="ctoday"><b>Today:</b> '+esc(p.hook)+'</p>'):'');
  return '<div class="cslide on"><span class="cverdict">'+esc(p.v||'Sleeping Beauty')+'</span><span class="csbi">☾ Sleeping-Beauty Index '+(p.sbi!=null?p.sbi:'—')+'</span>'
   +'<h3>'+esc(p.t)+'</h3><p class="cmeta">'+esc(p.au||'')+' · '+p.y+(p.org&&p.org!=='—'?(' · <em>'+esc(p.org)+'</em>'):'')+' · cited '+p.c+'× today · '+p.n+' modern papers</p>'
   +today+'<a class="cgo" href="dossier/'+pid+'.html">Open the full dossier →</a></div>';}
function showCar(i){ci=(i+sb.length)%sb.length;document.getElementById('carousel').innerHTML=slide(sb[ci]);
  var dots=document.getElementById('sbdots').children;for(var k=0;k<dots.length;k++)dots[k].className=(k===ci?'on':'');}
function nextCar(){showCar(ci+1);}
function buildDots(){document.getElementById('sbdots').innerHTML=sb.map(function(_,k){return '<i data-k="'+k+'"></i>';}).join('');}
function play(){if(timer)clearInterval(timer);timer=setInterval(nextCar,5200);playing=true;document.getElementById('sbtoggle').textContent='⏸';}
function pause(){if(timer)clearInterval(timer);timer=null;playing=false;document.getElementById('sbtoggle').textContent='▶';}
buildDots();showCar(0);play();
document.getElementById('sbNext').onclick=function(){nextCar();play();};
document.getElementById('sbPrev').onclick=function(){showCar(ci-1);play();};
document.getElementById('sbtoggle').onclick=function(){playing?pause():play();};
document.getElementById('sbdots').onclick=function(e){var i=e.target.getAttribute('data-k');if(i!==null){showCar(+i);play();}};
var cw=document.querySelector('.sbwrap');cw.onmouseenter=pause;cw.onmouseleave=function(){if(!playing)play();};
// ---------- explorer ----------
var st={q:'',status:'all',tax:'all',sort:'modern'};
function chips(){var counts={};D.order.forEach(function(pid){var s=P[pid].st;counts[s]=(counts[s]||0)+1;});
  var h='<button class="chip on" data-s="all">All ‹'+D.order.length+'›</button>';
  D.statuses.forEach(function(s){if(counts[s])h+='<button class="chip" data-s="'+esc(s)+'">'+esc(s)+'<span class="cc">'+counts[s]+'</span></button>';});
  document.getElementById('statuschips').innerHTML=h;}
function card(pid){var p=P[pid];var Q=st.q.trim();
  var lk='<a class="go" href="dossier/'+pid+'.html">Deep dive →</a>';
  if(p.read)lk+='<a href="papers/'+p.read+'.html">Translation</a>';
  lk+='<a href="reader.html?id='+pid+'">German</a>';
  lk+='<a href="catalog.html?id='+pid+'">Catalog ↗</a>';
  return '<article class="dcardx"><span class="stat '+(SC[p.st]||'st-dm')+'">'+esc(p.st)+'</span>'+(p.syn?'<span class="synbadge">✦ read &amp; compared</span>':'')
   +'<h3>'+hl(esc(p.t),Q)+'</h3><p class="cm">'+hl(esc(p.au||''),Q)+' · '+p.y+(p.org&&p.org!=='—'?(' · <em>'+hl(esc(p.org),Q)+'</em>'):'')+'</p>'
   +(p.hook?'<p class="ck">'+esc(p.hook)+'</p>':'<p class="ck"></p>')
   +'<p class="cn">'+p.n+' modern papers'+(p.l?(' · latest '+p.l):'')+' · cited '+p.c+'× today'+(p.sb?(' · <b>☾ SBI '+p.sbi+'</b>'):'')+'</p>'
   +'<div class="lk">'+lk+'</div></article>';}
function render(){var q=st.q.toLowerCase();
  var list=D.order.filter(function(pid){var p=P[pid];
    if(st.status!=='all'&&p.st!==st.status)return false;
    if(st.tax!=='all'&&p.tax!==st.tax)return false;
    if(q){var hay=(p.t+' '+(p.au||'')+' '+(p.org||'')+' '+(p.de||'')).toLowerCase();if(hay.indexOf(q)<0)return false;}
    return true;});
  if(st.sort==='modern')list.sort(function(a,b){return P[b].n-P[a].n;});
  else if(st.sort==='year')list.sort(function(a,b){return P[b].y-P[a].y;});
  else if(st.sort==='cites')list.sort(function(a,b){return P[b].c-P[a].c;});
  else if(st.sort==='recent')list.sort(function(a,b){return (P[b].l||0)-(P[a].l||0);});
  else if(st.sort==='sbi')list.sort(function(a,b){return (P[b].sbi||0)-(P[a].sbi||0);});
  document.getElementById('grid').innerHTML=list.map(card).join('');
  document.getElementById('count').textContent=list.length+' of '+D.order.length+' papers';}
chips();
var tax=document.getElementById('taxsel');tax.innerHTML='<option value="all">All groups</option>'+D.taxa.map(function(t){return '<option value="'+esc(t)+'">'+esc(t)+'</option>';}).join('');
document.getElementById('statuschips').onclick=function(e){var b=e.target.closest('.chip');if(!b)return;st.status=b.getAttribute('data-s');
  document.querySelectorAll('#statuschips .chip').forEach(function(x){x.classList.toggle('on',x===b);});render();};
document.getElementById('q').oninput=function(e){st.q=e.target.value;render();};
tax.onchange=function(e){st.tax=e.target.value;render();};
document.getElementById('sortsel').onchange=function(e){st.sort=e.target.value;render();};
render();
// unfinished business
if(D.unfinished&&document.getElementById('unfinished')){
  document.getElementById('unfinished').innerHTML=D.unfinished.map(function(u){
    return '<section class="ubcard"><h3>'+esc(u.title)+'</h3><p class="ubq">'+esc(u.question)+'</p>'
     +'<blockquote class="ubquote">“'+esc(u.quote_en)+'”<cite>— '+esc(u.source)+'</cite></blockquote>'
     +'<p class="ubmod"><span class="lab">Where it went</span>'+esc(u.modern)+'</p></section>';}).join('');}
})();
"""


def gen_discover():
    """All-175 interactive Discover hub: sleeping-beauty carousel + filterable explorer,
    each paper set against the current literature retrieved from Consensus."""
    ap = os.path.join(ROOT, "legacy_data", "consensus_all.json")
    A = json.load(open(ap, encoding="utf-8")) if os.path.exists(ap) else {}
    rp = os.path.join(ROOT, "legacy_data", "rediscovery.json")
    R = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    _synp = os.path.join(ROOT, "legacy_data", "consensus_synthesis.json")
    SYN = json.load(open(_synp, encoding="utf-8")) if os.path.exists(_synp) else {}
    cat_by_id = {c["id"]: c for c in catalog}
    read_for = {t["id"]: t["page_slug"] for t in translations}
    ov = {int(k): v for k, v in R.get("org_override", {}).items()}

    def org(c):
        return (ov.get(c["id"], (None,))[0]) or c.get("organism") or c.get("genus") or c.get("modern") or "—"

    def tax(c):
        t = (c.get("taxon") or "Other").strip()
        return {"Orthoptera / Mantis": "Insects", "Other arthropods": "Other invertebrates"}.get(t, t)

    papers = {}; order = []; sleeping = []
    for pid_s, d in A.items():
        pid = int(pid_s); c = cat_by_id.get(pid)
        if not c:
            continue
        res = d.get("results", [])
        hook = (res[0].get("takeaway") if res else "") or ""
        fresh = max(res, key=lambda r: (r.get("year") or 0)) if res else None
        papers[str(pid)] = dict(
            id=pid, t=(c.get("title_en") or c.get("title") or "").replace("�", "ä"),
            de=(c.get("title") or "").replace("�", "ä"), au=c.get("author"), y=c.get("year"),
            org=org(c), tax=tax(c), st=d.get("status"), sb=1 if d.get("sleeping") else 0,
            sbi=d.get("sbi"),
            c=d.get("cites", 0), n=d.get("n_unique", 0), l=d.get("latest"),
            v=(SYN.get(pid_s, {}).get("verdict") or d.get("verdict")),
            syn=1 if SYN.get(pid_s) else 0,
            read=(read_for.get(pid) or ""), hook=hook[:175],
            fy=(fresh.get("year") if fresh else None), ft=((fresh.get("takeaway") or "")[:185] if fresh else ""))
        order.append(pid)
        if d.get("sleeping"):
            sleeping.append(pid)
    order.sort(key=lambda pid: (0 if papers[str(pid)]["sb"] else 1, -(papers[str(pid)]["sbi"] or 0), -(papers[str(pid)]["n"] or 0)))
    sleeping.sort(key=lambda pid: -(papers[str(pid)]["sbi"] or 0))
    stats = dict(papers=len(papers), modern=sum(p["n"] for p in papers.values()),
                 sleeping=len(sleeping),
                 legacy=sum(1 for p in papers.values() if p["st"] == "Living Legacy"),
                 confirmed=sum(1 for p in papers.values() if p["st"] in ("Sleeping Beauty", "Quiet Classic")))
    data = dict(papers=papers, order=order, sleeping=sleeping, stats=stats,
                statuses=["Sleeping Beauty", "Quiet Classic", "Living Legacy", "Stirring", "Contested Legacy", "Rightly Rested"],
                taxa=sorted(set(p["tax"] for p in papers.values())), unfinished=R.get("unfinished", []))
    os.makedirs(DATA, exist_ok=True)
    open(os.path.join(DATA, "discover.js"), "w", encoding="utf-8").write(
        "window.DISCOVER=" + json.dumps(data, ensure_ascii=False) + ";")
    # slim cross-page index so the Catalog (and any other page) can show the
    # Discover verdict/status without loading the whole hub payload.
    open(os.path.join(DATA, "discidx.js"), "w", encoding="utf-8").write(
        "window.DISCIDX=" + json.dumps(
            {str(p["id"]): {"st": p["st"], "sbi": p["sbi"], "sb": p["sb"], "v": p["v"]}
             for p in papers.values()}, ensure_ascii=False) + ";")
    body = ('<p class="kicker">The corpus in the light of today’s science</p>'
            '<h1>Discover</h1>'
            '<p class="lede dlede">All ' + str(stats["papers"]) + ' Vivarium <em>research</em> papers (1904–1930), each set against the current literature — '
            '<b>' + str(stats["modern"]) + ' modern papers</b> retrieved from the Consensus API, then read and compared one by one. '
            'Every paper is placed on two axes — how much today’s science <em>remembers</em> it, and whether its ideas actually <em>held up</em>. '
            'Each card links back to its full <a href="catalog.html">Catalog</a> entry, and the Catalog carries these verdicts in its <b>Today</b> column. '
            '<span class="ledenote">The <a href="catalog.html">Catalog</a> holds 175 items; three carry no verdict here. '
            'Przibram’s 1917 <a href="papers/88-hans-przibram-1917.html">obituary of Franz Megušar</a> reports no experiment, '
            'so there is nothing to set against the literature. The other two — the 1906 '
            '<a href="papers/174-grosser-przibram-1906.html">dogfish malformations</a> and the 1922 '
            '<a href="papers/175-przibram-brecher-1922.html">stick-insect colour modifications</a> — are being reassessed: '
            'their catalogue rows were mistitled when the original assessments were made, so each had been given another '
            'paper’s verdict. Those assessments have been withdrawn rather than left standing. All three are translated '
            'and catalogued like the rest.</span></p>'
            '<section class="sbwrap"><div class="sbhead"><span class="sbeyebrow">☾ The search for sleeping beauties</span>'
            '<div class="sbnav"><button id="sbPrev" aria-label="previous">‹</button>'
            '<button id="sbtoggle" aria-label="play/pause">⏸</button><button id="sbNext" aria-label="next">›</button></div></div>'
            '<div id="carousel" class="carousel"></div><div id="sbdots" class="sbdots"></div></section>'
            '<div class="rstats">'
            '<div><b>' + str(stats["papers"]) + '</b><span>research papers, 1904–1930</span></div>'
            '<div><b>' + str(stats["modern"]) + '</b><span>modern papers via Consensus</span></div>'
            '<div><b>' + str(stats["sleeping"]) + '</b><span>sleeping beauties</span></div>'
            '<div><b>' + str(stats["confirmed"]) + '</b><span>forgotten yet confirmed</span></div>'
            '<div><b>' + str(stats["legacy"]) + '</b><span>living legacies</span></div></div>'
            '<div class="taxnote">'
            '<p><b>A new way to read the corpus.</b> Citation counts alone reward <em>notoriety</em>, not correctness — '
            'some of the institute’s most-cited papers are its most <em>refuted</em> (Kammerer’s inheritance claims, '
            'Steinach’s sexual-orientation theory), while genuinely confirmed work sits almost uncited. So each paper is placed on '
            'two axes: <b>recognition</b> (how often today’s literature cites it) and <b>vindication</b> (whether its science held up, '
            'from the read-and-compare verdicts). The <b>☾ Sleeping-Beauty Index</b> ranks the forgotten-yet-vindicated.</p>'
            '<ul class="taxleg">'
            '<li><span class="stat st-sb">Sleeping Beauty</span> forgotten, yet confirmed — the rediscovery prizes</li>'
            '<li><span class="stat st-qc">Quiet Classic</span> lightly cited, but vindicated</li>'
            '<li><span class="stat st-ll">Living Legacy</span> well cited, and it held up</li>'
            '<li><span class="stat st-st">Stirring</span> forgotten; the idea is alive but unsettled</li>'
            '<li><span class="stat st-cl">Contested Legacy</span> famous, but refuted</li>'
            '<li><span class="stat st-rr">Rightly Rested</span> forgotten, and it did not hold</li>'
            '</ul></div>'
            '<div class="explorer"><input id="q" class="search" placeholder="Search title, author, or organism…">'
            '<div id="statuschips" class="chips"></div>'
            '<div class="exrow"><select id="taxsel"></select>'
            '<select id="sortsel"><option value="modern">Sort: most modern papers</option>'
            '<option value="sbi">Sort: sleeping-beauty index</option>'
            '<option value="recent">Sort: most recent work</option>'
            '<option value="cites">Sort: most cited today</option>'
            '<option value="year">Sort: paper year</option></select>'
            '<span id="count" class="count"></span></div></div>'
            '<div id="grid" class="dgrid"></div>'
            '<h2 class="ubh">The institute’s unfinished business</h2>'
            '<p class="muted ubintro">Beyond the single papers, the Vivarium opened whole research programs it never closed — '
            'drawn from Przibram’s own monographs.</p><div id="unfinished"></div>')
    page("rediscovery.html", "Discover", "Discover", body,
         head="<style>" + DISCOVER_CSS + REDISC_CSS + "</style>",
         foot='<script src="data/discover.js"></script><script>' + DISCOVER_JS + '</script>')
    print("discover.html:", len(papers), "papers |", len(sleeping), "sleeping |", stats["modern"], "modern papers")


DOSSIER_CSS = r"""
.dossier{max-width:820px}
.dossier .detitle{font-style:italic;color:var(--muted);margin:.1em 0 .3em;font-size:16px}
.dossier .byline{color:var(--muted);font-size:14px;margin:.2em 0 14px}
.dsec{margin:26px 0;padding-top:6px}
.dsec h2{font-family:Georgia,serif;font-size:21px;border-bottom:2px solid var(--rule);padding-bottom:6px;margin:0 0 12px}
.dsec h2 .cnt{font-family:-apple-system,sans-serif;font-size:13px;color:var(--muted);font-weight:400}
.whatd{font-size:15.5px;line-height:1.6;margin:0}
.meth{font-size:14px;line-height:1.6;margin:10px 0 0;color:#3c3833}
.meth .lab,.openq .lab{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);font-weight:600;margin-bottom:2px}
.statebox{background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--accent2);border-radius:12px;padding:16px 18px}
.statebox h2{border-bottom:0;margin:.1em 0 8px;font-size:20px}
.verdict{display:inline-block;background:var(--accent2);color:#fff;font-size:12px;font-weight:600;letter-spacing:.02em;padding:3px 11px;border-radius:20px;margin-bottom:8px}
.dcat{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.02em;padding:3px 10px;border-radius:20px;margin:0 0 8px 7px}
.dcat .sbii{opacity:.8;font-weight:600;margin-left:5px}
.dcat.st-sb{background:#33485c;color:#f3efe6}.dcat.st-qc{background:#2e6f6a;color:#fff}.dcat.st-ll{background:#1d6e56;color:#fff}.dcat.st-st{background:#9a6a1f;color:#fff}.dcat.st-cl{background:#8a3a3a;color:#fff}.dcat.st-rr{background:#9a9387;color:#fff}
.stateprose{font-size:15.5px;line-height:1.65;margin:0 0 14px}
.cmph{font-family:-apple-system,sans-serif;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);margin:4px 0 5px;font-weight:700}
.dstats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:6px 0 14px}
.dstats div{background:var(--paper);border:1px solid var(--rule);border-radius:9px;padding:10px 12px;text-align:center}
.dstats b{display:block;font-family:Georgia,serif;font-size:24px;line-height:1}
.dstats span{font-size:11.5px;color:var(--muted)}
.openq{font-size:14.5px;line-height:1.6;margin:4px 0 0;padding-top:10px;border-top:1px dashed var(--rule)}
.summbox{margin:0 0 14px;padding:12px 14px;border-left:3px solid var(--accent2);background:#eef2f5;border-radius:0 8px 8px 0}
.summbox h3{margin:.1em 0 .4em;font-size:12.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--accent2)}
.summbox p{margin:0;font-size:14px;line-height:1.62}
.citelist{display:flex;flex-direction:column;gap:11px}
.citework{border:1px solid var(--rule);border-radius:9px;padding:10px 13px;background:var(--card)}
.citehd{margin:0;font-size:14px;line-height:1.5}
.citehd b{font-family:Georgia,serif}
.citenote{margin:6px 0 0;font-size:13.5px;line-height:1.6;color:#4a463f;padding-top:6px;border-top:1px dashed var(--rule)}
.histtag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.02em;background:#9a9387;color:#fff;border-radius:20px;padding:1px 8px}
.facets{margin:0;padding-left:20px;font-size:15px;line-height:1.5}
.facets li{margin:5px 0;color:#2f2c28}
.conslist{margin-top:4px}
.conspaper{padding:11px 0;border-top:1px solid var(--rule)}
.conspaper:first-child{border-top:0}
.conslink{font-weight:600;font-size:15px;line-height:1.4}
.consmeta2{font-size:12px;color:var(--muted);margin:3px 0 4px}
.ptag{display:inline-block;background:var(--card);border:1px solid var(--rule);border-radius:5px;padding:0 6px;margin-left:5px;font-size:10.5px;text-transform:capitalize}
.constake{margin:3px 0 0;font-size:14px;line-height:1.55;color:#2f2c28}
@media(max-width:640px){.dstats{grid-template-columns:repeat(3,1fr)}}
"""


def gen_dossier():
    """One deep scroll page per rediscovery paper: the historic work, the modern
    state of the field, the questions put to Consensus, and every relevant modern paper."""
    rp = os.path.join(ROOT, "legacy_data", "rediscovery.json")
    R = json.load(open(rp, encoding="utf-8"))
    dp = os.path.join(ROOT, "legacy_data", "consensus_all.json")
    DEEP = json.load(open(dp, encoding="utf-8")) if os.path.exists(dp) else {}
    if not DEEP:
        return
    cat_by_id = {c["id"]: c for c in catalog}
    read_for = {t["id"]: t["page_slug"] for t in translations}
    org_ov = {int(k): v for k, v in R.get("org_override", {}).items()}
    mpath = os.path.join(ROOT, "legacy_data", "methodology.json")
    meth = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {}
    _synp = os.path.join(ROOT, "legacy_data", "consensus_synthesis.json")
    SYN = json.load(open(_synp, encoding="utf-8")) if os.path.exists(_synp) else {}

    def _ld(name):
        p = os.path.join(ROOT, "legacy_data", name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    # direct reception: who actually cites the BVA paper (folded in from the old Legacy panel)
    ENR = _ld("citations_enriched.json")      # per paper -> works[]
    CNOTES = _ld("citation_notes.json")       # "<pid>:<oa_id>" -> curated prose note
    CTITLES = _ld("citation_titles.json")     # oa_id -> English title
    CSUMM = _ld("citation_summaries.json")    # pid -> "how later science draws on this work"
    os.makedirs(os.path.join(SITE, "dossier"), exist_ok=True)

    def cited_by_html(pid_s):
        rec = ENR.get(pid_s) or {}
        works = sorted(rec.get("works", []), key=lambda w: (w.get("year") or 0), reverse=True)
        summ = CSUMM.get(pid_s)
        if not works and not summ:
            return ""
        def _t(s):  # sources carry (sometimes doubly) encoded entities — fully decode, then escape once
            s = s or ""
            for _ in range(3):
                u = html.unescape(s)
                if u == s:
                    break
                s = u
            return html.escape(s)
        sm = ('<div class="summbox"><h3>How later science draws on this work</h3><p>'
              + _t(summ) + '</p></div>') if summ else ''
        items = ""
        for w in works:
            a = w.get("authors") or []
            who = _t(a[0] if a else "") + (" et al." if len(a) > 1 else "")
            ttl = CTITLES.get(w.get("oa_id")) or w.get("title") or "(untitled)"
            doi = ('<a href="https://doi.org/%s" target="_blank" rel="noopener">doi ↗</a>' % w["doi"]) if w.get("doi") else ''
            tag = '<span class="histtag">history of science</span>' if w.get("historiographic") else ''
            note = CNOTES.get("%s:%s" % (pid_s, w.get("oa_id")))
            nt = ('<p class="citenote">' + _t(note) + '</p>') if note else ''
            items += ('<div class="citework"><p class="citehd"><b>' + str(w.get("year") or "n.d.") + '</b> · '
                      + who + ' — ' + _t(ttl) + ' ' + doi + ' ' + tag + '</p>' + nt + '</div>')
        n = len(works)
        return ('<section class="dsec"><h2>Who cites this paper '
                + ('<span class="cnt">(%d work%s)</span>' % (n, "" if n == 1 else "s") if n else '')
                + '</h2>' + sm
                + (('<div class="citelist">' + items + '</div>') if items
                   else '<p class="muted">No modern citations recorded.</p>')
                + '</section>')

    def paper_html(r):
        bits = [str(r.get("year") or "")]
        au = html.escape(r.get("author") or "")
        if au:
            bits.append(au + (" +%d" % (r["n_authors"] - 1) if (r.get("n_authors") or 0) > 1 else ""))
        if r.get("journal"):
            bits.append(html.escape(r["journal"]))
        meta = " · ".join(x for x in bits if x)
        tags = ""
        if r.get("study_type"):
            tags += '<span class="ptag">' + html.escape(r["study_type"]) + '</span>'
        if r.get("citations") is not None:
            tags += '<span class="ptag">' + str(r["citations"]) + ' cites</span>'
        tk = ('<p class="constake">' + html.escape(r["takeaway"]) + '</p>') if r.get("takeaway") else ""
        u = r.get("url") or "#"
        return ('<div class="conspaper"><a class="conslink" href="' + u + '" target="_blank" rel="noopener">'
                + html.escape(r.get("title") or "(untitled)") + ' ↗</a><div class="consmeta2">' + meta + ' '
                + tags + '</div>' + tk + '</div>')

    n = 0
    for pid_s, d in DEEP.items():
        pid = int(pid_s)
        c = cat_by_id.get(pid)
        if not c:
            continue
        cur = R["cards"].get(pid_s, ["", ""])
        org, modern = org_ov.get(pid, (c.get("organism"), c.get("modern")))
        m = meth.get(pid_s, {})
        title_en = (c.get("title_en") or c.get("title") or "").replace("�", "ä")
        title_de = (c.get("title") or "").replace("�", "ä")
        read = ("../papers/" + read_for[pid] + ".html") if pid in read_for else None
        res = sorted(d.get("results", []), key=lambda r: (r.get("year") or 0), reverse=True)
        _sy = SYN.get(pid_s) or {}
        _verdict = _sy.get("verdict") or d.get("verdict") or "Still open today?"
        _state = _sy.get("state") or d.get("state") or ""
        _cmp_html = ('<h3 class="cmph">How this 1900s paper stands today</h3><p class="stateprose">'
                     + html.escape(_sy["comparison"]) + '</p>') if _sy.get("comparison") else ''
        _status = d.get("status") or ""
        _sbi = d.get("sbi")
        _SCLS = {"Sleeping Beauty": "st-sb", "Quiet Classic": "st-qc", "Living Legacy": "st-ll",
                 "Stirring": "st-st", "Contested Legacy": "st-cl", "Rightly Rested": "st-rr"}
        _sbi_html = ('<span class="sbii">☾ SBI %s</span>' % _sbi) if (d.get("sleeping") and _sbi is not None) else ''
        _cat_html = ('<span class="dcat %s">%s%s</span>' % (_SCLS.get(_status, "st-rr"), html.escape(_status), _sbi_html)) if _status else ''
        actions = '<a class="btn" href="../rediscovery.html">← Discover</a>'
        if read:
            actions += '<a class="btn primary" href="%s">Read the English translation</a>' % read
        actions += '<a class="btn" href="../reader.html?id=%d">German original</a>' % pid
        actions += '<a class="btn" href="../catalog.html?id=%d">Catalog entry ↗</a>' % pid
        if c.get("doi"):
            actions += '<a class="btn" href="https://doi.org/%s" target="_blank" rel="noopener">DOI ↗</a>' % c["doi"]
        body = f"""
<article class="dossier">
  <p class="kicker"><a href="../rediscovery.html">Rediscover</a> · BVA · {c.get('year')}{(' · <em>'+html.escape(org)+'</em>') if org else ''}</p>
  <h1>{html.escape(title_en)}</h1>
  {('<p class="detitle">'+html.escape(title_de)+'</p>') if title_de and title_de != title_en else ''}
  <p class="byline">{html.escape(c.get('author') or '')} · {c.get('year')}</p>
  <div class="actionbar">{actions}</div>
  {sens_html(pid, "dossier")}
  <section class="dsec">
    <h2>What this paper did</h2>
    <p class="whatd">{html.escape(cur[0])}</p>
    {('<p class="meth"><span class="lab">How</span>'+html.escape(m.get('manipulation') or '')+'</p>') if m.get('manipulation') else ''}
  </section>
  <section class="dsec statebox">
    <span class="verdict">{html.escape(_verdict)}</span>{_cat_html}
    <h2>The state of the art today</h2>
    <p class="stateprose">{html.escape(_state)}</p>
    {_cmp_html}
    <div class="dstats">
      <div><b>{d.get('n_unique',0)}</b><span>modern papers read</span></div>
      <div><b>{d.get('recent',0)}</b><span>since 2015</span></div>
      <div><b>{d.get('latest') or '—'}</b><span>most recent</span></div>
    </div>
    <p class="openq"><span class="lab">The paper’s open question</span>{html.escape(cur[1])}</p>
  </section>
  {cited_by_html(pid_s)}
  <section class="dsec">
    <h2>Questions put to Consensus</h2>
    <ul class="facets">{''.join('<li>'+html.escape(f['q'])+'</li>' for f in d.get('facets',[]))}</ul>
  </section>
  <section class="dsec">
    <h2>What modern research says <span class="cnt">({len(res)} papers)</span></h2>
    <div class="conslist">{''.join(paper_html(r) for r in res)}</div>
  </section>
  <footer class="cite">Modern literature retrieved via the <a href="https://consensus.app" target="_blank" rel="noopener">Consensus</a> API (June 2026) for this paper’s open questions; takeaways are Consensus’s one-line summaries of each study. A research aid, not a settled verdict.</footer>
</article>"""
        page(f"dossier/{pid}.html", title_en, "Rediscover", body,
             head="<style>" + DOSSIER_CSS + "</style>", prefix="../",
             desc=(f"{c.get('author') or ''} ({c.get('year')}). {_verdict}. " + (_state or ""))[:300])
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
.chip.v{background:rgba(205,185,138,.14);color:#e7d6ab}
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
  if(p.v) chips+='<span class="chip v">'+esc(shortT(p.v,46))+'</span>';
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
  if(p.dos) acts+='<a class="abtn" href="'+esc(p.dos)+'">☾ How it stands today</a>';
  acts+='<a class="abtn" href="'+esc(p.pdf)+'">The German original</a>';
  var sib=(rk==='_further'?pr.further:T.people[pr.id+'/'+rk].papers).filter(function(x){return String(x)!==String(aid);});
  var who=rk==='_further'?'this group':T.people[pr.id+'/'+rk].name;
  return heroHTML({acc:pr.accent,bg:img(p,'c'),plate:img(p,'d'),pw:p.img.w,ph:p.img.h,alt:p.kind==='titlepage'?'The paper\'s title page':'A figure from the paper',
      kick:p.year+' · '+esc(pr.title),title:p.t})+
    '<div class="art" style="--acc:'+pr.accent+'">'+(p.de&&p.de!==p.t?'<p class="de">'+esc(p.de)+'</p>':'')+
    '<p class="au">'+esc(p.au)+'</p>'+note+(p.text?'<p class="body">'+esc(p.text)+'</p>':'')+
    (p.v?'<div class="verd"><span class="lab">Today</span><span class="chip v">'+esc(p.v)+'</span>'+(p.st?'<span class="chip">'+esc(p.st)+(p.sbi?' · SBI '+p.sbi:'')+'</span>':'')+'</div>':'')+
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
    A, SYN, SENS = ld("consensus_all.json"), ld("consensus_synthesis.json"), ld("sensitivity.json")
    METH = ld("methodology.json")
    STOPS = {}
    skip = set(TT.get("bio_stops", []))   # stops about a person, not about the paper they point at
    for s in (ld("tour.json").get("stops") or []):        # the curated, fact-checked stop texts
        if s["id"] in skip:
            continue
        STOPS.setdefault(s.get("pid") or s.get("slug"), s)
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
        sy = SYN.get(ps) or {}; a = A.get(ps) or {}
        stop = STOPS.get(pid) or STOPS.get(slug_of.get(pid))
        if stop:
            text = stop["body"]
        elif sy.get("comparison"):
            text = sy["comparison"]
        else:
            m = METH.get(ps) or {}
            text = m.get("finding") or m.get("whats_new") or ""
        # keep the card text to a readable length, cut at a sentence
        if len(text) > 520:
            cutat = text.rfind(". ", 0, 520)
            text = text[:cutat + 1] if cutat > 200 else text[:517] + "…"
        s = SENS.get(ps)
        pk = (pics.get(ps) or {}).get("kind", "titlepage")
        papers[ps] = dict(
            id=pid, year=c["year"], t=c.get("title_en") or c.get("title") or "",
            de=c.get("title") or "", au=c.get("author_full") or c.get("author") or "",
            img=img, kind=pk, text=text,
            v=sy.get("verdict") or "", st=a.get("status") or "",
            sbi=a.get("sbi") if a.get("sleeping") else None,
            sens=({"c": s["category"], "s": s.get("short", ""), "sev": s.get("severity", "medium")} if s else None),
            read=("papers/%s.html" % read_for[pid]) if pid in read_for else None,
            dos=("dossier/%d.html" % pid) if ps in A else None,
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
    cat_by_id = {c["id"]: c for c in catalog}
    _sp = os.path.join(ROOT, "legacy_data", "citation_summaries.json")
    SUMM = json.load(open(_sp, encoding="utf-8")) if os.path.exists(_sp) else {}
    # Discover cross-link: which papers have a dossier, and their verdict
    _ap = os.path.join(ROOT, "legacy_data", "consensus_all.json")
    _A = json.load(open(_ap, encoding="utf-8")) if os.path.exists(_ap) else {}
    _synp = os.path.join(ROOT, "legacy_data", "consensus_synthesis.json")
    _SYN = json.load(open(_synp, encoding="utf-8")) if os.path.exists(_synp) else {}
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
        # (Legacy panel removed — its content now lives in the Discover dossier.)
        # connections panel: author bio(s), this paper's rediscovery card, related papers (same organism)
        auth_links = "".join(
            '<a class="cnchip" href="../authors.html#a-%s">%s &rarr;</a>' % (html.escape(k), html.escape(nm))
            for k, nm in pid2auth.get(pid, []))
        redis_link = ('<p class="ck">Rediscovery</p>'
                      '<a class="cnredis" href="../dossier/%d.html">Modern state of the field &rarr;</a>' % pid
                      ) if (lg.get("rediscovery") and str(pid) in _A) else ""
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
        _dd = _A.get(str(_pid)) or {}
        _dv = (_SYN.get(str(_pid)) or {}).get("verdict") or ""
        _doss_btn = ('<a class="btn" href="../dossier/%d.html">☾ Discover dossier</a>' % _pid) if _dd else ''
        _doss_chip = ('<span class="badge dverd">%s%s</span>' % (
            html.escape(_dd.get("status") or ""),
            (" · SBI %s" % _dd.get("sbi")) if _dd.get("sleeping") else "")) if _dd.get("status") else ''
        _doss_line = ('<p class="dverdline">☾ <b>Today:</b> %s <a href="../dossier/%d.html">see the full dossier →</a></p>'
                      % (html.escape(_dv), _pid)) if _dv else ''
        body = f"""
<article class="reading">
  <p class="kicker"><a href="../catalog.html">Catalog</a> · BVA · {t['year']}</p>
  <h1>{html.escape(t['title_en'])}</h1>
  <p class="detitle">{html.escape(t['title_de'])}</p>
  <p class="byline">{html.escape(t['author'])} · {html.escape(t['journal'])} · DOI {doi_a}</p>
  <div class="badges">{layer_badge(c['layer'])} {('<span class=badge org>'+html.escape(c['organism'])+'</span>') if c['organism'] else ''} {'<span class="badge wip">in progress</span>' if wip else '<span class="badge done">full text</span>'} {_doss_chip}</div>
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
@media(max-width:860px){.cols{grid-template-columns:1fr}.toc{position:static}.charts{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.rpanes{grid-template-columns:1fr}nav a{margin-left:12px}.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}#cat th{position:static}}
"""
    os.makedirs(os.path.join(SITE, "assets"), exist_ok=True)
    open(os.path.join(SITE, "assets", "style.css"), "w", encoding="utf-8").write(css)

def write_js():
    catalog_js = r"""
(function(){
var D=window.CATALOG||[];
var q=document.getElementById('q'),layer=document.getElementById('layer'),
phen=document.getElementById('phen'),tonly=document.getElementById('tonly'),
ronly=document.getElementById('ronly'),sort=document.getElementById('sort'),
statusSel=document.getElementById('status'),
tb=document.querySelector('#cat tbody'),count=document.getElementById('count');
// Discover cross-link: verdict + status + sleeping-beauty index, keyed by paper id
var DI=window.DISCIDX||{};
var SCLS={'Sleeping Beauty':'cst-sb','Quiet Classic':'cst-qc','Living Legacy':'cst-ll','Stirring':'cst-st','Contested Legacy':'cst-cl','Rightly Rested':'cst-rr'};
function di(c){return DI[c.id]||null;}
var ph={};D.forEach(function(c){(c.phenomena||[]).forEach(function(p){ph[p]=(ph[p]||0)+1})});
Object.keys(ph).sort().forEach(function(p){var o=document.createElement('option');o.value=p;o.textContent=p+' ('+ph[p]+')';phen.appendChild(o)});
var method=document.getElementById('method'),METH=window.METH||{};
var MLAB={"Regeneration & restitution":"Regeneration","Transplantation & grafting":"Transplantation","Endocrine & sex manipulation":"Endocrine/sex","Inheritance & breeding":"Inheritance","Colour change & pigment":"Colour change","Environmental modification":"Environment","Quantitative growth & biometry":"Growth/biometry","Developmental mechanics (egg/embryo)":"Dev. mechanics","Functional physiology & behaviour":"Physiology","Morphology, histology & biochemistry":"Morphology"};
function mcl(c){var m=METH[c.id];return m?(m.cluster||''):'';}
var ms={};D.forEach(function(c){var m=mcl(c);if(m)ms[m]=(ms[m]||0)+1;});
Object.keys(ms).sort().forEach(function(k){var o=document.createElement('option');o.value=k;o.textContent=(MLAB[k]||k)+' ('+ms[k]+')';method.appendChild(o);});
function esc(s){return (s||'').replace(/[&<>]/g,function(m){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[m]})}
// --- search-term highlighting: applied to ALREADY-ESCAPED html, so it can never break markup ---
function hlEsc(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function hl(escaped,term){
  if(!term)return escaped;
  var t=String(term).trim(); if(t.length<2)return escaped;
  var parts=t.split(/\s+/).filter(function(x){return x.length>1;}).map(hlEsc);
  if(!parts.length)return escaped;
  // never match inside a tag or an &entity;
  var re=new RegExp('(?![^<]*>)(?![^&;]*;)('+parts.join('|')+')','gi');
  return escaped.replace(re,'<mark class="hlt">$1</mark>');
}
function row(c){
 var d=di(c);
 var Q=(q.value||'').trim();
 var read;
 if(c.has_translation){read='<a href="papers/'+c.slug+'.html"><span class="dot on"></span>English</a><br><a href="reader.html?id='+c.id+'">German</a>';}
 else {read='<a href="reader.html?id='+c.id+'">Read original</a>';}
 if(d)read+='<br><a class="dosslink" href="dossier/'+c.id+'.html">☾ Dossier</a>';
 var lay=c.layer?('<span class="badge l'+c.layer+'">L'+c.layer+'</span>'):'';
 var rd=c.rediscovery?' <span class="rd">◆ rediscovery</span>':'';
 var today='—';
 if(d){
  today='<a class="cstat '+(SCLS[d.st]||'cst-rr')+'" href="dossier/'+c.id+'.html" title="'+esc(d.v||'')+'">'+esc(d.st)+'</a>'
   +(d.sb?('<span class="csbi">☾ '+d.sbi+'</span>'):'')
   +(d.v?('<div class="cverd">'+esc(d.v)+'</div>'):'');
 }
 return '<tr class="crow" data-id="'+c.id+'"><td>'+c.year+'</td><td>'+hl(esc(c.author).replace(/([\/;,])\s*/g,'$1\u200b'),Q)+'</td>'+
 '<td><div class="ti">'+hl(esc(c.title_en||c.title),Q)+'</div>'+((c.title&&c.title!==c.title_en)?'<div class="de">('+hl(esc(c.title),Q)+')</div>':'')+'</td>'+
 '<td><em>'+hl(esc(c.organism),Q)+'</em>'+rd+'</td>'+
 '<td class="meth">'+esc(MLAB[mcl(c)]||mcl(c)||'—')+((METH[c.id]&&METH[c.id].full)?' <span class="mfull" title="full methodology summary">●</span>':'')+'</td>'+
 '<td>'+lay+'</td><td class="num">'+(c.citations||0)+'</td><td class="today">'+today+'</td><td>'+read+'</td></tr>';
}
function apply(){
 var t=(q.value||'').toLowerCase(),L=layer.value,P=phen.value,M=method.value,S=statusSel?statusSel.value:'';
 var r=D.filter(function(c){
  var d=di(c);
  if(L&&String(c.layer)!==L)return false;
  if(P&&(c.phenomena||[]).indexOf(P)<0)return false;
  if(M&&mcl(c)!==M)return false;
  if(S&&(!d||d.st!==S))return false;
  if(tonly.checked&&!c.has_translation)return false;
  if(ronly.checked&&!(d&&d.sb))return false;
  if(t){var hay=(c.author+' '+c.title+' '+(c.title_en||'')+' '+(c.organism||'')).toLowerCase();if(hay.indexOf(t)<0)return false;}
  return true;});
 var s=sort.value;
 r.sort(function(a,b){
  if(s==='year')return a.year-b.year||a.id-b.id;
  if(s==='-year')return b.year-a.year;
  if(s==='-cit')return (b.citations||0)-(a.citations||0);
  if(s==='-sbi'){var da=di(a),db=di(b);return ((db&&db.sbi)||0)-((da&&da.sbi)||0);}
  if(s==='author')return a.author.localeCompare(b.author);
  if(s==='method')return (mcl(a)||'~').localeCompare(mcl(b)||'~')||a.year-b.year;
  return 0;});
 tb.innerHTML=r.map(row).join('');
 count.textContent=r.length+' of '+D.length+' papers';
}
[q,layer,phen,method,sort].forEach(function(e){e.addEventListener('input',apply)});
if(statusSel)statusSel.addEventListener('change',apply);
[tonly,ronly].forEach(function(e){e.addEventListener('change',apply)});
tb.addEventListener('click',function(e){if(e.target.closest('a'))return;var tr=e.target.closest('tr');if(tr&&tr.dataset.id)location.href='legacy.html?id='+tr.dataset.id;});
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
    legacy_js = r"""
(function(){
var C=window.CATALOG||[],L=window.LEGACY||{};
var byId={};C.forEach(function(c){byId[c.id]=c});
var q=document.getElementById('q'),conv=document.getElementById('conv'),
layer=document.getElementById('layer'),ronly=document.getElementById('ronly'),
list=document.getElementById('list'),count=document.getElementById('count');
var cv={};C.forEach(function(c){if(c.convergence)cv[c.convergence]=(cv[c.convergence]||0)+1});
Object.keys(cv).sort().forEach(function(k){var o=document.createElement('option');o.value=k;o.textContent=k;conv.appendChild(o)});
function esc(s){return (s||'').replace(/[&<>]/g,function(m){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[m]})}
function hlEsc(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function hl(escaped,term){
  if(!term)return escaped;
  var t=String(term).trim(); if(t.length<2)return escaped;
  var parts=t.split(/\s+/).filter(function(x){return x.length>1;}).map(hlEsc);
  if(!parts.length)return escaped;
  var re=new RegExp('(?![^<]*>)(?![^&;]*;)('+parts.join('|')+')','gi');
  return escaped.replace(re,'<mark class="hlt">$1</mark>');
}

var PID=new URLSearchParams(location.search).get('id');
if(PID){renderPaper(parseInt(PID,10));return;}
function renderPaper(id){
 var main=document.querySelector('main'),c=byId[id];
 ['.layers','.filters'].forEach(function(s){var e=main.querySelector(s);if(e)e.style.display='none';});
 var cn=document.getElementById('count');if(cn)cn.style.display='none';
 var lede=main.querySelector('.lede');if(lede)lede.style.display='none';
 var h1=main.querySelector('h1');if(h1)h1.textContent='Article dossier';
 if(!c){document.getElementById('list').innerHTML='<p class="muted">Paper not found. <a href="legacy.html">Back to the legacy explorer</a>.</p>';return;}
 document.title=c.author+' '+c.year+' — legacy · Vienna Vivarium';
 var arr=(window.CITATIONS&&window.CITATIONS[id])||[],lg=L[id]||{},NT=window.NOTES||{};
 var sci=arr.filter(function(x){return !x.h;}),hist=arr.filter(function(x){return x.h;});
 var en=c.has_translation?('<a class="btn" href="papers/'+c.slug+'.html">Read English translation →</a>'):'';
 var _di=(window.DISCIDX||{})[id];
 var doss=_di?('<a class="btn" href="dossier/'+id+'.html">☾ Discover dossier</a>'):'';
 var vchip=_di?(' <span class="badge dverd" title="'+esc(_di.v||'')+'">'+esc(_di.st)+(_di.sb?(' · SBI '+_di.sbi):'')+'</span>'):'';
 var head='<p class="kicker"><a href="legacy.html">‹ Legacy explorer</a> · '+esc(c.convergence||'')+'</p>'+
  '<h2 style="font-family:Georgia,serif;font-size:23px;margin:.1em 0">'+esc(c.title_en||c.title)+'</h2>'+
  ((c.title&&c.title!==c.title_en)?'<p style="font-style:italic;color:var(--muted);margin:.1em 0">('+esc(c.title)+')</p>':'')+
  '<p class="sub" style="font-size:14px;color:#4a463f">'+esc(c.author)+' · '+c.year+(c.organism?' · <em>'+esc(c.organism)+'</em>'+(lg.modern?' (now <em>'+esc(lg.modern)+'</em>)':''):'')+(c.layer?' · <span class="badge l'+c.layer+'">Layer '+c.layer+'</span>':'')+(c.rediscovery?' <span class="badge redis">rediscovery target</span>':'')+vchip+'</p>'+
  ((_di&&_di.v)?('<p class="dverdline">☾ <b>Today:</b> '+esc(_di.v)+'</p>'):'')+
  '<div class="actionbar" style="margin:12px 0"><a class="btn primary" href="reader.html?id='+id+'">Read original (PDF)</a>'+en+doss+(c.doi?'<a class="btn" target="_blank" href="https://doi.org/'+c.doi+'">DOI ↗</a>':'')+'</div>';
 function it(x){var note=NT[id+':'+x.k]||'';var doi=x.d?(' · <a target="_blank" href="https://doi.org/'+x.d+'">doi</a>'):'';
  var vr=(window.VERIFIED&&window.VERIFIED[id+':'+x.k])?' <span title="Written from the citing work\'s full text, read via the publisher or an open archive" style="background:#1d6e56;color:#fff;border-radius:4px;padding:1px 6px;font-size:10px;font-weight:600;white-space:nowrap">✓ verified from source</span>':'';
  return '<div class="litem"><div class="ti">'+esc(x.et||x.t||'(untitled)')+'</div>'+
   '<div class="sub">'+esc(x.a||'')+' · '+(x.y||'')+(x.s?' · '+esc(x.s):'')+(x.h?' · <span class="badge wip">historiographic</span>':'')+doi+vr+'</div>'+
   (note?'<p style="margin:7px 0 0;font-size:13.5px;line-height:1.6">'+esc(note)+'</p>':'')+'</div>';}
 var M=(window.METH&&window.METH[id])||{},F=M.full,methHtml='';
 if(F){var tg=(F.methods||[]).map(function(t){return '<span class="badge">'+esc(t)+'</span>';}).join(' ');
  methHtml='<section class="methbox"><h3>Methodology</h3>'+
   '<p style="margin:.2em 0 8px"><span class="badge mcl">'+esc(F.method||M.cluster||'')+'</span> '+tg+'</p>'+
   '<dl class="mgrid"><dt>Manipulation</dt><dd>'+esc(F.manipulation||'')+'</dd>'+
   '<dt>Design</dt><dd>'+esc(F.design||'')+'</dd><dt>Readout</dt><dd>'+esc(F.readout||'')+'</dd>'+
   '<dt>Quantification</dt><dd>'+esc(F.quantification||'')+'</dd><dt>Scale</dt><dd>'+esc(F.scale||'')+'</dd>'+
   (F.n?'<dt>Sample</dt><dd>'+esc(F.n)+'</dd>':'')+'</dl>'+
   (F.finding?'<p class="mfind"><b>Key finding.</b> '+esc(F.finding)+'</p>':'')+
   (F.summary?'<p style="line-height:1.62">'+esc(F.summary)+'</p>':'')+'</section>';
 }else if(M.cluster){methHtml='<section class="methbox"><h3>Methodology</h3><p><span class="badge mcl">'+esc(M.cluster)+'</span> <span class="muted">— full methodological summary not yet written for this paper.</span></p></section>';}
 var out=head+methHtml;
 var sm=(window.SUMMARIES&&window.SUMMARIES[id])||'';
 if(sm)out+='<section style="margin:18px 0 0;padding:13px 16px;border-left:4px solid var(--accent2);background:#eef2f5;border-radius:8px"><h3 style="margin:.1em 0 .4em">How later science draws on this work</h3><p style="margin:0;line-height:1.62;font-size:14.5px">'+esc(sm)+'</p></section>';
 var disc='<p class="muted" style="font-size:12px;line-height:1.5;margin:18px 0 0;padding:8px 10px;border:1px solid var(--rule);border-radius:8px;background:#fbf9f3"><b>How to read these notes.</b> Each line below describes the most likely reason a work cites this paper, reconstructed from the citing work\'s title, topic and (where available) abstract — <em>not</em> from the citing passage itself, which is rarely digitised for this century-old literature. They are a guide to the citation\'s likely sense, not a verified quotation; the linked DOI is the primary source.</p>';
 if(!arr.length){out+='<p class="muted" style="margin-top:14px">No modern citations are recorded for this paper.</p>';}
 else{out+=disc+'<h3 style="margin:20px 0 8px">Cited by today — '+sci.length+' scientific work'+(sci.length!=1?'s':'')+'</h3><div class="legacy">'+sci.map(it).join('')+'</div>';
  if(hist.length)out+='<h3 style="margin:20px 0 8px">Historiographic mentions — '+hist.length+'</h3><div class="legacy">'+hist.map(it).join('')+'</div>';}
 document.getElementById('list').innerHTML=out;
}
function item(c){
 var lg=L[c.id]||{};var cites=(lg.citations||[]).slice(0,10);
 var cl=cites.map(function(x){return '<li>'+(x.year?x.year+' · ':'')+esc(x.author)+' — '+esc((x.title||'').slice(0,120))+(x.doi?' <a target=_blank href="https://doi.org/'+x.doi+'">doi</a>':'')+'</li>'}).join('');
 var link=c.has_translation?'<a href="papers/'+c.slug+'.html">English translation →</a>':'<a href="reader.html?id='+c.id+'">read original →</a>';
 var Q=(q.value||'').trim();
 return '<div class="litem"><div class="h"><div><div class="ti">'+hl(esc(c.title_en||c.title),Q)+'</div>'+
 ((c.title&&c.title!==c.title_en)?'<div class="de" style="font-style:italic;color:var(--muted);font-size:12.5px;margin:1px 0 2px">('+hl(esc(c.title),Q)+')</div>':'')+
 '<div class="sub">'+hl(esc(c.author),Q)+' · '+c.year+' · <em>'+hl(esc(c.organism),Q)+'</em>'+(lg.modern?' (now <em>'+esc(lg.modern)+'</em>)':'')+'</div></div>'+
 '<div style="text-align:right">'+(c.rediscovery?'<span class="badge redis">rediscovery target</span><br>':'')+(c.layer?'<span class="badge l'+c.layer+'">L'+c.layer+'</span>':'')+'</div></div>'+
 '<div class="kv"><span><b>'+(lg.cited_by_count||0)+'</b> cited today</span><span><b>'+(lg.n_parallels||0)+'</b> modern parallels</span><span>'+esc(c.convergence||'')+'</span></div>'+
 (cl?'<details><summary>Show modern citations</summary><ul class="cites">'+cl+'</ul></details>':'')+
 '<div style="margin-top:8px">'+link+'</div></div>';
}
function apply(){
 var t=(q.value||'').toLowerCase(),V=conv.value,Y=layer.value;
 var r=C.filter(function(c){
  if(ronly.checked&&!c.rediscovery)return false;
  if(V&&c.convergence!==V)return false;
  if(Y&&String(c.layer)!==Y)return false;
  if(t){var hay=(c.author+' '+c.title+' '+(c.organism||'')).toLowerCase();if(hay.indexOf(t)<0)return false;}
  return true;});
 r.sort(function(a,b){return (b.n_parallels||0)-(a.n_parallels||0)});
 list.innerHTML=r.map(item).join('');
 count.textContent=r.length+' papers';
}
[q,conv,layer].forEach(function(e){e.addEventListener('input',apply)});
ronly.addEventListener('change',apply);apply();
})();
"""
    analytics_js = r"""
(function(){
var D=window.CATALOG||[];
var ink='#211f1c',mut='#6f6a61',grid='#e4ddce';
Chart.defaults.font.family='-apple-system,Segoe UI,Roboto,sans-serif';Chart.defaults.color=mut;
function years(){var m={};D.forEach(function(c){m[c.year]=(m[c.year]||0)+1});
 var ys=[];for(var y=1902;y<=1945;y++)ys.push(y);return{labels:ys,data:ys.map(function(y){return m[y]||0})};}
var yr=years();
new Chart(cYear,{type:'bar',data:{labels:yr.labels,datasets:[{data:yr.data,backgroundColor:'#7a3b2e'}]},
 options:{plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:12}},y:{grid:{color:grid},ticks:{precision:0}}}}});
var lc={1:0,2:0,3:0,4:0};D.forEach(function(c){if(c.layer)lc[c.layer]++});
new Chart(cLayer,{type:'doughnut',data:{labels:['Layer 1','Layer 2','Layer 3','Layer 4'],
 datasets:[{data:[lc[1],lc[2],lc[3],lc[4]],backgroundColor:['#1d6e56','#355e7d','#9a6a1f','#b8b1a4']}]},
 options:{plugins:{legend:{position:'right'}}}});
var am={};D.forEach(function(c){am[c.author]=(am[c.author]||0)+1});
var top=Object.keys(am).map(function(k){return[k,am[k]]}).sort(function(a,b){return b[1]-a[1]}).slice(0,12);
new Chart(cAuth,{type:'bar',data:{labels:top.map(function(x){return x[0]}),datasets:[{data:top.map(function(x){return x[1]}),backgroundColor:'#355e7d'}]},
 options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{grid:{color:grid},ticks:{precision:0}},y:{grid:{display:false}}}}});
var cc=D.slice().sort(function(a,b){return (b.citations||0)-(a.citations||0)}).slice(0,12);
new Chart(cCit,{type:'bar',data:{labels:cc.map(function(c){return c.author+' '+c.year}),datasets:[{data:cc.map(function(c){return c.citations||0}),backgroundColor:'#7a3b2e'}]},
 options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{afterLabel:function(i){return (cc[i.dataIndex].title_en||cc[i.dataIndex].title||'').slice(0,70)}}}},scales:{x:{grid:{color:grid}},y:{grid:{display:false}}}}});
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
var _di=(window.DISCIDX||{})[id];
if(_di)acts+='<a class="btn" href="dossier/'+id+'.html">☾ Discover dossier</a>';
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
    open(os.path.join(a, "legacy.js"), "w").write(legacy_js)
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
