// A 3D phone that carries the story. Its screen plays a real chat, and every AI
// message on it is quoted from the eval's saved answers (the build checks each
// quote word for word). The phone floats beside the text, tilts a little as the
// page scrolls, and moves between story steps. Without WebGL, a flat phone shows.

import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const DARK = matchMedia("(prefers-color-scheme: dark)");
const DATA = JSON.parse(document.getElementById("phone-data").textContent);

// Phone body, in world units (roughly a 6.1" phone).
const PHONE_W = 0.72;
const PHONE_H = 1.48;
const PHONE_D = 0.075;
const SCREEN_INSET = 0.028;
const SCR_W = 780;
const SCR_H = Math.round((SCR_W * (PHONE_H - 2 * SCREEN_INSET)) / (PHONE_W - 2 * SCREEN_INSET));

const LIGHT_UI = {
  bg: "#ffffff", ink: "#16181d", soft: "#6b7080", line: "#e6e8ee", card: "#ffffff", input: "#f4f5f8", hint: "#9a9ea9",
  user: "#1548c0", ai: "#eff1f5", red: "#c4372a", redBg: "#fbebe7",
  green: "#1d6b45", greenBg: "#e6f2ec", tint: "#f2f4ff", navy: "#031f49",
};
const DARK_UI = {
  bg: "#0d0d0f", ink: "#f2f2f5", soft: "#8e8e96", line: "#26262b", card: "#17171b", input: "#1c1c21", hint: "#6e6e76",
  user: "#2a5bd7", ai: "#232328", red: "#ff7b6b", redBg: "#3a1a16",
  green: "#6fd39c", greenBg: "#13281d", tint: "#1b2440", navy: "#c9d6ff",
};
let C = DARK.matches ? DARK_UI : LIGHT_UI;
const SANS = '"Inter", system-ui, sans-serif';
const SERIF = '"Newsreader", Georgia, serif';

// Where the phone sits in each story step: [x, y] of its center as a fraction of
// the viewport, and scale. Steps not listed move the phone out of view.
const LAYOUT = {
  desktop: {
    hero: [0.72, 0.5, 1.05], ask: [0.63, 0.5, 0.9], pages: [0.63, 0.5, 0.9], quote: [0.63, 0.5, 0.9],
    instant: [0.69, 0.5, 1.05], cancel: [0.69, 0.5, 1.05], end: [0.5, 0.19, 0.46],
  },
  mobile: {
    hero: [0.5, 0.21, 0.58], ask: [0.5, 0.17, 0.44], pages: [0.5, 0.17, 0.44], quote: [0.5, 0.17, 0.44],
    instant: [0.5, 0.21, 0.56], cancel: [0.5, 0.21, 0.56], end: [0.5, 0.15, 0.38],
  },
};

/* ---------------------------------------------------------------- drawing kit */

function font(g, weight, px, family = SANS) {
  g.font = `${weight} ${px}px ${family}`;
}

function wrap(g, text, maxW) {
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (g.measureText(test).width > maxW && line) {
      lines.push(line);
      line = w;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function roundRect(g, x, y, w, h, r, fill, stroke) {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
  if (fill) { g.fillStyle = fill; g.fill(); }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = 2; g.stroke(); }
}

const PAD = 40;
const BUBBLE_MAX = SCR_W * 0.8;
const LINE_H = 52;

/** Draws a chat bubble and returns its bottom y. `reveal` (0..1) types the text in. */
function bubble(g, y, text, { mine = false, reveal = 1, strike = 0, strikeWord = "", highlight = "" } = {}) {
  font(g, 500, 38);
  const shown = reveal >= 1 ? text : text.slice(0, Math.max(1, Math.round(text.length * reveal)));
  const lines = wrap(g, text, BUBBLE_MAX - 56);
  const w = Math.min(BUBBLE_MAX, Math.max(...lines.map((l) => g.measureText(l).width)) + 56);
  const h = lines.length * LINE_H + 40;
  const x = mine ? SCR_W - PAD - w : PAD;
  roundRect(g, x, y, w, h, 30, mine ? C.user : C.ai);
  g.fillStyle = mine ? "#ffffff" : C.ink;
  g.textBaseline = "top";
  let left = shown.length;
  lines.forEach((ln, i) => {
    const part = ln.slice(0, Math.max(0, left));
    left -= ln.length + 1;
    const ty = y + 22 + i * LINE_H;
    g.fillStyle = mine ? "#ffffff" : C.ink;
    g.fillText(part, x + 28, ty);
    if (highlight && reveal >= 1 && ln.includes(highlight.split(" ")[0])) {
      markPhrase(g, ln, highlight, x + 28, ty, C.red, 4);
    }
    if (strikeWord && strike > 0 && ln.includes(strikeWord)) {
      const start = g.measureText(ln.slice(0, ln.indexOf(strikeWord))).width;
      const width = g.measureText(strikeWord).width;
      g.strokeStyle = C.red;
      g.lineWidth = 5;
      g.lineCap = "round";
      g.beginPath();
      g.moveTo(x + 28 + start - 4, ty + 22);
      g.lineTo(x + 28 + start - 4 + (width + 8) * strike, ty + 20);
      g.stroke();
    }
  });
  return y + h;
}

/** Underlines the part of `highlight` that falls on this wrapped line. */
function markPhrase(g, line, highlight, x, y, color, thickness) {
  const words = highlight.split(" ");
  for (let n = words.length; n > 0; n--) {
    const piece = words.slice(0, n).join(" ");
    const at = line.indexOf(piece);
    if (at >= 0) {
      const start = g.measureText(line.slice(0, at)).width;
      g.fillStyle = color;
      g.fillRect(x + start, y + 45, g.measureText(piece).width, thickness);
      return;
    }
  }
  const tail = words.slice(-3).join(" ");
  const at = line.indexOf(tail);
  if (at >= 0) {
    g.fillStyle = color;
    g.fillRect(x, y + 45, g.measureText(line.slice(0, at + tail.length)).width, thickness);
  }
}

function typing(g, y, p) {
  roundRect(g, PAD, y, 120, 64, 30, C.ai);
  for (let i = 0; i < 3; i++) {
    const phase = (p * 3 + i * 0.33) % 1;
    g.globalAlpha = 0.35 + 0.65 * Math.abs(Math.sin(phase * Math.PI));
    g.beginPath();
    g.arc(PAD + 34 + i * 26, y + 32, 8, 0, Math.PI * 2);
    g.fillStyle = C.soft;
    g.fill();
  }
  g.globalAlpha = 1;
  return y + 64;
}

function chip(g, x, y, text, color, bg, icon = "") {
  font(g, 600, 30);
  const label = icon ? `${icon}  ${text}` : text;
  const w = g.measureText(label).width + 36;
  roundRect(g, x, y, w, 58, 29, bg);
  g.fillStyle = color;
  g.textBaseline = "middle";
  g.fillText(label, x + 18, y + 30);
  return y + 58;
}

function note(g, y, text) {
  font(g, 500, 28);
  g.fillStyle = C.soft;
  g.textBaseline = "top";
  g.textAlign = "center";
  g.fillText(text, SCR_W / 2, y);
  g.textAlign = "left";
  return y + 34;
}

function card(g, y, title, lines, accent) {
  font(g, 500, 32);
  const wrapped = lines.flatMap(([t, color]) => wrap(g, t, SCR_W - 2 * PAD - 48).map((l) => [l, color]));
  const h = 78 + wrapped.length * 46;
  roundRect(g, PAD, y, SCR_W - 2 * PAD, h, 24, C.card, C.line);
  g.fillStyle = accent;
  g.fillRect(PAD, y + 18, 5, h - 36);
  font(g, 600, 24);
  g.fillStyle = C.soft;
  g.textBaseline = "top";
  g.fillText(title.toUpperCase(), PAD + 26, y + 22);
  font(g, 500, 32);
  wrapped.forEach(([l, color], i) => {
    g.fillStyle = color;
    g.fillText(l, PAD + 26, y + 64 + i * 46);
  });
  return y + h;
}

function chrome(g, subtitle) {
  g.fillStyle = C.bg;
  g.fillRect(0, 0, SCR_W, SCR_H);
  font(g, 600, 30);
  g.fillStyle = C.ink;
  g.textBaseline = "middle";
  g.fillText("9:41", 60, 52);
  roundRect(g, SCR_W / 2 - 92, 26, 184, 54, 27, "#000000");
  g.fillStyle = C.ink;
  g.fillRect(SCR_W - 120, 42, 54, 22);
  g.beginPath();
  g.arc(SCR_W - 160, 53, 9, 0, Math.PI * 2);
  g.fill();
  g.strokeStyle = C.line;
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(0, 190);
  g.lineTo(SCR_W, 190);
  g.stroke();
  g.beginPath();
  g.arc(PAD + 28, 140, 28, 0, Math.PI * 2);
  g.fillStyle = C.tint;
  g.fill();
  font(g, 700, 26, SERIF);
  g.fillStyle = C.user;
  g.textAlign = "center";
  g.fillText("AI", PAD + 28, 141);
  g.textAlign = "left";
  font(g, 600, 30);
  g.fillStyle = C.ink;
  g.fillText("Assistant", PAD + 74, 126);
  font(g, 500, 24);
  g.fillStyle = C.soft;
  g.fillText(subtitle, PAD + 74, 160);
  roundRect(g, PAD, SCR_H - 130, SCR_W - 2 * PAD, 80, 40, C.input, C.line);
  font(g, 500, 28);
  g.fillStyle = C.hint;
  g.fillText("Ask anything", PAD + 32, SCR_H - 88);
  roundRect(g, SCR_W / 2 - 110, SCR_H - 30, 220, 10, 5, C.ink);
}

const between = (p, a, b) => Math.min(1, Math.max(0, (p - a) / (b - a)));

/* ---------------------------------------------------------------- the screens */

const SCREENS = {
  hero(g, p) {
    chrome(g, "General AI, no access to Albert's pages");
    let y = 240;
    y = bubble(g, y, DATA.price_q, { mine: true });
    y += 30;
    if (p < 0.4) return typing(g, y, p);
    bubble(g, y, `${DATA.wrong}…`, { reveal: between(p, 0.4, 0.95) });
  },
  ask(g, p) {
    chrome(g, "General AI, no access to Albert's pages");
    let y = 240;
    y = bubble(g, y, DATA.price_q, { mine: true });
    y = bubble(g, y + 30, `${DATA.wrong}…`, { strike: between(p, 0.1, 0.5), strikeWord: "$14.99" });
    if (p > 0.5) chip(g, PAD, y + 24, "Albert publishes $39.99", C.red, C.redBg, "✕");
  },
  pages(g, p) {
    chrome(g, "Reads Albert's help pages first");
    let y = 240;
    y = bubble(g, y, DATA.price_q, { mine: true });
    y = note(g, y + 26, p > 0.15 ? "Searched Albert's help center" : "Searching Albert's help center…");
    y += 18;
    if (p < 0.35) return typing(g, y, p);
    y = bubble(g, y, DATA.read, { reveal: between(p, 0.35, 0.75) });
    if (p > 0.8) chip(g, PAD, y + 24, DATA.source, C.user, C.tint, "↗");
  },
  quote(g, p) {
    chrome(g, "Must quote the page for every claim");
    let y = 240;
    y = bubble(g, y, DATA.price_q, { mine: true });
    y = note(g, y + 26, "Searched Albert's help center");
    y = bubble(g, y + 18, DATA.quoted);
    if (p > 0.2) y = card(g, y + 24, `Quote from "${DATA.source}"`, [[`“${DATA.quote}.”`, C.ink]], C.user);
    if (p > 0.6) chip(g, PAD, y + 24, "Quote found on the page", C.green, C.greenBg, "✓");
  },
  instant(g, p) {
    chrome(g, "Reads Albert's help pages first");
    let y = 240;
    y = bubble(g, y, DATA.fees_q, { mine: true });
    y = bubble(g, y + 30, DATA.conflict, { highlight: p > 0.35 ? DATA.conflict_mark : "" });
    if (p > 0.55) {
      y = card(g, y + 30, "What Albert's Terms of Use say", [
        ["Instant Advance: no late fees", C.green],
        ["Instant line of credit: late fee may apply", C.red],
        ["Instant Loan: late fees up to $10", C.red],
      ], C.navy);
    }
  },
  cancel(g, p) {
    chrome(g, "General AI, no access to Albert's pages");
    let y = 240;
    y = bubble(g, y, DATA.cancel_q, { mine: true });
    y = bubble(g, y + 30, `${DATA.cancel_wrong}…`, { strike: between(p, 0.1, 0.45), strikeWord: "shouldn't" });
    if (p > 0.5) card(g, y + 30, "Albert's Terms of Use", [[DATA.terms, C.ink], ["Help article: Deactivating or closing your Albert account", C.soft]], C.red);
  },
  end(g) {
    SCREENS.quote(g, 1);
  },
};

/* ---------------------------------------------------------------- 3D phone */

function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2);
  s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r);
  s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2);
  s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r);
  s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}

function makeScreen(renderer) {
  const c = document.createElement("canvas");
  c.width = SCR_W;
  c.height = SCR_H;
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const w = PHONE_W - 2 * SCREEN_INSET;
  const h = PHONE_H - 2 * SCREEN_INSET;
  const shape = roundedRect(w, h, 0.085);
  const geo = new THREE.ShapeGeometry(shape, 12);
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / w + 0.5, pos.getY(i) / h + 0.5);
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
  mesh.position.z = PHONE_D / 2 + 0.0012;
  const glass = new THREE.Mesh(geo, new THREE.MeshPhysicalMaterial({
    color: 0xffffff, roughness: 0.06, metalness: 0, clearcoat: 1, transparent: true, opacity: 0.07,
  }));
  glass.position.z = PHONE_D / 2 + 0.0024;
  return { mesh, glass, g: c.getContext("2d"), tex };
}

function makePhone(renderer) {
  const group = new THREE.Group();
  const frame = new THREE.MeshPhysicalMaterial({ color: 0x3a3b40, metalness: 0.85, roughness: 0.3, clearcoat: 0.4 });
  const front = new THREE.MeshPhysicalMaterial({ color: 0x0b0c0f, metalness: 0.2, roughness: 0.15, clearcoat: 1 });
  // Frame: a rounded rectangle extruded with a beveled edge, like a real phone band.
  const bevel = 0.016;
  const bodyGeo = new THREE.ExtrudeGeometry(roundedRect(PHONE_W - 2 * bevel, PHONE_H - 2 * bevel, 0.1), {
    depth: PHONE_D - 2 * bevel, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel,
    bevelSegments: 6, curveSegments: 32,
  });
  bodyGeo.translate(0, 0, -(PHONE_D - 2 * bevel) / 2);
  const body = new THREE.Mesh(bodyGeo, frame);
  body.castShadow = true;
  group.add(body);
  // Front glass: black, slightly inset from the frame.
  const face = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(PHONE_W - 0.016, PHONE_H - 0.016, 0.106), 32), front);
  face.position.z = PHONE_D / 2 + 0.0004;
  group.add(face);
  for (const [x, y, h] of [[-1, 0.3, 0.09], [-1, 0.16, 0.13], [-1, 0.0, 0.13], [1, 0.12, 0.2]]) {
    const btn = new THREE.Mesh(new RoundedBoxGeometry(0.012, h, 0.03, 3, 0.005), frame);
    btn.position.set(x * (PHONE_W / 2 + 0.003), y, 0);
    group.add(btn);
  }
  const screen = makeScreen(renderer);
  group.add(screen.mesh, screen.glass);
  return { group, screen };
}

/* ---------------------------------------------------------------- scene */

function viewSize(camera) {
  const h = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  return { w: h * camera.aspect, h };
}

function damp(current, target, rate, dt) {
  return REDUCED ? target : current + (target - current) * (1 - Math.exp(-rate * dt));
}

async function start(stage) {
  await Promise.all([
    document.fonts.load('500 32px "Inter"'),
    document.fonts.load('600 32px "Inter"'),
    document.fonts.load('700 26px "Newsreader"'),
  ]).catch(() => {});

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.VSMShadowMap;
  renderer.domElement.className = "phone3d";
  stage.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.8;

  const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 50);
  camera.position.z = 5;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x8c8a85, 0.5));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(-1.4, 2.4, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = key.shadow.camera.bottom = -4;
  key.shadow.camera.right = key.shadow.camera.top = 4;
  key.shadow.radius = 16;
  key.shadow.blurSamples = 20;
  key.shadow.bias = -0.0002;
  scene.add(key);

  const wall = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ opacity: 0.18 }));
  wall.position.z = -0.4;
  wall.receiveShadow = true;
  scene.add(wall);
  let dirty = true;
  const syncWall = () => {
    wall.material.opacity = DARK.matches ? 0.4 : 0.18;
    C = DARK.matches ? DARK_UI : LIGHT_UI;
    dirty = true;
  };
  syncWall();
  DARK.addEventListener("change", syncWall);

  const phone = makePhone(renderer);
  scene.add(phone.group);

  let mobile = window.innerWidth <= 820;
  window.addEventListener("resize", () => {
    mobile = window.innerWidth <= 820;
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    dirty = true;
  });

  // Scrolling tips the phone a little, like it's being carried down the page.
  let tilt = 0;
  let tiltV = 0;
  let lastScroll = window.scrollY;
  window.addEventListener("scroll", () => {
    if (REDUCED) return;
    tiltV += Math.max(-60, Math.min(60, window.scrollY - lastScroll)) * 0.0006;
    lastScroll = window.scrollY;
    dirty = true;
  }, { passive: true });

  let shownState = null;
  let progress = 1;
  let first = true;
  let prev = performance.now();

  function frame(now) {
    const dt = Math.min(0.05, (now - prev) / 1000);
    prev = now;
    const state = document.body.dataset.state || "hero";
    const spot = LAYOUT[mobile ? "mobile" : "desktop"][state];
    const { w, h } = viewSize(camera);
    const g = phone.group;

    const tx = spot ? (spot[0] - 0.5) * w : g.position.x;
    const ty = spot ? (0.5 - spot[1]) * h : -h * 0.95;
    const ts = spot ? spot[2] : g.scale.x;
    if (first) {
      g.position.set(tx, ty, 0);
      g.scale.setScalar(ts);
    }
    const before = g.position.x + g.position.y + g.scale.x;
    g.position.x = damp(g.position.x, tx, 4.5, dt);
    g.position.y = damp(g.position.y, ty, 4.5, dt);
    g.scale.setScalar(damp(g.scale.x, ts, 4.5, dt));

    if (!REDUCED) {
      tiltV += (-20 * tilt - 4 * tiltV) * dt;
      tilt += tiltV * dt;
    }
    const turn = mobile ? 0 : -0.2;
    g.rotation.set(0.05 + tilt, damp(g.rotation.y, turn, 4, dt), 0);

    // Each new step replays its screen from the start.
    if (spot && state !== shownState) {
      shownState = state;
      progress = REDUCED ? 1 : 0;
    }
    let repaint = false;
    if (spot && (progress < 1 || first || dirty)) {
      progress = Math.min(1, progress + dt / 1.6);
      SCREENS[state](phone.screen.g, progress);
      phone.screen.tex.needsUpdate = true;
      repaint = true;
    }

    const moving = Math.abs(before - (g.position.x + g.position.y + g.scale.x)) > 1e-5 || Math.abs(tiltV) > 1e-4;
    if (moving || repaint || dirty || first) {
      renderer.render(scene, camera);
      if (first) document.documentElement.classList.add("webgl");
      first = false;
      dirty = false;
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}

const stage = document.querySelector(".stage");
if (stage && webglAvailable()) {
  start(stage).catch((err) => {
    console.error("3D phone failed to start; keeping the flat phone.", err);
    document.documentElement.classList.remove("webgl");
  });
}
