// The 3D view. three.js is fetched from the CDN (pinned in index.html's import map) the first time a view is opened,
// never before. Meshes are GLB, in millimetres, Z up, as the designs were built; the view draws only when something
// changes, so it sits idle otherwise.

let libraries = null;

function loadLibraries() {
  libraries ||= Promise.all([
    import("three"),
    import("three/addons/controls/OrbitControls.js"),
    import("three/addons/loaders/GLTFLoader.js"),
  ]).then(([THREE, controls, loader]) => ({ THREE, OrbitControls: controls.OrbitControls, GLTFLoader: loader.GLTFLoader }));
  libraries.catch(() => { libraries = null; });
  return libraries;
}

function themeColors() {
  const style = getComputedStyle(document.documentElement);
  const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  return { part: read("--part", "#aab4be"), edge: read("--part-edge", "#2f3a45"), grid: read("--viewer-grid", "#c5cad0"), red: read("--viewer-red", "#de3428") };
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text) node.textContent = text;
  return node;
}

const NICE_MM = [1, 2, 5, 10, 20, 50, 100, 200, 500];

// spec: {label, items: [{url, matrix, layer, color, problem, opacity}], layers: [{key, label, color}], highlight: url|null,
//        frame: a layer key to frame the camera on (else everything)}
export async function mountViewer(stage, spec) {
  const { THREE, OrbitControls, GLTFLoader } = await loadLibraries();
  const colors = themeColors();
  const loader = new GLTFLoader();
  const load = (url) => new Promise((resolve, reject) => loader.load(url, resolve, undefined, () => reject(new Error("a mesh file didn't load"))));

  const [models, marked] = await Promise.all([
    Promise.all(spec.items.map((item) => load(item.url))),
    spec.highlight ? load(spec.highlight).catch(() => null) : null,
  ]);

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    throw new Error("this browser couldn't start WebGL");
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  const canvas = renderer.domElement;
  canvas.className = "viewer-canvas";
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `3D view of ${spec.label}. Drag to turn it; arrow keys turn it, plus and minus zoom, Home resets.`);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 5000);
  camera.up.set(0, 0, 1);
  scene.add(camera);
  // Fixed lights in the world, so faces keep their shading as the part turns, plus a weaker one that follows the
  // camera so nothing facing the reader is ever black.
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  scene.add(new THREE.HemisphereLight(0xffffff, 0x50565e, 0.55));
  const fill = new THREE.DirectionalLight(0xffffff, 0.8);
  fill.position.set(1, 1, 2);
  scene.add(fill);
  const under = new THREE.DirectionalLight(0xffffff, 0.45);
  under.position.set(-1, -0.6, -2);
  scene.add(under);
  const follow = new THREE.DirectionalLight(0xffffff, 1.1);
  follow.position.set(-1.4, 1.6, 0.8);
  camera.add(follow);

  const disposables = [];
  const keep = (thing) => { disposables.push(thing); return thing; };
  const layerGroups = new Map();
  const world = new THREE.Group();
  scene.add(world);
  const redSolid = keep(new THREE.MeshBasicMaterial({ color: colors.red, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  const redGhost = keep(new THREE.MeshBasicMaterial({ color: colors.red, side: THREE.DoubleSide, transparent: true, opacity: 0.25, depthTest: false, depthWrite: false }));
  const edgeMaterial = keep(new THREE.LineBasicMaterial({ color: colors.edge, transparent: true, opacity: 0.7 }));
  const problems = new THREE.Group();   // every red mesh, for "go to the red marks" and the opening view

  const meshesOf = (gltf) => { const found = []; gltf.scene.updateMatrixWorld(true); gltf.scene.traverse((node) => { if (node.isMesh) found.push(node); }); return found; };

  spec.items.forEach((item, at) => {
    const group = layerGroups.get(item.layer) || new THREE.Group();
    if (!layerGroups.has(item.layer)) { layerGroups.set(item.layer, group); world.add(group); }
    const holder = new THREE.Group();
    if (item.matrix) { holder.matrix.fromArray(item.matrix); holder.matrixAutoUpdate = false; }
    const seeThrough = item.opacity !== undefined && item.opacity < 1;
    const material = item.problem ? redSolid : keep(new THREE.MeshStandardMaterial({
      color: item.color || colors.part, flatShading: true, roughness: 0.8, metalness: 0, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      transparent: seeThrough, opacity: seeThrough ? item.opacity : 1, depthWrite: !seeThrough,
    }));
    for (const node of meshesOf(models[at])) {
      const geometry = keep(node.geometry);
      const mesh = new THREE.Mesh(geometry, material);
      mesh.applyMatrix4(node.matrixWorld);
      if (seeThrough) mesh.renderOrder = 1;
      holder.add(mesh);
      if (item.problem) {
        const ghost = new THREE.Mesh(geometry, redGhost);
        ghost.applyMatrix4(node.matrixWorld);
        ghost.renderOrder = 3;
        holder.add(ghost);
      } else if (!seeThrough && (geometry.index ? geometry.index.count : geometry.attributes.position.count) / 3 < 160000) {
        const lines = new THREE.LineSegments(keep(new THREE.EdgesGeometry(geometry, 30)), edgeMaterial);
        lines.applyMatrix4(node.matrixWorld);
        holder.add(lines);
      }
    }
    group.add(holder);
    if (item.problem) problems.userData.groups = [...(problems.userData.groups || []), holder];
  });

  // The failing region: the faces the check looked at, drawn over the part and faintly through it.
  const highlight = new THREE.Group();
  const normal = new THREE.Vector3();
  if (marked) {
    for (const node of meshesOf(marked)) {
      const geometry = keep(node.geometry);
      for (const material of [redSolid, redGhost]) {
        const mesh = new THREE.Mesh(geometry, material);
        mesh.applyMatrix4(node.matrixWorld);
        if (material === redGhost) mesh.renderOrder = 3;
        highlight.add(mesh);
      }
      normal.add(areaNormal(THREE, geometry).transformDirection(node.matrixWorld));
    }
    world.add(highlight);
    problems.userData.groups = [...(problems.userData.groups || []), highlight];
  }

  world.updateMatrixWorld(true);
  const boxOf = (objects) => { const box = new THREE.Box3(); for (const object of objects) box.expandByObject(object); return box; };
  const whole = new THREE.Box3().setFromObject(world);
  if (whole.isEmpty()) throw new Error("the mesh is empty");
  const framed = spec.frame && layerGroups.has(spec.frame) ? boxOf([layerGroups.get(spec.frame)]) : whole;
  const center = framed.getCenter(new THREE.Vector3());
  const radius = Math.max(framed.getSize(new THREE.Vector3()).length() / 2, 1);
  const problemBox = problems.userData.groups?.length ? boxOf(problems.userData.groups) : null;

  const extent = Math.max(whole.max.x - whole.min.x, whole.max.y - whole.min.y);
  const gridSize = Math.max(40, Math.ceil((extent * 1.5) / 20) * 20);
  const middle = whole.getCenter(new THREE.Vector3());
  const grid = new THREE.GridHelper(gridSize, gridSize / 10, colors.grid, colors.grid);
  grid.rotation.x = Math.PI / 2;  // GridHelper lies in XZ; the bed is XY
  grid.position.set(Math.round(middle.x / 10) * 10, Math.round(middle.y / 10) * 10, whole.min.z - 0.02);
  grid.material.transparent = true;
  grid.material.depthWrite = false;
  keep(grid.geometry); keep(grid.material);
  scene.add(grid);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  controls.enableZoom = false;   // the wheel zooms only once the view has been clicked, so it never steals page scroll
  controls.target.copy(center);
  controls.minDistance = radius * 0.1;
  controls.maxDistance = radius * 12;
  camera.near = Math.max(radius / 300, 0.05);
  camera.far = radius * 60;

  // Where to look from. A marked overhang is seen from the side its faces look out of (from below, for a roof); an
  // assembled scene from the side its red marks are on; otherwise the three-quarter view the still pictures use.
  const home = new THREE.Vector3(1, -1, 0.75);
  if (normal.lengthSq() > 1e-8) home.copy(normal.normalize()).multiplyScalar(1.6).add(new THREE.Vector3(0.55, -0.7, 0.12));
  else if (problemBox && !problemBox.isEmpty()) {
    const toward = problemBox.getCenter(new THREE.Vector3()).sub(center);
    if (toward.length() > radius * 0.05) home.copy(toward.normalize()).multiplyScalar(1.4).add(new THREE.Vector3(0.35, -0.45, toward.z < 0 ? -0.35 : 0.35));
  }
  home.normalize();
  const fit = (r) => (r / Math.sin((camera.fov * Math.PI) / 360)) * 1.1;
  const reset = () => {
    camera.position.copy(center).addScaledVector(home, fit(radius));
    controls.target.copy(center);
    controls.update();
    draw();
  };
  const focusProblem = () => {
    if (!problemBox || problemBox.isEmpty()) return;
    const spot = problemBox.getCenter(new THREE.Vector3());
    const size = Math.max(problemBox.getSize(new THREE.Vector3()).length() / 2, radius * 0.12);
    const direction = camera.position.clone().sub(controls.target).normalize();
    controls.target.copy(spot);
    camera.position.copy(spot).addScaledVector(direction, Math.max(fit(size) * 1.6, controls.minDistance));
    controls.update();
    draw();
  };

  // ---- overlays: a scale bar and an axis triad, so size and which way is up are never a guess ----
  const scale = el("div", "viewer-scale");
  const scaleBar = el("span", "viewer-scale-bar");
  const scaleText = el("span", "viewer-scale-text");
  scale.append(scaleBar, scaleText);
  scale.setAttribute("aria-hidden", "true");
  const triad = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  triad.setAttribute("class", "viewer-triad");
  triad.setAttribute("viewBox", "0 0 64 64");
  triad.setAttribute("aria-hidden", "true");
  const axes = [["X", new THREE.Vector3(1, 0, 0)], ["Y", new THREE.Vector3(0, 1, 0)], ["Z↑", new THREE.Vector3(0, 0, 1)]].map(([name, vector]) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.textContent = name;
    line.setAttribute("class", name === "Z↑" ? "axis axis-up" : "axis");
    triad.append(line, text);
    return { vector, line, text };
  });
  const viewVector = new THREE.Vector3();
  function overlays() {
    const height = stage.clientHeight || 1;
    const distance = camera.position.distanceTo(controls.target);
    const perPixel = (2 * distance * Math.tan((camera.fov * Math.PI) / 360)) / height;
    const mm = NICE_MM.find((value) => value / perPixel >= 44) || NICE_MM[NICE_MM.length - 1];
    scaleBar.style.width = `${Math.round(mm / perPixel)}px`;
    scaleText.textContent = `${mm} mm`;
    for (const axis of axes) {
      viewVector.copy(axis.vector).transformDirection(camera.matrixWorldInverse);
      const [x, y] = [32 + viewVector.x * 20, 32 - viewVector.y * 20];
      axis.line.setAttribute("x1", "32"); axis.line.setAttribute("y1", "32");
      axis.line.setAttribute("x2", x.toFixed(1)); axis.line.setAttribute("y2", y.toFixed(1));
      axis.text.setAttribute("x", (32 + viewVector.x * 29).toFixed(1));
      axis.text.setAttribute("y", (32 - viewVector.y * 29 + 3).toFixed(1));
    }
  }

  let queued = false;
  function draw() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      grid.material.opacity = camera.position.z > grid.position.z ? 0.7 : 0.25;  // from underneath the bed stays, faintly
      camera.updateMatrixWorld();
      renderer.render(scene, camera);
      overlays();
    });
  }
  controls.addEventListener("change", draw);

  const resize = () => {
    const width = stage.clientWidth, height = stage.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    draw();
  };
  const watcher = new ResizeObserver(resize);
  watcher.observe(stage);

  // Keyboard: turn about the vertical axis and tilt, zoom, and Home to reset.
  const turn = (azimuth, tilt) => {
    const offset = camera.position.clone().sub(controls.target);
    const distance = offset.length();
    const around = Math.atan2(offset.y, offset.x) + azimuth;
    const up = Math.max(-1.5, Math.min(1.5, Math.asin(Math.max(-1, Math.min(1, offset.z / distance))) + tilt));
    camera.position.set(Math.cos(around) * Math.cos(up), Math.sin(around) * Math.cos(up), Math.sin(up)).multiplyScalar(distance).add(controls.target);
    controls.update();
    draw();
  };
  const zoom = (factor) => {
    const offset = camera.position.clone().sub(controls.target);
    const distance = Math.max(controls.minDistance, Math.min(controls.maxDistance, offset.length() * factor));
    camera.position.copy(controls.target).add(offset.setLength(distance));
    controls.update();
    draw();
  };
  canvas.addEventListener("keydown", (event) => {
    const step = Math.PI / 18;
    const moves = { ArrowLeft: () => turn(-step, 0), ArrowRight: () => turn(step, 0), ArrowUp: () => turn(0, step), ArrowDown: () => turn(0, -step),
      "+": () => zoom(0.85), "=": () => zoom(0.85), "-": () => zoom(1 / 0.85), "_": () => zoom(1 / 0.85), Home: reset };
    if (!moves[event.key]) return;
    event.preventDefault();
    event.stopPropagation();
    moves[event.key]();
  });
  canvas.addEventListener("pointerdown", () => canvas.focus({ preventScroll: true }));
  canvas.addEventListener("focus", () => { controls.enableZoom = true; });
  canvas.addEventListener("blur", () => { controls.enableZoom = false; });

  // Touch: a finger on the picture scrolls the page until the reader taps to turn the part, and "Done" gives the
  // page its scroll back.
  const touch = matchMedia("(pointer: coarse)").matches;
  const cover = el("button", "viewer-cover", "Tap to turn it");
  cover.type = "button";
  const done = el("button", "viewer-done btn btn-small", "Done turning");
  done.type = "button";
  const setActive = (on) => {
    controls.enabled = on;
    canvas.style.touchAction = on ? "none" : "pan-y";
    cover.hidden = on;
    done.hidden = !on || !touch;
  };
  cover.addEventListener("click", () => { setActive(true); canvas.focus({ preventScroll: true }); });
  done.addEventListener("click", () => setActive(false));

  stage.append(canvas, scale, triad);
  if (touch) stage.append(cover, done);
  setActive(!touch);
  resize();
  reset();

  return {
    hasHighlight: Boolean(marked),
    canFocusProblem: Boolean(problemBox && !problemBox.isEmpty() && spec.frame),
    layers: (spec.layers || []).map((layer) => ({ ...layer, color: layer.color || colors.red })),
    setHighlight(on) { highlight.visible = on; draw(); },
    setLayer(key, on) { const group = layerGroups.get(key); if (group) { group.visible = on; draw(); } },
    reset,
    focusProblem,
    dispose() {
      watcher.disconnect();
      controls.dispose();
      for (const thing of disposables) thing.dispose();
      renderer.dispose();
      renderer.forceContextLoss?.();
      for (const node of [canvas, scale, triad, cover, done]) node.remove();
    },
  };
}

// The area-weighted sum of a mesh's face normals: which way its faces look, on the whole.
function areaNormal(THREE, geometry) {
  const position = geometry.attributes.position;
  const index = geometry.index;
  const count = index ? index.count : position.count;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), sum = new THREE.Vector3();
  for (let i = 0; i + 2 < count; i += 3) {
    const [ia, ib, ic] = index ? [index.getX(i), index.getX(i + 1), index.getX(i + 2)] : [i, i + 1, i + 2];
    a.fromBufferAttribute(position, ia); b.fromBufferAttribute(position, ib); c.fromBufferAttribute(position, ic);
    sum.add(b.sub(a).cross(c.sub(a)));
  }
  return sum;
}
