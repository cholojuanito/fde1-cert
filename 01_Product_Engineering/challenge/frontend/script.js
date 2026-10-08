// PokéChat frontend.
//
// Talks to the /chat endpoint through the Gradio client, still loaded from
// the public CDN (same dependency as before): on a network that blocks the
// CDN the console renders but the buttons go dead — check the browser
// console first in that case.

import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js";

// `let` so a dead connection can be re-established after a failed turn.
let client = await Client.connect(window.location.origin);

// --- DOM ---------------------------------------------------------------

const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("input");
const led = document.getElementById("led");
const badge = document.getElementById("model-badge");
const btnA = document.getElementById("btn-a");
const btnB = document.getElementById("btn-b");
const btnStart = document.getElementById("btn-start");
const btnSelect = document.getElementById("btn-select");

// --- State ---------------------------------------------------------------

const history = []; // the whole memory of the conversation
let busy = false; // a reply is streaming
let soundOn = true; // START
let autoScroll = true; // SELECT

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- Sound: square-wave blips, no audio assets ---------------------------

let audio = null;

function ensureAudio() {
  if (!audio) audio = new AudioContext();
  if (audio.state === "suspended") audio.resume();
}

function tone(freq, dur = 0.06, delay = 0, vol = 0.04) {
  if (!soundOn || !audio) return;
  const t0 = audio.currentTime + delay;
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = "square";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(vol, t0);
  gain.gain.exponentialRampToValueAtTime(0.0005, t0 + dur);
  osc.connect(gain).connect(audio.destination);
  osc.start(t0);
  osc.stop(t0 + dur);
}

const sfx = {
  send: () => tone(659, 0.05),
  tick: () => tone(988, 0.025, 0, 0.015),
  done: () => {
    tone(523, 0.07);
    tone(784, 0.12, 0.08);
  },
  clear: () => {
    tone(392, 0.06);
    tone(262, 0.1, 0.06);
  },
  error: () => {
    tone(196, 0.15);
    tone(131, 0.25, 0.13);
  },
  blip: () => tone(440, 0.04),
};

// --- Screen ---------------------------------------------------------------

function scrollBottom() {
  if (autoScroll) log.scrollTop = log.scrollHeight;
}

function setLed(state) {
  led.className = `led ${state === "busy" ? "busy" : "on"}`;
}

// Creates a dialogue box. kind: "ai" | "user" | "error".
// AI boxes carry the streaming cursor and the blinking ▼ end marker.
function addBubble(kind, label) {
  const msg = document.createElement("div");
  msg.className = `msg msg-${kind}`;

  const bubble = document.createElement("div");
  bubble.className = `bubble${kind === "error" ? " bubble-error" : ""}`;

  const tag = document.createElement("span");
  tag.className = `tag${kind === "error" ? " tag-error" : ""}${kind === "user" ? " tag-you" : ""}`;
  tag.textContent = label;
  bubble.append(tag);

  const p = document.createElement("p");
  p.className = "text";
  const body = document.createElement("span");
  p.append(body);
  bubble.append(p);

  let cursor = null;
  let vmark = null;
  if (kind === "ai") {
    cursor = document.createElement("span");
    cursor.className = "cursor";
    p.append(cursor);
    vmark = document.createElement("span");
    vmark.className = "vmark";
    vmark.textContent = "▼";
    bubble.append(vmark);
  }

  msg.append(bubble);
  log.append(msg);
  scrollBottom();
  return { body, bubble };
}

function finishTurn(ref) {
  ref.bubble.classList.add("done");
}

// Pokémon-style one-character-at-a-time text for the welcome box.
async function typeInto(ref, text, cps = 40) {
  if (reducedMotion) {
    ref.body.textContent = text;
    return;
  }
  for (let i = 1; i <= text.length; i++) {
    ref.body.textContent = text.slice(0, i);
    if (i % 3 === 0) sfx.tick();
    scrollBottom();
    await sleep(1000 / cps);
  }
}

// --- The conversation ------------------------------------------------------

async function welcome() {
  const w = addBubble("ai", "AI");
  await typeInto(
    w,
    "Welcome, trainer!\nI'm PokéChat. Ask me anything,\nthen press A to send.",
  );
  finishTurn(w);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || busy) return;

  busy = true;
  btnA.disabled = true;
  input.value = "";
  input.focus();
  ensureAudio();
  sfx.send();
  setLed("busy");

  const user = addBubble("user", "YOU");
  user.body.textContent = message;
  const ai = addBubble("ai", "AI");

  let reply = "";
  let lastTick = 0;
  let gotData = false;
  let failed = null;

  try {
    // Cheap reachability probe: with the server down the Gradio client
    // swallows the failure and the stream ends with no events at all.
    let health = null;
    try {
      health = await fetch("/health");
    } catch {
      // connection refused counts as unreachable too
    }
    if (!health || !health.ok) throw new Error("SIGNAL LOST: server is unreachable.");
    const job = client.submit("/chat", [message, history]);
    // A half-dead connection can accept the job and then deliver no
    // events at all. Watch for silence and treat it as a dropped
    // signal instead of waiting forever.
    const SILENCE_MS = 30000;
    const it = job[Symbol.asyncIterator]();
    let wake;
    let lastEvent = Date.now();
    const watcher = setInterval(() => {
      if (Date.now() - lastEvent > SILENCE_MS) {
        wake?.(new Error("SIGNAL LOST: the server stopped responding."));
      }
    }, 1000);
    try {
      while (true) {
        const step = await new Promise((resolve, reject) => {
          wake = reject;
          it.next().then(
            (r) => { wake = null; resolve(r); },
            (err) => { wake = null; reject(err); },
          );
        });
        if (step.done) break;
        lastEvent = Date.now();
        const evt = step.value;
        if (evt.type === "data") {
          gotData = true;
          reply = evt.data[0];
          ai.body.textContent = reply;
          const now = performance.now();
          if (now - lastTick > 70) {
            lastTick = now;
            sfx.tick();
          }
          scrollBottom();
        } else if (evt.type === "error") {
          throw new Error(errorText(evt));
        }
      }
    } finally {
      clearInterval(watcher);
    }
    if (!gotData) throw new Error("SIGNAL LOST: the stream ended without any data.");
  } catch (err) {
    failed = err;
  }

  if (failed) {
    // Keep whatever streamed in, then show the error box.
    if (!ai.body.textContent) ai.body.textContent = "(no signal)";
    finishTurn(ai);
    const errBox = addBubble("error", "CRITICAL");
    errBox.body.textContent = failed.message || String(failed);
    sfx.error();
    // The persistent connection is probably dead - try to re-establish it
    // so the next A press works without a reload.
    try {
      client = await Client.connect(window.location.origin);
    } catch {
      // still down; the next send will probe again
    }
  } else {
    finishTurn(ai);
    sfx.done();
  }

  history.push({ role: "user", content: message });
  if (reply) history.push({ role: "assistant", content: reply });

  busy = false;
  btnA.disabled = false;
  setLed("on");
});

function errorText(evt) {
  const d = evt?.data;
  if (typeof d === "string") return d;
  const inner = d?.error ?? d;
  if (inner && typeof inner === "object") {
    return inner.detail || inner.message || JSON.stringify(inner);
  }
  return "The stream broke.";
}

// --- Buttons ----------------------------------------------------------------

btnB.addEventListener("click", () => {
  if (busy) return; // don't wipe the screen mid-stream
  ensureAudio();
  sfx.clear();
  history.length = 0;
  log.innerHTML = "";
  welcome();
  input.focus();
});

btnStart.addEventListener("click", () => {
  soundOn = !soundOn;
  btnStart.setAttribute("aria-pressed", String(soundOn));
  if (soundOn) {
    ensureAudio();
    sfx.blip();
  }
});

btnSelect.addEventListener("click", () => {
  autoScroll = !autoScroll;
  btnSelect.setAttribute("aria-pressed", String(autoScroll));
  if (autoScroll) scrollBottom();
  ensureAudio();
  sfx.blip();
});

// D-pad scrolls; paging by hand switches autoscroll off, like paging
// through an old game's menu. (Right jumps to the end, which autoscroll
// already does, so it stays on.)
for (const btn of document.querySelectorAll("button.dpad-arm")) {
  btn.addEventListener("click", () => {
    const dir = btn.dataset.dir;
    const behavior = reducedMotion ? "auto" : "smooth";
    if (dir === "up") log.scrollBy({ top: -140, behavior });
    else if (dir === "down") log.scrollBy({ top: 140, behavior });
    else if (dir === "left") log.scrollTo({ top: 0, behavior });
    else if (dir === "right") {
      log.scrollTo({ top: log.scrollHeight, behavior });
      return;
    }
    if (autoScroll) {
      autoScroll = false;
      btnSelect.setAttribute("aria-pressed", "false");
    }
  });
}

// --- Boot -------------------------------------------------------------------

async function loadModel() {
  try {
    const res = await fetch("/health");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.model) badge.textContent = `MODEL: ${String(data.model).toUpperCase()}`;
  } catch {
    badge.textContent = "";
  }
}

setLed("on");
input.focus();
loadModel();
welcome();
