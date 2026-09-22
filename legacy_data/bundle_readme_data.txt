VIENNA VIVARIUM IN ENGLISH — RESEARCH BUNDLE
Snapshot: {{BUILD_DATE}}
https://eran11234.github.io/viennavivarium/

The Biologische Versuchsanstalt (the "Vivarium"), Vienna: 175 papers from the
institute's zoological department, 1904–1930, in English translation, with the
project's corpus analysis.

This is the data-and-text bundle. It contains no PDFs and no figure scans — if
you want the browsable site with those, see the Download page linked above.


WHAT IS HERE
------------
catalog.csv            One row per paper, 175 rows. The practical starting point.
                       Columns: id, year, author, English and German titles,
                       journal, DOI, organism/genus/taxon, citation count, legacy
                       layer, Discover status, sleeping-beauty flag and index,
                       the read-and-compare verdict, how many modern papers were
                       read against it, any context-note category, the matching
                       translation filename, and URLs for the reading page and
                       dossier.

translations/          All 175 translations as Markdown, one file per paper.
                       Figure references point at filenames that live in the
                       full site bundle, not here.

data/                  The project's working data. The ones most worth knowing:
                         consensus_all.json        modern literature retrieved per
                                                   paper (7,481 papers, via the
                                                   Consensus API)
                         consensus_synthesis.json  the hand-written verdict, state
                                                   of the field, and comparison for
                                                   each of 172 papers
                         methodology.json          structured summary of what each
                                                   paper did
                         citations_enriched.json   who cites each paper (OpenAlex)
                         citation_notes.json       per-citation curated notes
                         citation_verified.json    citations checked against the
                                                   citing paper's own text
                         authors.json              58 people, with biographies
                         sensitivity.json          papers needing reader context
                                                   before they are read
                         translation_issues.json   known gaps and provenance issues
                         tour.json                 the guided tour's 74 stops
                         rediscovery.json          rediscovery targets and the
                                                   institute's unfinished programmes

site-data/             The same corpus after the build step, as the website
                       consumes it: catalog.json, translations.json, legacy.json.

BVA Corpus Analysis.xlsx
                       The original working spreadsheet the corpus was built from.


A NOTE ON THE VERDICTS
----------------------
Each paper was read against the current literature and given a verdict, a
state-of-the-field paragraph, and an explicit comparison. Papers are placed on
two axes: recognition (how much today's science cites it) and vindication
(whether the science held up). These are deliberately separate, because citation
counts partly measure notoriety — some of the institute's most-cited papers are
among its most thoroughly refuted.

These are the project's own scholarly judgements, not a settled consensus. They
are a research aid. Disagreement is welcome and useful.


CONTEXT NOTES
-------------
Fourteen papers carry a reader-facing context note — see sensitivity.json, and
the context_note column in catalog.csv. They cover claims about sexual
orientation, claims about human races, an anatomical study of a named intersex
person whose body came from a penal institution, disabled people catalogued as
specimens, a proposal for human eye transplants, and one paper that publishes a
named colleague's mental illness in order to discredit his science.

Every one of those papers was read in full before the note was written. The
translations are complete and unedited — the notes sit alongside them, never
inside them, and nothing has been cut. If you quote from these papers, please
carry the context with the quotation.

Note for anyone running text analysis over this corpus: three papers carry no
verdict (a 1917 obituary with no experiment, and two whose assessments were
withdrawn for redoing), so consensus_synthesis.json has 172 entries, not 175.


CITATION AND RIGHTS
-------------------
Cite the original paper alongside the translation. Each translation's header
carries the full original reference; catalog.csv carries the DOI where one exists.

The German originals were published between 1904 and 1930 in Archiv für
Entwicklungsmechanik der Organismen (Springer; now Development Genes and
Evolution). Rights status varies by author and jurisdiction.

The translations and the corpus analysis are this project's own work. No reuse
licence has been set for them yet — please get in touch before redistributing or
republishing.

Corrections and collaborations are genuinely wanted:
  Eran Horowitz · eran.witz@gmail.com
  https://eran11234.github.io/viennavivarium/contribute.html
