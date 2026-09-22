VIENNA VIVARIUM IN ENGLISH — COMPLETE OFFLINE SITE
Snapshot: {{BUILD_DATE}}
Live version: https://eran11234.github.io/viennavivarium/


HOW TO USE THIS
---------------
Unzip anywhere, then open  index.html  in a browser.

Everything works with no internet connection and no server: all 175 English
translations, all 175 German originals as PDFs, the figure plates, the catalog,
the guided tour, the map, the Discover hub and all 172 dossiers. Only outbound
links (DOIs, Wikipedia, Consensus) need a connection.

Nothing needs to be installed. If your browser blocks local files, try Firefox,
or serve the folder with:  python3 -m http.server  and open http://localhost:8000


WHAT IS IN HERE
---------------
index.html        Start here.
papers/           175 reading pages — the English translations, with figures.
pdfs/             175 German originals, as scanned PDFs (360 MB of this bundle).
figures/          497 figure and plate scans.
dossier/          172 dossiers: each paper read against the current literature.
                  (Three of the 175 carry no verdict: a 1917 obituary, which reports no
                  experiment, and two whose assessments were withdrawn for redoing.)
catalog.html      All 175 papers, searchable and sortable.
tour.html         The guided tour: from six big questions down to the researchers
                  and their articles, with the figures from the papers.
map.html          Force-directed map of the whole corpus.
authors.html      58 people, with biographies.
data/             The underlying JSON the pages are built from.

For the data on its own — translations as Markdown, the catalog as CSV, every
JSON file, no PDFs — take the research bundle instead. It is a few
megabytes rather than this one's size, and is the better choice for analysis.


THIS IS A SNAPSHOT
------------------
Dated above. The live site continues to change: translations get corrected,
verdicts get revised, biographies get written. Check the live URL for anything
you intend to rely on or quote.


A NOTE ON THE VERDICTS
----------------------
Each paper was read against the current literature and given a verdict, a
state-of-the-field paragraph, and an explicit comparison. Papers are placed on
two axes: recognition (how much today's science cites it) and vindication
(whether the science held up). These are deliberately separate, because citation
counts partly measure notoriety — some of the institute's most-cited papers are
among its most thoroughly refuted.

These are the project's own scholarly judgements, not a settled consensus.
Disagreement is welcome and useful.


CONTEXT NOTES
-------------
Fourteen papers carry a context note at the top of their reading page and
dossier. They cover claims about sexual orientation, claims about human races,
an anatomical study of a named intersex person whose body came from a penal
institution, disabled people catalogued as specimens, a proposal for human eye
transplants, and one paper that publishes a named colleague's mental illness in
order to discredit his science.

Every one of those papers was read in full before the note was written. The
translations themselves are complete and unedited — the notes sit alongside
them, never inside them, and nothing has been cut. If you quote from these
papers, please carry the context with the quotation.

Where a note says a verdict applies only to part of a paper, that is deliberate:
several of these papers contain sound science next to material that should not
be endorsed, and the verdict refers to the former.

Known provenance problems are recorded in data/translation_issues.json and noted
on the pages themselves.


CITATION AND RIGHTS
-------------------
Cite the original paper alongside the translation. Each reading page carries the
full original reference and its DOI where one exists.

The German originals in pdfs/ were published between 1904 and 1930 in Archiv für
Entwicklungsmechanik der Organismen (Springer; now Development Genes and
Evolution). Rights status varies by author and by jurisdiction, and the scanned
editions may carry their own terms. They are assembled here for scholarly use.
Please do not redistribute the PDF set.

The translations and the corpus analysis are this project's own work. No reuse
licence has been set for them yet — please get in touch before redistributing or
republishing.

Citation and parallel-work data derive from OpenAlex. Modern literature was
retrieved via the Consensus API. Legacy layers, recognition/vindication axes and
the Sleeping-Beauty Index are the project's own working analysis.


CONTACT
-------
Corrections and collaborations are genuinely wanted.
  Eran Horowitz · eran.witz@gmail.com
  https://eran11234.github.io/viennavivarium/contribute.html
