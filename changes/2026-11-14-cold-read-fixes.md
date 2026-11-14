## 2026-11-14: README opening, half-up percentages, and stale reference text from a cold read

Before announcing, GPT-6.1 Sol and Gemini 4 Argon read the README, `docs/reference.md` and the live results site as first-time visitors ($0.35 through OpenRouter). Only findings checked against the files or the saved runs were acted on.

- **Percentages round half up.** `scripts/scorecard.py` used Python's `round()`, which sends 62.5 to 62, while the site rounds half up, so the same 25 of 40 read 62% in the README and 63% on the site. No count changes; GPT-6.1 Sol's, Opus 5.5's, Gemini 3.8 Flash's, Haiku 5.5's and GLM 5.3 Flash's affected cells now match the site.
- **README opening** says what the eval is first, says what the scored tasks actually are (single printed parts that fit real hardware, plus the harder Estoa enclosure), that assembly steps aren't graded yet, and links the results site.
- **Pass definition** says it rests on the documented assumptions and links them; the cost columns say print time and filament are slicer estimates and cost is the API's.
- **README:** the turn limit is 12 with test prints and 8 otherwise (it said 12); C3 no longer claims the checks catch thin insert posts, which pass for now (2026-11-13).
- **Estoa wording:** "12 of the 26 designs replayed (every one that had failed when the replays ran)", since 5 of 30 now pass on the first print.
- **docs/reference.md:** the README link went one folder too far; the clone command used the repo's old name; Estoa and Servo mount were listed as unmerged; Estoa's row showed the first 18 trials; "pilots, not pass rates" and "five trials per model" were stale; Sonnet 5.5's wheel t3 and Opus 5.5's ribbed M5 t2 were captioned with verdicts round 3 changed; the not-graded bearing-seat reason named sizes round 3 settled (the one left is a ribbed seat); the "no more prints before publishing" call is now dated, since round 3 came after it.
