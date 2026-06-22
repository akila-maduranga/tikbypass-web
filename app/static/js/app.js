// TikBypass Web
(function () {
  'use strict';

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
  const downloadLink = $('downloadLink');
  const resetBtn = $('resetBtn');
  const errorCard = $('errorCard');
  const errorInfo = $('errorInfo');
  const errorLog = $('errorLog');
  const errorResetBtn = $('errorResetBtn');

  let selectedFileObj = null;
  let progressTimer = null;

  // ── File selection ──
  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', () => { if (fileInput.files.length) pickFile(fileInput.files[0]); });

  function pickFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!['.mp4', '.mov', '.avi', '.mkv', '.webm'].includes(ext)) {
      alert('Unsupported format. Use MP4, MOV, AVI, MKV, or WEBM.');
      return;
    }
    selectedFileObj = file;
    selectedFile.textContent = file.name + ' (' + (file.size / 1024 / 1024).toFixed(1) + ' MB)';
    processBtn.disabled = false;
  }

  // ── Options ──
  function getOptions() {
    const parts = ($('resolution').value || '1080x1920').split('x');
    return {
      crf: +$('crf').value || 18,
      preset: $('preset').value,
      fps: +$('fps').value || 30,
      width: +parts[0] || 1080,
      height: +parts[1] || 1920,
      maxrate: $('maxrate').value,
      audio_bitrate: $('audioBitrate').value,
      device: $('device').value,
      ios: $('ios').value,
      no_sharpen: !$('sharpen').checked,
      no_grain: !$('grain').checked,
      no_spoof: !$('spoof').checked,
    };
  }

  // ── UI helpers ──
  function showStatus(msg) {
    statusCard.classList.remove('hidden');
    resultCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    progressBar.style.width = '10%';
    progressBar.style.background = '';
    statusText.textContent = msg;
    statusText.style.color = '';
    logOutput.classList.add('hidden');
    logOutput.textContent = '';
  }

  function showError(msg, log) {
    statusCard.classList.add('hidden');
    resultCard.classList.add('hidden');
    errorCard.classList.remove('hidden');
    errorInfo.textContent = msg;
    errorLog.textContent = log || '';
    errorLog.style.display = log ? 'block' : 'none';
  }

  function showResult(data) {
    statusCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    resultCard.classList.remove('hidden');
    resultInfo.textContent = data.filename + ' — ' + data.size_mb + ' MB';
    // Direct link — browser handles download via Content-Disposition
    downloadLink.href = '/api/download/' + data.job_id;
    downloadLink.setAttribute('download', data.filename);
    if (data.log) {
      logOutput.textContent = data.log;
      logOutput.classList.remove('hidden');
      statusCard.classList.remove('hidden');
    }
  }

  // ── Process ──
  processBtn.addEventListener('click', async () => {
    if (!selectedFileObj) return;
    processBtn.disabled = true;
    showStatus('Uploading…');

    const fd = new FormData();
    fd.append('file', selectedFileObj);
    for (const [k, v] of Object.entries(getOptions())) fd.append(k, v);

    progressTimer = setInterval(() => {
      const w = parseFloat(progressBar.style.width) || 10;
      if (w < 85) {
        progressBar.style.width = Math.min(w + Math.random() * 5, 90) + '%';
        if (w > 35) statusText.textContent = 'Processing… this may take a few minutes.';
      }
    }, 1500);

    try {
      const resp = await fetch('/api/upload', { method: 'POST', body: fd });
      clearInterval(progressTimer);
      const data = await resp.json();

      if (!resp.ok) {
        showError(data.error || 'Processing failed', data.log || data.detail || '');
        return;
      }

      progressBar.style.width = '100%';
      statusText.textContent = 'Complete!';
      showResult(data);
    } catch (err) {
      clearInterval(progressTimer);
      showError('Network error: ' + err.message, '');
    } finally {
      processBtn.disabled = false;
    }
  });

  // ── Reset ──
  function reset() {
    selectedFileObj = null;
    selectedFile.textContent = '';
    processBtn.disabled = true;
    statusCard.classList.add('hidden');
    resultCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    progressBar.style.width = '0%';
    fileInput.value = '';
    downloadLink.href = '#';
  }
  resetBtn.addEventListener('click', reset);
  errorResetBtn.addEventListener('click', reset);

})();
