// The assembled view's words and its "Play the fit" control, for a wheel, tripod plate or knob (scene.notes is set)
// and for the Estoa light box. The fit is an illustration of what the recorded test print of that size did, taken
// from the saved check's own words in scripts/hardware_scene.py; nothing here decides an outcome.

import { h, reader } from "./util.js";

const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const OUTCOME = {
  seats: "it goes in and stays",
  stops: "it won't go in, so it stops at the opening",
  falls: "it goes in but is too loose, so it drops out when the part is turned over",
};
// What the still view shows before the fit is played.
const RESTING = {
  seats: "It's shown in place.",
  stops: "It's shown where it stops, at the opening.",
  falls: "It's shown pressed in, as it went in; turned over, it falls out.",
};
// How each kind of part is turned for the view.
const TURNED = {
  wheel: "stood on its edge with the axle level, as it runs",
  plate: "with the clamp's face down and the camera's side up, as it's used",
  knob: "with the face the nut goes in from on top (a knob has no one way up)",
};

export const isHardwareScene = (scene) => Array.isArray(scene?.notes);

// The caption's first line.
export function sceneIntro(scene) {
  if (isHardwareScene(scene)) {
    const turned = TURNED[scene.kind] || "turned the way it's used";
    return `A render of the design, ${turned}, with the person's real parts drawn where the checks found their seat, pocket or hole. Nothing here was printed or assembled.`;
  }
  const plug = scene.layers.some((layer) => layer.key === "plug") ? ", the USB-C plug (where it reaches the port)" : "";
  return `A render of the printed parts with the LED disk (see-through), the perfboard${plug} and the screws where the design puts them. Nothing here was printed or assembled.`;
}

// What the fit shows, or why there's none, and the notes on what's drawn from estimates.
export function fitCaption(scene) {
  if (!isHardwareScene(scene)) return null;
  const nodes = [];
  if (scene.fit) {
    const source = scene.fit.assumed
      ? `That is what the nearest recorded test print did (the size is within the assumption tolerance of it), as ${scene.fit.check} records it`
      : `That is what the test print of this size did, as ${scene.fit.check} records it`;
    nodes.push(h("p", { class: "fit-line" }, h("strong", {}, "Play the fit: "),
      `${OUTCOME[scene.fit.outcome]}. ${source} (“${reader(scene.fit.detail)}”). ${RESTING[scene.fit.outcome]} `,
      h("span", { class: "caption-note" }, "An illustration of that recorded outcome, not a simulation, and this design wasn't printed.")));
    if (scene.fit.note) nodes.push(h("p", { class: "caption-note" }, scene.fit.note));
  } else if (scene.fit_note) {
    nodes.push(h("p", { class: "caption-note" }, reader(scene.fit_note.replace(/^No fit is played: /, "No fit to play: "))));
  }
  for (const note of scene.notes) nodes.push(h("p", { class: "caption-note" }, note));
  return nodes;
}

// The play button, for a mounted view whose scene has a fit. The layer checkboxes beside it follow what the fit
// hides and shows (matched by their label), so a box is never ticked on a hidden layer or the reverse.
export function fitControls(mounted) {
  if (!mounted.canPlayFit) return [];
  let changed = false;   // the view shows a fit's end state that isn't the assembled one
  const button = h("button", { type: "button", class: "btn btn-primary" }, "Play the fit");
  const label = () => { button.textContent = changed ? "Back to the still view" : "Play the fit"; };
  mounted.onLayerShown((key, on) => {
    const name = mounted.layers.find((layer) => layer.key === key)?.label;
    const box = [...(button.closest(".stage-controls")?.querySelectorAll("label.check-toggle") || [])]
      .find((found) => found.textContent.trim() === name)?.querySelector("input");
    if (box) box.checked = on;
  });
  button.addEventListener("click", async () => {
    if (changed) { mounted.endFit(); changed = false; label(); return; }
    changed = true;
    label();
    const seated = await mounted.playFit({ reduced: calm() });
    if (seated) { changed = false; label(); }
  });
  return [button];
}

// Why a wheel, tripod plate or knob has no assembled view, when the media manifest says.
export function noSceneNote(media) {
  if (!media?.scene_none || media.scene) return null;
  return h("p", { class: "caption-note" }, `No assembled view: ${media.scene_none}.`);
}
