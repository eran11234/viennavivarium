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

YEARS = [c["year"] for c in catalog]
STATS = dict(papers=len(catalog), trans=len(translations),
             y0=min(YEARS), y1=max(YEARS),
             authors=len({c["author"] for c in catalog}),
             redis=sum(1 for c in catalog if c["rediscovery"]))

NAV = [("index.html", "Home"), ("catalog.html", "Catalog"),
       ("map.html", "Map"), ("translations.html", "Translations"),
       ("rediscovery.html", "Rediscover"), ("authors.html", "Authors"),
       ("legacy.html", "Legacy"), ("analytics.html", "Analytics"), ("about.html", "About")]

# ---------------------------------------------------------------- shell
def page(path, title, active, body, prefix="", head="", foot=""):
    nav = "".join(
        f'<a class="{"on" if active==h else ""}" href="{prefix}{href}">{h}</a>'
        for href, h in NAV)
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Vienna Vivarium in English</title>
<link rel="stylesheet" href="{prefix}assets/style.css">{head}
</head><body>
<header class="site"><div class="wrap nav">
<a class="brand" href="{prefix}index.html"><span class="b1">Vienna Vivarium</span><span class="b2">the BVA corpus in English</span></a>
<nav>{nav}</nav></div></header>
<main class="wrap">{body}</main>
<footer class="site"><div class="wrap">
<p>Biologische Versuchsanstalt (the “Vivarium”), Vienna · {STATS['papers']} papers, {STATS['y0']}–{STATS['y1']} · {STATS['trans']} English translations.</p>
<p class="muted">An orientation platform for researchers. Translations and corpus analysis are scholarly working documents; cite the original alongside the translation.</p>
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
    body = f"""
<section class="hero">
  <p class="kicker">An orientation platform for researchers</p>
  <h1>The Vienna Vivarium, in English</h1>
  <p class="lede">The Biologische Versuchsanstalt (1902–1945) was one of the first institutes for experimental biology. This platform opens its early publications to English-language researchers: a searchable catalog of <strong>{STATS['papers']} papers</strong> ({STATS['y0']}–{STATS['y1']}), full English <strong>translations</strong> with figures, the German originals, and a citation-<strong>legacy</strong> layer showing where this work still touches living science.</p>
  <div class="cta">
    <a class="btn primary" href="catalog.html">Browse the catalog</a>
    <a class="btn" href="translations.html">Read translations</a>
    <a class="btn" href="legacy.html">Explore the legacy</a>
  </div>
</section>
<figure class="heroimg">
  <img src="assets/img/vivarium-building.jpg" alt="The Biologische Versuchsanstalt building in the Vienna Prater, with VIVARIUM inscribed on the façade" loading="lazy">
  <figcaption>The Biologische Versuchsanstalt — the “Vivarium” — in the Vienna Prater. Built in 1873 as an aquarium-exhibition hall, it became, from 1902, the world's first private institute for experimental biology. The name <em>VIVARIUM</em> is still legible on the façade.</figcaption>
</figure>
<section class="stats">
  <div><b>{STATS['papers']}</b><span>papers cataloged</span></div>
  <div><b>{STATS['trans']}</b><span>English translations</span></div>
  <div><b>{STATS['authors']}</b><span>authors</span></div>
  <div><b>{STATS['redis']}</b><span>rediscovery targets</span></div>
</section>
<section>
  <h2>Featured translations</h2>
  <div class="tgrid">{feat}</div>
</section>
<section class="how">
  <h2>How to use this platform</h2>
  <p>The <a href="catalog.html">Catalog</a> is the map of the whole corpus — filter by author, organism, phenomenon, or legacy depth, and jump to a paper's English translation (where one exists) or its German original. The <a href="translations.html">Translations</a> are full reading pages with the original plates and a side-by-side view against the scanned German. The <a href="legacy.html">Legacy</a> explorer surfaces the papers whose organisms are still studied today but whose original work goes uncited — the corpus's live edges. <a href="analytics.html">Analytics</a> shows the shape of the institute's output over four decades.</p>
</section>"""
    page("index.html", "Home", "Home", body)

# ---------------------------------------------------------------- catalog
def gen_catalog():
    body = """
<h1>Catalog</h1>
<p class="lede">All papers in the corpus. Search and filter; <strong>click any row to see the modern works that cite it</strong>, or use the Read column to open the translation or German original.</p>
<div class="filters">
  <input id="q" type="search" placeholder="Search author, title, organism…">
  <select id="layer"><option value="">Any legacy layer</option><option>1</option><option>2</option><option>3</option><option>4</option></select>
  <select id="phen"><option value="">Any phenomenon</option></select>
  <select id="method"><option value="">Any method</option></select>
  <label class="chk"><input type="checkbox" id="tonly"> Translated only</label>
  <label class="chk"><input type="checkbox" id="ronly"> Rediscovery targets</label>
  <select id="sort"><option value="year">Sort: year ↑</option><option value="-year">year ↓</option><option value="-cit">most cited</option><option value="author">author</option><option value="method">method</option></select>
</div>
<p id="count" class="muted"></p>
<div class="tablewrap"><table id="cat"><thead><tr>
<th>Year</th><th>Author</th><th>Title</th><th>Organism</th><th>Method</th><th>Legacy</th><th class="num">Cited</th><th>Read</th>
</tr></thead><tbody></tbody></table></div>
"""
    page("catalog.html", "Catalog", "Catalog", body,
         foot='<script src="data/site.js"></script><script src="data/methodology.js"></script><script src="data/catalog.js"></script><script src="assets/catalog.js"></script>')

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
         foot='<script src="data/catalog.js"></script><script src="data/legacy.js"></script><script src="data/citations.js"></script><script src="data/notes.js"></script><script src="data/summaries.js"></script><script src="data/methodology.js"></script><script src="assets/legacy.js"></script>')

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
<p>The <strong>Biologische Versuchsanstalt</strong> (BVA, the “Vivarium”) operated in Vienna's Prater from 1902 to 1945 — among the world's first institutions dedicated to experimental biology, founded by Hans Przibram, Leopold von Portheim, and Wilhelm Figdor. Its researchers studied regeneration, growth, inheritance, sex determination, and coloration across an unusually wide range of organisms.</p>
<h2>What this platform is</h2>
<p>An orientation layer for researchers who do not read German. It assembles, in one place: a searchable <strong>catalog</strong> of {STATS['papers']} papers ({STATS['y0']}–{STATS['y1']}); full English <strong>translations</strong> with the original figures; the scanned German <strong>originals</strong>; and a <strong>legacy</strong> analysis linking each paper to the modern works that cite it and to parallel research on the same organisms.</p>
<h2>How the translations were made</h2>
<p>Each German paper was OCR-corrected against the scanned source and translated in full, preserving numbered points, tables, and figure legends. Historical species names are kept as in the original, with modern equivalents noted (e.g. <em>Triton</em> → <em>Triturus</em>). Two translations remain in progress.</p>
<h2>How to cite</h2>
<p>Cite the original publication, noting the English translation and this platform as the access point, e.g.: <em>Author (Year), “Original German title,” Archiv … ; English translation, Vienna Vivarium in English.</em></p>
<h2>Sources &amp; data</h2>
<p>Citation and parallel-work data derive from OpenAlex. Corpus metadata, legacy layers, and convergence axes are part of the project's ongoing analysis and should be treated as scholarly working material.</p>
</div>"""
    page("about.html", "About", "About", body)

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
         foot='<script src="data/catalog.js"></script><script src="assets/reader.js"></script>')

# ---------------------------------------------------------------- legacy map
def gen_map():
    body = """
<h1>The legacy map</h1>
<p class="lede">Every paper the institute published, drawn as one network. Each dot is a paper, grouped by what it investigated and coloured by how deeply modern science still engages it. Hans Przibram's program — experiment, quantification, theory — ran across regeneration, growth, coloration, heredity, hormones, behaviour and more; in 1938 the Biologische Versuchsanstalt was destroyed and its findings scattered into the uneven afterlife this map charts. Hover a dot for its title; click it to open the paper and see the modern work that still carries it.</p>
<div class="legend" id="leg"></div>
<div class="mapctrl">
  <input id="q" type="search" placeholder="Search author, title, organism…">
  <select id="layer"><option value="">All legacy layers</option><option value="1">Layer 1 · same genus</option><option value="2">Layer 2 · same taxon</option><option value="3">Layer 3 · same phenomenon</option><option value="4">Layer 4 · logic only</option></select>
  <select id="phen"><option value="">All themes</option></select>
  <label class="chk"><input type="checkbox" id="ronly"> Rediscovery targets</label>
  <button class="btn" id="reset">Reset</button>
</div>
<div class="maplayout">
  <div class="mapwrap"><svg id="map" height="640" role="img" aria-label="Network of all 175 BVA papers grouped by research theme and coloured by legacy layer"></svg><div class="maptip" id="tip"></div></div>
  <aside class="mappanel" id="panel"><p class="muted"><b>Click any paper</b> to zoom in and open the modern works that cite it as cards on this panel — hover a card to find that work on the map. Scroll to zoom, drag to pan. Colour shows the legacy layer (see the <a href="legacy.html">Legacy</a> page); a dark ring marks a rediscovery target — an organism still studied today whose BVA original goes uncited. Dot size is modern citations.</p></aside>
</div>
"""
    page("map.html", "Map", "Map", body,
         head='<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>',
         foot='<script src="data/catalog.js"></script><script src="data/legacy.js"></script><script src="data/citations.js"></script><script src="data/notes.js"></script><script src="assets/map.js"></script>')

REDISC_CSS = r"""
.rstats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 8px}
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
.qedbtn{font-size:13px;border:1px solid var(--accent2);color:#fff;background:var(--accent2);border-radius:7px;padding:5px 11px;cursor:pointer;margin-left:auto}
.qedbtn:hover{background:#2b4d68}
.qedout{display:none;margin-top:11px;font-size:13.5px;line-height:1.5;border-left:3px solid var(--accent2);padding:9px 12px;background:#eef2f5;border-radius:6px}
.qpend b{color:var(--accent2)}
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
   +'<div class="dc-links">'+links(c)+'<button class="qedbtn" onclick="qedAnalyze('+pid+')">☾ Is this still open? · check the literature</button></div>'
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

window.qedAnalyze=function(id){var out=document.getElementById('qed-'+id),q=R.qed||{},c=R.cards[id];
  out.style.display='block';
  if(!q.enabled||!q.endpoint){out.innerHTML='<div class="qpend"><b>Q.E.D. Science — not connected yet.</b> '+esc(q.pending_note||'')+'</div>';return;}
  out.innerHTML='<div class="qpend">Analyzing “'+esc(c.title)+'” with Q.E.D. Science…</div>';
  fetch(q.endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,title:c.title,author:c.author,year:c.year,doi:c.doi,organism:c.organism})})
   .then(function(r){return r.json();})
   .then(function(d){out.innerHTML='<div class="qres">'+esc(d.summary||d.analysis||JSON.stringify(d))+'</div>';})
   .catch(function(e){out.innerHTML='<div class="qpend">Q.E.D. request failed: '+esc(String(e))+'</div>';});};
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
        return ('<article class="acard%s" id="a-%s">' % (" feat" if not compact else "", html.escape(p["key"]))
                + '<div class="ahead"><h2>%s</h2>%s%s</div>' % (html.escape(p["name"]), yrs, role)
                + '<p class="abio">%s</p>' % html.escape(p["bio"])
                + '<div class="apapers"><span class="lab">%s</span> %s</div>' % (
                    ("Wrote" if n != 1 else "Wrote"), chips)
                + link + '</article>')

    feat = [p for p in A["people"] if p["featured"]]
    rest = [p for p in A["people"] if not p["featured"]]
    body = ('<p class="kicker">The people behind the corpus</p>'
            '<h1>Authors of the Vivarium</h1>'
            '<p class="lede">' + A["intro"] + '</p>'
            '<div class="astats"><div><b>%d</b><span>contributors</span></div>'
            '<div><b>%d</b><span>principal figures</span></div>'
            '<div><b>%d</b><span>papers, 1904–1930</span></div></div>'
            % (A["stats"]["people"], A["stats"]["featured"], STATS["papers"])
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
.acard{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:16px 17px}
.acard.feat{border-left:4px solid var(--accent)}
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
            pdf=c.get("pdf"), doi=c.get("doi"))

    cards = {}
    for g in R["groups"]:
        for pid in g["papers"]:
            cards[str(pid)] = card(pid)
    maxgap = max((c["gap"] for c in cards.values()), default=63)
    zero = sum(1 for c in cards.values() if c["citations"] == 0)
    ob = cat_by_id.get(R.get("obituary"))
    obit = dict(id=ob["id"], author=ob["author"], year=ob["year"],
                title=(ob.get("title") or "").replace("�", "ä")) if ob else None
    data = dict(intro=R["intro"], qed=R["qed"], groups=R["groups"], cards=cards,
                unfinished=R["unfinished"], obituary=obit,
                stats=dict(targets=len(cards), systems=len(R["groups"]),
                           zero=zero, programs=len(R["unfinished"]), maxgap=maxgap))
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
        '</div>'
        '<div class="qbanner"><span class="qi">☾</span><div><b>Is it still open — or a sleeping beauty?</b> '
        'For each paper, the “Still open today?” line asks whether the question it touches remains unresolved, or '
        'whether the paper is a <em>sleeping beauty</em> — a forgotten early answer to something science is still asking. '
        'A green <span class="citetag wake" style="margin:0">re-cited · waking</span> tag means modern work (2010 on) has begun citing it again; a grey '
        '<span class="citetag dorm" style="margin:0">dormant</span> tag means it has gone quiet. '
        'The per-card button can be wired to the <b>Consensus</b> API to check this against today\'s literature live '
        '(a static site needs a small key-holding proxy for that — see below).</div></div>'
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
        '<h3 style="margin:.1em 0 .4em">Connecting Consensus</h3>'
        '<p class="muted" style="font-size:13.5px;line-height:1.6;max-width:80ch;margin:0">'
        'Consensus (<a href="https://consensus.app/home/api/" target="_blank" rel="noopener">consensus.app/api</a>) offers a '
        'developer API — a <code>GET /v1/quick_search</code> endpoint that returns ranked, peer-reviewed papers for a question '
        '(≈$0.10/call, access by application) — plus an MCP server. It is a natural fit for the “Still open today?” question: '
        'feed it each paper&rsquo;s open question and read back whether current literature has settled it. '
        'Two ways to wire it here: <b>(1) build-time</b> — run the queries once when the site is built (where the API key is '
        'safe) and bake the verdicts into the page, with no per-visitor cost or key exposure; or <b>(2) live</b> — the per-card '
        'button calls a tiny serverless proxy (a Cloudflare Worker or Netlify function) that holds the key, since a key must '
        'never sit in this static page&rsquo;s JavaScript. Give me a key and I&rsquo;ll wire whichever you prefer.</p></section>'
        '<p class="obit muted"></p>')

    page("rediscovery.html", "Rediscover", "Rediscover", body,
         head="<style>" + REDISC_CSS + "</style>",
         foot='<script src="data/summaries.js"></script><script src="data/rediscovery.js"></script><script>' + REDISC_JS + '</script>')
    print("rediscovery.html:", len(cards), "cards |", len(R["groups"]), "groups |",
          len(R["unfinished"]), "programs | zero-cite:", zero)


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
        # legacy panel
        cites = lg.get("citations", [])[:8]
        clist = "".join(
            f'<li>{ (str(x["year"])+" · ") if x.get("year") else ""}{html.escape(x.get("author") or "")} — {html.escape((x.get("title") or "")[:120])}'
            f'{" <a href=https://doi.org/"+x["doi"]+">doi</a>" if x.get("doi") else ""}</li>'
            for x in cites)
        redis = '<span class="badge redis">rediscovery target</span>' if lg.get("rediscovery") else ""
        lp = f"""<section class="legacypanel">
        <h2>Legacy</h2>
        <div class="lstats">
          <div><b>{lg.get('cited_by_count',0)}</b><span>cited today</span></div>
          <div><b>{lg.get('n_parallels',0)}</b><span>modern parallels</span></div>
          <div><b>{html.escape(lg.get('modern') or c.get('genus') or '—')}</b><span>organism now</span></div>
        </div>
        {redis}
        {('<div style="margin:10px 0;padding:11px 13px;border-left:3px solid var(--accent2);background:#eef2f5;border-radius:7px"><h3 style="margin:.1em 0 .35em;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--accent2)">How later science draws on this work</h3><p style="margin:0;font-size:13.5px;line-height:1.6">'+html.escape(SUMM[str(pid)])+'</p></div>') if str(pid) in SUMM else ''}
        {'<h3>Cited by today</h3><ul class="cites">'+clist+'</ul>' if clist else '<p class="muted">No modern citations recorded.</p>'}
        </section>"""
        # connections panel: author bio(s), this paper's rediscovery card, related papers (same organism)
        auth_links = "".join(
            '<a class="cnchip" href="../authors.html#a-%s">%s &rarr;</a>' % (html.escape(k), html.escape(nm))
            for k, nm in pid2auth.get(pid, []))
        redis_link = ('<p class="ck">Rediscovery</p>'
                      '<a class="cnredis" href="../rediscovery.html#card-%d">Why this is a rediscovery target &rarr;</a>' % pid
                      ) if lg.get("rediscovery") else ""
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
        body = f"""
<article class="reading">
  <p class="kicker"><a href="../catalog.html">Catalog</a> · BVA · {t['year']}</p>
  <h1>{html.escape(t['title_en'])}</h1>
  <p class="detitle">{html.escape(t['title_de'])}</p>
  <p class="byline">{html.escape(t['author'])} · {html.escape(t['journal'])} · DOI {doi_a}</p>
  <div class="badges">{layer_badge(c['layer'])} {('<span class=badge org>'+html.escape(c['organism'])+'</span>') if c['organism'] else ''} {'<span class="badge wip">in progress</span>' if wip else '<span class="badge done">full text</span>'}</div>
  <div class="actionbar">
    <a class="btn primary" href="{reader_sxs}">⇆ Read German side-by-side</a>
    <a class="btn" href="{reader_one}">German reader</a>
    <a class="btn" href="{pdf_rel}" download>↓ Download PDF</a>
    {('<a class="btn" href="https://doi.org/'+doi+'" target="_blank">DOI ↗</a>') if doi else ''}
  </div>
  {notice}
  <div class="cols">
    <div class="text">{frag}</div>
    <aside class="toc">{('<div class=tocbox><p>On this page</p>'+toc_html+'</div>') if toc_html else ''}{lp}{connect}</aside>
  </div>
  <footer class="cite">Cite: {html.escape(t['author'])} ({t['year']}), “{html.escape(t['title_de'])},” {html.escape(t['journal'])}. English translation, Vienna Vivarium in English.</footer>
</article>"""
        page(f"papers/{ps}.html", t["title_en"][:60], "Translations", body, prefix="../")

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
    imgsrc = os.path.join(ROOT, "legacy_data", "img")
    if os.path.isdir(imgsrc):
        imgout = os.path.join(SITE, "assets", "img"); os.makedirs(imgout, exist_ok=True)
        for f in glob.glob(os.path.join(imgsrc, "*")):
            _cp(f, os.path.join(imgout, os.path.basename(f)))

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
footer.site{margin-top:60px;border-top:1px solid var(--rule);padding:26px 0;font-size:13.5px;color:var(--muted)}
footer.site p{margin:.3em 0}
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
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:34px 0}
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
table#cat{border-collapse:collapse;width:100%;font-size:14px}
#cat th,#cat td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--rule);vertical-align:top}
#cat th{position:sticky;top:62px;z-index:5;background:var(--card);font-size:12.5px;letter-spacing:.03em;text-transform:uppercase;color:var(--muted);cursor:default;box-shadow:0 1px 0 var(--rule)}
#cat td.num,#cat th.num{text-align:right}
#cat tr:hover td{background:#fbf8f2}
#cat tbody tr{cursor:pointer}
#cat .ti{font-weight:500}#cat .de{color:var(--muted);font-style:italic;font-size:13px}
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
.cols{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:34px;margin-top:18px}
.text{font-family:Georgia,"Times New Roman",serif;font-size:17px;line-height:1.72;max-width:70ch}
.text h2{font-size:21px;margin-top:1.5em}.text h3{font-size:17px}
.text img{max-width:100%;height:auto;display:block;margin:14px auto;border:1px solid var(--rule);background:#fff;padding:4px}
.text table{border-collapse:collapse;margin:14px 0;font-size:14px}
.text th,.text td{border:1px solid var(--rule);padding:5px 9px}
.text blockquote{border-left:3px solid var(--rule);margin:14px 0;padding:4px 16px;color:#534e46;background:#fbf8f2}
.toc{align-self:start;position:sticky;top:74px}
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
.maplayout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:16px;align-items:start}
.mapwrap{position:relative;border:1px solid var(--rule);border-radius:10px;background:var(--card);overflow:hidden}
.mapwrap::before{content:"";position:absolute;inset:0;z-index:0;background:url(img/prater-map-1883.jpg) center/cover no-repeat;opacity:.20;filter:sepia(.35) saturate(.65) contrast(1.02);pointer-events:none}
.mapwrap::after{content:"the prater, vienna · 1883";position:absolute;right:9px;bottom:7px;z-index:2;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);background:rgba(247,244,238,.7);padding:1px 6px;border-radius:4px;pointer-events:none}
#map{width:100%;display:block;cursor:grab;position:relative;z-index:1}
#map:active{cursor:grabbing}
.maptip{z-index:3}
.mapctrl{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.mapctrl input[type=search],.mapctrl select{padding:7px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--card);font-size:13.5px}
.mapctrl #q{flex:1;min-width:200px}
.mappanel{border:1px solid var(--rule);border-radius:10px;background:var(--card);padding:14px 16px;font-size:14px;position:sticky;top:78px;max-height:82vh;overflow:auto}
.mappanel h3{font-family:Georgia,serif;font-size:17px;margin:.1em 0 .3em;line-height:1.25}
.mappanel .pde{font-style:italic;color:var(--muted);font-size:13px;margin:0 0 6px}
.mappanel .pmeta{font-size:13px;color:#4a463f;margin:4px 0}
.mappanel .pcites{font-size:12.5px;padding-left:16px;margin:6px 0}.mappanel .pcites li{margin:3px 0}
.maptip{position:absolute;pointer-events:none;background:#211f1c;color:#fff;font-size:12px;padding:5px 8px;border-radius:6px;opacity:0;transition:opacity .08s;max-width:240px;z-index:9}
text.cl{font-size:13px;fill:#3c3833;font-family:-apple-system,sans-serif;letter-spacing:.03em;font-weight:600}
rect.clbg{fill:var(--paper);opacity:.85}
text.blab{font-size:10px;fill:#6f6a61;font-family:-apple-system,sans-serif;pointer-events:none}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin:6px 0 2px;color:#4a463f}
.legend b{font-weight:600}
.legend .it{display:inline-flex;align-items:center;gap:6px;cursor:default}
.dotc{width:11px;height:11px;border-radius:50%;display:inline-block}
text.sat{font-size:10px;fill:var(--muted);font-family:-apple-system,sans-serif}
@media(max-width:860px){.cols{grid-template-columns:1fr}.toc{position:static}.charts{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.rpanes{grid-template-columns:1fr}.maplayout{grid-template-columns:1fr}.mappanel{position:static;max-height:none}nav a{margin-left:12px}}
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
tb=document.querySelector('#cat tbody'),count=document.getElementById('count');
var ph={};D.forEach(function(c){(c.phenomena||[]).forEach(function(p){ph[p]=(ph[p]||0)+1})});
Object.keys(ph).sort().forEach(function(p){var o=document.createElement('option');o.value=p;o.textContent=p+' ('+ph[p]+')';phen.appendChild(o)});
var method=document.getElementById('method'),METH=window.METH||{};
var MLAB={"Regeneration & restitution":"Regeneration","Transplantation & grafting":"Transplantation","Endocrine & sex manipulation":"Endocrine/sex","Inheritance & breeding":"Inheritance","Colour change & pigment":"Colour change","Environmental modification":"Environment","Quantitative growth & biometry":"Growth/biometry","Developmental mechanics (egg/embryo)":"Dev. mechanics","Functional physiology & behaviour":"Physiology","Morphology, histology & biochemistry":"Morphology"};
function mcl(c){var m=METH[c.id];return m?(m.cluster||''):'';}
var ms={};D.forEach(function(c){var m=mcl(c);if(m)ms[m]=(ms[m]||0)+1;});
Object.keys(ms).sort().forEach(function(k){var o=document.createElement('option');o.value=k;o.textContent=(MLAB[k]||k)+' ('+ms[k]+')';method.appendChild(o);});
function esc(s){return (s||'').replace(/[&<>]/g,function(m){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[m]})}
function row(c){
 var read;
 if(c.has_translation){read='<a href="papers/'+c.slug+'.html"><span class="dot on"></span>English</a> · <a href="reader.html?id='+c.id+'">German</a>';}
 else {read='<a href="reader.html?id='+c.id+'">Read original</a>';}
 var lay=c.layer?('<span class="badge l'+c.layer+'">L'+c.layer+'</span>'):'';
 var rd=c.rediscovery?' <span class="rd">◆ rediscovery</span>':'';
 return '<tr class="crow" data-id="'+c.id+'"><td>'+c.year+'</td><td>'+esc(c.author)+'</td>'+
 '<td><div class="ti">'+esc(c.title_en||c.title)+'</div>'+((c.title&&c.title!==c.title_en)?'<div class="de">('+esc(c.title)+')</div>':'')+'</td>'+
 '<td><em>'+esc(c.organism)+'</em>'+rd+'</td>'+
 '<td class="meth">'+esc(MLAB[mcl(c)]||mcl(c)||'—')+((METH[c.id]&&METH[c.id].full)?' <span class="mfull" title="full methodology summary">●</span>':'')+'</td>'+
 '<td>'+lay+'</td><td class="num">'+(c.citations||0)+'</td><td>'+read+'</td></tr>';
}
function apply(){
 var t=(q.value||'').toLowerCase(),L=layer.value,P=phen.value,M=method.value;
 var r=D.filter(function(c){
  if(L&&String(c.layer)!==L)return false;
  if(P&&(c.phenomena||[]).indexOf(P)<0)return false;
  if(M&&mcl(c)!==M)return false;
  if(tonly.checked&&!c.has_translation)return false;
  if(ronly.checked&&!c.rediscovery)return false;
  if(t){var hay=(c.author+' '+c.title+' '+(c.title_en||'')+' '+(c.organism||'')).toLowerCase();if(hay.indexOf(t)<0)return false;}
  return true;});
 var s=sort.value;
 r.sort(function(a,b){
  if(s==='year')return a.year-b.year||a.id-b.id;
  if(s==='-year')return b.year-a.year;
  if(s==='-cit')return (b.citations||0)-(a.citations||0);
  if(s==='author')return a.author.localeCompare(b.author);
  if(s==='method')return (mcl(a)||'~').localeCompare(mcl(b)||'~')||a.year-b.year;
  return 0;});
 tb.innerHTML=r.map(row).join('');
 count.textContent=r.length+' of '+D.length+' papers';
}
[q,layer,phen,method,sort].forEach(function(e){e.addEventListener('input',apply)});
[tonly,ronly].forEach(function(e){e.addEventListener('change',apply)});
tb.addEventListener('click',function(e){if(e.target.closest('a'))return;var tr=e.target.closest('tr');if(tr&&tr.dataset.id)location.href='legacy.html?id='+tr.dataset.id;});
apply();
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
 var head='<p class="kicker"><a href="legacy.html">‹ Legacy explorer</a> · '+esc(c.convergence||'')+'</p>'+
  '<h2 style="font-family:Georgia,serif;font-size:23px;margin:.1em 0">'+esc(c.title_en||c.title)+'</h2>'+
  ((c.title&&c.title!==c.title_en)?'<p style="font-style:italic;color:var(--muted);margin:.1em 0">('+esc(c.title)+')</p>':'')+
  '<p class="sub" style="font-size:14px;color:#4a463f">'+esc(c.author)+' · '+c.year+(c.organism?' · <em>'+esc(c.organism)+'</em>'+(lg.modern?' (now <em>'+esc(lg.modern)+'</em>)':''):'')+(c.layer?' · <span class="badge l'+c.layer+'">Layer '+c.layer+'</span>':'')+(c.rediscovery?' <span class="badge redis">rediscovery target</span>':'')+'</p>'+
  '<div class="actionbar" style="margin:12px 0"><a class="btn primary" href="reader.html?id='+id+'">Read original (PDF)</a>'+en+(c.doi?'<a class="btn" target="_blank" href="https://doi.org/'+c.doi+'">DOI ↗</a>':'')+'</div>';
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
 return '<div class="litem"><div class="h"><div><div class="ti">'+esc(c.title_en||c.title)+'</div>'+
 ((c.title&&c.title!==c.title_en)?'<div class="de" style="font-style:italic;color:var(--muted);font-size:12.5px;margin:1px 0 2px">('+esc(c.title)+')</div>':'')+
 '<div class="sub">'+esc(c.author)+' · '+c.year+' · <em>'+esc(c.organism)+'</em>'+(lg.modern?' (now <em>'+esc(lg.modern)+'</em>)':'')+'</div></div>'+
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
    map_js = r"""
(function(){
if(typeof d3==='undefined'){return;}
var C=(window.CATALOG||[]).slice(), L=window.LEGACY||{};
function esc(s){return (s||'').replace(/[&<>"]/g,function(m){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]})}
var THEMES=[['Regeneration',/regenerat/],['Transplantation',/transplant|graft|implant/],
['Coloration',/colou?r|pigment|farb|chromat/],['Growth & form',/growth|wachstum|instar|moult|molt|größe|form/],
['Heredity',/inherit|hered|vererb|lamarck|bastard|hybrid/],['Sex & hormones',/sex|gonad|pubert|endocrin|hormon|intersex|zwitter|erotiz/],
['Environment',/temperature|environment|klima|humid|gravit|light|medium/],['Behaviour',/behav|instinct|lern|frisch|orient/],
['Development',/development|embryo|entwicklung|cleavage|larv/]];
function theme(c){var s=(((c.phenomena||[]).join(' '))+' '+(c.title||'')+' '+(c.title_en||'')).toLowerCase();
 for(var i=0;i<THEMES.length;i++){if(THEMES[i][1].test(s))return THEMES[i][0];}return 'Other';}
var layerColor={1:'#1d6e56',2:'#355e7d',3:'#9a6a1f',4:'#9a9387'};
function colOf(c){return layerColor[c.layer]||'#cfc8b8';}
C.forEach(function(c){c._t=theme(c);c._r=4+Math.sqrt(c.citations||0)*1.7;});
var order=THEMES.map(function(t){return t[0];}).concat(['Other']);
var themes=[];C.forEach(function(c){if(themes.indexOf(c._t)<0)themes.push(c._t);});
themes.sort(function(a,b){return order.indexOf(a)-order.indexOf(b);});

var svg=d3.select('#map'),tip=d3.select('#tip'),panel=document.getElementById('panel');
var defaultPanel=panel.innerHTML;
(function(){var st=document.createElement('style');st.textContent=
'.cclist{margin-top:8px;display:flex;flex-direction:column;gap:8px}'+
'.cclbl{margin:8px 0 2px}'+
'.citecard{border:1px solid #e6dfcc;border-left:3px solid transparent;border-radius:10px;padding:8px 10px;background:#fffdf8;transition:box-shadow .15s ease,border-color .15s ease,transform .12s ease}'+
'.citecard.has{border-left-color:#7a3b2e}'+
'.citecard.hl{border-color:#b07a4e;box-shadow:0 3px 12px rgba(122,59,46,.15);transform:translateY(-1px)}'+
'.citecard.flash{animation:ccflash .9s ease}'+
'@keyframes ccflash{0%,100%{box-shadow:0 0 0 0 rgba(217,140,95,0)}30%{box-shadow:0 0 0 3px rgba(217,140,95,.5)}}'+
'.cc-h{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:2px}'+
'.cc-au{font-weight:600;color:#403a2e;font-size:11.5px}'+
'.cc-t{font-size:13px;line-height:1.38;color:#1c1a17;font-weight:600}'+
'.cc-de{font-size:11px;color:#8a8268;margin-top:1px;font-style:italic}'+
'.cc-note{font-size:12.5px;line-height:1.6;margin-top:6px;color:#34312a}'+
'.cc-pending{font-size:11.5px;color:#a59c84;margin-top:5px;font-style:italic}'+
'.cc-m{margin-top:5px;font-size:11px}.cc-m a{color:#7a3b2e}'+
'.badge.sci{background:#e7ddc6;color:#7a3b2e}';
document.head.appendChild(st);})();
var H=Math.max(680,Math.min(960,Math.round((window.innerHeight||820)*0.85)));
svg.attr('height',H);
var byId={};C.forEach(function(c){byId[c.id]=c;});
var groups={};C.forEach(function(c){var g=(c.genus||'').toLowerCase();if(g)(groups[g]=groups[g]||[]).push(c);});
var links=[];Object.keys(groups).forEach(function(g){var ar=groups[g].slice().sort(function(a,b){return a.year-b.year;});for(var i=1;i<ar.length;i++)links.push({source:ar[i-1],target:ar[i]});});
var nbr={};C.forEach(function(c){nbr[c.id]={};});links.forEach(function(l){nbr[l.source.id][l.target.id]=1;nbr[l.target.id][l.source.id]=1;});
var gz=svg.append('g'),gEdge=gz.append('g'),gThread=gz.append('g'),gRing=gz.append('g'),gNode=gz.append('g'),gLab=gz.append('g');
function width(){return svg.node().clientWidth||900;}
var centers={};
function computeCenters(){var w=width(),cols=Math.min(themes.length,w<640?2:(w<1000?3:4)),rows=Math.ceil(themes.length/cols);
 themes.forEach(function(t,i){var col=i%cols,row=Math.floor(i/cols);
  centers[t]={x:(col+0.5)/cols*w,y:(row+0.62)/rows*H,lx:(col+0.5)/cols*w,ly:row/rows*H+20};});}
computeCenters();
var sim=d3.forceSimulation(C)
 .velocityDecay(0.34).alphaDecay(0.022)
 .force('x',d3.forceX(function(c){return centers[c._t].x;}).strength(0.13))
 .force('y',d3.forceY(function(c){return centers[c._t].y;}).strength(0.13))
 .force('charge',d3.forceManyBody().strength(-9))
 .force('link',d3.forceLink(links).id(function(c){return c.id;}).distance(58).strength(0.05))
 .force('collide',d3.forceCollide(function(c){return c._r+1.9;}))
 .on('tick',tick);
var edge=gEdge.selectAll('line').data(links).join('line').attr('stroke','#cdc4b1').attr('stroke-width',0.7).attr('opacity',0.32);
var labG=gLab.selectAll('g.lg').data(themes).join('g').attr('class','lg');
labG.append('rect').attr('class','clbg');
var labels=labG.append('text').attr('class','cl').attr('text-anchor','middle').text(function(d){return d;});
function placeLabels(){labG.attr('transform',function(d){return 'translate('+centers[d].lx+','+centers[d].ly+')';});
 labels.attr('x',0).attr('y',0);
 labG.each(function(){var g=d3.select(this),tx=g.select('text').node();if(!tx)return;var bb=tx.getBBox();
  g.select('rect.clbg').attr('x',bb.x-8).attr('y',bb.y-3).attr('width',bb.width+16).attr('height',bb.height+6).attr('rx',9);});}
var rings=gRing.selectAll('circle').data(C.filter(function(c){return c.rediscovery;})).join('circle')
 .attr('r',function(c){return c._r+3;}).attr('fill','none').attr('stroke','#7a3b2e').attr('stroke-width',1.1).attr('pointer-events','none');
var nodes=gNode.selectAll('circle').data(C).join('circle')
 .attr('r',function(c){return c._r;}).attr('fill',colOf).attr('stroke','#fffdf9').attr('stroke-width',0.8).style('cursor','pointer')
 .on('mouseover',function(e,c){if(!selected)hoverNode(c);})
 .on('mousemove',function(e,c){var p=d3.pointer(e,svg.node());var nb=Object.keys(nbr[c.id]).length;tip.style('opacity',1).style('left',(p[0]+12)+'px').style('top',(p[1]+10)+'px').html('<b>'+esc(c.author)+' '+c.year+'</b><br>'+esc((c.title_en||c.title||'').slice(0,90))+(nb?'<br><span style="opacity:.65">'+nb+' same-genus link'+(nb>1?'s':'')+'</span>':''));})
 .on('mouseout',function(){tip.style('opacity',0);if(!selected)unhover();})
 .on('click',function(e,c){select(c);});
function hoverNode(c){var s=nbr[c.id];nodes.transition().duration(150).attr('opacity',function(d){return (d===c||s[d.id])?1:0.16;});
 edge.transition().duration(150).attr('opacity',function(l){return (l.source===c||l.target===c)?0.95:0.05;}).attr('stroke',function(l){return (l.source===c||l.target===c)?'#7a3b2e':'#cdc4b1';});}
function unhover(){nodes.transition().duration(150).attr('opacity',1);edge.transition().duration(150).attr('opacity',0.32).attr('stroke','#cdc4b1');}
function tick(){nodes.attr('cx',function(c){return c.x;}).attr('cy',function(c){return c.y;});
 rings.attr('cx',function(c){return c.x;}).attr('cy',function(c){return c.y;});
 edge.attr('x1',function(l){return l.source.x;}).attr('y1',function(l){return l.source.y;}).attr('x2',function(l){return l.target.x;}).attr('y2',function(l){return l.target.y;});}
sim.on('end',placeLabels);setTimeout(placeLabels,500);
var selected=null,bubbleSel=null;
function hasNote(c,d){return !!(window.NOTES&&window.NOTES[c.id+':'+d.k]);}
function layoutBubbles(n){var pts=[],ringR=[60,104,150,196,244,294],cap=[8,13,18,24,30,44],idx=0;
 for(var r=0;r<ringR.length&&idx<n;r++){var count=Math.min(cap[r],n-idx);
  for(var j=0;j<count;j++){var ang=(j+0.5)/count*2*Math.PI+r*0.4;pts.push({x:Math.cos(ang)*ringR[r],y:Math.sin(ang)*ringR[r]});idx++;}}
 while(idx<n){var ang=Math.random()*2*Math.PI;pts.push({x:Math.cos(ang)*330,y:Math.sin(ang)*330});idx++;}return pts;}
function ccHi(i,on){var el=document.getElementById('cc'+i);if(!el)return;
 if(on){el.classList.add('hl');el.scrollIntoView({block:'nearest',behavior:'smooth'});}else{el.classList.remove('hl');}}
function bubHi(i,on){if(!bubbleSel)return;bubbleSel.filter(function(d,j){return j===i;}).select('circle')
 .transition().duration(130).attr('r',function(d){return on?(hasNote(selected,d)?9.5:8.5):(hasNote(selected,d)?6:5);})
 .attr('fill',function(d){return on?'#c2540f':(d.h?'#cfc8b8':'#d98c5f');});}
function drawBubbles(c){gThread.selectAll('*').remove();
 var arr=(window.CITATIONS&&window.CITATIONS[c.id])||[];if(!arr.length){bubbleSel=null;return;}
 var pts=layoutBubbles(arr.length);
 gThread.selectAll('line').data(arr).join('line').attr('x1',c.x).attr('y1',c.y).attr('x2',c.x).attr('y2',c.y)
  .attr('stroke','#d3cbb9').attr('stroke-width',0.5).attr('opacity',0)
  .transition().duration(560).delay(function(d,i){return i*4;})
  .attr('x2',function(d,i){return c.x+pts[i].x;}).attr('y2',function(d,i){return c.y+pts[i].y;}).attr('opacity',0.6);
 var b=gThread.selectAll('g.bub').data(arr).join('g').attr('class','bub').style('cursor','pointer')
  .attr('transform','translate('+c.x+','+c.y+')')
  .on('mouseover',function(e,d){var i=arr.indexOf(d);ccHi(i,true);bubHi(i,true);})
  .on('mouseout',function(e,d){var i=arr.indexOf(d);ccHi(i,false);bubHi(i,false);})
  .on('click',function(e,d){if(e.stopPropagation)e.stopPropagation();var i=arr.indexOf(d);var el=document.getElementById('cc'+i);if(el){el.scrollIntoView({block:'center',behavior:'smooth'});el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}});
 b.transition().duration(560).delay(function(d,i){return i*4;}).attr('transform',function(d,i){return 'translate('+(c.x+pts[i].x)+','+(c.y+pts[i].y)+')';});
 b.append('circle').attr('r',function(d){return hasNote(c,d)?6:5;})
  .attr('fill',function(d){return d.h?'#cfc8b8':'#d98c5f';})
  .attr('stroke',function(d){return hasNote(c,d)?'#7a3b2e':'#fffdf9';})
  .attr('stroke-width',function(d){return hasNote(c,d)?1.4:0.7;})
  .attr('opacity',0).transition().duration(520).delay(function(d,i){return i*4;}).attr('opacity',1);
 b.append('text').attr('class','blab').attr('text-anchor',function(d,i){return pts[i].x<0?'end':'start';})
  .attr('x',function(d,i){return pts[i].x<0?-9:9;}).attr('y',3)
  .text(function(d){var ln=(d.a||'').replace(' et al.','').split(' ').slice(-1)[0];return ln+' '+(d.y||'');})
  .attr('opacity',0).transition().duration(420).delay(function(d,i){return 160+i*4;}).attr('opacity',1);
 bubbleSel=b;}
function citeCard(c,d,i){var note=(window.NOTES&&window.NOTES[c.id+':'+d.k])||'';
 var badge=d.h?'<span class="badge wip">historiographic</span>':'<span class="badge sci">scientific</span>';
 var vr=(window.VERIFIED&&window.VERIFIED[c.id+':'+d.k])?' <span title="Written from the full text" style="background:#1d6e56;color:#fff;border-radius:4px;padding:0 5px;font-size:9.5px;font-weight:600">✓ verified</span>':'';badge+=vr;
 var rel=(d.m&&d.m.indexOf('same')>=0)?(' <span class="badge">'+esc(d.m.replace(/_/g,' '))+'</span>'):'';
 var de=(d.et&&d.t&&d.et!==d.t)?'<div class="cc-de">'+esc(d.t)+'</div>':'';
 var body=note?'<div class="cc-note">'+esc(note)+'</div>':'<div class="cc-pending">How it cites the original — paragraph still to be written.</div>';
 var doi=d.d?'<div class="cc-m"><a target=_blank href="https://doi.org/'+d.d+'">'+esc(d.d)+'</a></div>':'';
 return '<div class="citecard'+(note?' has':'')+'" id="cc'+i+'" data-i="'+i+'">'+
  '<div class="cc-h"><span class="cc-au">'+esc(d.a||'(anon.)')+' · '+(d.y||'n.d.')+'</span>'+badge+rel+'</div>'+
  '<div class="cc-t">'+esc(d.et||d.t||'(untitled)')+'</div>'+de+body+doi+'</div>';}
function select(c){selected=c;
 nodes.transition().duration(220).attr('opacity',function(d){return d===c?1:0.1;}).attr('stroke',function(d){return d===c?'#211f1c':'#fffdf9';}).attr('stroke-width',function(d){return d===c?2:0.8;});
 rings.transition().duration(220).attr('opacity',0.18);edge.transition().duration(220).attr('opacity',0.04);
 var k=2.6,w=width();
 svg.transition().duration(760).ease(d3.easeCubicInOut).call(zoom.transform,d3.zoomIdentity.translate(w/2-c.x*k,H/2-c.y*k).scale(k));
 drawBubbles(c);
 var lg=L[c.id]||{},arr=(window.CITATIONS&&window.CITATIONS[c.id])||[];
 var ord=arr.map(function(d,i){return {d:d,i:i};});
 ord.sort(function(A,B){var na=hasNote(c,A.d)?0:1,nb=hasNote(c,B.d)?0:1;if(na!==nb)return na-nb;
  var ha=A.d.h?1:0,hb=B.d.h?1:0;if(ha!==hb)return ha-hb;return (B.d.y||0)-(A.d.y||0);});
 var nnote=arr.filter(function(x){return hasNote(c,x);}).length;
 var en=c.has_translation?('<a class="btn" href="papers/'+c.slug+'.html">Read English →</a>'):'';
 var head='<p class="kicker"><a href="#" id="backp">‹ all papers</a> · '+esc(c._t)+' · '+(c.layer?('Layer '+c.layer):'unranked')+'</p>'+
  '<h3>'+esc(c.title_en||c.title)+'</h3>'+
  ((c.title&&c.title!==c.title_en)?'<p class="pde">('+esc(c.title)+')</p>':'')+
  '<p class="pmeta">'+esc(c.author)+' · '+c.year+(c.organism?' · <em>'+esc(c.organism)+'</em>'+(lg.modern?' (now <em>'+esc(lg.modern)+'</em>)':''):'')+'</p>'+
  '<p class="pmeta"><b>'+(c.citations||0)+'</b> modern citations · <b>'+(lg.n_parallels||0)+'</b> parallels'+(c.rediscovery?' · <span class="badge redis">rediscovery</span>':'')+'</p>'+
  '<div class="actionbar" style="margin:10px 0"><a class="btn primary" href="reader.html?id='+c.id+'">Read original</a>'+en+'</div>';
 var listhdr=arr.length?('<p class="pmeta cclbl"><b>'+arr.length+'</b> works cite this paper'+(nnote?' · <b>'+nnote+'</b> annotated':'')+' — hover a card to find it on the map. <span class="muted" title="Each note is reconstructed from the citing work\'s title, topic and (where available) abstract, not from the citing passage itself.">How notes are written ⓘ</span></p>'):'<p class="muted" style="margin-top:6px">No modern citations recorded for this paper.</p>';
 panel.innerHTML=head+listhdr+(arr.length?('<div class="cclist">'+ord.map(function(o){return citeCard(c,o.d,o.i);}).join('')+'</div>'):'');
 var bp=document.getElementById('backp');if(bp)bp.addEventListener('click',function(e){e.preventDefault();deselect();});
 var lst=panel.querySelector('.cclist');
 if(lst){lst.addEventListener('mouseover',function(e){var card=e.target.closest('.citecard');if(!card)return;bubHi(+card.getAttribute('data-i'),true);card.classList.add('hl');});
  lst.addEventListener('mouseout',function(e){var card=e.target.closest('.citecard');if(!card)return;bubHi(+card.getAttribute('data-i'),false);card.classList.remove('hl');});}
 panel.scrollTop=0;}
function deselect(){selected=null;bubbleSel=null;
 nodes.transition().duration(280).attr('opacity',1).attr('stroke','#fffdf9').attr('stroke-width',0.8);
 rings.transition().duration(280).attr('opacity',0.9);edge.transition().duration(280).attr('opacity',0.32).attr('stroke','#cdc4b1');
 gThread.selectAll('*').remove();panel.innerHTML=defaultPanel;
 svg.transition().duration(640).ease(d3.easeCubicInOut).call(zoom.transform,d3.zoomIdentity);}
var zoom=d3.zoom().scaleExtent([0.4,5]).on('zoom',function(e){gz.attr('transform',e.transform);});
svg.call(zoom);
var q=document.getElementById('q'),fl=document.getElementById('layer'),fp=document.getElementById('phen'),fr=document.getElementById('ronly'),reset=document.getElementById('reset');
themes.forEach(function(t){var o=document.createElement('option');o.value=t;o.textContent=t;fp.appendChild(o);});
function matches(c){if(fl.value&&String(c.layer)!==fl.value)return false;if(fp.value&&c._t!==fp.value)return false;
 if(fr.checked&&!c.rediscovery)return false;var t=(q.value||'').toLowerCase();
 if(t){var hay=(c.author+' '+c.title+' '+(c.title_en||'')+' '+(c.organism||'')).toLowerCase();if(hay.indexOf(t)<0)return false;}return true;}
function applyFilter(){nodes.attr('opacity',function(c){return matches(c)?1:0.08;}).attr('pointer-events',function(c){return matches(c)?'all':'none';});
 rings.attr('opacity',function(c){return matches(c)?0.9:0.05;});}
[q,fl,fp].forEach(function(e){e.addEventListener('input',applyFilter);});fr.addEventListener('change',applyFilter);
reset.addEventListener('click',function(){q.value='';fl.value='';fp.value='';fr.checked=false;selected=null;bubbleSel=null;
 nodes.attr('opacity',1).attr('pointer-events','all').attr('stroke','#fffdf9').attr('stroke-width',0.8);
 rings.attr('opacity',0.9);edge.attr('opacity',0.32).attr('stroke','#cdc4b1');gThread.selectAll('*').remove();panel.innerHTML=defaultPanel;
 svg.transition().duration(520).ease(d3.easeCubicInOut).call(zoom.transform,d3.zoomIdentity);});
document.getElementById('leg').innerHTML='<span class="it"><b>Legacy layer:</b></span>'+
 [['1','1'],['2','2'],['3','3'],['4','4']].map(function(p){return '<span class="it"><span class="dotc" style="background:'+layerColor[p[0]]+'"></span>'+p[1]+'</span>';}).join('')+
 '<span class="it"><span class="dotc" style="background:#cfc8b8"></span>none</span>'+
 '<span class="it"><span class="dotc" style="background:transparent;border:1.5px solid #7a3b2e"></span>rediscovery</span>'+
 '<span class="it muted">size = citations</span>';
window.addEventListener('resize',function(){H=Math.max(680,Math.min(960,Math.round((window.innerHeight||820)*0.85)));svg.attr('height',H);computeCenters();placeLabels();sim.alpha(0.3).restart();});
})();
"""
    a = os.path.join(SITE, "assets")
    open(os.path.join(a, "catalog.js"), "w").write(catalog_js)
    open(os.path.join(a, "legacy.js"), "w").write(legacy_js)
    open(os.path.join(a, "analytics.js"), "w").write(analytics_js)
    open(os.path.join(a, "reader.js"), "w").write(reader_js)
    open(os.path.join(a, "map.js"), "w").write(map_js)

def main():
    os.makedirs(DATA, exist_ok=True)
    write_css(); write_js()
    open(os.path.join(DATA, "site.js"), "w").write("window.SITE=" + json.dumps({"fullPdfs": FULL}) + ";")
    open(os.path.join(SITE, ".nojekyll"), "w").write("")
    gen_index(); gen_catalog(); gen_map(); gen_translations(); gen_legacy(); gen_analytics(); gen_about(); gen_reader()
    gen_citations(); gen_methodology(); gen_rediscovery(); gen_authors(); gen_reading_pages(); copy_assets()
    print("Generated site at", SITE, "| FULL_PDFS =", FULL)
    print("pages:", sorted(os.path.basename(p) for p in glob.glob(os.path.join(SITE, "*.html"))))
    print("reading pages:", len(glob.glob(os.path.join(SITE, "papers", "*.html"))))
    print("figures:", len(glob.glob(os.path.join(SITE, "figures", "*", "*"))))
    print("pdfs:", len(glob.glob(os.path.join(SITE, "pdfs", "*.pdf"))))

if __name__ == "__main__":
    main()
