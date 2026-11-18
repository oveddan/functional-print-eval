## 2026-11-17: Estoa: the disc's holes at the middle of Estoa's printed positions, 16.96 mm, which decides the R1 verdicts that weren't graded

**Dan's call (2026-11-17):** "Let's just make the mid-disk 21-disk pass the assumption." R1 had held 21 Estoa designs not graded. Their screws go into the box only if the disc's holes sit at one end of the range Dan's readings and his Estoa print allow (16.81 to 17.11 mm from the disc's center, `changes/2026-11-17-estoa-measured.md`). Each hole is now taken at the middle of that range, 16.96 mm, which until now was the stated assumption, graded apart. R1 and R2 use it directly (`holes_r: [16.96, 16.96]`, a single point). Their `assume` entries are gone, since they would repeat the check.

**Regrade.** Every saved Estoa trial (`pilot-estoa`, `pilot-estoa-carbon`, `test-first`, `estoa-measured`) and every `loop-estoa` replay arm was graded again.
- **8 trials go from not graded to pass:**
  - First print: Haiku 5.5 t4, and Sonnet 5.5 t2, t4 and t5.
  - Test prints first: Opus 5.5 t1 and t4, Gemini 3.8 Flash t3, and Gemini 4 Argon t5.
- **8 replay arms move the same way:** Haiku 5.5 t4's three arms, Opus 5.5 t3's feedback arm, and Sonnet 5.5 t4's and t5's baseline and neutral arms.
- Every other R1 verdict this decides belongs to a design that already fails on something else.
- No verdict on any other task moved.

**Test prints first, five tasks:**

| Model | Before | After |
|---|---|---|
| Gemini 4 Argon | 1. 67% (30/45) | 1. 69% (31/45) |
| GPT-6.1 Sol | 2. 62% (28/45) | 2. 62% (28/45) |
| Gemini 3.8 Flash | 3. 58% (26/45) | 3. 60% (27/45) |
| Sonnet 5.5 | 4. 47% (21/45) | 5. 47% (21/45) |
| Opus 5.5 | 5. 47% (21/45) | 4. 51% (23/45) |
| DeepSeek V4.1 Flash | 6. 36% (16/45) | 6. 36% (16/45) |
| Haiku 5.5 | 7. 12% (3/25) | 7. 12% (3/25) |
| **Pooled** | **49% (145/295)** | **51% (149/295)** |

Opus moves back above Sonnet. Before, they tied at 47% and Sonnet led on cost per pass.

**Estoa:**
- First print: 5 → 9 of 30.
- After feedback: 12 → 14 of 26.
- Test prints first: 5 → 9 of 35.

The first-print and after-feedback columns of the headline cover the four other tasks, so they don't change.

**What this rests on:** neither of Dan's readings decides which end of the range is right. The middle is a call, not a measurement. A design whose screws fit only at 16.81 mm, or only at 17.11 mm, now passes or fails by where 16.96 falls. Dan's call is to go with it: the eval isn't about that half millimeter (2026-11-17).

Also updated: the brief's R1 note, the checks page's R1 text and its stated value (`scripts/results_site_checks.yaml`), the reference's tables (the Estoa assumption rows are gone), the assumption records, and the site's drawings for the designs whose findings changed.
