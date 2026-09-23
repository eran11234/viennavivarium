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
                       Columns: id, year, authors, English and German titles,
                       journal, DOI, organism, taxon; where the paper's claim
                       stands today (standing, verdict, why), any open question
                       and how it could be tested, what the paper offers, what
                       the assessment rests on and its confidence; how current
                       research uses it; its citing works by era; any
                       context-note category; the translation filename; and
                       URLs for the reading page and dossier.

translations/          All 175 translations as Markdown, one file per paper.
                       Figure references point at filenames that live in the
                       full site bundle, not here.

data/                  The project's working data. The ones most worth knowing:
                         assessment.json           where each paper's claim stands,
                                                   what it offers, how it is used
                                                   today, citations by era
                         paper_fixes.json          catalogue corrections checked
                                                   against each paper's title page
                         consensus_all.json        related modern literature per
                                                   paper (topical search via the
                                                   Consensus API; these papers do
                                                   not cite the originals)
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
                         tour_tree.json            the guided tour: six questions,
                                                   researchers, pictures

site-data/             The same corpus after the build step, as the website
                       consumes it: catalog.json and translations.json.

BVA Corpus Analysis.xlsx
                       The original working spreadsheet the corpus was built from.


HOW THE PAPERS WERE ASSESSED
----------------------------
In September 2026 every paper was re-read from its full translation, with every
work that cites it (OpenAlex) and a search of the related modern literature, and
judged under one written rubric. Three things are recorded (assessment.json):

  standing   established      later work confirmed this paper's own result, or
                              explicitly credits it for a result now standard
             consistent       the phenomenon is accepted today, but this paper's
                              result was never re-tested (an early instance)
             revised          holds only in part, or for other reasons
             unresolved       a specific point was never settled; open/test say
                              what is open and how it could be tested
             not_supported    contradicted, not replicated, or resting on a
                              rejected framework
             no_claim         obituary, review, methods paper, description
  use        tested / precedent (cited in science since 1990, usually as an
             early description or background) / historians / none (no citing
             work since 1990)
  offers     testable, data, method, organism (an unusual system), history

Where the more modest label was defensible, it was chosen; when a paper made two
claims with different fates, its central claim decides and the other is named.
Each assessment records what it rests on and how confident it is.

These readings replaced an earlier scheme ("sleeping beauties", a
sleeping-beauty index, "legacy layers", statuses such as "Quiet Classic") that
mistook general acceptance of a phenomenon for confirmation of a particular
paper, and citation counts for present-day use. It has been withdrawn and is
not included here.

These are careful readings, not a consensus of the field: a research aid.
Disagreement is welcome and useful.


PLEASE NOTE
-----------
These papers are historical documents, reproduced for study, not as
endorsements, and we are not responsible for their content. Some data may be
wrong or harmful: early twentieth-century science sometimes used methods and
arguments that would be considered unscientific or harmful today. The
translations and assessments may also contain errors.


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

Every paper, including the 1917 obituary (standing: no_claim), has an entry in
assessment.json. Two papers (ids 17 and 55) have no related-literature search in
consensus_all.json, so that file has 172 entries, not 175.


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
