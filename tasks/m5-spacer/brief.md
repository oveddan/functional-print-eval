# M5 spacer (control)

A control task. Everything is stated and nothing is withheld, and each check is simple, so a
frontier model should pass. If models fail it, the harness, the prompt or the submission format
is broken, not the model's design skill. It's reported apart from the real tasks. The person's
words are a draft until Dan writes or approves them.

> I need a round spacer to go on an M5 bolt between two plates. Make it 20 mm long and 12 mm across, with a clearance hole for the bolt.

What's checked, in code (`requirements.yaml`), besides the standard checks every task gets
(the code builds, each part is one body, it fits the bed, every overhang can be bridged):
- one printed part;
- its bounding box is 20 x 12 x 12 mm, within 0.2 mm;
- one hole runs the full length: a cross-section every 0.2 mm (each layer) has exactly one hole,
  at least 5.3 mm clear at its narrowest and at most 5.8 mm at its widest, ISO 273's fine to
  coarse clearance hole for M5;
- the outline is round.

"Round" is in the request because "12 mm across" is ambiguous for a hex spacer (12 across flats
is 13.9 across corners), and the size check would fail a hex that some would accept. The hole's
position isn't checked: the request doesn't say it's centred, so checking it would grade
something the task never states.
