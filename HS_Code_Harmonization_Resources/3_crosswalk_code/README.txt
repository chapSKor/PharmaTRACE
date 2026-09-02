THE CROSSWALK PIPELINE, IN RUN ORDER

Python 3.14 or later, standard library only; there is nothing to install. The prefix on
each file is its place in the run; the original module name follows it, and every project
document refers to that name. The four helper files are not steps and keep their plain
names.

  01  s01_stage0_read_source.py              read the delivery and build the commodity inventory
  02  s02_stage1_candidates.py               find every retirement and assemble its candidates
  03  s03_stage1b_official_record.py         let the official record speak, in order
  04  s04_stage1c_rank.py                    let meaning veto, then let text rank
  05  s05_make_adjudication_queue.py         build the worklist a person answers
  06  s06_stage2_apply_decisions.py          turn the answers into successions
  07  s07_stage3_route.py                    follow every commodity to the end of its chain
  08  s08_stage4_build_families.py           group the codes that carry the same goods, and name them
  09  s09_stage5_lineage.py                  unfold every journey into steps
  10  s10_stage6_outputs.py                  publish the four tables per flow
   -  _shorthand.py                          helper, imported by the stages
   -  _xlsx.py                               helper, imported by the stages
   -  families.py                            helper, imported by the stages
   -  meaning_gates.py                       helper, imported by the stages

The stages read and write relative to a project root holding source (the two Statistics
Canada databases), decisions, evidence, work and output folders; the repository this folder
was copied from has that layout, and Provenance.txt in the fourth folder of this set names
the public datasets exactly. The verification suite, the check files carrying the automated controls and
the one command that rebuilds and verifies everything twice, is the fifth folder of this
set and runs in that same layout.
