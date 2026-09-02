THE PUBLISHED CROSSWALK

Four tables per trade flow. The lookup is one row per commodity string: what it was, what
it became, and its family. The commodity journeys give the whole path per string. The
lineage timeline gives one row per step. The provenance states what settled every chain
and whether the official record agrees.

The v1_to_v2_identifiers files map the released identifiers to the corrected ones, both
directions. The gate2 tail disclosure lists the commodity strings that stopped trading
without a recorded termination; the reuse silence disclosure lists the long quiet spells
kept inside one commodity because the wording never changed.

The lookup, the journeys and the timeline join on orig_commodity, the full source commodity
string, and join with the provenance on uid. A reader guide for an application built against
the released tables is in this folder: Crosswalk consumer notes.txt.
