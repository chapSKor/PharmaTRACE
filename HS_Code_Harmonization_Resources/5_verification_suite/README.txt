THE VERIFICATION SUITE, AND THE ONE COMMAND

Fifteen check files, one per question, carrying the automated controls, and the command that
runs everything:

    python checks/run_pipeline_end_to_end.py

Run from the repository root, in its layout, with the two databases in source/. It deletes
every derived artefact, runs the ten stages in order, runs every check with the exact
control count per check pinned inside it, then repeats the whole build and compares every
artefact byte for byte. Success reads SOUND; anything else names what failed and exits with a
non-zero code. The paragraph above is the whole of what it does.

The files keep their repository names because the runner calls them by name, and it runs the
stages by their repository names too. The suite therefore runs in the repository as it
stands, not against the prefixed copies in the code folder.

That layout is not the one these folders use. These folders are numbered for reading, and no
checks/ directory exists here. REPRODUCE.py, beside the numbered folders, writes the layout
the runner expects and then runs the command above, so from this package the one command is:

    python REPRODUCE.py --source PATH_TO_THE_DATABASES

sweep_published_columns.py is a separate tool: it overwrites each published column in turn
and re-runs the suite, to find any column no control reads.
