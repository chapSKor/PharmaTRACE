THE OFFICIAL RECORD: THE DOCUMENTS, THE EXTRACTS, AND HOW ONE BECAME THE OTHER

The first layer of the method. Before any description is compared, the build asks what the
official record says. This folder holds what it asks, in three parts.

  source_documents/   the official records themselves, as published
  extracts/           the machine-readable tables the build reads, transcribed from them
  transcription/      the code that did the transcribing

The build reads the extracts, not the PDFs. A pipeline cannot read a tariff schedule, and the
extracts hold the Chapter 30 rows, which is the part this work uses. Every extract carries a
column naming the document and page it came from, so any row can be checked against the source.

SOURCE DOCUMENTS

  WTO_HSCodes_*.pdf                    the five World Customs Organization correlation tables,
                                       circulated by the WTO Committee on Market Access as
                                       G/MA/W/26, /76, /105, /122 and /164 for the 2002, 2007,
                                       2012, 2017 and 2022 revisions. Each states that the
                                       tables are a guide without legal status.
  CBSA concordance 2011 to 2012.pdf    Canada's own ten-digit concordances. Where one names a
  CBSA concordance 2016 to 2017.pdf    successor it DECIDES, and no wording is consulted. These
                                       two settle 89 of the 320 retirements, and they are the
                                       only two the Agency published for Chapter 30 between
                                       2005 and 2026.
  PS35-7-*  and  PS36-1-*             the CBSA Customs Tariff for each year from 2005 to
    (Chapter 30).pdf                   2025, CUT TO ITS CHAPTER 30 PAGES. Each publication runs
                                       about 1,500 pages across all 99 chapters and the 22 of
                                       them come to 310 MB whole; their Chapter 30 pages come to
                                       2.1 MB. Every row of every sched_ch30_*.csv was checked
                                       against the page it cites before these were cut: 2,740
                                       rows, none unverified. gate1/extract_chapter30_pages.py
                                       does the cutting and carries that check.

EXTRACTS, AND THE COLUMN THAT POINTS BACK

  sched_ch30_YYYY*.csv        the CBSA tariff schedule for Chapter 30, one file per vintage.
                              source_file names the publication, page gives the page.
                              Presence proves a code existed in that year; absence proves
                              nothing, because the schedule lists tariff items and Statistics
                              Canada adds statistical breakouts beneath them.
  concordance_*_ch30.csv      the concordance rows. pdf_page gives the page in the PDF beside
                              it in source_documents/.
  wto_ch30_pairs.csv          the correlation tables and the documents' own remarks.
  wto_ch30_statements.csv     source_pdf and page_label give the document and page.
  decision_dates.csv          when each ruling was made. NOT a transcription of an official
                              record: it is derived from this repository's own commit history,
                              which transcription/derive_decision_dates.py shows.

TRANSCRIPTION

  extract_wto_pairs.py        reads the five WTO PDFs and writes wto_ch30_pairs.csv and
                              wto_ch30_statements.csv.
  derive_decision_dates.py    writes decision_dates.csv from the commit history.

The schedule and concordance extracts were transcribed before this package was assembled and
their scripts are not here; the page columns are how those are checked, against the PDFs in
source_documents/ for the concordances, and against the publications named below for the
schedules.

AT THE TOP OF THIS FOLDER

  family_differences_*.csv    where this build's families differ from the released version.
  Gate 1 differences explained  the document that explains every difference they list.

These two are not official records and are not transcribed from one. They sit apart for that
reason. check_stage6_outputs holds the tables and the prose equal: a family the tables flag and
the document does not explain is a failure.

WHAT DEPENDS ON THIS FOLDER

Stages 1 to 5 read the schedules and the concordances; without them every stage after Stage 0
stops. Measured 2026-08-28: a package without these files completed 56 of the suite's controls
instead of the full total. check_stage1c_rank confirms that a row held for a correlation table
is waiting on a document that is actually here. check_stage6_outputs reads the two difference
tables.

WHAT IS NOT HERE

The two trade databases the build reads, 650 MB. Provenance.txt in folder 4 names them exactly.

The rest of each CBSA Customs Tariff. Chapters 1 to 29 and 31 to 99 are not this work's
subject, and carrying them would add 308 MB to say nothing. source_file in each extract names
the publication it was read from: PS35-7-YYYY-eng and PS36-1-YYYYE are the Customs Tariff for
that year, published by the Canada Border Services Agency and available whole from its website.
The page column is a ZERO-BASED index into that publication, which is worth knowing before
checking a row against the full document rather than against the excerpt here.
