// TikBypass Web — Frontend

(function () {
  'use strict';

  // ── State ──
  const state = {
    file: null,
    jobId: null,
    processing: false
  };

  // ── DOM refs ──
  const $ = id => document.getElementById(id);
  const dropzone = $('dropzone');
  const fileInput = $('fileInput');
  const selectedFile = $('selectedFile');
  const processBtn = $('processBtn');
  const statusCard = $('statusCard');
  const progressBar = $('progressBar');
  const statusText = $('statusText');
  const logOutput = $('logOutput');
  const resultCard = $('resultCard');
  const resultInfo = $('resultInfo');
  const downloadBtn = $('downloadBtn');
  const resetBtn = $('resetBtn');

  // ── File selection ──
  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length) selectFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) selectFile(fileInput.files[0]);
  });

  function selectFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!['.mp4', '.mov', '.avi', '.mkv', '.webm'].includes(ext)) {
      alert('Unsupported format. Use MP4, MOV, AVI, MKV, or WEBM.');
      return;
    }
    state.file = file;
    selectedFile.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
    processBtn.disabled = false;
  }

  // ── Read options ──
  function readOptions() {
    const [w, h] = ($('resolution').value || '1080x1920').split('x').map(Number);
    return {
      crf: parseInt($('crf').value) || 18,
      preset: $('preset').value || 'medium',
      fps: parseInt($('fps').value) || 30,
      width: w || 1080,
      height: h || 1920,
      maxrate: $('maxrate').value || '8M',
      audio_bitrate: $('audioBitrate').value || '192k',
      device: $('device').value || 'iPhone15,2',
      ios: $('ios').value || '16.4',
      inflate_loops: parseInt($('inflateLoops').value) || 5,
      no_sharpen: !$('sharpen').checked,
      no_grain: !$('grain').checked,
      no_spoof: !$('spoof').checked,
      no_inflate: !$('inflate').checked
    };
  }

  // ── Simulate progress ──
  function startProgress() {
    let pct = 10;
    return setInterval(() => {
      if (pct < 85) {
        pct += Math.random() * 5;
        progressBar.style.width = Math.min(pct, 90) + '%';
        if (pct > 40) statusText.textContent = 'Processing… this may take a few minutes.';
      }
    }, 1500);
  }

  // ── Show status ──
  function showStatus(msg) {
    statusCard.classList.remove('hidden', 'error');
    resultCard.classList.add('hidden');
    progressBar.style.width = '10%';
    progressBar.style.background = '';
    statusText.textContent = msg;
    statusText.style.color = '';
    logOutput.classList.add('hidden');
    logOutput.textContent = '';
    logOutput.className = 'log hidden';
  }

  function showError(msg, log) {
    statusCard.classList.add('error');
    statusText.textContent = msg;
    statusText.style.color = 'var(--danger)';
    progressBar.style.width = '100%';
    progressBar.style.background = 'var(--danger)';
    if (log) {
      logOutput.textContent = log;
      logOutput.className = 'log error';
      logOutput.classList.remove('hidden');
    }
  }

  function showResult(data) {
    statusCard.classList.add('hidden');
    resultCard.classList.remove('hidden');
    resultInfo.textContent = `${data.filename} — ${data.size_mb} MB`;
    downloadBtn.onclick = null; // clear previous handler
    downloadBtn.onclick = async () => {
      downloadBtn.textContent = '⬇ Downloading…';
      downloadBtn.disabled = true;
      try {
        const resp = await fetch('/api/download/' + state.jobId);
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.error || 'File not found (may have expired)');
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = data.filename || 'tikbypass_output.mp4';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
        downloadBtn.textContent = '⬇ Download Processed Video';
        downloadBtn.disabled = false;
      } catch (err) {
        alert('Download failed: ' + err.message);
        downloadBtn.textContent = '⬇ Download Processed Video';
        downloadBtn.disabled = false;
      }
    };
    // Also show log if available
    if (data.log) {
      logOutput.textContent = data.log;
      logOutput.className = 'log';
      logOutput.classList.remove('hidden');
    }
  }

  // ── Process ──
  processBtn.addEventListener('click', async () => {
    if (!state.file || state.processing) return;
    state.processing = true;
    processBtn.disabled = true;

    showStatus('Uploading…');

    const formData = new FormData();
    formData.append('file', state.file);
    const opts = readOptions();
    for (const [k, v] of Object.entries(opts)) formData.append(k, v);

    const timer = startProgress();

    try {
      const resp = await fetch('/api/upload', { method: 'POST', body: formData });
      clearInterval(timer);

      const data = await resp.json();

      if (!resp.ok) {
        showError(data.error || 'Processing failed', data.log || data.detail || '');
        return;
      }

      state.jobId = data.job_id;
      progressBar.style.width = '100%';
      statusText.textContent = 'Complete!';
      showResult(data);

    } catch (err) {
      clearInterval(timer);
      showError('Network error: ' + err.message, '');
    } finally {
      state.processing = false;
      processBtn.disabled = false;
    }
  });

  // ── Reset ──
  resetBtn.addEventListener('click', () => {
    state.file = null;
    state.jobId = null;
    state.processing = false;
    selectedFile.textContent = '';
    processBtn.disabled = true;
    statusCard.classList.add('hidden');
    resultCard.classList.add('hidden');
    progressBar.style.width = '0%';
    progressBar.style.background = '';
    statusText.textContent = '';
    statusText.style.color = '';
    logOutput.textContent = '';
    logOutput.classList.add('hidden');
    logOutput.className = 'log hidden';
    statusCard.classList.remove('error');
    fileInput.value = '';
    downloadBtn.onclick = null;
  });

})();
