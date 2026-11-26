"use strict";
const languages = { en: "English", vi: "Vietnamese", ja: "Japanese", ko: "Korean", fr: "French", es: "Spanish", th: "Thai", "zh-cn": "Chinese (Simplified)" };
const $ = id => document.getElementById(id);
const phrase = $("phrase");
const source = $("source");
const target = $("target");
const result = $("result");
let translated = null;
let pending = false;

for (const [code, name] of Object.entries(languages)) {
  source.add(new Option(name, code));
  target.add(new Option(name, code));
}
target.value = "vi";

function resetResult() {
  translated = null;
  result.textContent = "Your translation will appear here.";
  result.classList.add("placeholder");
  $("detected").textContent = "";
  $("copy").disabled = true;
  $("status").textContent = "";
  $("count").textContent = phrase.value.length + " / 1000";
}

for (const field of [phrase, source, target]) field.addEventListener("input", resetResult);
document.querySelectorAll("[data-sample]").forEach(button => button.addEventListener("click", () => {
  if (pending) return;
  phrase.value = button.dataset.sample;
  source.value = "auto";
  resetResult();
  phrase.focus();
}));
$("clear").addEventListener("click", () => { phrase.value = ""; resetResult(); phrase.focus(); });
$("swap").addEventListener("click", () => {
  const from = source.value === "auto" ? translated?.source : source.value;
  if (!from || !(from in languages)) {
    $("status").textContent = "Translate once or select a source language before swapping.";
    return;
  }
  const newPhrase = translated?.text ?? phrase.value;
  if (newPhrase.length > 1000) {
    $("status").textContent = "The translation is too long to use as a new phrase.";
    return;
  }
  source.value = target.value;
  target.value = from;
  phrase.value = newPhrase;
  resetResult();
});
$("copy").addEventListener("click", async () => {
  if (!translated) return;
  try {
    await navigator.clipboard.writeText(translated.text);
    $("status").textContent = "Translation copied.";
  } catch {
    $("status").textContent = "Clipboard unavailable. Select the translation to copy it.";
  }
});
$("translator").addEventListener("submit", async event => {
  event.preventDefault();
  if (pending) return;
  if (!phrase.value.trim()) {
    $("status").textContent = "Enter a phrase to translate.";
    phrase.focus();
    return;
  }
  resetResult();
  pending = true;
  const controls = [phrase, source, target, $("clear"), $("swap"), $("translate")];
  controls.forEach(control => { control.disabled = true; });
  $("translate").textContent = "Translating…";
  $("status").textContent = "Waiting for the translation service.";
  try {
    const response = await fetch("/api/translate", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: phrase.value, source: source.value, target: target.value}),
      signal: AbortSignal.timeout(16000),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Translation failed.");
    translated = data;
    result.textContent = data.text;
    result.classList.remove("placeholder");
    $("detected").textContent = "Source: " + (languages[data.source] ?? data.source);
    $("copy").disabled = false;
    $("status").textContent = "Translation received.";
  } catch (error) {
    $("status").textContent = error.name === "TimeoutError" ? "The request timed out. Try again." : error.message;
  } finally {
    pending = false;
    controls.forEach(control => { control.disabled = false; });
    $("translate").textContent = "Translate phrase";
  }
});
