const form = document.getElementById("search-form");
const urlInput = document.getElementById("url-input");
const searchBtn = document.getElementById("search-btn");
const errorMsg = document.getElementById("error-msg");
const result = document.getElementById("result");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");

let currentUrl = "";
let splitPollTimer = null;

const tierLabel = { high: "Tinggi", medium: "Sedang", low: "Rendah", unknown: "-" };

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("video-panel").classList.toggle("hidden", tab !== "video");
    document.getElementById("audio-panel").classList.toggle("hidden", tab !== "audio");
    document.getElementById("split-panel").classList.toggle("hidden", tab !== "split");
  });
});

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.classList.remove("hidden");
}

function clearError() {
  errorMsg.classList.add("hidden");
  errorMsg.textContent = "";
}

function formatDuration(sec) {
  if (!sec && sec !== 0) return "-";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  const parts = [];
  if (h) parts.push(String(h).padStart(2, "0"));
  parts.push(String(m).padStart(2, "0"));
  parts.push(String(s).padStart(2, "0"));
  return parts.join(":");
}

function tierBadge(tier) {
  return `<span class="tier-badge tier-${tier}">${tierLabel[tier] || tier}</span>`;
}

function renderVideoFormats(formats) {
  const body = document.getElementById("video-body");
  body.innerHTML = "";
  formats.forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${tierBadge(f.quality_tier)}</td>
      <td>${f.resolution}${f.has_audio ? "" : " *"}</td>
      <td>${(f.ext || "").toUpperCase()}</td>
      <td>${f.fps || "-"}</td>
      <td>${f.bitrate_kbps ? f.bitrate_kbps + " kbps" : "-"}</td>
      <td>${f.filesize_human || "~"}</td>
      <td><button class="dl-btn">Download</button></td>
    `;
    tr.querySelector(".dl-btn").addEventListener("click", () =>
      startDownload(f.format_id, "video", null, `Video ${f.resolution}`)
    );
    body.appendChild(tr);
  });
}

function renderAudioFormats(formats) {
  const body = document.getElementById("audio-body");
  body.innerHTML = "";
  formats.forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${tierBadge(f.quality_tier)}</td>
      <td>${(f.ext || "").toUpperCase()}</td>
      <td>${f.bitrate_kbps ? f.bitrate_kbps + " kbps" : "-"}</td>
      <td>${f.filesize_human || "~"}</td>
      <td><button class="dl-btn">Download MP3</button></td>
    `;
    tr.querySelector(".dl-btn").addEventListener("click", () =>
      startDownload(f.format_id, "audio", "mp3", `Audio ${f.bitrate_kbps || ""}kbps`)
    );
    body.appendChild(tr);
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  const url = urlInput.value.trim();
  if (!url) return;
  currentUrl = url;

  searchBtn.disabled = true;
  searchBtn.textContent = "Mencari...";
  result.classList.add("hidden");

  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Gagal mengambil info video");

    document.getElementById("thumb").src = data.thumbnail || "";
    document.getElementById("video-title").textContent = data.title || "-";
    document.getElementById("video-sub").textContent = `${data.uploader || "-"} • ${formatDuration(data.duration)}`;

    renderVideoFormats(data.video_formats || []);
    renderAudioFormats(data.audio_formats || []);
    resetSplitPanel();

    result.classList.remove("hidden");
  } catch (err) {
    showError(err.message);
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = "Cari";
  }
});

async function startDownload(formatId, mode, ext, label) {
  loadingOverlay.classList.remove("hidden");
  loadingText.textContent = `Mengunduh ${label}... (bisa memakan waktu untuk kualitas tinggi)`;

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl, format_id: formatId, mode, ext }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Gagal mendownload file");
    }

    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : "download";

    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (err) {
    showError(err.message);
  } finally {
    loadingOverlay.classList.add("hidden");
  }
}

const splitStartBtn = document.getElementById("split-start-btn");
const splitIntro = document.getElementById("split-intro");
const splitProgress = document.getElementById("split-progress");
const splitProgressText = document.getElementById("split-progress-text");
const splitError = document.getElementById("split-error");
const splitResults = document.getElementById("split-results");
const stemList = document.getElementById("stem-list");
const splitDownloadAll = document.getElementById("split-download-all");
const splitEngineSelect = document.getElementById("split-engine-select");
const splitQualitySelect = document.getElementById("split-quality-select");

function resetSplitPanel() {
  if (splitPollTimer) {
    clearInterval(splitPollTimer);
    splitPollTimer = null;
  }
  splitIntro.classList.remove("hidden");
  splitStartBtn.disabled = false;
  splitStartBtn.textContent = "Mulai Pisahkan Instrumen";
  splitProgress.classList.add("hidden");
  splitError.classList.add("hidden");
  splitResults.classList.add("hidden");
  stemList.innerHTML = "";
}

function renderStems(jobId, stems) {
  stemList.innerHTML = "";
  stems.forEach((stem) => {
    const card = document.createElement("div");
    card.className = "stem-card";
    card.innerHTML = `
      <span class="stem-card-title">${stem.label}</span>
      <span class="stem-card-size">${stem.size_human || ""}</span>
      <a class="dl-btn" href="/api/split/${jobId}/download/${stem.key}" download>Download</a>
    `;
    stemList.appendChild(card);
  });
  splitDownloadAll.href = `/api/split/${jobId}/download-all`;
}

async function pollSplitJob(jobId) {
  try {
    const res = await fetch(`/api/split/${jobId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Gagal memeriksa status");

    if (data.status === "done") {
      clearInterval(splitPollTimer);
      splitPollTimer = null;
      splitProgress.classList.add("hidden");
      renderStems(jobId, data.stems || []);
      splitResults.classList.remove("hidden");
    } else if (data.status === "error") {
      clearInterval(splitPollTimer);
      splitPollTimer = null;
      splitProgress.classList.add("hidden");
      splitIntro.classList.remove("hidden");
      splitStartBtn.disabled = false;
      splitStartBtn.textContent = "Coba Lagi";
      splitError.textContent = data.message || "Gagal memisahkan instrumen";
      splitError.classList.remove("hidden");
    } else {
      splitProgressText.textContent = data.message || "Memproses...";
    }
  } catch (err) {
    clearInterval(splitPollTimer);
    splitPollTimer = null;
    splitProgress.classList.add("hidden");
    splitIntro.classList.remove("hidden");
    splitStartBtn.disabled = false;
    splitStartBtn.textContent = "Coba Lagi";
    splitError.textContent = err.message;
    splitError.classList.remove("hidden");
  }
}

splitStartBtn.addEventListener("click", async () => {
  if (!currentUrl) return;

  splitError.classList.add("hidden");
  splitResults.classList.add("hidden");
  splitIntro.classList.add("hidden");
  splitProgress.classList.remove("hidden");
  splitProgressText.textContent = "Mengirim permintaan...";
  splitStartBtn.disabled = true;

  try {
    const res = await fetch("/api/split", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: currentUrl,
        engine: splitEngineSelect.value,
        quality: splitQualitySelect.value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Gagal memulai proses pemisahan");

    splitPollTimer = setInterval(() => pollSplitJob(data.job_id), 3000);
    pollSplitJob(data.job_id);
  } catch (err) {
    splitProgress.classList.add("hidden");
    splitIntro.classList.remove("hidden");
    splitStartBtn.disabled = false;
    splitError.textContent = err.message;
    splitError.classList.remove("hidden");
  }
});
