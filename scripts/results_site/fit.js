// The assembled view's words and its "Play the fit" control, for a wheel, tripod plate or knob (scene.notes is set)
// and for the Estoa light box. The fit is an illustration of what the recorded test print of that size did, taken
// from the saved check's own words in scripts/hardware_scene.py; nothing here decides an outcome.

import { h } from "./util.js";

const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const OUTCOME = {
  seats: "it goes in and stays",
  stops: "it won't go in, so it stops at the opening",
  falls: "it goes in but is too loose, so it drops out when the part is turned over",
};

export const isHardwareScene = (scene) => Array.isArray(scene?.notes);

// The caption's first line.
export function sceneIntro(scene) {
  if (isHardwareScene(scene)) {
    return "A render of the design, turned the way it's used, with the person's real parts drawn where the grader found their seat, pocket or hole. Nothing here was printed or assembled.";
  }
  const plug = scene.layers.some((layer) => layer.key === "plug") ? ", the USB-C plug (where it reaches the port)" : "";
  return `A render of the printed parts with the LED disk (see-through), the perfboard${plug} and the screws where the design puts them. Nothing here was printed or assembled.`;
}

// What the fit shows, or why there's none, and the notes on what's drawn from estimates.
export function fitCaption(scene) {
  if (!isHardwareScene(scene)) return null;
  const nodes = [];
  if (scene.fit) {
    nodes.push(h("p", { class: "fit-line" }, h("strong", {}, "Play the fit: "),
      `${OUTCOME[scene.fit.outcome]}. That is what the test print of this size did, as ${scene.fit.check} records it (“${scene.fit.detail}”). `,
      h("span", { class: "caption-note" }, "An illustration of that recorded outcome, not a simulation, and this design wasn't printed.")));
    if (scene.fit.note) nodes.push(h("p", { class: "caption-note" }, scene.fit.note));
  } else if (scene.fit_note) {
    nodes.push(h("p", { class: "caption-note" }, scene.fit_note.replace(/^No fit is played: /, "No fit to play: ")));
  }
  for (const note of scene.notes) nodes.push(h("p", { class: "caption-note" }, note));
  return nodes;
}

// The play button, for a mounted view whose scene has a fit.
export function fitControls(mounted) {
  if (!mounted.canPlayFit) return [];
  let playing = false;
  const button = h("button", { type: "button", class: "btn btn-primary" }, "Play the fit");
  const label = () => { button.textContent = playing ? "Show it assembled" : "Play the fit"; };
  button.addEventListener("click", async () => {
    if (playing) { mounted.endFit(); playing = false; label(); return; }
    playing = true;
    label();
    await mounted.playFit({ reduced: calm() });
  });
  return [button];
}

// Why a wheel, tripod plate or knob has no assembled view, when the media manifest says.
export function noSceneNote(media) {
  if (!media?.scene_none || media.scene) return null;
  return h("p", { class: "caption-note" }, `No assembled view: ${media.scene_none}.`);
}
