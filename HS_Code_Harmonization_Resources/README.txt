WHAT TO SHARE, IN FIVE FOLDERS

1_outputs_for_pharmatrace/ holds the published crosswalk: the four tables per flow, the
identifier crosswalk to the released version, and the two disclosure tables. These are the
files the PharmaTRACE application and its maintainer consume, and Crosswalk consumer notes.txt
beside them is the reader guide written for that maintainer.

2_official_record/ holds what the build asks before it compares any wording: the tariff
schedules, Canada's own concordances, the international correlation tables and the two
documents' extractions. The build cannot run without them.

3_crosswalk_code/ holds the complete pipeline that builds the crosswalk, numbered in run
order. Edits here are pulled the same way. Its own README states the order, the data the
stages expect, and where the verification suite lives.

4_candidates_and_decisions/ holds what the pipeline reads and writes between the two
databases and the published tables: the commodity inventories, every candidate with its
similarity score, every threshold with its rationale, and every ruling as readable text.
Its own README names each file.

5_verification_suite/ holds the checks that carry the automated controls and the one
command that rebuilds every stage, runs them all, and repeats the build to prove every artefact
reproduces. It runs in the repository layout, with the two databases in source/. Edits here
are pulled the same way as the code.

Beside these folders sit three files: this README, REPRODUCE.py, and CODE_COMPANION.txt,
which reads the whole pipeline start to finish in run order for anyone who would rather read
it than run it.

The tables in the first and fourth folders are never edited by hand, here or anywhere. A
wrong number is fixed in the generator and re-proven, and the prose in the fourth folder is
vetted in the repository's own documents.

Each folder carries a MANIFEST.txt naming every file with its size and checksum; the pull
uses those fingerprints to see what changed.
