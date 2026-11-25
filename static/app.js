/* Read-It-For-Me — frontend logic.
 *
 * Accessibility contract:
 *  - Every state change is announced in #live-region (aria-live="polite").
 *  - Every error is both shown and spoken, with a next step.
 *  - Model text is inserted with textContent only — never innerHTML.
 *  - Audio plays automatically after analysis; if server TTS fails we
 *    fall back to speechSynthesis, and if the device has no voice for
 *    the language we say so in spoken English and show the text.
 */
"use strict";

/* ------------------------------------------------------------------ */
/* UI strings per language                                             */
/* ------------------------------------------------------------------ */
const STRINGS = {
  ur: {
    title: "میرے لیے پڑھیں",
    tagline: "دوائی، بل یا نوٹس کی تصویر لیں — ہم پڑھ کر سنائیں گے۔",
    takePhoto: "تصویر لیں",
    gallery: "گیلری سے منتخب کریں",
    guidance: "فون کو کاغذ کے تقریباً 20 سینٹی میٹر اوپر رکھیں اور فون کو ہلنے نہ دیں۔",
    welcome: "السلام علیکم! یہ ایپ آپ کے لیے کاغذ پڑھتی ہے۔ تصویر لینے کے لیے بڑا بٹن دبائیں۔ فون کو کاغذ کے تقریباً 20 سینٹی میٹر اوپر رکھیں، اور فون کو ہلنے نہ دیں۔",
    langName: "اردو",
    analyzing: "آپ کی دستاویز پڑھی جا رہی ہے، براہ کرم انتظار کریں…",
    keyFactsHeading: "اہم باتیں",
    showOriginal: "اصل متن دیکھیں",
    pause: "⏸ روکیں",
    play: "▶ سنیں",
    repeat: "🔁 دوبارہ سنیں",
    slower: "🐢 آہستہ",
    faster: "🐇 تیز",
    keyFactsOnly: "⭐ صرف اہم باتیں",
    footer: "آپ کی تصویر محفوظ نہیں کی جاتی۔ دوائی کھانے سے پہلے فارماسسٹ یا ڈاکٹر سے ضرور پوچھیں۔",
    errorGeneric: "معاف کریں، کچھ مسئلہ ہو گیا ہے۔ براہ کرم پھر سے کوشش کریں۔",
    errorNoImage: "تصویر منتخب نہیں ہوئی۔ براہ کرم پھر سے کوشش کریں۔",
    resultReady: "نتیجہ تیار ہے۔",
    retakeReady: "تصویر صاف نہیں آئی۔ نیچے ہدایت سنیں اور پھر سے تصویر لیں۔",
    docTypes: { medicine: "دوائی", bill: "بل", notice: "سرکاری نوٹس", other: "دستاویز", unreadable: "پڑھا نہیں جا سکا" },
  },
  ps: {
    title: "زما لپاره یې ولوله",
    tagline: "د درملو، بل یا نوټس عکس واخلئ — موږ به یې درته ولولو او وایو به یې۔",
    takePhoto: "عکس واخلئ",
    gallery: "له ګالري نه غوره کړئ",
    guidance: "تلیفون د کاغذ نه شاوخوا 20 سانتي متره پورته ونیسئ او تلیفون مه خوځوئ۔",
    welcome: "سلام! دا اپ ستاسو لپاره کاغذ لولي. د عکس اخیستلو لپاره لویه تڼۍ کېکاږئ. تلیفون د کاغذ نه شاوخوا 20 سانتي متره پورته ونیسئ، او تلیفون مه خوځوئ۔",
    langName: "پښتو",
    analyzing: "ستاسو سند لوستل کېږي، مهرباني وکړئ انتظار وکړئ…",
    keyFactsHeading: "مهم ټکي",
    showOriginal: "اصلي متن وګورئ",
    pause: "⏸ ودروئ",
    play: "▶ واورئ",
    repeat: "🔁 بیا واورئ",
    slower: "🐢 ورو",
    faster: "🐇 ګړندی",
    keyFactsOnly: "⭐ یوازې مهم ټکي",
    footer: "ستاسو عکس نه ساتل کېږي. درمل خوړلو نه مخکې له فارماسسټ یا ډاکټر نه پوښتنه وکړئ۔",
    errorGeneric: "بخښنه غواړم، یوه ستونزه رامنځته شوه۔ مهرباني وکړئ بیا هڅه وکړئ۔",
    errorNoImage: "عکس غوره نه شو۔ مهرباني وکړئ بیا هڅه وکړئ۔",
    resultReady: "پایله تیاره ده۔",
    retakeReady: "عکس ښکاره نه دی راغلی۔ لاندې لارښوونه واورئ او بیا عکس واخلئ۔",
    docTypes: { medicine: "درمل", bill: "بل", notice: "رسمي نوټس", other: "سند", unreadable: "ونه لوستل شو" },
  },
  en: {
    title: "Read It For Me",
    tagline: "Take a photo of a medicine, a bill or a notice — we will read it aloud.",
    takePhoto: "Take photo",
    gallery: "Choose from gallery",
    guidance: "Hold the phone about 20 cm above the paper, and keep it steady.",
    welcome: "Welcome! This app reads papers for you. Press the big button to take a photo. Hold the phone about 20 centimetres above the paper, and keep it steady.",
    langName: "English",
    analyzing: "Reading your document, please wait…",
    keyFactsHeading: "Key facts",
    showOriginal: "See the original text",
    pause: "⏸ Pause",
    play: "▶ Play",
    repeat: "🔁 Listen again",
    slower: "🐢 Slower",
    faster: "🐇 Faster",
    keyFactsOnly: "⭐ Key facts only",
    footer: "Your photo is not saved. Please confirm with a pharmacist or doctor before taking any medicine.",
    errorGeneric: "Sorry, something went wrong. Please try again.",
    errorNoImage: "No photo was chosen. Please try again.",
    resultReady: "Your result is ready.",
    retakeReady: "The photo was not clear. Listen to the hint below and take the photo again.",
    docTypes: { medicine: "Medicine", bill: "Bill", notice: "Official notice", other: "Document", unreadable: "Could not be read" },
  },
};
const NO_VOICE_NOTICE = "Sorry, no voice is available for this language on this device. The text is shown on the screen.";
const LANG_VOICE_LOCALES = { ur: ["ur-PK", "ur"], ps: ["ps-AF", "ps"], en: ["en-US", "en-GB", "en"] };

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
let currentLang = "ur";
let lastResult = null;       // last AnalyzeResponse from the server
let lastAudioUrl = null;     // object URL of the current server audio
let toneTimer = null;        // subtle "working" tone while analyzing

const $ = (id) => document.getElementById(id);
const liveRegion = $("live-region");
const player = $("player");

function announce(text) {
  // Clear first so repeated identical messages are re-announced.
  liveRegion.textContent = "";
  window.setTimeout(() => { liveRegion.textContent = text; }, 30);
}

function vibrate(pattern) {
  if (navigator.vibrate) { try { navigator.vibrate(pattern); } catch (e) { /* unsupported */ } }
}

/* ------------------------------------------------------------------ */
/* Speech: server TTS first, speechSynthesis fallback                  */
/* ------------------------------------------------------------------ */
function browserSpeak(text, lang, rate) {
  if (!("speechSynthesis" in window)) { announce(text); return; }
  const locales = LANG_VOICE_LOCALES[lang] || ["en"];
  const voices = window.speechSynthesis.getVoices();
  const voice = voices.find((v) => locales.some((l) => v.lang && v.lang.toLowerCase().startsWith(l.toLowerCase())));
  const utter = new SpeechSynthesisUtterance(text);
  if (voice) {
    utter.voice = voice;
    utter.lang = voice.lang;
  } else {
    // No voice for this language: say so in spoken English (per spec),
    // then still try the requested text with the default voice.
    const notice = new SpeechSynthesisUtterance(NO_VOICE_NOTICE);
    notice.lang = "en-US";
    window.speechSynthesis.speak(notice);
    utter.lang = locales[0];
  }
  utter.rate = rate || 1;
  window.speechSynthesis.speak(utter);
}

async function speak(text, lang) {
  /* Ask the server to synthesize; fall back to the browser on failure. */
  stopTone();
  try {
    const resp = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, lang: lang }),
    });
    if (!resp.ok) { throw new Error("tts " + resp.status); }
    const blob = await resp.blob();
    if (lastAudioUrl) { URL.revokeObjectURL(lastAudioUrl); }
    lastAudioUrl = URL.createObjectURL(blob);
    player.src = lastAudioUrl;
    player.playbackRate = currentRate;
    await player.play();
    $("playback").hidden = false;
    updatePlayPauseLabel();
  } catch (err) {
    browserSpeak(text, lang, currentRate);
    $("playback").hidden = false;
  }
}

/* Subtle looping tone while analyzing (WebAudio, very quiet). */
let audioCtx = null;
function startTone() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const beep = () => {
      if (!audioCtx) { return; }
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.frequency.value = 660;
      gain.gain.value = 0.04;
      osc.connect(gain); gain.connect(audioCtx.destination);
      osc.start(); osc.stop(audioCtx.currentTime + 0.15);
    };
    beep();
    toneTimer = window.setInterval(beep, 2000);
  } catch (e) { /* audio not available — progress text still announces */ }
}
function stopTone() {
  if (toneTimer) { window.clearInterval(toneTimer); toneTimer = null; }
}

/* ------------------------------------------------------------------ */
/* Language switching                                                  */
/* ------------------------------------------------------------------ */
function applyLanguage(lang, speakName) {
  currentLang = lang;
  const s = STRINGS[lang];
  const rtl = lang !== "en";
  document.documentElement.lang = lang === "ps" ? "ps" : lang;
  document.documentElement.dir = rtl ? "rtl" : "ltr";
  document.body.classList.toggle("en", !rtl);
  $("app-title").textContent = s.title;
  $("app-tagline").textContent = s.tagline;
  $("take-photo-text").textContent = s.takePhoto;
  $("gallery-text").textContent = s.gallery;
  $("capture-guidance").textContent = s.guidance;
  $("progress-text").textContent = s.analyzing;
  $("key-facts-heading").textContent = s.keyFactsHeading;
  $("extracted-summary").textContent = s.showOriginal;
  $("btn-repeat").textContent = s.repeat;
  $("btn-slower").textContent = s.slower;
  $("btn-faster").textContent = s.faster;
  $("btn-keyfacts").textContent = s.keyFactsOnly;
  $("footer-note").textContent = s.footer;
  updatePlayPauseLabel();
  document.querySelectorAll(".lang-btn").forEach((b) => {
    b.setAttribute("aria-pressed", b.dataset.lang === lang ? "true" : "false");
  });
  announce(s.langName);
  if (speakName) { browserSpeak(s.langName, lang, 1); }
}

document.querySelectorAll(".lang-btn").forEach((btn) => {
  btn.addEventListener("click", () => applyLanguage(btn.dataset.lang, true));
});

/* ------------------------------------------------------------------ */
/* Image handling: compress client-side, then upload                   */
/* ------------------------------------------------------------------ */
function compressImage(file) {
  /* Canvas resize: longest edge <= 1600 px, JPEG quality 0.8. Falls
     back to the original file if anything in the pipeline fails. */
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const longest = Math.max(img.naturalWidth, img.naturalHeight);
        const scale = longest > 1600 ? 1600 / longest : 1;
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.naturalWidth * scale);
        canvas.height = Math.round(img.naturalHeight * scale);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => {
          URL.revokeObjectURL(url);
          resolve(blob || file);
        }, "image/jpeg", 0.8);
      } catch (e) { URL.revokeObjectURL(url); resolve(file); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

function showError(message) {
  const box = $("error-box");
  box.textContent = message;
  box.hidden = false;
  announce(message);
  browserSpeak(message, currentLang, 1);
  vibrate([80, 40, 80]);
  box.focus && box.focus();
}

function hideError() { $("error-box").hidden = true; }

function renderResult(result) {
  const s = STRINGS[currentLang];
  lastResult = result;
  const card = $("result-card");
  card.hidden = false;
  const rtl = currentLang !== "en";
  card.setAttribute("dir", rtl ? "rtl" : "ltr");

  $("result-doc-type").textContent = s.docTypes[result.doc_type] || s.docTypes.other;

  const expl = $("result-explanation");
  expl.textContent = result.needs_retake ? result.retake_hint : result.plain_explanation;

  // Key facts: built with DOM APIs + textContent (model text is untrusted).
  const dl = $("key-facts");
  dl.replaceChildren();
  (result.key_facts || []).forEach((fact) => {
    const dt = document.createElement("dt");
    dt.textContent = fact.label || "";
    const dd = document.createElement("dd");
    dd.textContent = fact.value || "";
    dl.append(dt, dd);
  });
  $("key-facts-heading").hidden = !(result.key_facts && result.key_facts.length);

  const warnBox = $("result-warnings");
  warnBox.replaceChildren();
  (result.warnings || []).forEach((w) => {
    const p = document.createElement("p");
    p.textContent = w;
    warnBox.appendChild(p);
  });

  const extracted = $("extracted-text");
  extracted.textContent = result.extracted_text || "";
  // Keep the document's own direction for the verbatim text.
  extracted.setAttribute("dir", "auto");
  $("extracted-wrap").hidden = !result.extracted_text;

  announce(result.needs_retake ? s.retakeReady : s.resultReady);
  card.focus();
}

async function handleFile(file) {
  const s = STRINGS[currentLang];
  if (!file) { showError(s.errorNoImage); return; }
  hideError();
  $("result-card").hidden = true;
  $("playback").hidden = true;
  if ("speechSynthesis" in window) { window.speechSynthesis.cancel(); }
  player.pause();
  vibrate(40);

  // State: analyzing (spoken + progress + subtle tone).
  $("progress-wrap").hidden = false;
  announce(s.analyzing);
  browserSpeak(s.analyzing, currentLang, 1);
  startTone();

  try {
    const blob = await compressImage(file);
    const form = new FormData();
    form.append("image", blob, "photo.jpg");
    form.append("lang", currentLang);
    const resp = await fetch("/api/analyze", { method: "POST", body: form });
    if (!resp.ok) {
      let msg = s.errorGeneric;
      try { const data = await resp.json(); if (data && data.message) { msg = data.message; } } catch (e) { /* keep generic */ }
      throw new Error(msg);
    }
    const result = await resp.json();
    stopTone();
    $("progress-wrap").hidden = true;
    renderResult(result);
    vibrate(60);
    // Auto-play the spoken result (retake hint if a retake is needed).
    await speak(result.spoken_script || result.plain_explanation || result.retake_hint, currentLang);
  } catch (err) {
    stopTone();
    $("progress-wrap").hidden = true;
    showError(err && err.message ? err.message : s.errorGeneric);
  }
}

["camera-input", "gallery-input"].forEach((id) => {
  $(id).addEventListener("change", (ev) => {
    const file = ev.target.files && ev.target.files[0];
    handleFile(file);
    ev.target.value = ""; // allow re-choosing the same file
  });
});
// Spoken guidance right before capture: tapping the big button first
// reminds the user how to hold the phone (the file dialog still opens).
$("take-photo-label").addEventListener("click", () => {
  browserSpeak(STRINGS[currentLang].guidance, currentLang, 1);
});

/* ------------------------------------------------------------------ */
/* Playback controls                                                   */
/* ------------------------------------------------------------------ */
let currentRate = 1.0;
function updatePlayPauseLabel() {
  const s = STRINGS[currentLang];
  $("btn-playpause").textContent = player.paused ? s.play : s.pause;
}
player.addEventListener("play", updatePlayPauseLabel);
player.addEventListener("pause", updatePlayPauseLabel);
player.addEventListener("ended", updatePlayPauseLabel);

$("btn-playpause").addEventListener("click", () => {
  if (player.src) {
    if (player.paused) { player.play(); } else { player.pause(); }
  } else if (lastResult) {
    speak(lastResult.spoken_script, currentLang);
  }
});
$("btn-repeat").addEventListener("click", () => {
  if (player.src) { player.currentTime = 0; player.play(); }
  else if (lastResult) { speak(lastResult.spoken_script, currentLang); }
});
$("btn-slower").addEventListener("click", () => {
  currentRate = Math.max(0.75, Math.round((currentRate - 0.25) * 100) / 100);
  player.playbackRate = currentRate;
  announce(String(currentRate) + "x");
});
$("btn-faster").addEventListener("click", () => {
  currentRate = Math.min(1.25, Math.round((currentRate + 0.25) * 100) / 100);
  player.playbackRate = currentRate;
  announce(String(currentRate) + "x");
});
$("btn-keyfacts").addEventListener("click", () => {
  if (!lastResult) { return; }
  const facts = (lastResult.key_facts || [])
    .map((f) => (f.label ? f.label + ": " : "") + (f.value || ""))
    .filter(Boolean)
    .join(". ");
  const text = facts || lastResult.plain_explanation || lastResult.spoken_script;
  if ("speechSynthesis" in window) { window.speechSynthesis.cancel(); }
  player.pause();
  speak(text, currentLang);
});

/* ------------------------------------------------------------------ */
/* Welcome on load (spoken). Browsers may block audio before the first */
/* tap; the welcome is therefore also repeated on first interaction.  */
/* ------------------------------------------------------------------ */
let welcomed = false;
function welcome() {
  if (welcomed) { return; }
  welcomed = true;
  browserSpeak(STRINGS[currentLang].welcome, currentLang, 1);
}
window.addEventListener("load", () => {
  applyLanguage("ur", false);
  if ("speechSynthesis" in window) {
    window.speechSynthesis.getVoices(); // warm up the voice list
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
  }
  welcome();
});
document.addEventListener("pointerdown", welcome, { once: false });
