THE CANDIDATES, THE THRESHOLDS, AND EVERY DECISION

What the pipeline reads and writes between the two databases and the published tables, so a
reader can check each step without running it. Every file except this README, the manifest
and the layout is a copy of an original in the repository; three are transformed on copy, and
the transformation is stated below.

The working tables, in pairs, imports and exports, in run order:

  commodity_inventory_*.csv   stage 0: every commodity string in the delivery, its trading
                              life, and the termination or introduction the schedule states
  stage1_candidates_*.csv     stage 1: every retirement event with its candidate lists and
                              the narrowest tier that bounded them
  stage1_official_*.csv       stage 1b: what the official record says about each retirement,
                              and which layer decided
  stage1_ranked_*.csv         stage 1c: every candidate that reached the ranking, with its
                              similarity score and the rule that vetoed it where one did
  stage1_review_*.csv         stage 1c: the retirements the record did not decide outright,
                              with the top candidate, its margin over the runner-up, and the
                              review flag
  stage2_resolved_*.csv       stage 2: the succession each retirement received, on whose
                              authority and on what basis; the analyst's own rulings carry
                              their date
  stage3_routed_*.csv         stage 3: every commodity followed to the end of its chain
  stage4_families_*.csv       stage 4: the families, and their names
  stage5_lineage_*.csv        stage 5: every journey unfolded into steps

Three ledgers the queue builder carries across runs rather than rebuilding from nothing:
_row_numbers.json pins each row number to its link, so the workbook's rows keep their
identity; _queue_previous.json and _decisions_seen.json are the snapshots the change report
and the stale-evidence flag compare against.

Thresholds.txt declares every named threshold in one place, each with its rationale.

The decision files, every human and authoritative ruling as readable text, and the notes
around them. Decisions.txt states what each one governs and how many rows it holds:

  stage2_decisions.csv, stage2_decisions.xlsx
      the answer to every retirement the official record did not settle outright; the
      workbook is the one the analyst answered in, the CSV the same answers as the build
      reads them. In this copy the rows the analyst REJECTED are filled red-pink, and no
      other row is filled, so the reversals can be read down the sheet at a glance. The
      verdict column says ANALYST where the method proposed nothing it could recommend and
      the answer had to come from a person.
  stage2_adjudication_queue.csv           the worklist those answers respond to
  Readme adjudication queue.txt            how the worklist is read and answered
  decisive_distinctions.csv               the written rules about meaning
  official_constraint_sets.csv            where the record bounds an answer without choosing
  medicine_families.csv                   the medicine-name layer one check uses
  cbsa_override_table.csv                 every pair the two concordances state, as applied
  cbsa_override_exclusions.csv            the two hand-curated departures, ricin and saxitoxin
  cbsa_partial_transfers.csv              lines the concordance maps to two codes at once,
                                          excluded and published as a stated limitation
  cbsa_override_ambiguous_imports.csv     lines where the concordance names several successors
                                          and the crosswalk's own routing picks the branch
  five_way_split_receipts.csv             the receipts for the five-way 2017 split
  leftover_line_gaps.csv                  every deleted leftover line and where its goods went
  ADJUDICATION_FINDINGS.csv               the register of every defect found in this rebuild

ADJUDICATION_FINDINGS.csv is a copy with its found_by column generalised: a finding records
that it came from automated review verified by hand, with the date it was found, without
naming the tooling. The repository original is untouched.

The two workbooks are copies whose internal metadata carries no folder path from the saving
machine; every cell is unchanged.

Provenance.txt names the public Statistics Canada datasets exactly, and the extraction that
produced the databases the build reads. The databases themselves are not here: the three
extracts come to 721,137,664 bytes, and a reader needs the two the build reads only to
re-run it.

Nothing in this folder is edited by hand. The working tables are rebuilt by the pipeline, the
decision files are edited in the repository's decisions folder and read by the build, and the
prose is vetted in the repository's own documents: the thresholds and the provenance, the
decision notes in volume 2.
