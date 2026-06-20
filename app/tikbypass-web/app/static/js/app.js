// TikBypass Web — Frontend Logic

const state = {
    file: null,
    jobId: null,
    processing: false,
};

const dom = {
    dropTarget: document.getElementById('dropTarget'),
    fileInput: document.getElementById('fileInput'),
    fileName: document.getElementById('fileName'),
    processBtn: document.getElementById('processBtn'),
    statusPanel: document.getElementById('statusPanel'),
    progressFill: document.getElementById('progressFill'),
    statusText: document.getElementById('statusText'),
    logOutput: document.getElementById('logOutput'),
    resultPanel: document.getElementById('resultPanel'),
    resultInfo: document.getElementById('resultInfo'),
    downloadLink: document.getElementById('downloadLink'),
    resetBtn: document.getElementById('resetBtn'),
};

// ── File selection ────────────────────────────────────────────────

dom.dropTarget.addEventListener('click', () => dom.fileInput.click());

dom.dropTarget.addEventListener('dragover', (e) => {
    e.preventDefault();
    dom.dropTarget.classList.add('dragover');
});

dom.dropTarget.addEventListener('dragleave', () => {
    dom.dropTarget.classList.remove('dragover');
});

dom.dropTarget.addEventListener('drop', (e) => {
    e.preventDefault();
    dom.dropTarget.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) setFile(files[0]);
});

dom.fileInput.addEventListener('change', () => {
    if (dom.fileInput.files.length > 0) setFile(dom.fileInput.files[0]);
});

function setFile(file) {
    const validExts = ['.mp4', '.mov', '.avi', '.mkv', '.webm'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!validExts.includes(ext)) {
        alert(`Unsupported format: ${ext}. Use MP4, MOV, AVI, MKV, or WEBM.`);
        return;
    }
    state.file = file;
    dom.fileName.textContent = `📁 ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
    dom.processBtn.disabled = false;
}

// ── Options helpers ───────────────────────────────────────────────

function getOptions() {
    const [w, h] = document.getElementById('optRes').value.split('x').map(Number);
    return {
        crf: parseInt(document.getElementById('optCrf').value),
        preset: document.getElementById('optPreset').value,
        fps: parseInt(document.getElementById('optFps').value),
        width: w || 1080,
        height: h || 1920,
        maxrate: document.getElementById('optMaxrate').value,
        audio_bitrate: document.getElementById('optAudio').value,
        device: document.getElementById('optDevice').value,
        ios: document.getElementById('optIos').value,
        inflate_loops: parseInt(document.getElementById('optLoops').value),
        no_sharpen: !document.getElementById('optSharpen').checked,
        no_grain: !document.getElementById('optGrain').checked,
        no_faststart: !document.getElementById('optFaststart').checked,
        no_spoof: !document.getElementById('optSpoof').checked,
        no_inflate: !document.getElementById('optInflate').checked,
    };
}

// ── Processing ────────────────────────────────────────────────────

dom.processBtn.addEventListener('click', async () => {
    if (!state.file || state.processing) return;
    state.processing = true;

    // UI: show status
    dom.processBtn.disabled = true;
    dom.statusPanel.classList.remove('hidden');
    dom.resultPanel.classList.add('hidden');
    dom.progressFill.style.width = '10%';
    dom.statusText.textContent = 'Uploading...';
    dom.logOutput.classList.add('hidden');
    dom.logOutput.textContent = '';

    const formData = new FormData();
    formData.append('file', state.file);
    const opts = getOptions();
    for (const [k, v] of Object.entries(opts)) {
        formData.append(k, v);
    }

    try {
        // Simulate progress during upload + processing
        const progressInterval = simulateProgress();

        const resp = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });

        clearInterval(progressInterval);

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || `Server error: ${resp.status}`);
        }

        const data = await resp.json();
        state.jobId = data.job_id;

        dom.progressFill.style.width = '100%';
        dom.statusText.textContent = 'Complete!';
        dom.logOutput.textContent = data.log || '';
        if (data.log) dom.logOutput.classList.remove('hidden');

        // Show result
        dom.statusPanel.classList.add('hidden');
        dom.resultPanel.classList.remove('hidden');
        dom.resultInfo.textContent = `${data.filename} — ${data.size_mb} MB`;
        dom.downloadLink.href = `/api/download/${data.jobId}`;
        dom.downloadLink.download = data.filename;

    } catch (err) {
        dom.progressFill.style.width = '100%';
        dom.progressFill.style.background = 'var(--danger)';
        dom.statusText.textContent = `Error: ${err.message}`;
        dom.statusText.style.color = 'var(--danger)';

        // Try to show server log
        try {
            const errData = JSON.parse(err.message);
            if (errData.log) {
                dom.logOutput.textContent = errData.log;
                dom.logOutput.classList.remove('hidden');
            }
        } catch {}
    } finally {
        state.processing = false;
        dom.processBtn.disabled = false;
    }
});

function simulateProgress() {
    let pct = 10;
    return setInterval(() => {
        if (pct < 85) {
            pct += Math.random() * 5;
            dom.progressFill.style.width = `${Math.min(pct, 90)}%`;
            if (pct > 30) dom.statusText.textContent = 'Processing (this may take a few minutes)...';
        }
    }, 2000);
}

// ── Reset ─────────────────────────────────────────────────────────

dom.resetBtn.addEventListener('click', () => {
    state.file = null;
    state.jobId = null;
    state.processing = false;
    dom.fileName.textContent = '';
    dom.processBtn.disabled = true;
    dom.statusPanel.classList.add('hidden');
    dom.resultPanel.classList.add('hidden');
    dom.progressFill.style.width = '0%';
    dom.progressFill.style.background = '';
    dom.statusText.style.color = '';
    dom.fileInput.value = '';
});
