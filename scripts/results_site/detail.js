// One trial, in full, in the order a reader needs it: what was asked, what was designed and what failed on it, what
// the model asked and tried, its second print, the code, the transcript, and last the cost and the record.
// Built from data/trials/<slug>.json, fetched when the trial is opened.

import {
  h, add, clear, icon, badge, VERDICT, ISSUE_VERDICT, money, int, tokens, duration, grams, dateOnly, copyButton, plural,
} from "./util.js";

let viewer = null;       // the open 3D view's controller, if any
let systemPrompts = null;

export function teardown() {
  viewer?.dispose();
  viewer = null;
}

const KIND_NOTE = {
  loop_arm: "The first print's conversation, continued for one more turn. Cost, tokens and time below are for that turn only.",
  crash_replay: "The model was sent its design's build error and asked to fix it. Cost, tokens and time below are for that turn only.",
};
const AUDIT_GLOSS = { Decided: "a ruling by Dan on how this kind of case is graded", Checked: "checked by hand against the parts", Open: "not yet decided" };
const RED_MEANS = { bridges: "the overhang that can't be bridged", connected_bodies: "the pieces not joined to the rest" };
// A provider's error body can carry an account id; the page doesn't repeat it.
const maskIds = (text) => String(text).replace(/"user_id"\s*:\s*"[^"]*"?/g, '"user_id":"[left out]"');
const lowerFirst = (text) => text.charAt(0).toLowerCase() + text.slice(1);
const roleLabel = (part) => part.role_label || (part.role === "final" ? "final part" : "test print");
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- the frame: shown at once from the index row (or the detail itself), before anything else arrives ----

function barOf(row, context) {
  const nav = (target, label, name) => h("button", {
    type: "button", class: "btn btn-icon", disabled: !target, "aria-label": label, title: label + (name === "prev" ? " (left arrow)" : " (right arrow)"),
    onclick: () => target && context.open(target.slug),
  }, icon(name));
  const position = context.position
    ? h("span", { class: "td-pos" }, String(context.position.at), h("span", { class: "td-pos-of" }, ` of ${context.position.of}`))
    : h("span", { class: "td-pos" }, context.ready ? "Not in the list now shown" : "");
  return h("div", { class: "td-bar" },
    h("div", { class: "td-nav" }, nav(context.prev, "Previous trial in the list", "prev"), nav(context.next, "Next trial in the list", "next"), position),
    h("div", { class: "td-actions" },
      copyButton(() => new URL(context.listHref({ trial: row.slug }), location.href).href, "Copy link"),
      h("button", { type: "button", class: "btn btn-icon", "aria-label": "Close", title: "Close (Esc)", onclick: context.close }, icon("close"))));
}

function crumbsOf(row, context) {
  const group = context.groupLabel(row.group);
  const task = context.meta.tasks[row.task]?.label || row.task_name || row.task;
  return h("p", { class: "td-crumbs" },
    group ? [context.listLink({ cond: row.group }, {}, group), h("span", { "aria-hidden": "true" }, " / ")] : null,
    context.ready ? context.listLink({ cond: row.group, task: row.task }, {}, task) : task);
}

export function renderDetailShell(body, row, context) {
  teardown();
  const issues = row.issues?.length
    ? h("ul", { class: "td-issues" }, row.issues.map((issue) => h("li", { class: VERDICT[ISSUE_VERDICT[issue.kind]]?.cls || "" }, icon(VERDICT[ISSUE_VERDICT[issue.kind]]?.icon || "bang"), h("span", {}, issue.reason))))
    : null;
  const head = h("header", { class: "td-head" },
    crumbsOf(row, context),
    h("h2", { id: "trial-title", tabindex: "-1" }, `${row.model_short}, ${lowerFirst(row.title || `Trial ${row.trial}`)}`),
    h("div", { class: "td-verdict", title: context.meta.definitions?.[row.verdict] || "" }, badge(row.verdict), issues),
    row.counted ? null : h("p", { class: "td-excluded" }, h("span", { class: "tag tag-excluded" }, "Not counted"), " ", row.note || row.excluded_reason),
    KIND_NOTE[row.kind] ? h("p", { class: "td-kind" }, KIND_NOTE[row.kind]) : null);
  add(clear(body), barOf(row, context), head, h("div", { class: "td-content" }, h("p", { class: "td-loading loading", role: "status" }, "Loading this trial…")));
}

// Prev and next, the position and the breadcrumb depend on the list, which may arrive after the trial itself.
export function updateShell(body, row, context) {
  body.querySelector(".td-bar")?.replaceWith(barOf(row, context));
  body.querySelector(".td-crumbs")?.replaceWith(crumbsOf(row, context));
}

// ---- the detail ----

export function renderDetail(body, row, detail, context) {
  const content = clear(body.querySelector(".td-content"));
  const media = mediaSection(row, detail);
  const sections = [
    ["What it asked and tried", askedSection(detail)],
    [row.kind === "trial" ? "Second print" : row.kind === "crash_replay" ? "The trial it retries" : "First and second print", pairSection(row, detail, context)],
    ["Design and code", designSection(detail)],
    ["Transcript", transcriptSection(row, detail)],
    ["Cost and record", recordSection(row, detail, context)],
  ].filter(([, el]) => el);
  const toc = h("nav", { class: "td-toc", "aria-label": "Sections of this trial" }, sections.map(([label, el]) => h("button", {
    type: "button", class: "toc-btn",
    onclick: () => {
      if (el.tagName === "DETAILS") el.open = true;
      el.scrollIntoView({ block: "start", behavior: calm() ? "auto" : "smooth" });
      el.querySelector("h3")?.focus({ preventScroll: true });
    },
  }, label)));
  add(content, requestBlock(detail),
    h("div", { class: "td-top" }, media.el, checksSection(detail, context, media)),
    toc, sections.map(([, el]) => el));
}

function section(title, ...kids) {
  return h("section", { class: "td-section" }, h("h3", { tabindex: "-1" }, title), kids);
}

function requestBlock(detail) {
  if (!detail.request) return null;
  const quote = h("blockquote", { class: "td-request clamped" }, detail.request);
  const more = h("button", { type: "button", class: "btn btn-quiet btn-small", "aria-expanded": "false" }, "Show all of it");
  more.addEventListener("click", () => {
    const open = quote.classList.toggle("clamped");
    more.textContent = open ? "Show all of it" : "Show less";
    more.setAttribute("aria-expanded", String(!open));
  });
  const block = h("div", { class: "td-ask" }, h("p", { class: "td-ask-label" }, "What the person asked for"), quote, more);
  requestAnimationFrame(() => { if (quote.scrollHeight <= quote.clientHeight + 2) more.remove(); });
  return block;
}

// ---- pictures and the 3D view ----

function mediaSection(row, detail) {
  const box = h("section", { class: "td-media", "aria-label": "What it designed" });
  const media = detail.media;
  const notBuilt = detail.parts_not_built || [];
  const notBuiltNote = notBuilt.length
    ? h("div", { class: "callout callout-fail" },
      h("p", {}, h("strong", {}, detail.parts_built?.length ? `${plural(notBuilt.length, "part")} of this design didn't build. ` : "This design's code didn't run. "),
        detail.parts_built?.length ? `The picture shows what did: ${detail.parts_built.join(", ")}.` : null),
      h("ul", { class: "not-built" }, notBuilt.map((part) => h("li", {}, h("code", {}, part.part), part.test_print ? " (test print)" : " (final part)", ": ", h("code", {}, part.error)))))
    : null;
  if (!media || !media.parts.length) {
    const why = detail.thumb_none_reason || (row.verdict === "no design" ? "No design was handed in" : "No render of this design is saved");
    box.append(h("div", { class: "stage stage-none" }, h("p", {}, h("strong", {}, why + "."))), notBuiltNote);
    return { el: box, showPart() {}, marked: new Map() };
  }

  const marked = new Map();  // check id -> the part whose picture marks it in red
  for (const part of media.parts) for (const check of part.highlight_checks || []) if (!marked.has(check)) marked.set(check, part.id);
  const views = media.parts.map((part) => ({ kind: "part", part, label: part.id, role: roleLabel(part) }));
  if (media.scene) views.push({ kind: "scene", label: "Assembled", role: "with the person's parts in place" });
  let current = 0;
  let mode = "picture";
  const stage = h("div", { class: "stage" });
  const caption = h("div", { class: "stage-caption" });
  const controls = h("div", { class: "stage-controls" });
  const tabs = h("div", { class: "part-tabs", role: "group", "aria-label": "Parts of this design" });
  const titleOf = (check) => detail.findings.find((finding) => finding.check === check)?.title || check;

  const show = () => {
    teardown();
    const view = views[current];
    clear(tabs);
    if (views.length > 1) {
      views.forEach((entry, at) => tabs.append(h("button", {
        type: "button", class: "part-tab", "aria-pressed": String(at === current),
        onclick: () => { current = at; mode = entry.kind === "scene" ? "3d" : "picture"; show(); },
      }, h("span", { class: "part-tab-id" }, entry.label), h("small", {}, entry.role))));
    }
    clear(stage); clear(caption); clear(controls);
    stage.classList.toggle("stage-3d", mode === "3d");
    if (view.kind === "part") partCaption(caption, view.part, titleOf);
    else sceneCaption(caption, media.scene);
    if (mode === "3d") { open3d(view); return; }
    const part = view.part;
    if (part.thumb) {
      const image = h("img", { src: part.thumb, width: "640", height: "512", alt: pictureAlt(row, part), decoding: "async" });
      image.addEventListener("error", () => stage.replaceChildren(h("p", { class: "stage-msg" }, "The picture didn't load.")));
      stage.append(image);
    } else {
      stage.append(h("p", { class: "stage-msg" }, part.mesh ? "No picture of this part." : "This part came out as an empty shape."));
    }
    if (part.mesh) controls.append(h("button", { type: "button", class: "btn btn-primary", onclick: () => { mode = "3d"; show(); } }, icon("cube"), "Turn it in 3D"));
  };

  const open3d = async (view) => {
    const spec = view.kind === "scene" ? sceneSpec(media) : { label: view.part.id, items: [{ url: view.part.mesh, layer: "part" }], highlight: view.part.highlight, layers: [] };
    const status = h("p", { class: "stage-msg", role: "status" }, "Loading the 3D view…");
    stage.append(status);
    const back = view.kind === "part" ? h("button", { type: "button", class: "btn", onclick: () => { mode = "picture"; show(); } }, "Back to the picture") : null;
    try {
      const { mountViewer } = await import("./viewer.js");
      const mounted = await mountViewer(stage, spec);
      if (!stage.isConnected) { mounted.dispose(); return; }
      status.remove();
      viewer = mounted;
      const toggle = (label, swatch, on, change) => {
        const input = h("input", { type: "checkbox", checked: on });
        input.addEventListener("change", () => change(input.checked));
        return h("label", { class: "check-toggle" }, input, swatch, label);
      };
      if (mounted.hasHighlight) controls.append(toggle("Mark where it fails", h("span", { class: "swatch swatch-red", "aria-hidden": "true" }), true, (on) => mounted.setHighlight(on)));
      for (const layer of mounted.layers) {
        controls.append(toggle(layer.label, h("span", { class: "swatch", style: `background:${layer.color}`, "aria-hidden": "true" }), true, (on) => mounted.setLayer(layer.key, on)));
      }
      if (mounted.canFocusProblem) controls.append(h("button", { type: "button", class: "btn", onclick: () => mounted.focusProblem() }, "Go to the red marks"));
      controls.append(h("button", { type: "button", class: "btn", onclick: () => mounted.reset() }, "Reset the view"));
      if (back) controls.append(back);
      controls.append(h("p", { class: "stage-help" }, "Drag to turn it; click it first to zoom with the wheel; right-drag or two fingers to move. With the view focused: arrow keys turn, + and - zoom, Home resets. Z is up and the grid is the printer's bed, in 10 mm squares."));
    } catch (error) {
      console.error("3D view failed", error);
      const text = /Failed to fetch|import|module/i.test(String(error.message)) ? "The 3D library couldn't be fetched. Check the connection and try again." : `The reason given: ${error.message || error}.`;
      stage.replaceChildren(h("div", { class: "stage-msg", role: "alert" },
        h("p", {}, h("strong", {}, "The 3D view didn't load. "), text),
        h("p", {}, h("button", { type: "button", class: "btn", onclick: () => show() }, "Try again"),
          view.kind === "part" ? [" ", h("a", { class: "btn", href: view.part.mesh, download: "" }, "Download the mesh (.glb)")] : null)));
      if (back) controls.append(back);
    }
  };

  add(box, tabs, stage, caption, controls, notBuiltNote);
  show();
  return {
    el: box, marked,
    showPart(id) {
      const at = views.findIndex((view) => view.kind === "part" && view.part.id === id);
      if (at < 0) return;
      current = at; mode = "picture"; show();
      box.scrollIntoView({ block: "nearest", behavior: calm() ? "auto" : "smooth" });
    },
  };
}

function pictureAlt(row, part) {
  const marked = part.highlight_checks?.length ? ", with the region that fails a check in red" : "";
  return `Render of ${part.id}, the ${roleLabel(part)} ${row.model_short} designed${marked}`;
}

function partCaption(caption, part, titleOf) {
  const size = part.size_mm?.some((value) => value) ? `${part.size_mm.map((value) => +value.toFixed(1)).join(" × ")} mm` : null;
  add(caption,
    h("p", {}, h("code", {}, part.id), `, ${roleLabel(part)}`, size ? ` · ${size}` : null, h("span", { class: "caption-note" }, " · a render of the design; it wasn't printed")),
    part.highlight_checks?.length
      ? h("p", { class: "caption-red" }, h("span", { class: "swatch swatch-red", "aria-hidden": "true" }), "Red: ",
        part.highlight_checks.map((check, at) => [at ? "; " : null, RED_MEANS[check] || `where “${titleOf(check)}” fails`]), ".")
      : null);
}

function sceneCaption(caption, scene) {
  // "R6: keyhole at (-50, 75): its slot runs…" reads better without the id; the checks beside the picture carry it.
  const plain = (line) => line.replace(/^[A-Za-z_]+\d*:\s*/, "");
  add(caption, h("p", {}, "The printed parts with the LED disk (see-through), the perfboard and the screws where the design puts them. Nothing here was printed or assembled."),
    scene.fails.length ? [h("p", { class: "caption-red" }, h("span", { class: "swatch swatch-red", "aria-hidden": "true" }), "Marked in red:"), h("ul", { class: "scene-fails" }, scene.fails.map((line) => h("li", {}, lowerFirst(plain(line)))))] : null,
    scene.assumed_fails?.length ? [h("p", {}, "Fails only under the task's stated assumptions (not counted):"), h("ul", { class: "scene-fails" }, scene.assumed_fails.map((line) => h("li", {}, lowerFirst(plain(line)))))] : null);
}

function sceneSpec(media) {
  const items = [];
  const layers = [];
  for (const layer of media.scene.layers) {
    const drawn = layer.parts.filter((part) => part.mesh);
    if (!drawn.length) continue;
    layers.push({ key: layer.key, label: layer.label, color: layer.key === "problem" ? null : layer.color });
    for (const part of drawn) {
      items.push({ url: part.mesh, matrix: part.matrix, layer: layer.key, color: layer.color, problem: layer.key === "problem" || layer.key === "assumed", opacity: layer.key === "disk" ? 0.3 : 1 });
    }
  }
  return { label: "the assembled design", items, layers, highlight: null, frame: "printed" };
}

// ---- checks, beside the picture ----

function markNote(finding, media) {
  if (finding.state !== "fail") return null;
  const where = media.marked.get(finding.check);
  if (!where) return h("p", { class: "mark-note" }, "Not shown on the picture: this check has no red mark.");
  return h("p", { class: "mark-note mark-note-red" }, h("span", { class: "swatch swatch-red", "aria-hidden": "true" }), "Marked in red on ",
    h("button", { type: "button", class: "linkish", onclick: () => media.showPart(where) }, where), ".");
}

function checkCard(finding, media) {
  const diagnosis = finding.diagnosis;
  return h("li", { class: `check ${VERDICT[finding.state].cls}` },
    h("div", { class: "check-head" }, badge(finding.state, { small: true }), h("span", { class: "check-title" }, finding.title || finding.check),
      h("code", { class: "check-id", title: "The check's id in the eval's code" }, finding.check),
      finding.part && finding.part !== "-" ? h("span", { class: "check-part" }, "on ", h("code", {}, finding.part)) : null),
    finding.meaning && finding.meaning !== finding.title ? h("p", { class: "check-meaning" }, finding.meaning) : null,
    finding.detail ? h("p", { class: "check-detail" }, h("span", { class: "check-label" }, "Found: "), finding.detail) : null,
    diagnosis ? h("p", { class: "check-why" }, h("span", { class: "check-label" }, "Why: "), String(diagnosis.reason || diagnosis.text).replace(/\.$/, ""), ".",
      diagnosis.kind === "decided" ? " Dan ruled that this kind of case fails." : diagnosis.kind === "gap" ? " No recorded test print decides it." : diagnosis.kind === "open" ? " Still to be decided." : "") : null,
    diagnosis?.would_help ? h("p", { class: "check-why" }, h("span", { class: "check-label" }, "What would have helped: "), diagnosis.would_help) : null,
    markNote(finding, media));
}

function checkLine(finding) {
  return h("li", {}, h("span", { class: "check-title" }, finding.title || finding.check), " ", h("code", { class: "check-id" }, finding.check),
    finding.part && finding.part !== "-" ? [" on ", h("code", {}, finding.part)] : null, finding.detail ? h("span", { class: "check-found" }, `: ${finding.detail}`) : null);
}

function fold(summary, ...kids) {
  return h("details", { class: "fold" }, h("summary", {}, summary), kids);
}

function checksSection(detail, context, media) {
  const box = h("section", { class: "td-checks", "aria-label": "Checks" });
  const counted = (detail.findings || []).filter((finding) => finding.counted);
  const uncounted = (detail.findings || []).filter((finding) => !finding.counted);
  const of = (state) => counted.filter((finding) => finding.state === state);
  const [failed, undecided, blocked, passed] = [of("fail"), of("not graded"), of("not reached"), of("pass")];
  const definitions = context.meta.definitions || {};
  const tally = [failed.length ? `${failed.length} fail` : null, undecided.length ? `${undecided.length} not graded` : null, blocked.length ? `${blocked.length} not reached` : null, `${passed.length} pass`].filter(Boolean).join(", ");
  box.append(h("h3", { tabindex: "-1" }, "Checks"));
  if (detail.declined) {
    box.append(h("div", { class: "callout" },
      h("p", {}, h("strong", {}, "Declined. "), detail.handed_in?.text ? detail.handed_in.text + ". " : null, detail.declined_diagnosis?.reason ? detail.declined_diagnosis.reason.replace(/^Declined: /, "It ") + "." : null),
      detail.declined_diagnosis?.would_help ? h("p", {}, h("span", { class: "check-label" }, "What would have helped: "), detail.declined_diagnosis.would_help, ".") : null,
      h("p", { class: "fine" }, definitions.declined)));
  }
  if (detail.error && !counted.length) {
    box.append(h("div", { class: "callout" }, h("p", {}, h("strong", {}, "The trial stopped before a design. "), detail.excluded_reason || "", "."),
      h("p", { class: "fine" }, definitions.error), fold("The error as the provider returned it", h("pre", { class: "error-text" }, maskIds(detail.error)))));
  }
  if (counted.length) box.append(h("p", { class: "section-note" }, `${plural(counted.length, "counted check")}: ${tally}.`));
  if (failed.length || undecided.length) box.append(h("ul", { class: "checks" }, [...failed, ...undecided].map((finding) => checkCard(finding, media))));
  if (blocked.length) {
    box.append(fold([badge("not reached", { small: true }), ` ${plural(blocked.length, "check")} not reached: ${blocked.map((finding) => finding.title || finding.check).join(", ")}`],
      h("p", { class: "fine" }, definitions["not reached"]), h("ul", { class: "check-lines" }, blocked.map(checkLine))));
  }
  if (passed.length) {
    box.append(fold([badge("pass", { small: true }), ` ${plural(passed.length, "check")} pass: ${passed.map((finding) => finding.title || finding.check).join(", ")}`],
      h("ul", { class: "check-lines" }, passed.map(checkLine))));
  }
  if (uncounted.length) {
    const failing = uncounted.filter((finding) => finding.state === "fail").length;
    box.append(fold(detail.declined
      ? `${plural(uncounted.length, "check")} on what it handed in, reported but not counted`
      : `${plural(uncounted.length, "check")} on its test prints, reported but never counted${failing ? ` (${failing} fail)` : ""}`,
    h("ul", { class: "checks" }, uncounted.filter((finding) => finding.state !== "pass").map((finding) => checkCard(finding, media))),
    h("ul", { class: "check-lines" }, uncounted.filter((finding) => finding.state === "pass").map(checkLine))));
  }
  if (detail.unprompted_test_prints) box.append(h("p", { class: "callout" }, detail.unprompted_test_prints));
  if (detail.assumed) {
    box.append(h("div", { class: "callout" },
      h("p", {}, h("strong", {}, "If the task's stated assumptions held. "), "This is not the verdict and is never counted. It shows how the undecided checks would come out: ", badge(detail.assumed.verdict, { small: true })),
      h("ul", { class: "assumed" }, detail.assumed.findings.map((finding) => h("li", {},
        badge(finding.ok === true ? "pass" : finding.ok === false ? "fail" : "not graded", { small: true }), " ", h("code", {}, finding.check), " ", finding.detail, h("small", {}, "Assumes: ", finding.assumption))))));
  }
  if (detail.audit) {
    box.append(h("div", { class: "audit" }, h("p", {}, h("span", { class: "check-label" }, `Reviewer's note (${AUDIT_GLOSS[detail.audit.label] || lowerFirst(detail.audit.label)}): `), detail.audit.note)));
  }
  return box;
}

// ---- what it asked the person ----

function answerLine(line) {
  return h("li", { class: "answer" + (line.cant_tell ? " answer-cant" : "") },
    h("span", { class: "answer-text" }, line.text),
    line.cant_tell ? h("span", { class: "tag tag-ng" }, "Can't tell") : null,
    line.prediction ? h("span", { class: "tag" }, "A prediction, not a recorded print") : null,
    h("small", {}, line.basis_label || line.basis));
}

function answersBlock(answers) {
  return Object.entries(answers || {}).map(([part, lines]) => h("div", { class: "answers simulated" },
    h("p", { class: "answers-part" }, h("span", { class: "sim-tag" }, "Simulated reply, from Dan's records"), " about ", h("code", {}, part)),
    lines.length ? h("ul", {}, lines.map(answerLine)) : h("p", { class: "fine" }, "No answer recorded for this piece.")));
}

const MATCH_TAG = {
  "whole item": ["tag tag-ng", "Nearest recorded answer, not what was asked"],
  "nothing recorded": ["tag tag-ng", "Nothing recorded"],
};

function measureItem(measure) {
  const pieces = String(measure.reply || "").split(/;\s+/).filter(Boolean);
  const tag = MATCH_TAG[measure.match];
  return h("li", { class: "measure" + (measure.match === "nothing recorded" ? " measure-none" : "") },
    h("p", { class: "q" }, h("span", { class: "check-label" }, "The model asked: "), measure.item ? [h("strong", {}, measure.item), ": "] : null, measure.what),
    h("div", { class: "a simulated" }, h("span", { class: "sim-tag" }, "Simulated reply"), " ",
      pieces.length > 1 ? h("ul", { class: "reply-list" }, pieces.map((piece) => h("li", {}, piece))) : h("span", {}, measure.reply),
      tag ? [" ", h("span", { class: tag[0], title: measure.match_note || "" }, tag[1])] : null,
      tag && measure.match === "whole item" && measure.match_note ? h("small", {}, measure.match_note) : null));
}

function askedSection(detail) {
  const rounds = detail.test_prints || [];
  const measures = detail.measures || [];
  const kids = [];
  if (detail.handed_in?.text) kids.push(h("p", {}, detail.handed_in.text, "."));
  if (!rounds.length && !measures.length) {
    if (detail.kind !== "trial" || !detail.submission) return null;
    kids.push(h("p", { class: "section-note" }, detail.condition_key === "can_test"
      ? "It asked for no measurements and no test prints before handing in its design."
      : "It asked for no measurements before handing in its design."));
    return section("What it asked and tried", kids);
  }
  kids.push(h("p", { class: "section-note" }, "The person is a program. It answers measurements from a fixed list and says how a print came out only from Dan's recorded test prints. Nothing was printed for this trial."));
  if (detail.condition_key === "can_test" && detail.kind === "trial" && !rounds.length) {
    kids.push(h("p", { class: "callout" }, h("strong", {}, "It asked for no test prints, "), "though it could have before its final design."));
  }
  for (const round of rounds) {
    const cant = Object.values(round.answers || {}).flat().some((line) => line.cant_tell);
    kids.push(h("h4", {}, rounds.length > 1 ? `Test prints it asked for, request ${round.round} of ${rounds.length}` : "Test prints it asked for",
      cant ? [" ", h("span", { class: "tag tag-ng" }, "Includes “I can't tell you how that one came out”")] : null),
    answersBlock(round.answers),
    round.parts.filter((part) => part.code).map((part) => codeFold(`Code for test print ${part.id}`, part.code)));
  }
  if (measures.length) {
    const list = h("ul", { class: "measures" }, measures.map(measureItem));
    kids.push(h("h4", {}, `Measurements it asked for (${measures.length})`), measures.length > 6 ? fold(`Show all ${measures.length} questions and replies`, list) : list);
  }
  return section("What it asked and tried", kids);
}

// ---- first print and second print ----

function designThumb(detail) {
  return detail.thumb || detail.media?.parts?.find((part) => part.thumb)?.thumb || null;
}

function printColumn(title, detail, context, isCurrent) {
  const thumb = designThumb(detail);
  const open = (event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return; event.preventDefault(); context.openOther(detail.slug); };
  return h("div", { class: "pair-col" + (isCurrent ? " pair-current" : "") },
    h("div", { class: "pair-thumb" }, thumb
      ? h("img", { src: thumb, alt: `Render of the ${title.toLowerCase()}'s design`, loading: "lazy", width: "640", height: "512", onerror: (event) => event.target.replaceWith(h("span", { class: "thumb-none" }, "Picture didn't load")) })
      : h("span", { class: "thumb-none" }, "No picture")),
    h("div", { class: "pair-text" },
      h("p", { class: "pair-title" }, title, isCurrent ? h("small", {}, " (this one)") : null),
      h("p", {}, badge(detail.verdict)),
      detail.issues?.length ? h("ul", { class: "td-issues" }, detail.issues.map((issue) => h("li", { class: VERDICT[ISSUE_VERDICT[issue.kind]]?.cls || "" }, icon(VERDICT[ISSUE_VERDICT[issue.kind]]?.icon || "bang"), h("span", {}, issue.reason)))) : null,
      isCurrent ? null : h("p", {}, h("a", { class: "btn", href: context.hrefFor({ trial: detail.slug }), onclick: open }, `Open the ${title.toLowerCase()}`, icon("arrow")))));
}

function valueOf(param) {
  if (param === undefined || param === null) return null;
  return typeof param === "object" ? param.value : param;
}

function showValue(param) {
  const value = valueOf(param);
  if (value === null || value === undefined) return "not set";
  const unit = typeof param === "object" && param.unit && param.unit !== "count" ? ` ${param.unit}` : "";
  return `${typeof value === "object" ? JSON.stringify(value) : value}${unit}`;
}

function changes(first, second) {
  if (!first.submission || !second.submission) return [h("p", { class: "fine" }, !second.submission ? "The second turn handed in no design." : "The first print has no saved design to compare.")];
  const kids = [];
  // 1. which checks moved
  const results = (detail) => {
    const worst = new Map();
    const rank = { fail: 0, "not graded": 1, "not reached": 2, pass: 3 };
    for (const finding of detail.findings || []) {
      if (!finding.counted) continue;
      if (!worst.has(finding.check) || rank[finding.state] < rank[worst.get(finding.check).state]) worst.set(finding.check, finding);
    }
    return worst;
  };
  const [was, now] = [results(first), results(second)];
  const moved = [...new Set([...was.keys(), ...now.keys()])].filter((check) => was.get(check)?.state !== now.get(check)?.state);
  const cell = (finding) => (finding ? badge(finding.state, { small: true }) : h("span", { class: "fine" }, "not run"));
  if (moved.length) {
    kids.push(h("div", { class: "table-scroll" }, h("table", { class: "plain moves" },
      h("thead", {}, h("tr", {}, ["Check", "First print", "Second print"].map((label) => h("th", { scope: "col" }, label)))),
      h("tbody", {}, moved.map((check) => h("tr", {}, h("th", { scope: "row" }, (now.get(check) || was.get(check)).title || check, " ", h("code", { class: "check-id" }, check)), h("td", {}, cell(was.get(check))), h("td", {}, cell(now.get(check)))))))));
  } else {
    kids.push(h("p", {}, "Every counted check came out the same as on the first print."));
  }
  // 2. which parameters moved
  const before = first.submission.params || {};
  const after = second.submission.params || {};
  const names = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter((name) => showValue(before[name]) !== showValue(after[name]));
  if (names.length) {
    const delta = (name) => {
      const [a, b] = [valueOf(before[name]), valueOf(after[name])];
      if (typeof a !== "number" || typeof b !== "number") return "";
      const change = Math.round((b - a) * 1000) / 1000;
      return (change > 0 ? "+" : "") + change;
    };
    kids.push(h("div", { class: "table-scroll" }, h("table", { class: "plain params" },
      h("caption", {}, `${plural(names.length, "named size")} changed`),
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Parameter (the model's own name)"), h("th", { scope: "col", class: "num" }, "First print"), h("th", { scope: "col", class: "num" }, "Second print"), h("th", { scope: "col", class: "num" }, "Change"))),
      h("tbody", {}, names.map((name) => h("tr", {}, h("th", { scope: "row" }, h("code", {}, name)), h("td", { class: "num" }, showValue(before[name])), h("td", { class: "num" }, showValue(after[name])), h("td", { class: "num" }, delta(name))))))));
  } else {
    kids.push(h("p", {}, "No named size changed value."));
  }
  const codeOf = (detail) => new Map(detail.submission.parts.map((part) => [part.id, part.code]));
  const [codeBefore, codeAfter] = [codeOf(first), codeOf(second)];
  const notes = [...new Set([...codeBefore.keys(), ...codeAfter.keys()])].map((id) => (!codeBefore.has(id) ? [h("code", {}, id), " is new"] : !codeAfter.has(id) ? [h("code", {}, id), " was dropped"] : codeBefore.get(id) !== codeAfter.get(id) ? [h("code", {}, id), "'s code changed"] : null)).filter(Boolean);
  kids.push(h("p", {}, notes.length ? ["Parts: ", notes.map((note, at) => [at ? "; " : null, note]), "."] : "The code of every part is the same as the first print's."));
  return kids;
}

function linkToTrial(row, context, label) {
  return h("a", { class: "btn", href: context.hrefFor({ trial: row.slug }), onclick: (event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return; event.preventDefault(); context.openOther(row.slug); } }, label, icon("arrow"));
}

function pairSection(row, detail, context) {
  if (row.kind === "crash_replay") {
    const first = context.rowOf(detail.replays);
    return section("The trial it retries",
      h("p", {}, "The original design's code didn't build. The model was sent this message and asked to fix it:"),
      h("pre", { class: "said simulated" }, detail.message || ""),
      first ? h("p", {}, linkToTrial(first, context, "Open the original trial")) : null);
  }
  const isSecond = row.kind === "loop_arm";
  const otherSlug = isSecond ? detail.first_print?.slug : detail.second_print_slug;
  if (!otherSlug) {
    if (row.group !== "first") return null;
    const after = detail.after_feedback;
    return section("Second print", h("p", { class: "section-note" }, row.verdict === "pass"
      ? "This first print passes, so it wasn't sent back for a second print."
      : after && !after.replayed ? "No second print was run for this trial." : "This first print wasn't sent back for a second print."));
  }
  const title = isSecond ? "First and second print" : "Second print";
  const holder = h("div", { class: "pair-wrap" }, h("p", { class: "loading", role: "status" }, isSecond ? "Loading the first print…" : "Loading the second print…"));
  context.fetchDetail(otherSlug).then((other) => {
    const [first, second] = isSecond ? [other, detail] : [detail, other];
    const cant = Object.values(second.report || {}).flat().some((line) => line.cant_tell);
    const note = second.note || first.after_feedback?.note;
    add(clear(holder),
      note ? h("p", { class: "callout" }, note) : null,
      second.arm === "neutral" ? h("p", { class: "callout" }, "In this version the person only asked for the design again, without saying how the first came out.") : null,
      h("div", { class: "pair" }, printColumn("First print", first, context, !isSecond), printColumn("Second print", second, context, isSecond)),
      h("h4", {}, "What changed"), changes(first, second),
      h("h4", {}, "What the person said after the first print", cant ? [" ", h("span", { class: "tag tag-ng" }, "Includes “I can't tell you how that one came out”")] : null),
      h("p", { class: "section-note" }, "The person is a program and answers only from Dan's recorded prints. The message says “I printed what you sent” because that is what the model was told; nothing was printed."),
      answersBlock(second.report),
      second.reply ? fold("The whole message, as the model received it", h("pre", { class: "said simulated" }, second.reply)) : null,
      second.baseline ? h("p", { class: "fine" }, "The second print is graded with its test prints left out. Graded the same way, the first design is: ", badge(second.baseline.verdict, { small: true }), ".") : null);
  }).catch((error) => {
    add(clear(holder), h("p", { role: "alert" }, `The ${isSecond ? "first" : "second"} print's detail didn't load (${error.message || error}).`));
  });
  return section(title, holder);
}

// ---- the design ----

function codeFold(title, code, open = false) {
  const pre = h("pre", { class: "code", tabindex: "0" }, h("code", {}, code));
  return h("details", { class: "fold fold-code", open }, h("summary", {}, title), h("div", { class: "code-wrap" }, copyButton(() => code, "Copy code"), pre));
}

function manualBlock(manual) {
  if (!manual) return null;
  let steps = null;
  try { const parsed = JSON.parse(manual); if (Array.isArray(parsed)) steps = parsed; } catch { /* a cut or plain-text manual */ }
  const bodyEl = steps
    ? h("ol", { class: "manual" }, steps.map((step) => h("li", {}, typeof step === "string" ? step : step.text || JSON.stringify(step))))
    : h("p", { class: "prewrap" }, manual);
  return fold("Its instructions for printing and putting it together", bodyEl);
}

function designSection(detail) {
  const sub = detail.submission;
  if (!sub) return null;
  const params = Object.entries(sub.params || {});
  const failed = new Map((detail.parts_not_built || []).map((part) => [part.part.replace(/[-_]/g, ""), part.error]));
  const kids = [];
  if (sub.note) kids.push(h("p", { class: "note-quote" }, h("span", { class: "check-label" }, "The model's note with its design: "), sub.note));
  sub.parts.forEach((part, at) => {
    const error = failed.get(part.id.replace(/[-_]/g, ""));
    kids.push(h("div", { class: "part" },
      h("p", { class: "part-head" }, h("code", {}, part.id), h("span", { class: "tag" }, part.role_label), part.material ? h("span", { class: "fine" }, part.material) : null,
        error ? h("span", { class: "tag tag-fail" }, "Didn't build") : null),
      error ? h("pre", { class: "error-text" }, error) : null,
      part.print_orientation ? h("p", { class: "fine" }, h("span", { class: "check-label" }, "How it says to print it: "), part.print_orientation) : null,
      part.use_orientation ? h("p", { class: "fine" }, h("span", { class: "check-label" }, "How it's used: "), part.use_orientation) : null,
      codeFold(`CadQuery code for ${part.id} (${part.code.split("\n").length} lines)`, part.code, at === 0 && part.code.length < 2500)));
  });
  if (params.length) {
    kids.push(fold(`Sizes it named (${params.length})`,
      h("div", { class: "table-scroll" }, h("table", { class: "plain params" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Name"), h("th", { scope: "col", class: "num" }, "Value"), h("th", { scope: "col" }, "From"), h("th", { scope: "col" }, "The model's note"))),
        h("tbody", {}, params.map(([name, param]) => h("tr", {}, h("th", { scope: "row" }, h("code", {}, name)), h("td", { class: "num" }, showValue(param)), h("td", {}, param?.source || ""), h("td", {}, param?.note || ""))))))));
  }
  if (sub.hardware?.length) {
    kids.push(fold(`Hardware it uses (${sub.hardware.length})`,
      h("ul", {}, sub.hardware.map((item) => h("li", {}, typeof item === "string" ? item : [item.qty ? `${item.qty} × ` : "", item.ref || item.id || JSON.stringify(item)])))));
  }
  if (sub.criteria?.length) {
    kids.push(fold(`What it said must hold (${sub.criteria.length})`,
      h("ul", { class: "criteria" }, sub.criteria.map((item) => h("li", {}, typeof item === "string" ? item : [h("strong", {}, item.feature || item.id || ""), item.relation ? ` ${item.relation} ` : " ", item.hardware || "",
        item.check?.description ? h("small", {}, item.check.description) : null])))));
  }
  if (sub.questions?.length) {
    kids.push(fold(`Questions it left for the person (${sub.questions.length})`,
      h("ul", {}, sub.questions.map((question) => h("li", {}, typeof question === "string" ? question : JSON.stringify(question))))));
  }
  kids.push(manualBlock(sub.manual));
  return section("Design and code", kids);
}

// ---- the transcript ----

function argsBlock(call) {
  const args = call.args;
  if (typeof args === "string") return fold("What it sent", h("pre", { class: "code" }, args));
  const kids = [];
  if (args && Array.isArray(args.parts)) {
    for (const part of args.parts) {
      if (part && typeof part === "object" && part.code) kids.push(codeFold(`${part.id || "part"}: code as sent`, part.code));
    }
    const other = args.other;
    if (other && (typeof other === "string" || Object.keys(other).length)) {
      kids.push(fold("The rest of what it sent", h("pre", { class: "code wrap-code" }, typeof other === "string" ? other : JSON.stringify(other, null, 1))));
    }
    return kids;
  }
  if (args && typeof args === "object" && typeof args.code === "string") return codeFold("The code it ran", args.code);
  if (call.tool === "measure") return null;  // the summary line says it all
  return fold("What it sent", h("pre", { class: "code wrap-code" }, JSON.stringify(args, null, 1)));
}

function systemBlock(ref) {
  const body = h("div", {}, h("p", { class: "loading" }, "Loading…"));
  const block = fold("Show the system prompt", body);
  block.addEventListener("toggle", async () => {
    if (!block.open || body.dataset.done) return;
    try {
      systemPrompts ||= fetch("data/system_prompts.json").then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); });
      const prompts = await systemPrompts;
      body.replaceChildren(h("pre", { class: "said" }, prompts[ref] || "This prompt isn't in the saved set."));
      body.dataset.done = "1";
    } catch (error) {
      systemPrompts = null;
      body.replaceChildren(h("p", { role: "alert" }, `The system prompt didn't load (${error.message || error}).`));
    }
  });
  return block;
}

const REPLY_ABOUT = { measure: "answering a measurement", print_test: "on how the test prints came out", submit_design: "after the design was handed in" };

function transcriptSection(row, detail) {
  const transcript = detail.transcript;
  if (!transcript) return null;
  let users = 0;
  const items = transcript.excerpt.map((message) => {
    if (message.role === "omitted") return h("li", { class: "msg msg-omitted" }, message.text);
    if (message.role === "system") return h("li", { class: "msg msg-harness" }, h("p", { class: "msg-who" }, "The eval's harness: system prompt"), systemBlock(message.ref));
    if (message.speaker === "harness") {
      return h("li", { class: "msg msg-harness" }, h("p", { class: "msg-who" }, "The eval's harness", message.tool ? `, replying to ${message.tool}` : ""),
        message.summary ? [h("p", {}, message.summary), fold("The whole message", h("p", { class: "prewrap" }, message.text))] : h("p", { class: "prewrap" }, message.text));
    }
    if (message.speaker === "person (simulated)") {
      users += message.role === "user" ? 1 : 0;
      const request = message.role === "user" && row.kind === "trial" && users === 1;
      return h("li", { class: "msg msg-person" + (request ? "" : " simulated") },
        h("p", { class: "msg-who" }, request ? "The person's request, as sent to the model" : ["The person ", h("span", { class: "sim-tag" }, "simulated, from Dan's records"), message.tool && REPLY_ABOUT[message.tool] ? `, ${REPLY_ABOUT[message.tool]}` : ""]),
        h("p", { class: "prewrap" }, message.text));
    }
    return h("li", { class: "msg msg-model" },
      h("p", { class: "msg-who" }, row.model_short),
      message.reasoning ? fold("Its reasoning summary, as the provider returned it", h("p", { class: "prewrap" }, message.reasoning)) : null,
      message.text ? h("p", { class: "prewrap" }, message.text) : null,
      (message.tool_calls || []).map((call) => h("div", { class: "call" }, h("p", { class: "call-name" }, icon("arrow"), call.summary || `uses ${call.tool}`), argsBlock(call))));
  });
  return h("details", { class: "td-section td-fold-section" },
    h("summary", {}, h("h3", { tabindex: "-1" }, "Transcript"), h("span", { class: "fold-count" }, `${plural(transcript.messages, "message")}, excerpted`)),
    h("p", { class: "section-note" }, "Long texts are cut. Replies marked simulated come from a program that answers only from Dan's recorded measurements and test prints. ",
      h("a", { href: transcript.url, rel: "noopener" }, "The full transcript on GitHub", icon("out"))),
    h("ol", { class: "transcript" }, items));
}

// ---- cost and the record ----

function recordSection(row, detail, context) {
  const t = detail.tokens || {};
  const estimate = detail.slicer_estimate;
  const definitions = context.meta.definitions || {};
  const stat = (label, value, note) => h("div", { class: "stat-cell" }, h("dt", {}, label), h("dd", {}, value, note ? h("small", {}, note) : null));
  const stats = h("dl", { class: "stats" },
    stat("API cost", money(detail.cost_usd)),
    stat("Tokens", tokens(detail.tokens_total), t.calls ? `${int(t.prompt)} in, ${int(t.completion)} out` + (t.reasoning ? `, ${int(t.reasoning)} reasoning` : "") + (t.cached ? `, ${int(t.cached)} cached` : "") : null),
    stat("Turns", String(detail.turns), `${duration(detail.elapsed_s)} of model time`),
    stat("Filament (est.)", detail.est_filament_g === null ? "not estimated" : `est. ${grams(detail.est_filament_g)}`, estimate?.est_test_print_filament_g ? `est. ${grams(estimate.est_test_print_filament_g)} of it test prints` : null),
    stat("Print time (est.)", detail.est_print_s === null ? "not estimated" : `est. ${duration(detail.est_print_s)}`, estimate?.est_test_print_s ? `est. ${duration(estimate.est_test_print_s)} of it test prints` : null));
  const regrades = detail.regrade_dates || [];
  const settings = detail.settings ? Object.entries(detail.settings).map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`).join(", ") : null;
  const facts = [
    ["Run", dateOnly(detail.run_date) + (regrades.length ? `; graded again against newer test-print records on ${[...new Set(regrades.map(dateOnly))].join(", ")}` : "")],
    ["Model", h("code", {}, detail.model)],
    ["Condition", context.meta.condition_labels?.[detail.condition_key] || detail.condition_key || "n/a"],
    ["Code version", [h("code", {}, detail.code_version || "n/a"), detail.graded_code_version && detail.graded_code_version !== detail.code_version ? [" when run, ", h("code", {}, detail.graded_code_version), " when last graded"] : null, detail.code_version_note ? h("small", {}, detail.code_version_note) : null]],
    settings ? ["Settings", settings] : null,
    detail.repairs ? ["Repairs", `${detail.repairs} (a malformed tool call the harness asked the model to send again)`] : null,
    ["Saved as", h("code", {}, detail.id)],
  ].filter(Boolean);
  const kids = [stats,
    h("p", { class: "fine" }, definitions["print time and filament"] || "Print time and filament are slicer estimates. Nothing was printed."),
    estimate?.parts?.length ? fold("The slicer's estimate, part by part",
      h("div", { class: "table-scroll" }, h("table", { class: "plain" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Part"), h("th", { scope: "col" }, "Role"), h("th", { scope: "col", class: "num" }, "Print time (est.)"), h("th", { scope: "col", class: "num" }, "Filament (est.)"), h("th", { scope: "col" }, "Status"))),
        h("tbody", {}, estimate.parts.map((part) => h("tr", {},
          h("th", { scope: "row" }, h("code", {}, part.part)), h("td", {}, part.role === "final" ? "final part" : "test print"), h("td", { class: "num" }, duration(part.est_print_s)), h("td", { class: "num" }, grams(part.est_filament_g)),
          h("td", {}, part.status.replace(/_/g, " "), part.error ? `: ${part.error}` : "", part.warning ? ` (${part.warning})` : "")))))),
      estimate.plate_error ? h("p", { class: "fine" }, "Plate: ", estimate.plate_error) : null) : null,
    h("dl", { class: "facts" }, facts.map(([label, value]) => h("div", {}, h("dt", {}, label), h("dd", {}, value))))];
  if (detail.error) kids.push(fold("The error, as recorded", h("pre", { class: "error-text" }, maskIds(detail.error))));
  if (detail.limitations?.length) {
    kids.push(h("h4", {}, "Limitations the model reported"), h("ul", { class: "limits" }, detail.limitations.map((item) => h("li", {},
      typeof item === "string" ? item : [h("p", {}, h("span", { class: "check-label" }, "Wanted: "), item.wanted), h("p", {}, h("span", { class: "check-label" }, "Blocked by: "), item.blocked_by), item.why ? h("p", {}, h("span", { class: "check-label" }, "Why it matters: "), item.why) : null]))));
  }
  if (detail.regrades?.length) {
    kids.push(h("h4", {}, "Earlier verdicts, before a regrade"),
      h("p", { class: "fine" }, "The verdict at the top is today's. These are the ones it replaced as newer test prints were recorded and the checks changed."),
      h("div", { class: "table-scroll" }, h("table", { class: "plain" },
        h("thead", {}, h("tr", {}, ["Graded on", "Verdict", "Failed", "Not graded"].map((label) => h("th", { scope: "col" }, label)))),
        h("tbody", {}, detail.regrades.map((entry) => h("tr", {}, h("td", {}, dateOnly(entry.date)), h("td", {}, VERDICT[entry.verdict] ? badge(entry.verdict, { small: true }) : entry.verdict), h("td", {}, entry.failed || ""), h("td", {}, entry.not_graded || "")))))));
  }
  return section("Cost and record", kids);
}
