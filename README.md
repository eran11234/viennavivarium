# Vienna Vivarium in English

An orientation platform for researchers to access the corpus of the **Biologische Versuchsanstalt** (the Vienna "Vivarium") in English: a searchable catalog of 175 papers (1904–1930), full English translations with figures, the German originals, and a citation-legacy layer.

This repository is the **source**. The website is generated from it and published automatically to GitHub Pages.

## How it works (CI/CD)

```
edit source  ──►  git push  ──►  GitHub Actions  ──►  GitHub Pages (live in ~2 min)
```

On every push to `main`, `.github/workflows/deploy.yml`:
1. installs Python + pandoc,
2. runs `build_site.py` (cleans the data → `vivarium_site/data/`),
3. runs `gen_site.py` with `FULL_PDFS=1` (renders all pages, copies figures and **all 175 German PDFs**),
4. publishes `vivarium_site/` to GitHub Pages.

You never edit the website directly and never commit it — it is rebuilt from source each time.

## Make a change and deploy

- **Add / fix a translation:** drop `NN_Author_Year_slug_FULL.md` and its `figures/` into `translations_full/`, register it in the maps in `build_site.py`, commit, push. Done.
- **Tweak the site (styling, copy, layout):** edit `gen_site.py` (CSS/JS/templates), commit, push.
- **Update the data:** edit the sources below, commit, push.

```bash
git add -A && git commit -m "update" && git push   # → live in ~2 minutes
```

## Build locally (optional)

```bash
pip install openpyxl          # pandoc also required
python build_site.py
python gen_site.py            # light: 7 PDFs. For all 175: FULL_PDFS=1 python gen_site.py
python -m http.server -d vivarium_site 8000   # http://localhost:8000
```

## Repository layout

| Path | What it is |
|---|---|
| `build_site.py` | Cleans + joins the corpus/legacy data → `vivarium_site/data/*.json` |
| `gen_site.py` | Generates all HTML/CSS/JS, copies figures and PDFs |
| `BVA Corpus Analysis.xlsx` | Master corpus metadata (175 papers) |
| `legacy_data/` | Per-paper legacy profiles + citing/parallel works |
| `translations_full/` | The English translation Markdown + `figures/` + source metadata |
| `articles/` | The 175 German source PDFs (hosted on the site) |
| `.github/workflows/deploy.yml` | Build + deploy pipeline |
| `vivarium_site/` | Generated output — **not committed** (built by CI) |

## Notes

- The repo is **public** (required for free GitHub Pages), so its contents are visible. Before publishing, confirm you have the right to host the German source PDFs — most BVA authors are long out of copyright, but check any post-1953 author (e.g. P. Weiss) and the scanned editions' terms.
- Citation/parallel data derive from OpenAlex. Legacy layers and convergence axes are the project's own working analysis.
