// "How the checks work": data/checks.json (scripts/results_site.py, from scripts/results_site_checks.yaml and the
// saved results) as one page. Every string from the data goes in as a text node, never as HTML.

import { h, add, clear, badge, VERDICT, plural } from "./util.js";

const $ = (id) => document.getElementById(id);
const OUTCOME_WORD = { pass: "Passes", fail: "Fails", "not graded": "Not graded" };

function figure(example) {
  const view = example.view;
  if (!view) {
    return example.no_view_reason ? h("p", { class: "ck-noview" }, `No drawing: ${example.no_view_reason}.`) : null;
  }
  const [width, height] = view.width && view.height ? [view.width, view.height] : [900, 800];
  const image = h("img", { src: view.url, alt: view.caption, loading: "lazy", decoding: "async", width: String(width), height: String(height) });
  const link = h("a", { href: view.url, target: "_blank", rel: "noopener", title: "Open the drawing at full size" }, image);
  image.addEventListener("error", () => link.replaceWith(h("p", { class: "ck-noview" }, "The drawing didn't load.")), { once: true });
  return h("figure", { class: "ck-fig", style: `--ratio: ${width} / ${height}` }, link,
    h("figcaption", { class: "fine" }, "Drawn from the design's geometry by the check's own code. Not printed."));
}

function exampleCard(example) {
  if (example.missing) {
    return h("li", { class: "ck-example" }, h("p", { class: "ck-noview" }, `This example (${example.trial_id}) isn't in the saved results any more.`));
  }
  const state = example.state || example.outcome;
  const meta = VERDICT[state] || VERDICT.error;
  return h("li", { class: `ck-example ${meta.cls}` },
    h("div", { class: "ck-example-head" },
      badge(state, { small: true, label: example.label || OUTCOME_WORD[state] || meta.label }),
      h("a", { href: example.href }, `${example.model_short}, ${example.task_label}, trial ${example.trial}`),
      example.part && example.part !== "-" ? h("span", { class: "fine" }, " on ", h("code", {}, example.part)) : null),
    example.failed_title ? h("p", { class: "ck-fail-title" }, example.failed_title) : null,
    example.detail ? h("p", { class: "ck-found" }, h("span", { class: "ck-label" }, "The check found: "), example.detail) : null,
    example.via_test_print && !example.label ? h("p", { class: "ck-note" }, "This pass rests on the design's test print or template, not on its size as drawn.") : null,
    example.note ? h("p", { class: "ck-note" }, example.note) : null,
    figure(example),
    example.drawing_note ? h("p", { class: "fine" }, `In the drawing: ${example.drawing_note}.`) : null);
}

function photo(found) {
  if (!found) return null;
  const image = h("img", { src: found.thumb || found.url, alt: found.caption, loading: "lazy", decoding: "async", width: String(found.width), height: String(found.height) });
  const link = h("a", { href: found.url, target: "_blank", rel: "noopener", title: "Open the photo at full size" }, image);
  image.addEventListener("error", () => link.closest("figure")?.remove(), { once: true });
  const own = found.kind !== "test print";
  return h("figure", { class: "ck-photo", style: `--ratio: ${found.width} / ${found.height}` }, link,
    h("figcaption", {}, h("span", { class: "ck-label" }, own ? "On a real print, from Dan's own build: " : "On a real print, one of Dan's test prints: "),
      found.caption, " ", h("span", { class: "fine" }, "Not a model's design; none was printed.")));
}

function counts(section) {
  const c = section.counts;
  const sentence = [`Of the ${c.first_prints} counted first prints this check applies to, it fails ${plural(c.failed, "design")}`];
  if (c.not_graded) sentence.push(`, leaves ${c.not_graded} not graded`);
  sentence.push(` and passes ${c.passed}`);
  const inside = [];
  if (c.via_test_print) inside.push(`${c.via_test_print} of the passes rest on the design's test print or template rather than its size as drawn`);
  if (c.crashed) inside.push(`${c.crashed} of the failures ${c.crashed === 1 ? "is" : "are"} the check's own code crashing on the shape`);
  if (c.overlap && c.overlap.trials) inside.push(`${c.overlap.trials} of the designs it fails or leaves not graded also fail ${c.overlap.check}`);
  const unread = [];
  if (c.not_reached) unread.push(`${c.not_reached} not reached`);
  if (c.no_part_built) unread.push(`${c.no_part_built} whose code didn't run for any part`);
  if (c.declined) unread.push(`${c.declined} declined`);
  if (c.no_design) unread.push(`${c.no_design} with no design`);
  if (unread.length) inside.push(`the rest were never read by it: ${unread.join(", ")}`);
  const extra = inside.length ? ` ${inside.map((text) => text[0].toUpperCase() + text.slice(1)).join(". ")}.` : "";
  const reasons = c.reasons.length ? h("ul", { class: "ck-reasons" }, c.reasons.map((reason) => h("li", {},
    h("a", { href: reason.href }, reason.label), " ", h("span", { class: "fine" }, `${reason.trials} ${reason.kind === "not graded" ? "not graded" : "failed"}`)))) : null;
  return h("div", { class: "ck-counts" }, h("p", {}, sentence.join(""), ".", extra, c.reasons.length ? " Open the designs behind each reason:" : ""), reasons);
}

function section(found) {
  const titleId = `${found.anchor}-h`;
  return h("section", { class: "ck-check", id: found.anchor, "aria-labelledby": titleId },
    h("p", { class: "ck-task" }, found.task_label),
    h("h2", { id: titleId }, found.title, " ", h("code", { class: "check-id", title: "The check's id in the eval's code" }, found.check)),
    h("p", { class: "ck-tests" }, found.tests),
    h("h3", {}, "How the code decides"),
    h("ol", { class: "ck-how" }, found.how.map((step) => h("li", {}, step))),
    h("p", { class: "ck-code" }, h("span", { class: "ck-label" }, "Read it in the code: "),
      found.code.map((code, at) => [at ? ", " : null, h("a", { href: code.url }, h("code", {}, `${code.file}`), " ", h("code", {}, code.function))])),
    h("h3", {}, "What it rests on"),
    h("p", {}, found.record),
    h("p", {}, h("span", { class: "ck-label" }, "Not graded means: "), found.not_graded),
    found.weak ? h("p", { class: "ck-weak" }, h("span", { class: "ck-label" }, "Where it's weak: "), found.weak) : null,
    found.inference ? h("p", { class: "ck-weak" }, h("span", { class: "ck-label" }, "Inference, not a print: "), found.inference) : null,
    found.examples.length ? [h("h3", {}, "Designs that pass and fail it"),
      found.examples_note ? h("p", {}, found.examples_note) : null,
      h("ul", { class: "ck-examples" }, found.examples.map(exampleCard))] : null,
    photo(found.photo),
    counts(found));
}

function tocEntry(found) {
  const c = found.counts;
  const tally = [c.failed ? `${c.failed} failed` : null, c.not_graded ? `${c.not_graded} not graded` : null].filter(Boolean).join(", ");
  return h("li", {}, h("a", { href: `#${found.anchor}` }, found.title), " ", h("span", { class: "fine" }, `${found.task_label}${tally ? `; ${tally}` : ""}`));
}

function render(data) {
  add(clear($("intro")), data.intro.map((text) => h("p", {}, text)));
  add(clear($("states")), Object.entries(data.states).map(([state, text]) => h("div", {}, h("dt", {}, badge(state, { small: true })), h("dd", {}, text))));
  $("denominators").textContent = data.denominators || "";
  $("nearest").textContent = data.nearest_print || "";
  $("claude").textContent = data.claude || "";
  add(clear($("toc")), data.checks.map(tocEntry));
  add(clear($("checks-list")), data.checks.map(section));
  if (location.hash) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
}

fetch("data/checks.json").then((response) => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(render).catch((error) => {
  add(clear($("intro")), h("p", { class: "ck-noview" }, `The checks couldn't be loaded (${error.message}).`));
});
