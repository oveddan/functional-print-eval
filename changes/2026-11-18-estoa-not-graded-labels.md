## 2026-11-18: Results site: an Estoa check that isn't graded gives the grader's own reason (no result changed)

`estoa_missing` in `scripts/results_page.py` picked the reason for a not graded Estoa check from the check id alone, so cards gave reasons the grader never wrote. GPT-6.1 Sol's Estoa trial 2 with test prints first (`test-first--estoa-light--can_test--openai__gpt-6.1-sol--t2`) said "The screws may bottom out; the disk's thickness was never measured", though Dan's reading of the disk's thickness (1.56 mm, 2026-11-17) is in `tasks/estoa-light/requirements.yaml`. The grader's note was "a part's mesh isn't a closed volume, so this can't be read".

The reason now comes from the grader's note first, and from the check id only after that:

- A part whose mesh isn't a closed volume (`enclosure.UNREADABLE`, on any check): "A part isn't a closed solid, so the checker can't read it", counted as the checker's limit, not a missing print.
- R2, a screw that runs over the perfboard: "The screws run over the perfboard, where its parts' heights aren't all recorded".
- R2, no screw through one of the disk's holes while R1 can't settle where they are: its own reason. No saved design has it.
- R2's other not graded cases are a screw held by less thread, or less of a nut, than any print showed holds. The old fallback, "the disk's thickness was never measured", is gone: with one recorded thickness the grader's "which wasn't measured" branches can't come up.

`docs/reference.md`'s Estoa section said most not graded checks need "the board's thickness"; it now says most are parts the checker can't read, and the rest mostly need the heights of the perfboard's parts. The photo of the USB wall test print was shown on the 7 R3 cards that were really unreadable meshes. No saved design has that reason now, so the photo is kept and not shown (`PARKED_REASON_PHOTOS` in `tests/test_results_site.py`).

No grade, finding, verdict or saved run changed; only the reason text on Estoa's not graded cards moved. Not graded reasons on Estoa trials, from a full local build (`scripts/results_site.py`, 121 Estoa entries):

| Check | Before | After |
|---|---|---|
| R2 | 11 "the disk's thickness was never measured" | 7 a part the checker can't read, 4 screws over the perfboard |
| R3 | 7 "a USB opening between the size that stopped plugs and the one that seated" | 7 a part the checker can't read |
| R5 | 10 "plastic near the perfboard, where its parts' places aren't recorded" | 7 a part the checker can't read, 3 plastic near the perfboard (unchanged) |
| R1, R6 | 2 parts not placed, 5 keyhole-only | the same |

The table of not graded reasons in `docs/reference.md` leaves Estoa out, so its counts don't move. Site, copy, table and site-file tests: 205 passed.
