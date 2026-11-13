| Test | Model | Agrees with recorded key | After hand check | Commonest-answer baseline | Calls | Median latency per call | Cost | Failed calls |
|---|---|---|---|---|---|---|---|---|
| 1-supports | GPT-6 Luna | 42/44 (95%) | 43/44 (98%) | 23/44 (52%) | 22 | 0.41 s | $0.0023 | 0 |
| 1-supports | Jev 1.14 | 42/44 (95%) | 43/44 (98%) | 23/44 (52%) | 22 | 0.26 s | $0.0010 | 0 |
| 2-outcomes | GPT-6 Luna | 36/40 (90%) | 36/40 (90%) | 16/40 (40%) | 40 | 0.35 s | $0.0009 | 0 |
| 2-outcomes | Jev 1.14 | 33/40 (82%) | 33/40 (82%) | 16/40 (40%) | 40 | 0.24 s | $0.0007 | 0 |
| 3-box | Jev 1.14 | 13/13 (100%) | 13/13 (100%) | 13/13 (100%) | 2 | 0.51 s | $0.0004 | 0 |
| 3-photos | GPT-6 Luna | 13/19 (68%) | 13/19 (68%) | 13/19 (68%) | 19 | 0.48 s | $0.0009 | 0 |
| 3-photos | Jev 1.14 | 13/19 (68%) | 13/19 (68%) | 13/19 (68%) | 19 | 0.30 s | $0.0010 | 0 |
| 3c-references | GPT-6 Luna | 10/19 (53%) | 10/19 (53%) | 13/19 (68%) | 19 | 0.62 s | $0.0044 | 0 |
| 3c-references | Jev 1.14 | 9/19 (47%) | 9/19 (47%) | 13/19 (68%) | 19 | 0.54 s | $0.0049 | 0 |
| 4-checklist | GPT-6 Luna | 222/238 (93%) | 244/250 (98%) | 176/250 (70%) | 46 | 0.41 s | $0.0271 | 2 |
| 4-checklist | Jev 1.14 | 229/246 (93%) | 250/258 (97%) | 184/258 (71%) | 48 | 0.27 s | $0.0098 | 0 |
| 5-classes | GPT-6 Luna | 38/57 (67%) | 38/57 (67%) | 13/57 (23%) | 57 | 0.34 s | $0.0033 | 0 |
| 5-classes | Jev 1.14 | 49/57 (86%) | 49/57 (86%) | 13/57 (23%) | 57 | 0.24 s | $0.0021 | 0 |
| 5-held-out | GPT-6 Luna | 40/57 (70%) | 40/57 (70%) | 57/57 (100%) | 57 | 0.35 s | $0.0030 | 0 |
| 5-held-out | Jev 1.14 | 11/57 (19%) | 11/57 (19%) | 57/57 (100%) | 57 | 0.24 s | $0.0019 | 0 |
| 7-measure | GPT-6 Luna | 564/2330 (24%) | 564/2330 (24%) | 437/2330 (19%) | 2688 | 0.35 s | $0.4705 | 0 |
| 7-measure | Gemini Decision 1 | 664/2330 (28%) | 664/2330 (28%) | 437/2330 (19%) | 2688 | 0.34 s | $0.2934 | 0 |
| 7-measure | Jev 1.14 | 505/2330 (22%) | 505/2330 (22%) | 437/2330 (19%) | 2688 | 0.25 s | $0.1128 | 0 |
| 7b-measure-listed | Jev 1.14 | 427/2330 (18%) | 427/2330 (18%) | 437/2330 (19%) | 2688 | 0.24 s | $0.2410 | 0 |
| 7c-measure-said | Jev 1.14 | 411/2330 (18%) | 411/2330 (18%) | 437/2330 (19%) | 2688 | 0.23 s | $0.1375 | 0 |
| 7d-single-asks | Jev 1.14 | 413/479 (86%) | 413/479 (86%) | 320/479 (67%) | 479 | 0.26 s | $0.0144 | 0 |

Total reported cost: $1.3333

| Test | Question | Model | Recorded key | After hand check | Baseline |
|---|---|---|---|---|---|
| 1-supports | asks_plainly | GPT-6 Luna | 20/22 (91%) | 21/22 (95%) | 16/22 (73%) |
| 1-supports | asks_plainly | Jev 1.14 | 21/22 (95%) | 22/22 (100%) | 16/22 (73%) |
| 1-supports | expects_supports | GPT-6 Luna | 22/22 (100%) | 22/22 (100%) | 15/22 (68%) |
| 1-supports | expects_supports | Jev 1.14 | 21/22 (95%) | 21/22 (95%) | 15/22 (68%) |
| 4-checklist | any_test | GPT-6 Luna | 18/18 (100%) | 18/18 (100%) | 11/18 (61%) |
| 4-checklist | any_test | Jev 1.14 | 18/18 (100%) | 18/18 (100%) | 11/18 (61%) |
| 4-checklist | bridge_reasoned | GPT-6 Luna | no key | 4/4 (100%) | 4/4 (100%) |
| 4-checklist | bridge_reasoned | Jev 1.14 | no key | 4/4 (100%) | 4/4 (100%) |
| 4-checklist | disk_holes | GPT-6 Luna | 46/46 (100%) | 46/46 (100%) | 46/46 (100%) |
| 4-checklist | disk_holes | Jev 1.14 | 48/48 (100%) | 48/48 (100%) | 48/48 (100%) |
| 4-checklist | esp32_height | GPT-6 Luna | 42/46 (91%) | 44/46 (96%) | 42/46 (91%) |
| 4-checklist | esp32_height | Jev 1.14 | 42/48 (88%) | 44/48 (92%) | 44/48 (92%) |
| 4-checklist | fastener_test | GPT-6 Luna | 16/18 (89%) | 16/18 (89%) | 11/18 (61%) |
| 4-checklist | fastener_test | Jev 1.14 | 17/18 (94%) | 17/18 (94%) | 11/18 (61%) |
| 4-checklist | keyhole_test | GPT-6 Luna | 16/18 (89%) | 16/18 (89%) | 15/18 (83%) |
| 4-checklist | keyhole_test | Jev 1.14 | 16/18 (89%) | 16/18 (89%) | 15/18 (83%) |
| 4-checklist | plug_head | GPT-6 Luna | 39/46 (85%) | 46/46 (100%) | 32/46 (70%) |
| 4-checklist | plug_head | Jev 1.14 | 41/48 (85%) | 48/48 (100%) | 34/48 (71%) |
| 4-checklist | screw_length | GPT-6 Luna | no key | 4/4 (100%) | 4/4 (100%) |
| 4-checklist | screw_length | Jev 1.14 | no key | 3/4 (75%) | 4/4 (100%) |
| 4-checklist | tool_reach | GPT-6 Luna | no key | 4/4 (100%) | 4/4 (100%) |
| 4-checklist | tool_reach | Jev 1.14 | no key | 4/4 (100%) | 4/4 (100%) |
| 4-checklist | wall_screw_size | GPT-6 Luna | 45/46 (98%) | 46/46 (100%) | 39/46 (85%) |
| 4-checklist | wall_screw_size | Jev 1.14 | 47/48 (98%) | 48/48 (100%) | 41/48 (85%) |

| Cell | IoU with Claude's box |
|---|---|
| IMG_6164.HEIC ring roof 10 | 0.89 |
| IMG_6164.HEIC ring roof 9 | 0.91 |
| IMG_6164.HEIC ring roof 8 | 0.60 |
| IMG_6164.HEIC ring roof 7 | 0.70 |
| IMG_6164.HEIC ring roof 6 | 0.57 |
| IMG_6164.HEIC ring roof 5 | 0.51 |
| IMG_6164.HEIC ring roof 4 | 0.49 |
| IMG_6164.HEIC ring roof 3 | 0.52 |
| IMG_6164.HEIC ring roof 2 | 0.60 |
| IMG_6164.HEIC ring roof 1 | 0.69 |
| IMG_6188.HEIC 100 mm span | 0.41 |
| IMG_6188.HEIC 80 mm span | 0.18 |
| IMG_6188.HEIC 60 mm span | 0.53 |

| Flag rule | Held-out class flagged | Offered class flagged (false flag) |
|---|---|---|
| GPT-6 Luna says none | 40/57 (70%) | 6/57 (11%) |
| Jev 1.14 says none | 11/57 (19%) | 1/57 (2%) |
| Jev 1.14 says none or its pick is under 0.5 | 26/57 (46%) | 7/57 (12%) |
| Luna says none and Jev's pick is under 0.7 (tuned on this run) | 34/57 (60%) | 4/57 (7%) |
