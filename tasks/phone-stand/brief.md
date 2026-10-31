# Desk phone stand

What the model is given. The consumer's words are a draft until Dan writes or approves them.

> Design a printable phone stand that clamps to the edge of my desk and lets me film myself while I work.

Also given:
- `catalog/hardware.yaml`: the hardware bin, with real specs including partly threaded bolts.
- `catalog/printer.yaml`: printer and filament profiles. The printer's dimensional error stays hidden.

The model must return:
1. CadQuery code for every part, with print orientation.
2. A bill of materials using only the hardware bin.
3. A test-print plan with pass criteria.
4. A step-by-step assembly manual, naming the parts used in each step.

Facts in `hidden_facts.yaml` are revealed only if the model asks for them.
