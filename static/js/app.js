// DecodeRx - Medication Assistant Application

// DOM Elements
const codeForm = document.getElementById('codeForm');
const codeInput = document.getElementById('codeInput');
const chatOutput = document.getElementById('chatOutput');
const resultsContainer = document.getElementById('resultsContainer');
const shareBtn = document.getElementById('shareButton');
const speakResultBtn = document.getElementById('speakResultBtn');
const similarMeds = document.getElementById('similarMeds');
const similarMedsContainer = document.getElementById('similarMedsContainer');
const spinnerOverlay = document.getElementById('spinnerOverlay');
const imageInput = document.getElementById("medImageInput");
const scanButton = document.getElementById("scanButton");
const startVoiceBtn = document.getElementById("startVoiceBtn");

// Get search param from URL
function getSearchParam() {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get("search") || "";
}

// Chunked upload function for large files
async function uploadInChunks(file, chunkSize = 1048576) {
  const totalChunks = Math.ceil(file.size / chunkSize);
  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
    const start = chunkIndex * chunkSize;
    const end = Math.min(start + chunkSize, file.size);
    const chunk = file.slice(start, end);
    const response = await fetch("/api/chunked_upload", {
      method: "POST",
      headers: {
        "X-Filename": file.name,
        "X-Chunk-Index": chunkIndex.toString(),
        "X-Total-Chunks": totalChunks.toString()
      },
      body: chunk
    });
    const result = await response.json();
    if (!result.success) throw new Error(result.error || "Unknown error");
  }
  const finalResponse = await fetch("/api/process_chunked_upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name })
  });
  return await finalResponse.json();
}

// Main search form
codeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  let code = codeInput.value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  const match = code.match(/^([A-Z]+)(\d+)$/);
  if (match) code = `${match[1]}-${match[2]}`;
  if (!code) return;

  // Reset UI
  chatOutput.innerHTML = "";
  similarMeds.innerHTML = "";
  resultsContainer.style.display = "none";
  similarMedsContainer.style.display = "none";
  shareBtn.style.display = "none";
  speakResultBtn.style.display = "none";
  spinnerOverlay.style.display = "flex";

  try {
    const response = await fetch("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code })
    });

    if (!response.ok) {
      const errorData = await response.json();
      chatOutput.innerHTML = `<div class="alert alert-danger">${errorData.error || "Unknown error"}</div>`;
      if (errorData.suggestions) {
        chatOutput.innerHTML += "<ul>" + errorData.suggestions.map(s => `<li>${s.code}</li>`).join("") + "</ul>";
      }
      return;
    }

    const data = await response.json();
    chatOutput.innerHTML = data.summary;
    shareBtn.style.display = "inline-block";
    speakResultBtn.style.display = "inline-block";
    addToHistory({ code, name: data.name || code });

    if (data.similar_meds && data.similar_meds.length > 0) {
      renderSimilarMeds(data.similar_meds);
      similarMedsContainer.style.display = "block";
    } else {
      similarMeds.innerHTML = "<p class='text-muted'>No similar medications found</p>";
    }

  } catch (err) {
    console.error("Search error:", err);
    chatOutput.innerHTML = `<div class="alert alert-danger">${err.message || "An error occurred"}</div>`;
  } finally {
    spinnerOverlay.style.display = "none";
    resultsContainer.style.display = "flex";
    codeInput.value = "";
  }
});

function renderSimilarMeds(medications) {
  similarMeds.innerHTML = "";
  medications.forEach(med => {
    const relationClass = getRelationClass(med.relation);
    const card = document.createElement("div");
    card.className = "card med-card mb-2";
    card.innerHTML = `
      <div class="card-body med-card-body p-2">
        <h6 class="card-title med-card-title">${med.name}</h6>
        <p class="card-text med-card-category">${med.category}</p>
        <div class="d-flex justify-content-between align-items-center">
          <span class="badge relation-badge bg-${relationClass}">${med.relation}</span>
          <button class="btn btn-sm btn-link p-0" onclick="loadMedication('${med.code}')">View</button>
        </div>
      </div>`;
    similarMeds.appendChild(card);
  });
}

function getRelationClass(relation) {
  if (relation === 'Brand name') return 'primary';
  if (relation === 'Generic') return 'success';
  if (relation.includes('Higher')) return 'warning';
  if (relation.includes('Lower')) return 'info';
  if (relation === 'Alternative') return 'secondary';
  return 'light text-dark';
}

function loadMedication(code) {
  codeInput.value = code;
  codeForm.dispatchEvent(new Event("submit"));
}

function addToHistory(medication) {
  let history = JSON.parse(localStorage.getItem('medicationHistory') || '[]');
  if (!history.some(item => item.code === medication.code)) {
    history.unshift(medication);
    history = history.slice(0, 10);
    localStorage.setItem('medicationHistory', JSON.stringify(history));
  }
  updateHistoryUI();
}

function updateHistoryUI() {
  const history = JSON.parse(localStorage.getItem('medicationHistory') || '[]');
  const historyContent = document.getElementById('historyContent');
  if (!historyContent) return;

  if (history.length === 0) {
    historyContent.innerHTML = `<p class="text-muted text-center">No recent medication lookups</p>`;
    return;
  }

  let html = `<div class="list-group">`;
  history.forEach(med => {
    html += `
      <button type="button" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" 
              onclick="loadMedication('${med.code}')" data-bs-dismiss="modal">
        <div>
          <strong>${med.code}</strong>
          <div class="small text-muted">${med.name}</div>
        </div>
        <i class="bi bi-arrow-right text-muted"></i>
      </button>`;
  });
  html += `</div><div class="text-center mt-3">
    <button class="btn btn-sm btn-outline-danger" onclick="clearHistory()">Clear History</button>
  </div>`;
  historyContent.innerHTML = html;
}

// Auto-run search on load if ?search= is in the URL
document.addEventListener("DOMContentLoaded", () => {
  const search = getSearchParam().trim();
  if (search !== "") {
    codeInput.value = search;
    codeForm.dispatchEvent(new Event("submit"));
  }
});

// Scan button
scanButton.addEventListener("click", async () => {
  const file = imageInput.files[0];
  if (!file) {
    alert("Please select an image first");
    return;
  }

  spinnerOverlay.style.display = "flex";
  chatOutput.innerHTML = "";
  similarMeds.innerHTML = "";
  resultsContainer.style.display = "none";
  similarMedsContainer.style.display = "none";
  shareBtn.style.display = "none";
  speakResultBtn.style.display = "none";

  try {
    let data;
    if (file.size > 1048576) {
      data = await uploadInChunks(file);
    } else {
      const formData = new FormData();
      formData.append("image", file);
      const response = await fetch("/api/identify_pill", {
        method: "POST",
        body: formData
      });
      data = await response.json();
    }

    chatOutput.innerHTML = data.summary;
    shareBtn.style.display = "inline-block";
    speakResultBtn.style.display = "inline-block";
    resultsContainer.style.display = "flex";

    addToHistory({ code: data.code, name: data.name });

    if (data.similar_meds && data.similar_meds.length > 0) {
      renderSimilarMeds(data.similar_meds);
      similarMedsContainer.style.display = "block";
    } else {
      similarMeds.innerHTML = "<p class='text-muted'>No similar medications found</p>";
    }

  } catch (err) {
    chatOutput.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    resultsContainer.style.display = "flex";
  } finally {
    imageInput.value = "";
    spinnerOverlay.style.display = "none";
  }
});

// Voice search
let mediaRecorder;
let audioChunks = [];

startVoiceBtn.addEventListener("click", async () => {
  audioChunks = [];

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = event => audioChunks.push(event.data);

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append("audio", audioBlob, "recording.webm");

      spinnerOverlay.style.display = "flex";

      try {
        const response = await fetch("/api/voice_search", {
          method: "POST",
          body: formData
        });

        const result = await response.json();
        spinnerOverlay.style.display = "none";

        if (result.transcript) {
          codeInput.value = result.transcript;
          codeForm.dispatchEvent(new Event("submit"));
        } else {
          alert("Sorry, could not understand audio.");
        }
      } catch (err) {
        spinnerOverlay.style.display = "none";
        alert("Voice processing failed.");
      }
    };

    mediaRecorder.start();
    startVoiceBtn.innerText = "🎧 Listening...";
    setTimeout(() => {
      mediaRecorder.stop();
      startVoiceBtn.innerText = "🎙️ Voice Search";
    }, 4000);

  } catch (err) {
    alert("Microphone access denied.");
  }
});

function clearHistory() {
  localStorage.removeItem('medicationHistory');
  updateHistoryUI();
}

window.loadMedication = loadMedication;
window.clearHistory = clearHistory;
