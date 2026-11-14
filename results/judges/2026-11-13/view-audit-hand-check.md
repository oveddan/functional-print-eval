# View audit: hand check of 10 judgments

The run: `view-audit.jsonl` beside this file (Jev 1.14, `typesafe/jev-1.14-20261014`, question v1: "Does this image show this failure clearly enough for a person to see what is wrong?", yes at p ≥ 0.5).

**Who checked.** Claude (Opus 5.5), an LLM too, looked at each image (the local copy under `results/local/site-views/objects/`) with its caption and wrote an answer before setting it beside the judge's. This is a sanity check, not ground truth. The column for Dan's own call is empty.

**How the 10 were picked.** Stratified by hand from the finished run: four of the judge's lowest answers (two clear "no", two near the line), two just over the line, and four confident "yes" in the commonest kinds (bridge layer, nut pocket fit, bearing seat fit, a test print's pieces). Picking by p meant Claude knew roughly which side of the line each fell on before looking, so the blinding is partial: each answer below was written from the image, before the exact p was read back. Row 3 was meant to be the 3-piece `coupon_thread` view at p 0.19; the lookup matched a different `coupon_thread` image first (2 pieces, p 0.92), and that one is what was checked.

**Agreement: 7 of 10.** Claude agreed with all 6 of the judge's "yes" answers and with 1 of its 4 "no" answers.

| # | Kind (check) | Caption, shortened | Image | Judge p(yes) | Judge | Claude | Agree | Claude's reason | Dan |
|---|---|---|---|---|---|---|---|---|---|
| 1 | final-parts (R1) | One printed part: fails. 2 printed parts: knob, coupon | [b998c518/design-R1.webp](https://media.danoved.xyz/print-build-eval/site/b998c518/design-R1.webp) | 0.08 | no | yes | no | Two labelled parts side by side, which is the failure: a person sees there are two. | |
| 2 | wheel-bolt (R4) | M8 bolt goes through: fails. No hole runs through the wheel | [773ef00e/design-R4.webp](https://media.danoved.xyz/print-build-eval/site/773ef00e/design-R4.webp) | 0.14 | no | no | yes | Only the bolt's dotted outline is drawn: no wheel, no red "plastic in the bolt's way", though the legend lists both. The drawing is empty where the failure should be. | |
| 3 | pieces (connected_bodies), test print | Each part is one piece (test print coupon_thread): fails. 2 pieces, not all on the bed | [7a09c797/coupon_thread-connected_bodies.webp](https://media.danoved.xyz/print-build-eval/site/7a09c797/coupon_thread-connected_bodies.webp) | 0.92 | yes | yes | yes | The thread is red and stands apart from the base in both the top and side views. | |
| 4 | back-keyholes (R6) | Hangs on the wall screws: fails. Nothing in the back for the wall screws to go through | [14733bf5/design-R6.webp](https://media.danoved.xyz/print-build-eval/site/14733bf5/design-R6.webp) | 0.35 | no | yes | no | A plain disc with no openings: the absence is the failure, and it shows. The legend lists keyhole and screw-head marks that aren't drawn, which could confuse a reader. | |
| 5 | bridge-layer (bridges) | 1 unbridgeable overhang at z = 3.0 mm, 150 mm², 5% of strands anchored | [f35f5921/plate-bridges.webp](https://media.danoved.xyz/print-build-eval/site/f35f5921/plate-bridges.webp) | 0.47 | no | yes | no | The roof over air is a red strip along one edge, with red strands in the zoom and a red line in the side cut. Small but marked. | |
| 6 | screw-cut (R2) | Disk screws hold safely: fails. An 8 mm screw bottoms out 4.0 mm behind the board | [82101fd7/design-R2.webp](https://media.danoved.xyz/print-build-eval/site/82101fd7/design-R2.webp) | 0.51 | yes | yes | yes | Section through the screw. The red block is where the screw runs into plastic below the hole. | |
| 7 | enclosure-cut (R3) | USB-C plug reaches the port: fails. The board isn't inside the box: nothing on its +x, -x, +y side | [ea7dc6e1/design-R3.webp](https://media.danoved.xyz/print-build-eval/site/ea7dc6e1/design-R3.webp) | 0.53 | yes | yes | yes | Red arrows labelled "nothing on +x/-x/+y" run out from the board's point through gaps in the box. The board itself (in the legend) is hard to find. | |
| 8 | bridge-layer (bridges) | 1 unbridgeable overhang at z = 5.4 mm, 177 mm², 41% of strands anchored | [f59e7066/tripod_qr_plate-bridges.webp](https://media.danoved.xyz/print-build-eval/site/f59e7066/tripod_qr_plate-bridges.webp) | 0.84 | yes | yes | yes | The ring roof is red, with red and green strands in the zoom and red segments in the side cut. | |
| 9 | pocket-fit (R4) | Nut presses in and stays: fails. Pocket 5.50 across flats, +0.00 over the 5.5 nut | [896ae1b5/design-R4.webp](https://media.danoved.xyz/print-build-eval/site/896ae1b5/design-R4.webp) | 0.92 | yes | yes | yes | The nut outline fills the hex, and a number line puts this pocket at +0.00 "won't go in", left of the sizes that held. | |
| 10 | wheel-seat-fit (R3) | Bearings press in and stay: fails. 21.91 mm, a 22.05 mm seat wouldn't take the bearing | [0010d36d/design-R3.webp](https://media.danoved.xyz/print-build-eval/site/0010d36d/design-R3.webp) | 0.89 | yes | yes | yes | The seat widths are labelled on the cut, and the number line puts 21.91 left of the "wouldn't take it" mark. | |

**What this says about the judge.** It said yes to 773 of 785 views (98.5%). In this sample its "yes" answers held up. Its "no" answers mostly didn't: three of four were drawings Claude found legible, each with a short caption or a small marked area. The one "no" Claude agreed with (row 2) is a real defect in the drawing, not just a hard one to read. So a low p is a cheap pointer to drawings worth a look, not a finding. A high p doesn't show the drawing is right, only that the judge found the captioned thing in it.

## Since redrawn (views manifest version 5)

The drawings were redrawn after this check: 791 views changed URL and 10 lost their view (`results/local/site-views/changed-urls.tsv`, local). The judge was rerun on the new images; the old rows stay in `view-audit.jsonl` and are left out of the summary. Nine of the ten checked images were redrawn. The judgments in the table above are kept as they were made, on the old images. The new image and the judge's new score are listed below. Nobody has looked at the new images again for this file.

| # | Kind | Old judge p(yes) | Now | New image | New judge p(yes) | New judge |
|---|---|---|---|---|---|---|
| 1 | final-parts | 0.08 | redrawn | [f502834f/design-R1.webp](https://media.danoved.xyz/print-build-eval/site/f502834f/design-R1.webp) | 0.58 | yes |
| 2 | wheel-bolt | 0.14 | no view now: the manifest says "the wheel built as a flat sheet 0.00 mm thick, so there's no section to cut" | none | n/a | n/a |
| 3 | pieces (test print) | 0.92 | redrawn | [90f7a45f/coupon_thread-connected_bodies.webp](https://media.danoved.xyz/print-build-eval/site/90f7a45f/coupon_thread-connected_bodies.webp) | 0.94 | yes |
| 4 | back-keyholes | 0.35 | redrawn | [fb51342d/design-R6.webp](https://media.danoved.xyz/print-build-eval/site/fb51342d/design-R6.webp) | 0.52 | yes |
| 5 | bridge-layer | 0.47 | redrawn | [9c8407d4/plate-bridges.webp](https://media.danoved.xyz/print-build-eval/site/9c8407d4/plate-bridges.webp) | 0.69 | yes |
| 6 | screw-cut | 0.51 | redrawn | [6476ff67/design-R2.webp](https://media.danoved.xyz/print-build-eval/site/6476ff67/design-R2.webp) | 0.46 | no |
| 7 | enclosure-cut | 0.53 | redrawn | [bb343d4c/design-R3.webp](https://media.danoved.xyz/print-build-eval/site/bb343d4c/design-R3.webp) | 0.37 | no |
| 8 | bridge-layer | 0.84 | redrawn | [06bf8379/tripod_qr_plate-bridges.webp](https://media.danoved.xyz/print-build-eval/site/06bf8379/tripod_qr_plate-bridges.webp) | 0.84 | yes |
| 9 | pocket-fit | 0.92 | redrawn | [a9d91e13/design-R4.webp](https://media.danoved.xyz/print-build-eval/site/a9d91e13/design-R4.webp) | 0.92 | yes |
| 10 | wheel-seat-fit | 0.89 | unchanged (same URL and bytes) | [0010d36d/design-R3.webp](https://media.danoved.xyz/print-build-eval/site/0010d36d/design-R3.webp) | 0.89 | yes |

The 7 of 10 agreement applies to the first run's images only.
