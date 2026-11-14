## 2026-11-13: Results site: a passing design's part can be downloaded as an STL (no result changed)

A trial that passes now has a "Download STL" button beside its picture and in its 3D view, for each final part. The file is made in the reader's browser from the same mesh the 3D view shows (`scripts/results_site/stl.js`, three.js's STL exporter), in millimetres and in the orientation the model drew it, so nothing new is stored on the media host. A line under the button says the design passes every check against the recorded test prints and hasn't been printed.

Only passing designs get the button, and only their final parts, not their test prints: a file offered on a failing design would read as "print this".

Evidence: for Opus 5.5's tripod plate, trial 5, the exported file is a well-formed binary STL (1,056 triangles, 52,884 bytes, which is 84 + 50 per triangle) whose bounding box is 37.8 × 60 × 11 mm, the size the site records for that part. `tests/test_results_site.py` checks the button's condition. The file was not opened in a slicer.
