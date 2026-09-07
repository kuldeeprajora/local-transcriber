const $ = (selector) => document.querySelector(selector);
const state = { system: null, file: null, job: null, poller: null, transcript: [] };

function formatTime(value, millis = false) {
  const seconds = Math.max(0, Number(value) || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const base = [hours, minutes, secs].map(n => String(n).padStart(2, "0")).join(":");
  return millis ? `${base}.${String(Math.floor((seconds % 1) * 1000)).padStart(3, "0")}` : base;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

async function loadSystem() {
  try {
    state.system = await api("/api/system");
    const machine = state.system.machine;
    $("#chip").textContent = machine.device === "cuda" ? machine.gpu_name : machine.chip;
    $("#memory").textContent = machine.device === "cuda"
      ? `${machine.gpu_memory_gb} GB VRAM · ${machine.memory_gb} GB RAM`
      : `${machine.memory_gb} GB ${machine.backend === "mlx" ? "Unified Memory" : "RAM"}`;
    $("#backend").textContent = machine.backend === "mlx"
      ? "Apple MLX"
      : machine.device === "cuda" ? "NVIDIA CUDA" : "Faster Whisper CPU";
    $("#profile").textContent = title(machine.recommended_profile);
    $("#ffmpeg").textContent = machine.ffmpeg_available ? "Ready" : "Missing";
    const dependenciesReady = state.system.dependencies?.ready;
    $("#systemState").textContent = machine.supported && machine.ffmpeg_available && dependenciesReady ? "Ready" : "Needs setup";
    updateModel();
    if (!machine.supported || !machine.ffmpeg_available || !dependenciesReady) {
      const dependency = state.system.dependencies?.required?.replace("_", "-") || "transcription backend";
      $("#formError").textContent = !machine.supported
        ? "Use macOS, Windows, or Linux."
        : !machine.ffmpeg_available
          ? "FFmpeg is missing. Install FFmpeg and restart the tool."
          : `${dependency} is missing. Install the project requirements.`;
    }
  } catch (error) {
    $("#systemState").textContent = "Unavailable";
    $("#formError").textContent = error.message;
  }
}

function title(value) { return String(value || "").replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()); }
function quality() { return document.querySelector('input[name="quality"]:checked').value; }
function updateModel() {
  const selection = state.system?.selections?.[quality()];
  $("#modelName").textContent = selection ? `Whisper ${selection.model}` : "No compatible model";
}

async function selectFile(file) {
  if (!file) return;
  state.file = file;
  $("#dropzone").classList.add("hidden");
  $("#fileSummary").classList.remove("hidden");
  $("#fileName").textContent = file.name;
  $("#fileMeta").textContent = `${formatBytes(file.size)} · Ready to analyze`;
  $("#transcribeButton").disabled = !(state.system?.machine?.supported && state.system?.machine?.ffmpeg_available && state.system?.dependencies?.ready);
  $("#formError").textContent = "";
}

function clearFile() {
  state.file = null; state.job = null; $("#fileInput").value = "";
  $("#dropzone").classList.remove("hidden"); $("#fileSummary").classList.add("hidden");
  $("#transcribeButton").disabled = true;
}

async function createAndStart() {
  if (!state.file) return;
  const button = $("#transcribeButton");
  button.disabled = true; button.querySelector("span").textContent = "Analyzing media…";
  try {
    const form = new FormData();
    form.append("file", state.file); form.append("language", $("#language").value); form.append("quality", quality());
    state.job = await api("/api/jobs", { method: "POST", body: form });
    state.job = await api(`/api/jobs/${state.job.id}/start`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: $("#language").value, quality: quality() })
    });
    showProgress(); poll();
  } catch (error) {
    $("#formError").textContent = error.message; button.disabled = false;
  } finally { button.querySelector("span").textContent = "Transcribe locally"; }
}

function showProgress() {
  $("#setupView").classList.add("hidden"); $("#transcriptView").classList.add("hidden"); $("#progressView").classList.remove("hidden");
  renderJob();
}

function renderJob() {
  const job = state.job; if (!job) return;
  $("#jobFilename").textContent = job.filename;
  $("#stageDetail").textContent = job.stage_detail;
  $("#jobDuration").textContent = formatTime(job.media?.duration);
  $("#jobModel").textContent = job.model?.model || "—";
  $("#processed").textContent = formatTime(job.processed_seconds);
  $("#percent").textContent = `${Math.round(job.progress)}%`;
  $("#progressBar").style.width = `${job.progress}%`;
  $("#chunkCount").textContent = `${job.completed_chunks} / ${job.total_chunks}`;
  $("#progressLabel").textContent = job.status === "COMPLETED" ? "Transcription complete" : title(job.status);
  $("#chunkList").innerHTML = (job.chunks || []).map(c => `<span class="chunk ${c.status}" title="Chunk ${c.chunk_id}: ${c.status}">${c.status === "completed" ? "✓" : c.status === "processing" ? "▶" : String(c.chunk_id).padStart(2, "0")}</span>`).join("");
  $("#failureBox").classList.toggle("hidden", job.status !== "FAILED");
  $("#failureMessage").textContent = job.error || "The job stopped. Completed chunks are safe.";
  $("#completeActions").classList.toggle("hidden", job.status !== "COMPLETED");
  const accurateModel = state.system?.selections?.accurate?.model;
  $("#retranscribe").classList.toggle("hidden", job.status !== "COMPLETED" || job.model?.model === accurateModel || job.model?.model === "large-v3");
  if (job.model_adjustment) {
    $("#adjustment").classList.remove("hidden");
    $("#adjustment").innerHTML = `<strong>Model adjusted automatically</strong><br>${job.model_adjustment.from} → ${job.model_adjustment.to}<br>${job.model_adjustment.reason}`;
  }
  if (job.quality_report?.warnings?.length) {
    $("#qualityWarning").classList.remove("hidden");
    $("#qualityWarning").innerHTML = `<strong>Quality review recommended</strong><br>${job.quality_report.warnings.map(escapeHtml).join("<br>")}`;
  } else {
    $("#qualityWarning").classList.add("hidden");
  }
  document.querySelectorAll(".exports a").forEach(a => a.href = `/api/jobs/${job.id}/exports/${a.dataset.kind}`);
}

async function poll() {
  clearTimeout(state.poller);
  if (!state.job) return;
  try { state.job = await api(`/api/jobs/${state.job.id}`); renderJob(); } catch (error) { $("#stageDetail").textContent = error.message; }
  if (!["COMPLETED", "FAILED"].includes(state.job?.status)) state.poller = setTimeout(poll, 1200);
}

async function retry() {
  try {
    state.job = await api(`/api/jobs/${state.job.id}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    renderJob(); poll();
  } catch (error) { $("#failureMessage").textContent = error.message; }
}

async function retranscribe() {
  const button = $("#retranscribe");
  button.disabled = true; button.textContent = "Starting Accurate transcription…";
  try {
    state.job = await api(`/api/jobs/${state.job.id}/retranscribe`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: state.job.language, quality: "accurate" })
    });
    renderJob(); poll();
  } catch (error) {
    $("#stageDetail").textContent = error.message;
    button.disabled = false; button.textContent = "Re-transcribe in Accurate mode";
  }
}

async function markMusic() {
  const button = $("#markMusic");
  button.disabled = true; button.textContent = "Marking music sections…";
  try {
    state.job = await api(`/api/jobs/${state.job.id}/mark-music`, { method: "POST" });
    button.textContent = state.job.music_segments?.length ? `Music markers added (${state.job.music_segments.length})` : "No music sections detected";
    renderJob();
  } catch (error) {
    $("#stageDetail").textContent = error.message;
    button.disabled = false; button.textContent = "Mark music / song sections";
  }
}

async function openTranscript() {
  try {
    const transcript = await api(`/api/jobs/${state.job.id}/transcript`);
    state.transcript = transcript.segments || [];
    $("#transcriptTitle").textContent = state.job.filename;
    $("#progressView").classList.add("hidden"); $("#transcriptView").classList.remove("hidden"); renderTranscript();
  } catch (error) { $("#stageDetail").textContent = error.message; }
}

function renderTranscript() {
  const query = $("#search").value.trim().toLowerCase();
  const segments = state.transcript.filter(s => !query || s.text.toLowerCase().includes(query));
  $("#segments").innerHTML = segments.length ? segments.map(s => `<article class="segment ${s.kind === "music" ? "music-segment" : ""}"><time>${formatTime(s.start, true)}</time><p>${escapeHtml(s.text)}</p></article>`).join("") : '<p class="error-text">No matching transcript text.</p>';
}
function escapeHtml(text) { const node = document.createElement("div"); node.textContent = text; return node.innerHTML; }

async function restoreRecentJob() {
  try {
    const jobs = await api("/api/jobs");
    const recent = jobs.find(job => !["CREATED"].includes(job.status));
    if (recent) { state.job = recent; showProgress(); if (!["COMPLETED", "FAILED"].includes(recent.status)) poll(); }
  } catch (_) {}
}

$("#fileInput").addEventListener("change", e => selectFile(e.target.files[0]));
$("#removeFile").addEventListener("click", clearFile);
document.querySelectorAll('input[name="quality"]').forEach(input => input.addEventListener("change", updateModel));
$("#transcribeButton").addEventListener("click", createAndStart);
$("#retryButton").addEventListener("click", retry);
$("#retranscribe").addEventListener("click", retranscribe);
$("#markMusic").addEventListener("click", markMusic);
$("#viewTranscript").addEventListener("click", openTranscript);
$("#backToJob").addEventListener("click", showProgress);
$("#search").addEventListener("input", renderTranscript);
$("#newJob").addEventListener("click", () => { clearTimeout(state.poller); state.job = null; clearFile(); $("#progressView").classList.add("hidden"); $("#setupView").classList.remove("hidden"); });
const dropzone = $("#dropzone");
["dragenter", "dragover"].forEach(name => dropzone.addEventListener(name, e => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach(name => dropzone.addEventListener(name, e => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", e => selectFile(e.dataTransfer.files[0]));

loadSystem().then(restoreRecentJob);
