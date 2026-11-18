## 2026-11-17: The person's answer for a test print of the disc's holes uses the checks' hole positions (no result changed)

Codex's review of PR #56 found that the test-print loop still judged a printed pair of disc-screw holes against the old range, 33.2 to 34.22 mm apart (2 × 16.6 to 2 × 17.11), after R1 moved. `pbe/runner/coupon_loop.py` now reads R1's `holes_r` from `tasks/estoa-light/requirements.yaml` (`disk_hole_centers`). Since 2026-11-17 that puts both holes 16.96 mm out, 33.92 apart, with the screws' 0.15 mm play a side as before. A test piece whose holes are 33.2 mm apart now hears that both screws won't go in, where before it heard that they go through.

No saved verdict uses this answer. It only changes what later Estoa runs with test prints first hear. The three `estoa-measured` trials (PR #57) heard the old range. None of them printed a disc-hole test piece, so their replies don't change either way. `tests/test_loop.py` covers it.
