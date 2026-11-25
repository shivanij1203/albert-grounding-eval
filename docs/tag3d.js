// Real 3D paper tags for the story page.
//
// Every tag is lit geometry: a die-cut card with thickness, a paper texture with
// fibers and grain, a brass eyelet, and a twine loop. Prices and notes are printed
// into the paper texture, so the ink takes the same light as the card. Tags hang
// from their string, swing a little when they move or the page scrolls, and flip
// in 3D. If WebGL isn't available the flat CSS tags already on the page stay.

import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const DARK = matchMedia("(prefers-color-scheme: dark)");

// Tag geometry, in world units. The hole sits near the top; the tag hangs from it.
const TAG_W = 0.6;
const TAG_H = 1.0;
const HOLE_Y = TAG_H / 2 - 0.12;
const HOLE_R = 0.03;
const DEPTH = 0.007;
const TEX_W = 1024;
const TEX_H = Math.round((TEX_W * TAG_H) / TAG_W);

const INK = "#2b2723";
const SOFT = "#76694f";
const MARKER = "#c4372a";
const STAMP = "#1548c0";
const GREEN = "#1d6b45";
const RED = "#a8321f";

const FIBER = "120,95,55";
const FIBER_LIGHT = "255,250,235";

// Where each tag hangs in each story state: [x, y] of the eyelet as a fraction of
// the viewport, scale, and resting tilt. "flip" shows the back of the main tag.
const LAYOUT = {
  desktop: {
    hero: { main: [0.72, 0.29, 1.0, -0.05] },
    ask: { main: [0.72, 0.1, 0.74, -0.04] },
    pages: { main: [0.72, 0.1, 0.74, -0.04], flip: true },
    quote: { main: [0.72, 0.1, 0.74, -0.04], flip: true },
    instant: { m1: [0.6, 0.3, 0.62, -0.05], m2: [0.72, 0.27, 0.62, 0.03], m3: [0.84, 0.31, 0.62, -0.02] },
    cancel: { word: [0.72, 0.26, 0.86, -0.04] },
    method: {},
    end: { main: [0.5, 0.07, 0.42, -0.03], flip: true },
  },
  mobile: {
    hero: { main: [0.5, 0.05, 0.46, -0.05] },
    ask: { main: [0.5, 0.03, 0.3, -0.04] },
    pages: { main: [0.5, 0.03, 0.3, -0.04], flip: true },
    quote: { main: [0.5, 0.03, 0.3, -0.04], flip: true },
    instant: { m1: [0.2, 0.07, 0.4, -0.05], m2: [0.5, 0.05, 0.4, 0.03], m3: [0.8, 0.08, 0.4, -0.02] },
    cancel: { word: [0.5, 0.05, 0.56, -0.04] },
    method: {},
    end: { main: [0.5, 0.03, 0.3, -0.03], flip: true },
  },
};
const HIDDEN_Y = -0.55; // above the top edge, lifted out on its string

/* ---------------------------------------------------------------- paper */

function makePaperBase() {
  const c = document.createElement("canvas");
  c.width = TEX_W;
  c.height = TEX_H;
  const g = c.getContext("2d");
  g.fillStyle = "#efe3c4";
  g.fillRect(0, 0, TEX_W, TEX_H);
  const img = g.getImageData(0, 0, TEX_W, TEX_H);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 12;
    img.data[i] += n;
    img.data[i + 1] += n;
    img.data[i + 2] += n * 0.85;
  }
  g.putImageData(img, 0, 0);
  g.lineCap = "round";
  for (let k = 0; k < 1100; k++) {
    const x = Math.random() * TEX_W;
    const y = Math.random() * TEX_H;
    const a = Math.random() * Math.PI;
    const len = 6 + Math.random() * 24;
    g.strokeStyle = `rgba(${Math.random() < 0.55 ? FIBER : FIBER_LIGHT},${0.05 + Math.random() * 0.08})`;
    g.lineWidth = 0.6 + Math.random() * 1.3;
    g.beginPath();
    g.moveTo(x, y);
    g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    g.stroke();
  }
  return c;
}

function makeBumpTexture() {
  const size = 512;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const img = g.createImageData(size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 128 + (Math.random() - 0.5) * 70;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(2, 3);
  return tex;
}

function makeTwineTexture() {
  const c = document.createElement("canvas");
  c.width = 32;
  c.height = 128;
  const g = c.getContext("2d");
  g.fillStyle = "#a47f4e";
  g.fillRect(0, 0, 32, 128);
  for (let y = -32; y < 160; y += 14) {
    g.strokeStyle = "rgba(90,64,34,.55)";
    g.lineWidth = 5;
    g.beginPath();
    g.moveTo(0, y);
    g.lineTo(32, y + 22);
    g.stroke();
    g.strokeStyle = "rgba(214,184,130,.35)";
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(0, y + 6);
    g.lineTo(32, y + 28);
    g.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

/* ---------------------------------------------------------------- printing */

function setFont(g, weight, px, family, spacing = 0) {
  g.font = `${weight} ${px}px ${family}`;
  if ("letterSpacing" in g) g.letterSpacing = `${spacing}px`;
}

function fitFont(g, text, weight, family, maxPx, maxW, spacing = 0) {
  let px = maxPx;
  setFont(g, weight, px, family, spacing);
  while (g.measureText(text).width > maxW && px > 24) {
    px -= 4;
    setFont(g, weight, px, family, spacing);
  }
  return px;
}

function print(g, text, y, { weight = 600, px, family, color = INK, spacing = 0, maxW = 860, alpha = 0.92 }) {
  g.save();
  g.globalCompositeOperation = "multiply";
  g.globalAlpha = alpha;
  g.fillStyle = color;
  g.textAlign = "center";
  g.textBaseline = "alphabetic";
  fitFont(g, text, weight, family, px, maxW, spacing);
  g.fillText(text, TEX_W / 2, y);
  g.restore();
}

function label(g, text, y) {
  print(g, text, y, { weight: 500, px: 58, family: '"JetBrains Mono", monospace', color: SOFT, spacing: 8 });
}

function hand(g, text, y, px, color, tilt) {
  g.save();
  g.translate(TEX_W / 2, y);
  g.rotate(tilt);
  g.globalCompositeOperation = "multiply";
  g.globalAlpha = 0.9;
  g.fillStyle = color;
  g.textAlign = "center";
  setFont(g, 600, px, '"Caveat", cursive');
  g.fillText(text, 0, 0);
  g.restore();
}

function marker(g, x0, y0, x1, y1, progress) {
  if (progress <= 0) return;
  const steps = 48;
  g.save();
  g.globalCompositeOperation = "multiply";
  g.globalAlpha = 0.82;
  g.strokeStyle = MARKER;
  g.lineCap = g.lineJoin = "round";
  for (const pass of [{ dy: 0, w: 24 }, { dy: 18, w: 15 }]) {
    g.lineWidth = pass.w;
    g.beginPath();
    const last = Math.max(1, Math.round(steps * progress));
    for (let i = 0; i <= last; i++) {
      const t = i / steps;
      const x = x0 + (x1 - x0) * t;
      const y = y0 + (y1 - y0) * t + Math.sin(t * 3.1) * 9 + pass.dy * (t - 0.25);
      if (i === 0) g.moveTo(x, y);
      else g.lineTo(x, y);
    }
    g.stroke();
  }
  g.restore();
}

function stamp(g, text, y, alpha) {
  if (alpha <= 0) return;
  const c = document.createElement("canvas");
  c.width = 900;
  c.height = 200;
  const s = c.getContext("2d");
  setFont(s, 600, 60, '"JetBrains Mono", monospace', 6);
  const w = Math.min(860, s.measureText(text).width + 70);
  const x = (900 - w) / 2;
  s.strokeStyle = s.fillStyle = STAMP;
  s.lineWidth = 7;
  s.beginPath();
  s.roundRect(x, 50, w, 100, 12);
  s.stroke();
  s.textAlign = "center";
  s.textBaseline = "middle";
  s.fillText(text, 450, 103);
  s.globalCompositeOperation = "destination-out";
  for (let k = 0; k < 340; k++) {
    s.globalAlpha = 0.35 + Math.random() * 0.5;
    s.beginPath();
    s.arc(x + Math.random() * w, 45 + Math.random() * 110, 0.6 + Math.random() * 2.2, 0, Math.PI * 2);
    s.fill();
  }
  g.save();
  g.globalCompositeOperation = "multiply";
  g.globalAlpha = 0.86 * alpha;
  g.translate(TEX_W / 2, y);
  g.rotate(-0.07);
  g.drawImage(c, -450, -100);
  g.restore();
}

const SERIF = '"Newsreader", Georgia, serif';
const SANS = '"Inter", system-ui, sans-serif';

const FACES = {
  front(g, p) {
    label(g, "GENIUS · PER MONTH", 660);
    print(g, "$14.99", 960, { px: 300, family: SERIF });
    marker(g, 130, 880, 900, 900, p);
    hand(g, "the AI's answer", 1230, 120, MARKER, -0.06);
  },
  back(g) {
    label(g, "GENIUS · PER MONTH", 660);
    print(g, "$39.99", 960, { px: 300, family: SERIF });
    stamp(g, "ALBERT'S PRICE", 1220, 1);
  },
  m1(g) {
    label(g, "INSTANT", 650);
    print(g, "Advance", 830, { px: 150, family: SERIF });
    print(g, "No late fees", 1090, { px: 112, family: SANS, color: GREEN });
    print(g, "No interest", 1230, { weight: 500, px: 100, family: SANS, color: SOFT });
  },
  m2(g) {
    label(g, "INSTANT", 650);
    print(g, "Line of credit", 830, { px: 150, family: SERIF });
    print(g, "Draw fee", 1090, { weight: 500, px: 100, family: SANS, color: SOFT });
    print(g, "Late fee may apply", 1230, { px: 104, family: SANS, color: RED });
  },
  m3(g) {
    label(g, "INSTANT", 650);
    print(g, "Loan", 830, { px: 150, family: SERIF });
    print(g, "Late fees", 1090, { px: 112, family: SANS, color: RED });
    print(g, "up to $10", 1230, { px: 112, family: SANS, color: RED });
  },
  word(g, p) {
    const strike = Math.min(1, p / 0.4);
    const stampIn = Math.min(1, Math.max(0, (p - 0.4) / 0.3));
    const wordIn = Math.min(1, Math.max(0, (p - 0.7) / 0.3));
    label(g, "CUSTOMER TYPES", 630);
    hand(g, "cancel", 890, 250, INK, -0.04);
    marker(g, 250, 830, 780, 820, strike);
    stamp(g, "ALBERT'S ARTICLE SAYS", 1070, stampIn);
    if (wordIn > 0) print(g, "deactivate", 1330, { px: 170, family: SERIF, alpha: 0.92 * wordIn });
  },
};

/* ---------------------------------------------------------------- tag object */

function tagShape() {
  const w = TAG_W / 2;
  const h = TAG_H / 2;
  const chamfer = 0.15;
  const r = 0.035;
  const s = new THREE.Shape();
  s.moveTo(-w + r, -h);
  s.lineTo(w - r, -h);
  s.quadraticCurveTo(w, -h, w, -h + r);
  s.lineTo(w, h - chamfer);
  s.lineTo(w - chamfer, h);
  s.lineTo(-w + chamfer, h);
  s.lineTo(-w, h - chamfer);
  s.lineTo(-w, -h + r);
  s.quadraticCurveTo(-w, -h, -w + r, -h);
  const hole = new THREE.Path();
  hole.absarc(0, HOLE_Y, HOLE_R, 0, Math.PI * 2, true);
  s.holes.push(hole);
  return s;
}

function remapUV(geo) {
  geo.computeBoundingBox();
  const b = geo.boundingBox;
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    uv.setXY(i, (pos.getX(i) - b.min.x) / (b.max.x - b.min.x), (pos.getY(i) - b.min.y) / (b.max.y - b.min.y));
  }
  uv.needsUpdate = true;
}

function makeFace(shared, draw, back) {
  const c = document.createElement("canvas");
  c.width = TEX_W;
  c.height = TEX_H;
  const g = c.getContext("2d");
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = shared.anisotropy;
  const geo = new THREE.ShapeGeometry(shared.shape, 24);
  remapUV(geo);
  if (back) geo.rotateY(Math.PI);
  const mat = new THREE.MeshStandardMaterial({
    map: tex, bumpMap: shared.bump, bumpScale: 0.9, roughness: 0.92,
    polygonOffset: true, polygonOffsetFactor: -2,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.z = (back ? -1 : 1) * (DEPTH / 2 + 0.0006);
  mesh.receiveShadow = true;
  let last = null;
  return {
    mesh,
    paint(progress) {
      const key = Math.round(progress * 200);
      if (key === last) return false;
      last = key;
      g.drawImage(shared.paper, 0, 0);
      draw(g, progress);
      tex.needsUpdate = true;
      return true;
    },
  };
}

function makeString(shared) {
  const group = new THREE.Group();
  const curves = [
    [[0, 0, 0.012], [0, 0.07, 0.03], [0.02, 0.18, 0.02], [0.03, 0.3, 0]],
    [[0, 0, -0.012], [0, 0.07, -0.03], [0.026, 0.18, -0.015], [0.03, 0.3, 0]],
    [[0.03, 0.3, 0], [0.055, 0.38, 0.004], [0.025, 0.48, 0.012], [-0.02, 0.56, 0]],
  ];
  for (const pts of curves) {
    const curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p)));
    const tex = shared.twine.clone();
    tex.needsUpdate = true;
    tex.repeat.set(1, curve.getLength() * 30);
    const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 1 });
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.0058, 8, false), mat);
    tube.castShadow = true;
    group.add(tube);
  }
  const knot = new THREE.Mesh(new THREE.IcosahedronGeometry(0.014, 1), new THREE.MeshStandardMaterial({ map: shared.twine, roughness: 1 }));
  knot.position.set(0.03, 0.3, 0);
  knot.scale.set(1.2, 0.9, 1);
  knot.castShadow = true;
  group.add(knot);
  return group;
}

function makeTag(shared, frontDraw, backDraw) {
  const pivot = new THREE.Group();
  const swing = new THREE.Group();
  const flip = new THREE.Group();
  pivot.add(swing);
  swing.add(flip);
  swing.add(makeString(shared));

  const card = new THREE.Group();
  card.position.y = -HOLE_Y;
  flip.add(card);

  const body = new THREE.Mesh(
    new THREE.ExtrudeGeometry(shared.shape, { depth: DEPTH, bevelEnabled: false, curveSegments: 24 }),
    shared.edge,
  );
  body.geometry.translate(0, 0, -DEPTH / 2);
  body.castShadow = true;
  card.add(body);

  const front = makeFace(shared, frontDraw, false);
  card.add(front.mesh);
  const faces = [front];
  if (backDraw) {
    const back = makeFace(shared, backDraw, true);
    card.add(back.mesh);
    faces.push(back);
  }
  for (const side of [1, -1]) {
    const ring = new THREE.Mesh(shared.eyeletGeo, shared.brass);
    ring.position.set(0, HOLE_Y, side * (DEPTH / 2 + 0.004));
    ring.castShadow = true;
    card.add(ring);
  }

  return {
    pivot, swing, flip, faces,
    theta: 0, omega: 0, twist: 0, twistV: 0, flipAngle: 0,
    progress: 0, vx: 0, lastX: null,
  };
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
    document.fonts.load('600 100px "Newsreader"'),
    document.fonts.load('600 100px "Caveat"'),
    document.fonts.load('500 40px "JetBrains Mono"'),
    document.fonts.load('600 40px "Inter"'),
  ]).catch(() => {});

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.VSMShadowMap;
  renderer.domElement.className = "tags3d";
  stage.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;

  const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 50);
  camera.position.z = 5;

  scene.add(new THREE.HemisphereLight(0xfff6e8, 0x8c8577, 0.6));
  const key = new THREE.DirectionalLight(0xfff3e0, 1.9);
  key.position.set(-1.2, 2.2, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = key.shadow.camera.bottom = -4;
  key.shadow.camera.right = key.shadow.camera.top = 4;
  key.shadow.bias = -0.0002;
  key.shadow.radius = 14;
  key.shadow.blurSamples = 20;
  scene.add(key);

  const wall = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ opacity: 0.16 }));
  wall.position.z = -0.16;
  wall.receiveShadow = true;
  scene.add(wall);
  const syncWall = () => { wall.material.opacity = DARK.matches ? 0.36 : 0.2; };
  syncWall();
  DARK.addEventListener("change", syncWall);

  const shared = {
    shape: tagShape(),
    paper: makePaperBase(),
    bump: makeBumpTexture(),
    twine: makeTwineTexture(),
    anisotropy: renderer.capabilities.getMaxAnisotropy(),
    edge: new THREE.MeshStandardMaterial({ color: 0xe6d6b0, roughness: 0.95 }),
    brass: new THREE.MeshStandardMaterial({ color: 0xc2a46b, metalness: 0.9, roughness: 0.32 }),
    eyeletGeo: new THREE.TorusGeometry(0.034, 0.009, 16, 40),
  };

  const tags = {
    main: makeTag(shared, FACES.front, FACES.back),
    m1: makeTag(shared, FACES.m1),
    m2: makeTag(shared, FACES.m2),
    m3: makeTag(shared, FACES.m3),
    word: makeTag(shared, FACES.word),
  };
  for (const t of Object.values(tags)) {
    scene.add(t.pivot);
    t.faces.forEach((f) => f.paint(0));
  }

  let mobile = window.innerWidth <= 820;
  function resize() {
    mobile = window.innerWidth <= 820;
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    dirty = true;
  }
  window.addEventListener("resize", resize);

  let lastScroll = window.scrollY;
  window.addEventListener("scroll", () => {
    if (REDUCED) return;
    const dy = Math.max(-80, Math.min(80, window.scrollY - lastScroll));
    lastScroll = window.scrollY;
    for (const t of Object.values(tags)) t.omega += dy * 0.00032;
    dirty = true;
  }, { passive: true });

  let dirty = true;
  let firstFrame = true;
  let prev = performance.now();

  function targetFor(name, t, state) {
    const layout = LAYOUT[mobile ? "mobile" : "desktop"][state] || {};
    const spot = layout[name];
    const { w, h } = viewSize(camera);
    if (!spot) {
      const x = t.pivot.position.x || 0;
      return { x, y: (0.5 - HIDDEN_Y) * h, s: t.pivot.scale.x || 0.6, tilt: 0, flip: t.flipAngle > 1.5, visible: false };
    }
    const [fx, fy, s, tilt] = spot;
    return { x: (fx - 0.5) * w, y: (0.5 - fy) * h, s, tilt, flip: !!layout.flip && name === "main", visible: true };
  }

  function step(name, t, state, dt) {
    const target = targetFor(name, t, state);
    const p = t.pivot.position;
    const startX = p.x;
    const startY = p.y;
    if (firstFrame) {
      p.set(target.x, target.y, 0);
      t.pivot.scale.setScalar(target.s);
    }
    p.x = damp(p.x, target.x, 5, dt);
    p.y = damp(p.y, target.y, 4.5, dt);
    const s = damp(t.pivot.scale.x, target.s, 5, dt);
    t.pivot.scale.setScalar(s);

    // Pendulum on the eyelet: sideways acceleration of the pivot pushes the tag.
    const vx = dt > 0 ? (p.x - startX) / dt : 0;
    const ax = dt > 0 ? (vx - t.vx) / dt : 0;
    t.vx = vx;
    if (!REDUCED) {
      t.omega += (-26 * t.theta - 3.2 * t.omega - ax * 0.55) * dt;
      t.theta += t.omega * dt;
      t.twistV += (-18 * t.twist - 2.4 * t.twistV + ax * 0.12) * dt;
      t.twist += t.twistV * dt;
    } else {
      t.theta = t.omega = t.twist = t.twistV = 0;
    }
    t.swing.rotation.z = target.tilt + t.theta;

    t.flipAngle = damp(t.flipAngle, target.flip ? Math.PI : 0, 4, dt);
    t.flip.rotation.y = t.flipAngle + t.twist;

    // Ink animations: the marker strike on the main tag, and the cancel sequence.
    let paint = false;
    if (name === "main") {
      const want = state === "hero" ? 0 : 1;
      t.progress = REDUCED ? want : Math.min(1, Math.max(0, t.progress + Math.sign(want - t.progress) * dt * 1.8));
      paint = t.faces[0].paint(t.progress);
    } else if (name === "word") {
      const want = state === "cancel" ? 1 : 0;
      t.progress = REDUCED ? want : Math.min(1, Math.max(0, t.progress + Math.sign(want - t.progress) * dt * (want ? 0.9 : 3)));
      paint = t.faces[0].paint(t.progress);
    }

    const moved = Math.abs(p.x - startX) + Math.abs(p.y - startY) + Math.abs(t.omega) + Math.abs(t.twistV)
      + Math.abs(t.flipAngle - (target.flip ? Math.PI : 0)) + Math.abs(s - target.s);
    return moved > 1e-4 || paint;
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - prev) / 1000);
    prev = now;
    const state = document.body.dataset.state || "hero";
    let active = dirty;
    for (const [name, t] of Object.entries(tags)) active = step(name, t, state, dt) || active;
    if (active || firstFrame) {
      renderer.render(scene, camera);
      if (firstFrame) document.documentElement.classList.add("webgl");
      firstFrame = false;
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
    console.error("3D tags failed to start; keeping the flat tags.", err);
    document.documentElement.classList.remove("webgl");
  });
}
