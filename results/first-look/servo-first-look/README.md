# servo-first-look

The first run of `servo-mount`, 2026-11-05: one trial per lineup model in `can_ask` and `all_given`, $1.50.

Run without the cable's location. The catalog's `tab_shape` note says where the MG996R's cable leaves the case, but `hidden_facts.yaml` didn't carry it, so `measure` couldn't answer it and `all_given` didn't state it. R3 fails a plain cutout seated from above on test print D's cable-exit record, so 7 of its R3 failures rest on a fact no model could learn. That was the eval's fault, and the note was added before `servo-first-look-2`, which is the run to read. This one is kept as the record of what went wrong.

Two trials needed retries: Opus `can_ask` (the OpenRouter key's limit) and Gemini 4 Argon `can_ask` (a 502, then the key's limit), so their records show the last attempt.
