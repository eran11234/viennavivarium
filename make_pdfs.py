#!/usr/bin/env python3
"""English PDF edition of every translation, with each figure placed where the original prints it.

Run after build_site.py and before gen_site.py (gen_site links a page's English PDF only if it exists):

    python make_pdfs.py                          # all translations, in parallel
    python make_pdfs.py 74_ 136-przibram-1924    # just these (trans_slug or page_slug prefixes)
    python make_pdfs.py --plan 153_              # print where each figure goes; write nothing

Writes vivarium_site/pdf/<page_slug>.pdf.  Needs pandoc and WeasyPrint (pip install weasyprint).

How figures are placed.  The translations keep the original's figure captions in the running
text ("**Fig. 3.** Regenerate after 14 days. *(figure not reproduced)*") and collect the images
in a "## Figures" section at the end.  For the PDF each image is moved to its place:

  * a text figure goes in front of the caption that names it (a bold caption first, then a plain
    "Fig. 3. ..." one, then one in a plate legend); failing that, after the first paragraph that
    mentions it;
  * a plate goes under the heading of its legend ("#### Plate I."), or in front of the line that
    opens with its name ("**Tafel VI.** ...");
  * anything that cannot be placed stays in a section at the end, as on the web page.

Captions inside a plate legend anchor a text figure only as a last resort.  Where an image now
appears, the "(figure not reproduced)" note by its caption is dropped.
"""
import datetime
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.abspath(__file__))
TRANS = os.path.join(ROOT, "translations_full")
SITE = os.path.join(ROOT, "vivarium_site")
OUT = os.path.join(SITE, "pdf")
CACHE = os.path.join(tempfile.gettempdir(), "vv_pdf_images")
SITE_URL = "https://eran11234.github.io/viennavivarium/"
SCAN_DPI = 300           # the figure crops are 300-dpi renders of the scans: 1 px = 1/300 in as printed
PDF_DPI = 230            # images are downsampled to this resolution at their size in the PDF
TEXT_W_MM = 168          # A4 minus the side margins below
FIG_H_MM = 232           # tallest an image may be, leaving room for a caption line
LAND_W_MM, LAND_H_MM = 259, 160   # the same on a sideways (A4 landscape) page

# ------------------------------------------------------------------------------- figure designators
FIGWORDS = [
    (r"Text[- ]?fig(?:ures?|s?\.)?|Textfig(?:ur(?:en)?)?\.?|Textabb\.?", "fig"),
    (r"Figs?\.?|Figures?|Figur(?:en)?|Abb\.?|Abbildung(?:en)?", "fig"),
    (r"Diagrams?|Diagr\.", "diagram"),
    (r"Curves?|Kurven?", "curve"),
    (r"Schemas?|Schemata", "schema"),
    (r"Plates?|Pl\.|Tafeln?|Taf\.?", "plate"),
]
FIGWORD_SRC = "|".join(w for w, _ in FIGWORDS)
FIGWORD_RE = re.compile(r"(?<![A-Za-zÄÖÜäöüß-])(" + FIGWORD_SRC + r")(?![A-Za-zÄÖÜäöüß])", re.I)
GROUP_OF = [(re.compile(r"^(?:" + w + r")$", re.I), g) for w, g in FIGWORDS]
PAREN_RE = re.compile(r"\(([^()]*)\)")
LETTER_RANGE = re.compile(r"^\s*[a-zα-ω]\s*[-–—]\s*[a-zα-ω]\s*$", re.I)
RANGE_SEP = r"\s*(?:-{1,2}|–|—|\bbis\b|\bto\b)\s*"
_RV = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _to_roman(n):
    out = ""
    for v, s in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s; n -= v
    return out


def roman(s):
    if not s or any(c not in _RV for c in s):
        return None
    n = sum(-_RV[c] if i + 1 < len(s) and _RV[s[i + 1]] > _RV[c] else _RV[c] for i, c in enumerate(s))
    return n if 0 < n < 200 and _to_roman(n) == s else None


def group_of(word):
    for rx, g in GROUP_OF:
        if rx.match(word):
            return g
    return "fig"


def _tok(s):
    """One designator token -> (base, sub): '3a' -> (3, 'a'); '6A' -> (6, 'a'); 'IVα' -> (4, 'α'); 'h' -> ('h', '')."""
    s = s.strip().strip("()*.,;:[]_").replace("*", "").strip()
    m = re.match(r"^(\d{1,3})([a-zA-Zα-ω]?)\)?$", s)
    if m:
        return int(m.group(1)), m.group(2).lower()
    m = re.match(r"^([IVXL]{1,7})([a-zα-ω]?)\)?$", s)
    if m and roman(m.group(1)):
        return roman(m.group(1)), m.group(2)
    m = re.match(r"^([A-Za-zα-ω])\)?$", s)
    if m:
        return m.group(1), ""
    return None


def _letters(a, b):
    a, b = a.lower(), b.lower()
    if a.isalpha() and b.isalpha() and len(a) == len(b) == 1 and 0 <= ord(b) - ord(a) < 26:
        return [chr(c) for c in range(ord(a), ord(b) + 1)]
    return [a, b]


def designators(text, default_group=None, strip_parens=True):
    """Every figure designator named in a label, caption or phrase: a set of (group, base, sub).
    'Figs. 3a–c and 5' -> {(fig,3,a), (fig,3,b), (fig,3,c), (fig,5,'')}; an unnumbered 'Fig.' -> (fig,'*','')."""
    keys = set()
    text = text.replace(" ", " ")
    text = re.sub(r"\[\s*(?:" + FIGWORD_SRC + r")\s*\]", " ", text, flags=re.I)        # "Tafel [Plate] I"
    text = re.sub(r"\bu\.\s", " and ", text)
    text = re.sub(r"(\d+\s*[a-z]?)\s*(?:to|bis|–|—|-)\s*(?:Figs?\.|Fig\b|Abb\.)\s*(?=\d)", r"\1–", text)
    if strip_parens:
        text = PAREN_RE.sub(lambda m: (" " + m.group(1) + " ") if LETTER_RANGE.match(m.group(1)) else " ", text)
    spans = [(m.start(), m.end(), group_of(m.group(1))) for m in FIGWORD_RE.finditer(text)]
    if not spans and default_group:
        spans = [(0, 0, default_group)]
    for i, (s, e, g) in enumerate(spans):
        stop = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        rest = re.sub(r"^\s*\.?\s*", "", text[e:stop])
        rest = re.split(r"\.(?!\d)|;|:|\[|\b[pS]\.\s*\d|\bvon\b|\bfrom\b|\bof\b|\bon\b|\bin\b", rest)[0]
        rest = rest.replace("*", "").replace("_", "")
        got, prev_num = False, None
        for part in re.split(r",|\band\b|\bund\b|&|/|\bor\b|\boder\b", rest):
            part = part.strip()
            if not part:
                continue
            rm = re.match(r"^(\S+?)" + RANGE_SEP + r"(\S+)", part)
            if rm:
                a, b = _tok(rm.group(1)), _tok(rm.group(2))
                if a and b:
                    if isinstance(a[0], int) and isinstance(b[0], int) and 0 <= b[0] - a[0] < 60:
                        for n in range(a[0], b[0] + 1):
                            keys.add((g, n, ""))
                        got, prev_num = True, b[0]
                        continue
                    if isinstance(a[0], int) and a[1] and isinstance(b[0], str):         # 3a–e
                        for ch in _letters(a[1], b[0]):
                            keys.add((g, a[0], ch))
                        got, prev_num = True, a[0]
                        continue
                    if isinstance(a[0], str) and isinstance(b[0], str):                   # h–j
                        for ch in _letters(a[0], b[0]):
                            keys.add((g, prev_num, ch) if prev_num is not None else (g, ch, ""))
                        got = True
                        continue
            rm = re.match(r"^(\d{1,3}|[IVXL]{1,7})\s+([a-zα-ω])" + RANGE_SEP + r"([a-zα-ω])\b", part, re.I)   # 4 a–d
            if rm and _tok(rm.group(1)):
                n = _tok(rm.group(1))[0]
                for ch in _letters(rm.group(2), rm.group(3)):
                    keys.add((g, n, ch))
                got, prev_num = True, n
                continue
            toks = part.split()
            t = _tok(toks[0])
            if t is None:
                continue
            if isinstance(t[0], int) and not t[1] and len(toks) >= 2 and re.match(r"^[a-zA-Zα-ω][).]?$", toks[1]):
                t = (t[0], toks[1][0].lower())                                               # 27 a, I a α
            if isinstance(t[0], str) and prev_num is not None and t[0].islower():
                t = (prev_num, t[0])                                                         # 5a, b
            keys.add((g, t[0], t[1]))
            got = True
            if isinstance(t[0], int):
                prev_num = t[0]
        if not got:
            keys.add((g, "*", ""))
    return keys


def _compatible(g1, g2):
    return g1 == g2 or {g1, g2} <= {"fig", "curve", "diagram"}


def match_score(ekeys, ckeys):
    """3 = same figure, 2 = same number with/without a letter, 1 = both unnumbered; −1 across groups."""
    best = 0
    for g, b, s in ekeys:
        for g2, b2, s2 in ckeys:
            if not _compatible(g, g2) or b != b2:
                continue
            if b == "*":
                sc = 1 if g == g2 else 0
            elif s and s2:
                sc = 3 if s == s2 else 0
            elif not s and not s2:
                sc = 3
            else:
                sc = 2
            if g != g2:
                sc -= 1
            best = max(best, sc)
    return best


def covered(ckeys, shown):
    """True if every figure a caption names is shown by one of the placed images."""
    real = [k for k in ckeys if k[1] != "*"]
    if not real:
        return False
    return all(any(_compatible(g, g2) and b == b2 and (not s2 or not s or s == s2) for g2, b2, s2 in shown)
               for g, b, s in real)


# ------------------------------------------------------------------------------------------ blocks
NOTE_RE = re.compile(r"\*\((?:(?!\)\*).)*?not reproduced(?:(?!\)\*).)*?\)\*", re.I | re.S)
HEAD_RE = re.compile(r"^#{1,6}\s")
EMB_LABEL_RE = re.compile(r"\*\*(?:" + FIGWORD_SRC + r")[^*\n]{0,40}?\*\*", re.I)


def bare(block):
    return re.sub(r"^(\s*>\s*)+", "", block.strip())


def caption_info(block):
    """(keys, strength) for a caption paragraph: strength 2 = opens with a bold figure label,
    1 = a plain or italic one ('Fig. 5. ...', '*Plate IV.*', '> Diagram 9: ...'); else (None, 0)."""
    b = bare(block)
    if not b or HEAD_RE.match(b) or b.startswith("|"):
        return None, 0
    if b.startswith("**"):
        m = re.match(r"^\*\*(.+?)\*\*", b, re.S)
        if not m:
            return None, 0
        lab = m.group(1).strip()
        if FIGWORD_RE.match(lab.lstrip("([ ")):
            first = lab
            tm = re.match(r"^\*?([a-zα-ω](?:\s*[-–—]\s*[a-zα-ω])?)\.?\*?(?=\s|$)", b[m.end():])
            if tm and not lab.endswith("."):                    # "**Fig. 8***b—e.*"
                first = lab + tm.group(1)
            keys = designators(first)
            for seg in re.findall(r"\*\*(.+?)\*\*", b[m.end():], re.S):
                if FIGWORD_RE.match(seg.strip().lstrip("([ ")):
                    keys |= designators(seg)
            if keys and all(k[1] == "*" for k in keys):         # "**Fig.** Kurve IVα."
                after = b[m.end():m.end() + 60].strip().lstrip("*([ ")
                if FIGWORD_RE.match(after):
                    more = {k for k in designators(after) if k[1] != "*"}
                    keys = more or keys
            return (keys or None), (2 if keys else 0)
        if re.match(r"^\d{1,3}[a-z]?\)$", lab):                  # "**31)**" — a numbered curve
            return {("curve", int(re.match(r"\d+", lab).group()), "")}, 2
        return None, 0
    s = b.lstrip("*_([ ")
    m = FIGWORD_RE.match(s)
    if not m:
        return None, 0
    tail = s[m.end():]
    d = re.match(r"^\s*\.?\s*((?:[\dIVXL]{1,7}[a-zα-ω]?\)?|[a-zA-Zα-ω]\)?)"
                 r"(?:\s*(?:,|–|—|-|\band\b|\bund\b|u\.|&|\bto\b|\bbis\b)\s*(?:[\dIVXL]{1,7}[a-zα-ω]?\)?|[a-zα-ω]\)?))*)"
                 r"\s*([.:)—–*\[]|$)", tail)
    if not d:
        return None, 0
    keys = {k for k in designators(s[:m.end()] + " " + d.group(1)) if k[1] != "*"}
    return (keys or None), (1 if keys else 0)


def split_blocks(text):
    """Markdown -> list of blocks (paragraphs, headings, tables, lists), blank lines dropped.
    Captions run together with other text are given blocks of their own, so that each figure can
    go in front of its own caption: a blockquote holding several captions is split per caption, a
    caption label in mid-paragraph starts a new block, and text after a '(figure not reproduced)'
    note starts another."""
    raw, cur = [], []
    for line in text.split("\n"):
        if line.strip() == "":
            if cur:
                raw.append("\n".join(cur)); cur = []
        elif HEAD_RE.match(line):
            if cur:
                raw.append("\n".join(cur)); cur = []
            raw.append(line)
        else:
            cur.append(line)
    if cur:
        raw.append("\n".join(cur))
    out = []
    for blk in raw:
        for piece in _split_quote(blk):
            for p2 in _split_before_captions(piece):
                out.extend(_split_after_notes(p2))
    return out


def _split_quote(block):
    lines = block.split("\n")
    if not all(l.lstrip().startswith(">") for l in lines):
        return [block]
    groups, cur = [], []
    for l in lines:
        if re.match(r"^\s*>\s*$", l):
            if cur:
                groups.append("\n".join(cur)); cur = []
        else:
            cur.append(l)
    if cur:
        groups.append("\n".join(cur))
    if len(groups) > 1 and any(caption_info(g)[0] for g in groups):
        return groups
    return [block]


def _cut(block, cuts):
    if not cuts:
        return [block]
    quote = block.lstrip().startswith(">")
    pieces, prev = [], 0
    for c in sorted(set(cuts)):
        pieces.append(block[prev:c]); prev = c
    pieces.append(block[prev:])
    out = []
    for p in pieces:
        p = p.strip()
        if not p or p == ">":
            continue
        if quote and not p.startswith(">"):
            p = "> " + p
        out.append(p)
    return out


def _has_text_before(block, pos):
    return bool(re.search(r"[^\s>]", block[:pos]))


def _split_before_captions(block):
    """'... and the increase **Fig. 1.** *(figure not reproduced)*' -> text | caption."""
    if block.lstrip().startswith(("|", "#")):
        return [block]
    cuts = []
    if caption_info(block)[1] != 2:             # "**Abb. 25.** Nr. 198; **Abb. 26.** Nr. 9." stays one caption
        prev = 0
        for note in NOTE_RE.finditer(block):
            labels = [m for m in EMB_LABEL_RE.finditer(block, prev, note.start())
                      if note.start() - m.end() <= 600]
            prev = note.end()
            if not labels:
                continue
            m = labels[0]                       # the first label of the run in front of the note
            label_like = (re.search(r"[.:]\s*\*\*$", m.group(0))
                          or re.match(r"\s*(\[[^\]]{0,30}\]\s*)?\*\(", block[m.end():]))
            if label_like and _has_text_before(block, m.start()):
                cuts.append(m.start())
    for m in NOTE_RE.finditer(block):          # "... **1,912.** *(Tafel 2 [Plate 2] — a full-page plate ...)*"
        inner = m.group(0)[2:].lstrip()
        if not _has_text_before(block, m.start()) or not opens_with_plate(inner) or \
                not any(g == "plate" and b != "*" for g, b, s in designators(inner[:60])):
            continue
        pre = block[:m.start()].rstrip()
        lb = re.search(r"\*\*([^*]+)\*\*$", pre)
        if lb and FIGWORD_RE.match(lb.group(1).strip().lstrip("([ ")):
            continue                            # the note belongs to the caption label in front of it
        cuts.append(m.start())
    return _cut(block, cuts)


def _split_after_notes(block):
    """'**Fig. 3.** ... *(figure not reproduced)* results of 100%, ...' -> caption | text."""
    if block.lstrip().startswith(("|", "#")):
        return [block]
    cuts = []
    for m in NOTE_RE.finditer(block):
        t = re.sub(r"^>\s*", "", block[m.end():].lstrip())
        if len(t) >= 2 and re.match(r"[\w*\[„\"“…‘]", t):
            cuts.append(m.end())
    return _cut(block, cuts)


def heading_plates(block):
    if not HEAD_RE.match(block):
        return set()
    return {b for g, b, s in designators(re.sub(r"^#{1,6}\s*", "", block), strip_parens=False)
            if g == "plate" and b != "*"}


PLATE_HEAD_RE = re.compile(r"\b(Plates?|Tafeln?|Taf\.|Tafelerkl\w*)\b", re.I)
PLATE_MARK_RE = re.compile(r"\*\*([^*]{0,120}?\b(?:Tafel|Taf\.|Plate|Pl\.)\s*[IVXL\d]+\b[^*]{0,24})\*\*\s*$", re.I)


def plate_marker(block):
    """A paragraph ending in a bold plate imprint ('... **Archiv f. E. Bd. XLIII. Tafel IX.**'): the
    scan's bound-in plate page.  -> the plate numbers, or set()."""
    m = PLATE_MARK_RE.search(bare(block).rstrip())
    return {b for g, b, s in designators(m.group(1)) if g == "plate" and b != "*"} if m else set()


def opens_with_plate(block, strip="*_([ "):
    m = FIGWORD_RE.match(bare(block).lstrip(strip))
    return bool(m) and group_of(m.group(1)) == "plate"


# ------------------------------------------------------------------------------------ figures section
def parse_figures_section(md):
    """-> (body, entries, notes, tail).  entries: [{label, img}] in order; tail: what follows the section."""
    m = re.search(r"\n## Figures[ \t]*\n", md)
    if not m:
        return md, [], [], ""
    body, rest = md[:m.start()], md[m.end():]
    end = len(rest)
    for pat in (r"\n---[ \t]*\n", r"\n## "):
        mm = re.search(pat, rest)
        if mm:
            end = min(end, mm.start())
    sec, tail = rest[:end], rest[end:]
    entries, notes, label = [], [], None
    for blk in re.split(r"\n\s*\n", sec):
        s = blk.strip()
        if not s:
            continue
        im = re.match(r"^!\[[^\]]*\]\(([^)\s]+)\)(\{[^}]*\})?\s*$", s)
        if im:
            entries.append(dict(label=label or "", img=im.group(1)))
            label = None
        elif re.match(r"^\*\*.+\*\*$", s, re.S) and len(s) < 200:
            label = s.strip("*").strip()
        else:
            notes.append(s)
    return body, entries, notes, tail


def entry_keys(e):
    """-> ('plate' | 'fig', keys)."""
    fname = os.path.basename(e["img"])
    lab = e["label"]
    if re.match(r"^(Plate|Taf)", fname) or re.match(r"^(Plates?|Pl\.|Taf\.?|Tafel)\b", lab, re.I):
        ks = {b for g, b, s in designators(lab or "", "plate") if g == "plate" and b != "*"}
        if not ks:
            m = re.match(r"^(?:Plate|Taf)_([IVXL]+|\d+)", fname)
            if m:
                ks = {roman(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else None)}
        return "plate", {("plate", k, "") for k in ks if k is not None}
    ks = {k for k in designators(lab) if k[0] != "plate"} if lab else set()
    if not lab or not FIGWORD_RE.search(lab):
        base = re.sub(r"\.\w+$", "", fname).replace("_", " ")
        ks = {k for k in designators(base) if k[0] != "plate" and k[1] != "*"} or ks
    return "fig", ks


# --------------------------------------------------------------------------------------- placement
def place_figures(md):
    """-> (markdown with every placeable image moved to its place, plan).
    plan: one (label, image, how, anchor block, anchor text) per image."""
    body, entries, notes, tail = parse_figures_section(md)
    if not entries:
        return md, []
    blocks = split_blocks(body)
    n = len(blocks)
    kinds = [entry_keys(e) for e in entries]
    has_plates = any(k == "plate" for k, _ in kinds)
    caps = [caption_info(b) for b in blocks]

    # plate context: under a plate-legend heading, or the run of captions after a plate's name or imprint
    ctx, owner = [False] * n, [set() for _ in range(n)]
    if has_plates:
        on, on_owner, local, local_owner = False, set(), False, set()
        stack = []                 # open headings: (level, names a plate legend, its plates)
        for i, b in enumerate(blocks):
            if HEAD_RE.match(b):   # a legend runs on through its sub-headings, to the next heading as high
                lvl = len(re.match(r"^#+", b).group(0))
                while stack and stack[-1][0] >= lvl:
                    stack.pop()
                isp = bool(PLATE_HEAD_RE.search(b))
                stack.append((lvl, isp, heading_plates(b) if isp else set()))
                on = any(x[1] for x in stack)
                on_owner = next((x[2] for x in reversed(stack) if x[2]), set()) if on else set()
                local = False
                ctx[i], owner[i] = on, set(on_owner)
                continue
            keys, st = caps[i]
            if local and not keys:
                local = False
            ctx[i] = on or local
            owner[i] = set(local_owner if local else on_owner)
            pm = plate_marker(b)
            if pm and not (keys and any(k[0] != "plate" for k in keys)):
                local, local_owner = True, pm
            elif keys and all(k[0] == "plate" for k in keys) and opens_with_plate(b):
                local, local_owner = True, {k[1] for k in keys if k[1] != "*"}
                owner[i] = set(local_owner)

    # soft context: the stretch after a bound-in plate's imprint or name, up to the next heading or
    # long paragraph -- a caption there is more likely the plate's than a text figure's
    soft = list(ctx)
    if has_plates:
        on = False
        for i, b in enumerate(blocks):
            if HEAD_RE.match(b):
                on = False
                continue
            keys = caps[i][0]
            if on and not keys and len(bare(b)) > 400:
                on = False
            soft[i] = soft[i] or on
            if plate_marker(b) or (keys and all(k[0] == "plate" for k in keys) and opens_with_plate(b)):
                on = True

    before, after = {}, {}         # block index -> entries to put in front of / after it
    lead = {}                      # block index -> landscape plates to put in front of its legend heading
    plan, unplaced = [], []
    shown, shown_ctx, placed_plates, used_star = set(), set(), set(), set()
    fig_entries = [ek for k, ek in kinds if k == "fig"]

    def pick_caption(ek, strength, star, in_ctx):
        cands = []
        for i in range(n):
            keys, st = caps[i]
            if st != strength or ctx[i] != in_ctx or (star and i in used_star):
                continue
            sc = match_score(ek, keys)
            if sc >= (1 if star else 2):
                extra = sum(1 for g2, b2, s2 in keys
                            if b2 != "*" and not any(_compatible(g, g2) and b == b2 for g, b, s in ek))
                cands.append((sc, extra, i))
        if not cands:
            return None
        top = max(c[0] for c in cands)
        best = [c for c in cands if c[0] == top]
        best = [c for c in best if c[1] <= 2] or [min(best, key=lambda c: (c[1], c[2]))]
        best = [c for c in best if not soft[c[2]]] or best
        return min(best, key=lambda c: c[2])[2]

    def pick_mention(e, ek, star):
        textlab = e["label"].lower().startswith("text")
        for i, b in enumerate(blocks):
            if HEAD_RE.match(b) or b.lstrip().startswith("|") or ctx[i] or caps[i][0]:
                continue
            ms = list(FIGWORD_RE.finditer(b))
            for j, m in enumerate(ms):
                if group_of(m.group(1)) == "plate" or re.search(r"\d\s*$", b[:m.start()]):
                    continue             # a plate, or a count ("with 1 text-figure")
                if re.search(r"(Plate|Pl\.|Taf\.?|Tafel)\s*[IVXL\d]+[,.]?\s*(?:and\s+)?$", b[max(0, m.start() - 18):m.start()], re.I):
                    continue             # "Plate VI Fig. 1" is a plate figure, not a text figure
                if re.match(r"^[^.;()]{0,20}\b(?:of|on|in|auf|der)\s+(?:Plate|Pl\.|Taf\.?|Tafel)\b", b[m.end():m.end() + 40], re.I):
                    continue
                stop = ms[j + 1].start() if j + 1 < len(ms) else len(b)
                ks = designators(b[m.start():min(stop, m.start() + 60)])
                if star:
                    if any(g2 != "fig" and b2 == "*" and (g2, "*", "") in ek for g2, b2, s2 in ks):
                        return i
                    if textlab and m.group(1).lower().startswith("text") and all(b2 == "*" for g2, b2, s2 in ks):
                        return i
                elif match_score(ek, ks) >= 2:
                    return i
        return None

    for e, (kind, ek) in zip(entries, kinds):
        anchor, how = None, None
        if kind == "plate" and ek:
            nums = {k[1] for k in ek}
            cands = []
            for i, b in enumerate(blocks):
                hp = heading_plates(b)
                if hp & nums:
                    named_first = opens_with_plate(re.sub(r"^#{1,6}\s*", "", b), strip="*_ ")
                    cands.append(((0 if hp <= nums else 2) if named_first else 2.2, i, "plate legend"))
                keys, st = caps[i]
                if keys and opens_with_plate(b):
                    pk = {k[1] for k in keys if k[0] == "plate" and k[1] != "*"}
                    if pk & nums:
                        cands.append(((1 if st == 2 else 1.5) if pk <= nums else 2.5, i, "plate caption"))
                if plate_marker(b) & nums:
                    cands.append((3, i, "plate page"))
            if cands:
                _, anchor, how = min(cands)
                placed_plates |= nums
                if how == "plate legend" and is_landscape_plate(e["img"]):
                    lead.setdefault(anchor, []).append(e)     # its own sideways page, then the legend
                else:
                    (after if how in ("plate legend", "plate page") else before).setdefault(anchor, []).append(e)
        elif kind == "fig" and ek:
            star = all(k[1] == "*" for k in ek)
            for st in (2, 1):
                bi = pick_caption(ek, st, star, False)
                if bi is not None:
                    anchor, how = bi, ("caption" if st == 2 else "plain caption")
                    break
            if anchor is None and star and len(fig_entries) == 1:     # the paper's one unnumbered figure
                named = {(g, b) for keys, st in caps if keys and st for g, b, s in keys if g != "plate" and b != "*"}
                if len(named) == 1:
                    for i in range(n):
                        if caps[i][0] and not ctx[i] and any(k[0] != "plate" for k in caps[i][0]):
                            anchor, how = i, "only caption"; break
            if anchor is None:
                mi = pick_mention(e, ek, star)
                if mi is not None:
                    anchor, how = mi, "first mention"
                    after.setdefault(mi, []).append(e)
                    shown.update(ek)
            if anchor is None:                      # last resort: its caption in a plate legend
                for st in (2, 1):
                    bi = pick_caption(ek, st, star, True)
                    if bi is not None:
                        anchor, how = bi, ("caption" if st == 2 else "plain caption") + " in legend"
                        break
            if anchor is not None and how != "first mention":
                before.setdefault(anchor, []).append(e)
                if star:
                    used_star.add(anchor)
                (shown_ctx if ctx[anchor] else shown).update(ek if not star else caps[anchor][0])
        if anchor is None:
            unplaced.append(e)
            plan.append((e["label"], e["img"], "end", None, ""))
        else:
            plan.append((e["label"], e["img"], how, anchor, bare(blocks[anchor])[:70].replace("\n", " ")))

    # which captions lose their "(figure not reproduced)" note
    drop = set(before)              # a caption with its image right above it
    for i in range(n):
        keys, st = caps[i]
        fk = {k for k in keys if k[0] != "plate"} if keys else set()
        if fk and covered(fk, shown_ctx if ctx[i] else shown) and (ctx[i] or not soft[i] or i in before):
            drop.add(i)
        if keys and opens_with_plate(blocks[i]) and {k[1] for k in keys if k[0] == "plate"} & placed_plates:
            drop.add(i)
        if ctx[i] and owner[i] & placed_plates:
            drop.add(i)
        if plate_marker(blocks[i]) & placed_plates:
            drop.add(i)
    for i in sorted(drop):          # a lone "*(figure not reproduced)*" right after a placed caption
        if i + 1 < n and NOTE_RE.fullmatch(bare(blocks[i + 1]).strip()):
            drop.add(i + 1)

    def img_md(e):
        return "![](%s)" % e["img"]

    out = []
    for i, b in enumerate(blocks):
        for e in lead.get(i, []):
            lab = ("\n\n<p class=\"figlabel\">%s</p>" % html.escape(e["label"])) if e["label"] else ""
            out.append("::: {.figure .plate}\n%s%s\n:::" % (img_md(e), lab))
        cap = drop_not_reproduced(b) if i in drop else b
        if not bare(cap).strip():
            cap = ""
        if i in before:
            es = before[i]
            for e in es[:-1]:
                out.append("::: {.figure}\n%s\n:::" % img_md(e))
            out.append(("::: {.figure}\n%s\n\n%s\n:::" % (img_md(es[-1]), cap)) if cap else
                       ("::: {.figure}\n%s\n:::" % img_md(es[-1])))
        elif cap:
            out.append(cap)
        for e in after.get(i, []):
            if HEAD_RE.match(b):
                out.append("::: {.figure .plate}\n%s\n:::" % img_md(e))
            else:
                lab = e["label"] or os.path.splitext(os.path.basename(e["img"]))[0].replace("_", " ")
                out.append("::: {.figure}\n%s\n\n<p class=\"figlabel\">%s</p>\n:::" % (img_md(e), html.escape(lab)))
    new = "\n\n".join(out)
    if unplaced or notes:
        sec = ["## Figures"]
        for e in unplaced:
            lab = ("\n\n<p class=\"figlabel\">%s</p>" % html.escape(e["label"])) if e["label"] else ""
            sec.append("::: {.figure}\n%s%s\n:::" % (img_md(e), lab))
        sec += notes
        new += "\n\n" + "\n\n".join(sec)
    return new.rstrip("\n") + "\n" + tail, plan


NOTE_SUBS = [
    (r"\s*[—–]\s*(?:figures?\s+)?not reproduced(?:\s+here)?\.?\s+(?=[A-Z])", ". "),
    (r"\s*[—–]\s*(?:figures?\s+)?not reproduced(?:\s+here)?\.?", ""),
    (r"[;,]\s*(?:figures?\s+|figure plate\s+)?not reproduced(?:\s+here)?", ""),
    (r"\b(?:photographic figure|photographs?|figure plate|figure/plate|plate image|plate of figures|plates?|"
     r"figures?|curves?|diagrams?|images?)[;,]?\s+(?:are\s+|is\s+)?not reproduced(?:\s+here)?[;,.]?\s*", ""),
    (r"^\*\(\s*not reproduced(?:\s+here)?\b\.?", "*("),
]


def drop_not_reproduced(block):
    """Remove the '(figure not reproduced)' remark from a caption, keeping anything else in it."""
    def fix(m):
        inner = m.group(0)
        for pat, rep in NOTE_SUBS:
            inner = re.sub(pat, rep, inner, flags=re.I)
        if re.search(r"not reproduced", inner, re.I):
            return m.group(0)            # "(arrows not reproduced)": not about the figure; leave it
        inner = re.sub(r"\s*\(\s*[;,.:—–]?\s*\)", "", inner)          # "(newt profile) ()"
        inner = re.sub(r"^\*\(\s*[—–;,:.]\s*", "*(", inner)             # "(— plate showing ...)"
        inner = re.sub(r"\s*[—–;,:]\s*\)\*$", ")*", inner)
        core = inner.strip("*()").strip(" ;,.—–:")
        return "" if not core else inner
    out = NOTE_RE.sub(fix, block)
    out = re.sub(r"\((?:figures?|plate|photographs?)\s+not reproduced\)", "", out, flags=re.I)
    out = re.sub(r"\*\(\s*[;,.:—–]?\s*\)\*", "", out)
    out = re.sub(r"\(\s*[;,]\s*", "(", out)
    out = re.sub(r"\s*[;,]\s*\)", ")", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+$", "", out, flags=re.M)
    return out


# ------------------------------------------------------------------------------------------- PDF
CSS = r"""
@page {
  size: A4; margin: 22mm 21mm 20mm 21mm;
  @top-left { content: "Vienna Vivarium in English"; font: 7.5pt "DejaVu Sans", sans-serif; color: #8a8173; }
  @top-right { content: string(runhead); font: 7.5pt "DejaVu Sans", sans-serif; color: #8a8173; }
  @bottom-center { content: counter(page) " / " counter(pages); font: 8pt "DejaVu Sans", sans-serif; color: #6d665b; }
}
@page :first { @top-left { content: none; } @top-right { content: none; } }
@page wide { size: A4 landscape; margin: 16mm 19mm 15mm 19mm; }
.figure.landscape { page: wide; break-before: page; break-after: page; margin: 0; }
html { font-family: "Liberation Serif", "DejaVu Serif", serif; font-size: 10.6pt; line-height: 1.42; color: #1d1b18; }
body { margin: 0; }
.mast { font: 7.5pt "DejaVu Sans", sans-serif; color: #8a8173; letter-spacing: .08em; text-transform: uppercase;
        border-bottom: .6pt solid #cfc6b4; padding-bottom: 4pt; margin-bottom: 14pt; }
h1.title { font-size: 19pt; line-height: 1.18; margin: 0 0 6pt; font-weight: bold; string-set: runhead attr(data-short); }
p.de { font-style: italic; color: #4b463f; margin: 0 0 7pt; }
p.by { font-size: 9.6pt; color: #3b3732; margin: 0 0 3pt; }
p.src { font: 7.8pt "DejaVu Sans", sans-serif; color: #6d665b; margin: 0 0 13pt; }
.box { border: .6pt solid #d8cdb6; background: #faf6ee; padding: 7pt 9pt; margin: 0 0 12pt; font-size: 9pt; line-height: 1.38; }
.box p { margin: 0 0 4pt; } .box p:last-child { margin-bottom: 0; }
.box .h { font-weight: bold; }
.box .cat { font: 7pt "DejaVu Sans", sans-serif; text-transform: uppercase; letter-spacing: .06em; color: #8a5a2b; margin-right: 6pt; }
.sens { border-left: 2.5pt solid #b5651d; }
.text p { margin: 0 0 6.5pt; text-align: justify; hyphens: auto; orphans: 2; widows: 2; }
.text li { text-align: left; }
h1, h2, h3, h4, h5, h6 { break-after: avoid; font-weight: bold; line-height: 1.25; }
.text h1 { font-size: 15pt; margin: 16pt 0 8pt; }
.text h2 { font-size: 13pt; margin: 14pt 0 6pt; }
.text h3 { font-size: 11.5pt; margin: 12pt 0 5pt; }
.text h4 { font-size: 10.6pt; margin: 10pt 0 4pt; font-style: italic; }
.text h5, .text h6 { font-size: 10.6pt; margin: 8pt 0 3pt; font-weight: normal; font-style: italic; }
blockquote { margin: 6pt 0 8pt 10pt; padding-left: 8pt; border-left: 1.5pt solid #e0d7c5; color: #2b2925; }
.figure { break-inside: avoid; margin: 10pt 0 11pt; text-align: center; }
.figure img { max-width: 100%; }
.figure p, .figure blockquote p { text-align: left; font-size: 9.2pt; line-height: 1.34; margin: 5pt 0 0; hyphens: auto; }
.figure blockquote { margin: 0; border: none; padding: 0; }
.figure p.figlabel { text-align: center; font-style: italic; }
.figure p.img, .text p.img { text-align: center; margin: 0; }
.figure.plate { margin-top: 4pt; }
img { max-width: 100%; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 9pt; font-size: 8pt; line-height: 1.25; }
th, td { border: .5pt solid #c9bfab; padding: 1.5pt 3pt; vertical-align: top; overflow-wrap: anywhere; text-align: left; }
th { background: #f2ece0; }
hr { border: none; border-top: .6pt solid #cfc6b4; margin: 12pt 0; }
sup { font-size: 70%; line-height: 0; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 85%; }
a { color: inherit; text-decoration: none; }
section.footnotes { font-size: 8.8pt; border-top: .6pt solid #cfc6b4; margin-top: 12pt; padding-top: 4pt; }
.end { margin-top: 18pt; font-size: 8.6pt; color: #3b3732; border-top: .6pt solid #cfc6b4; padding-top: 6pt; break-inside: avoid; }
.end p { margin: 0 0 4pt; }
"""

DISCLAIMER = ("These papers are historical documents, reproduced for study, not as endorsements, and we are not "
              "responsible for their content. Some data may be wrong or harmful: early twentieth-century science "
              "sometimes used methods and arguments that would be considered unscientific or harmful today. The "
              "translations and assessments on this site may also contain errors.")


def load_json(rel, default):
    p = os.path.join(ROOT, rel)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def md_to_html(md):
    r = subprocess.run(["pandoc", "-f", "markdown-implicit_figures", "-t", "html5", "--no-highlight"],
                       input=md, capture_output=True, text=True, check=True)
    return r.stdout


def is_landscape_plate(rel):
    """A plate wider than it is tall and wider than the text: it gets a sideways page of its own."""
    from PIL import Image
    src = os.path.join(TRANS, rel)
    if not os.path.exists(src) or not re.match(r"^(Plate|Taf)", os.path.basename(rel)):
        return False
    w, h = Image.open(src).size
    return w > 1.15 * h and w / SCAN_DPI * 25.4 > TEXT_W_MM * 1.02


def prepared_image(rel):
    """Downsampled copy of translations_full/<rel> -> (path, width in mm as it will print, landscape?)
    or (None, None, False).  A plate wider than it is tall, and wider than the text, gets a page of
    its own turned sideways (A4 landscape), so that it prints at its full size, upright."""
    from PIL import Image
    src = os.path.join(TRANS, rel)
    if not os.path.exists(src):
        return None, None, False
    im = Image.open(src)
    w, h = im.size
    w_mm, h_mm = w / SCAN_DPI * 25.4, h / SCAN_DPI * 25.4
    landscape = is_landscape_plate(rel)
    if landscape:
        scale = min(1.0, LAND_W_MM / w_mm, LAND_H_MM / h_mm)
    else:
        scale = min(1.0, TEXT_W_MM / w_mm, FIG_H_MM / h_mm)
    out_mm = w_mm * scale
    target_w = int(out_mm / 25.4 * PDF_DPI)
    dst = os.path.join(CACHE, "%s_%d.jpg" % (os.path.splitext(rel)[0], target_w))
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst, out_mm, landscape
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if im.mode not in ("L", "RGB"):
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
        im = bg
    if w > target_w * 1.08:
        im = im.resize((target_w, max(1, round(h * target_w / w))), Image.LANCZOS)
    im.save(dst, "JPEG", quality=80, optimize=True, progressive=True)
    return dst, out_mm, landscape


def _norm(s):
    return re.sub(r"[^a-z0-9äöüß]+", "", re.sub(r"[*_]", "", s.lower()))


def build_html(t, md, notes):
    # our title block replaces the translation's own title lines: the first H1 (as on the web page),
    # and any opening heading that only repeats the English or German title
    titles = {_norm(t["title_en"]), _norm(t["title_de"])}
    lines = md.split("\n")
    dropped_h1 = False
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        hm = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if not hm:
            break
        h = _norm(hm.group(2))
        if (hm.group(1) == "#" and not dropped_h1) or (h and any(h == x or (len(h) > 25 and (h in x or x in h)) for x in titles)):
            dropped_h1 = dropped_h1 or hm.group(1) == "#"
            lines[i] = ""
        else:
            break
    frag = md_to_html("\n".join(lines))
    frag = re.sub(r"<p>\s*(<img\b[^>]*>)\s*</p>", r'<p class="img">\1</p>', frag)

    def img(m):
        sm = re.search(r'src="(figures/[^"]+)"', m.group(0))
        if not sm:
            return m.group(0)
        path, wmm, land = prepared_image(html.unescape(sm.group(1)))
        if not path:
            return m.group(0)
        return '<img src="file://%s" style="width:%.1fmm" alt=""%s>' % (path, wmm, ' class="wide"' if land else "")
    frag = re.sub(r"<img\b[^>]*>", img, frag)
    # a landscape plate takes its figure block onto a sideways page of its own
    frag = re.sub(r'<div class="figure( plate)?">(\s*<p class="img"><img [^>]*class="wide")',
                  lambda m: '<div class="figure%s landscape">%s' % (m.group(1) or "", m.group(2)), frag)
    doi = t.get("doi") or ""
    url = SITE_URL + "papers/%s.html" % t["page_slug"]
    short = "%s (%s)" % (t["author"], t["year"])
    ctx = ""
    s = notes.get("sens")
    if s:
        cat = ('<span class="cat">%s</span>' % html.escape(s["category"])) if s.get("category") else ""
        ctx += ('<div class="box sens"><p class="h">%s%s</p>%s</div>'
                % (cat, html.escape(s.get("heading") or "Before you read this"),
                   "".join("<p>%s</p>" % html.escape(p) for p in s.get("paras", []))))
    if notes.get("issue"):
        ctx += '<div class="box"><p>%s</p></div>' % html.escape(notes["issue"])
    if t.get("status") and t["status"] != "complete":
        ctx += '<div class="box"><p>This translation is still being finalized (figures or full text in progress).</p></div>'
    today = datetime.date.today()
    made = "%d %s %d" % (today.day, today.strftime("%B"), today.year)
    title = html.escape(t["title_en"])
    head = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<meta name="author" content="{html.escape(t['author'])}">
<meta name="description" content="English translation of {html.escape(t['author'])} ({t['year']}), {html.escape(t['title_de'])}">
<meta name="generator" content="Vienna Vivarium in English">
<meta name="keywords" content="Biologische Versuchsanstalt, Vivarium, Vienna, {t['year']}, English translation">
<style>{CSS}</style></head><body>
<div class="mast">Vienna Vivarium in English · English translation</div>
<h1 class="title" data-short="{html.escape(short)}">{title}</h1>
<p class="de">{html.escape(t['title_de'])}</p>
<p class="by">{html.escape(t['author'])} · {html.escape(t['journal'])}{(' · DOI ' + html.escape(doi)) if doi else ''}</p>
<p class="src">With the German original side by side: <a href="{url}">{url}</a></p>
{ctx}
<div class="text">"""
    foot = f"""</div>
<div class="end">
<p><b>Cite:</b> {html.escape(t['author'])} ({t['year']}), “{html.escape(t['title_de'])},” {html.escape(t['journal'])}. English translation, Vienna Vivarium in English, {url}</p>
<p><b>Please note.</b> {DISCLAIMER}</p>
<p>Figures are reproduced from the scanned original, at their printed size where the page allows. This PDF was made on {made}.</p>
</div></body></html>"""
    return head + frag + foot


def make_one(t, notes, outdir=OUT):
    from weasyprint import HTML
    md = open(os.path.join(TRANS, t["trans_slug"] + "_FULL.md"), encoding="utf-8").read()
    md, plan = place_figures(md)
    doc = build_html(t, md, notes)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, t["page_slug"] + ".pdf")
    tmp = out + ".part"
    HTML(string=doc, base_url=TRANS).write_pdf(tmp)
    os.replace(tmp, out)
    return out, plan


def _work(args):
    t, notes = args
    try:
        out, plan = make_one(t, notes)
        return t["page_slug"], os.path.getsize(out), sum(1 for p in plan if p[2] != "end"), len(plan), None
    except Exception as e:      # one bad document must not stop the others
        return t["page_slug"], 0, 0, 0, "%s: %s" % (type(e).__name__, e)


def _selected(T, args):
    return [t for t in T if not args or any(t["trans_slug"].startswith(a) or t["page_slug"].startswith(a) for a in args)]


def main(argv):
    T = json.load(open(os.path.join(SITE, "data", "translations.json"), encoding="utf-8"))
    if argv and argv[0] == "--plan":
        for t in _selected(T, argv[1:]):
            md = open(os.path.join(TRANS, t["trans_slug"] + "_FULL.md"), encoding="utf-8").read()
            _, plan = place_figures(md)
            if not plan:
                continue
            print("==", t["trans_slug"])
            for lab, img, how, at, anc in plan:
                print("   %-26s %-26s %-14s %-5s %s" % (lab[:26], os.path.basename(img)[:26], how,
                                                     "" if at is None else "#%d" % at, anc[:64]))
        return
    jobs = int(os.environ.get("PDF_JOBS", str(min(4, os.cpu_count() or 1))))
    if argv and argv[0].startswith("-j"):
        if argv[0] == "-j":
            jobs, argv = int(argv[1]), argv[2:]
        else:
            jobs, argv = int(argv[0][2:]), argv[1:]
    sens = load_json("legacy_data/sensitivity.json", {})
    issues = load_json("legacy_data/translation_issues.json", {})
    work = []
    for t in _selected(T, argv):
        s = sens.get(str(t["id"]))
        iss = issues.get(t["trans_slug"])
        work.append((t, dict(sens=s if isinstance(s, dict) and "read" in (s.get("where") or ["read", "dossier"]) else None,
                             issue=iss.get("public_note") if isinstance(iss, dict) else None)))
    os.makedirs(OUT, exist_ok=True)
    fails, total = [], 0
    with Pool(jobs) as pool:
        for slug, size, placed, nfig, err in pool.imap_unordered(_work, work):
            if err:
                fails.append((slug, err)); print("FAILED", slug, err, flush=True)
            else:
                total += size
                print("pdf %-44s %6.1f MB   figures placed in the text %d/%d" % (slug, size / 1e6, placed, nfig), flush=True)
    print("English PDFs: %d written, %.0f MB in all, %d failed" % (len(work) - len(fails), total / 1e6, len(fails)))
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
