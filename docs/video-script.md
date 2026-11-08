# Video outline (under 5 minutes)

Every spoken line is copied from the README, in Dan's own words, so the video and the README say the same thing. Every shot is a picture, GIF or page already in the README or the repo, plus new footage marked **New**. Lines in [brackets] are notes, not narration. About 650 spoken words, roughly 4.5 minutes at a normal pace, which leaves room for the longer timelapse.

## 1. Why (0:00 to 0:50)

| Shot | Say |
|---|---|
| The Estoa light on the wall, then the OpenSCAD screenshot | 3D printing is becoming far more accessible to the general public, as state of the art printers have become cheaper while increasing their capabilities, and LLMs can generate designs using open source tools, without a user needing to learn 3D modeling or purchase expensive software. |
| The enclosure coming apart and back together, the frosted wall, the insert test print | Over the past month, I've been working on a bunch of 3D printing projects at home. A week before a gallery show, I was asked to make a piece for it. A key part of all of this was doing test prints: to see how the frosting looked, and whether the inserts fit the holes the model designed. |
| The warped insert post and the back plate | In the design process, these models often make mistakes, which are costly both in time and money, as prints can take hours to complete, and physical material is consumed. |
| The examples grid | How can we determine which models produce the best designs, with the least amount of tokens spent, material consumed, and time waited for printing? |

## 2. The test prints (0:50 to 1:50)

The longer stretch Dan asked for: let the footage run, with his words from the time over it.

| Shot | Say |
|---|---|
| Round one timelapse, full length | The hackathon started on Oct 30, but I was flying away from home that day and would be away from my 3D printer for the whole hackathon. So on Oct 28, I began creating test prints that could provide the ground truth for parts of the 3D printing simulation. |
| Round one timelapse continues | Each print tests the ground truth of one thing. For example, if there's a roof over a hole, will it print successfully? |
| The roof strip, the tunnel underside | [Dan at the time:] "We're testing if the modeling tool properly predicts if a print is going to be okay when there's a bridge." "Both tunnels got messed up." |
| The nut-pressing video, full length | We printed nut pockets at different sizes, using different techniques, to see which size a nut would fit into snugly without falling out. |
| Round two timelapse, then the servo photo | [Dan at the time:] "The small servo goes into 3, it's snug. For 2, you really have to push. For 1 and none, it doesn't go in." |
| **New:** Dan's hands testing a print, if there's footage | [Dan at the time:] "Ok, so are we good now? Cause I'm flying tomorrow, I won't have access to the printer." |

## 3. How a trial runs (1:50 to 2:50)

| Shot | Say |
|---|---|
| The flowchart | A person asks in plain language for a printed fix: a camera plate, a knob with a nut pressed in, a wheel with bearings. |
| The flowchart, the measure and test-print steps | The model decides if it needs to know if an aspect of a print will work, such as an opening, or a connection between hardware and the print. It can then design a test print that can help answer this. |
| The failure-class table | Every one of our checks comes from failures that happened on my real builds. We used AI to scrape my existing sessions, found 57 failures, and categorized them into 10 classes. |
| The storyboard, panel by panel | In each trial, nothing actually gets printed. We have checks, run by code, that simulate the model's parts and compare them with the results of my test prints to see if they would print successfully. Here's an example of a trial that failed and then succeeded after we gave the model feedback about what failed. |

## 4. Results (2:50 to 3:50)

| Shot | Say |
|---|---|
| The results table, the winner's column outlined | [Read the first three lines of "Best to worst" from the README once it's regenerated with the test-first run.] |
| The knob gallery: Sonnet's pocket cut across, 5.50 mm against the 5.5 mm nut | The models design a print without really understanding the constraints of 3D printing. They design a place to slot in a nut without any kind of gap, so the nut won't go in. |
| The wheel gallery | The models do make test prints, but they test the wrong thing. On the wheel they tested if the bearing fits, and mostly got that right. Then the wheel failed on stuff they never tested. |
| The not-graded table with its pictures | For the duration of the hackathon, I was away from my 3D printer, so I could not print additional test prints that would help me grade unanticipated designs that the model produced. We can't count this kind of trial as a pass, because we don't know the truth, so we mark it as not graded. |

## 5. Takeaway (3:50 to 4:40)

| Shot | Say |
|---|---|
| The knob test-print assembly GIF | A test print is like a unit test of code. An experienced 3D print designer would know the edge cases of what can go wrong, and would make a test that minimally tests a specific error. A good test print, like a good unit test, tests just one thing, and can save loads of time when printing the final result. |
| The back plate again | The final print is like deploying a release, except the consequences of being wrong are more expensive than in software, in both time and material. |

## Recording notes

- Record in OBS as Apple VT ProRes 422, 1920x1080, 30 fps, then make an H.264 copy to upload. Check the first take's bitrate with ffprobe before recording the rest.
- The timelapses and the nut video are on R2 (links in the README); use the full-length originals from Dan's movies folder for section 2, not the GIFs.
- Scroll the README on GitHub for the rest. Upload somewhere the link opens without asking for permission, and keep it under 5 minutes.
