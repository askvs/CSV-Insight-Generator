/**
 * CSV & Multi-Dataset Insight Agent — Frontend Application Logic
 * Implements real-time SSE streaming, Plotly chart injection,
 * dataset profiling telemetry, and interactive data exploration.
 */

(() => {
  'use strict';

  // ────────────────────────────────────────────────────────────
  // State & Configuration
  // ────────────────────────────────────────────────────────────
  const urlParams = new URLSearchParams(window.location.search);
  let sessionId = urlParams.get('session_id') || localStorage.getItem('csv_insight_session_id');
  if (!sessionId) {
    sessionId = (typeof crypto !== 'undefined' && crypto.randomUUID) 
      ? crypto.randomUUID() 
      : 'sess_' + Math.random().toString(36).substring(2, 15);
  }
  localStorage.setItem('csv_insight_session_id', sessionId);

  let currentDatasets = [];
  let activeTableName = '';
  let currentTablePage = 1;
  const tablePageSize = 25;
  let tableSearchDebounceTimer = null;
  let isAgentAnalyzing = false;
  let activeStreamReader = null;  // Track active SSE reader to abort on new upload

  // Configure Marked.js options
  if (typeof marked !== 'undefined') {
    marked.setOptions({
      gfm: true,
      breaks: true,
      highlight: function (code, lang) {
        if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
          try {
            return hljs.highlight(code, { language: lang }).value;
          } catch (e) {}
        }
        return code;
      }
    });
  }

  // ────────────────────────────────────────────────────────────
  // DOM Elements
  // ────────────────────────────────────────────────────────────
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const uploadProgressBar = document.getElementById('uploadProgressBar');
  const progressFill = document.getElementById('progressFill');
  const progressLabel = document.getElementById('progressLabel');
  const uploadedCompactBar = document.getElementById('uploadedCompactBar');
  const uploadedFilesList = document.getElementById('uploadedFilesList');
  const btnCompactAdd = document.getElementById('btnCompactAdd');

  const metricsCard = document.getElementById('metricsCard');
  const metricsGrid = document.getElementById('metricsGrid');
  const tableCountTag = document.getElementById('tableCountTag');
  const relationalKeysBox = document.getElementById('relationalKeysBox');
  const relationalKeysList = document.getElementById('relationalKeysList');

  const tablePreviewCard = document.getElementById('tablePreviewCard');
  const tableTabList = document.getElementById('tableTabList');
  const tableSearchInput = document.getElementById('tableSearchInput');
  const dataGridHead = document.getElementById('dataGridHead');
  const dataGridBody = document.getElementById('dataGridBody');
  const paginationInfo = document.getElementById('paginationInfo');
  const pageCurrentIndicator = document.getElementById('pageCurrentIndicator');
  const btnPagePrev = document.getElementById('btnPagePrev');
  const btnPageNext = document.getElementById('btnPageNext');

  const chatTimeline = document.getElementById('chatTimeline');
  const welcomeHero = document.getElementById('welcomeHero');
  const chatForm = document.getElementById('chatForm');
  const questionInput = document.getElementById('questionInput');
  const btnSend = document.getElementById('btnSend');

  const btnExportPdf = document.getElementById('btnExportPdf');
  const btnExportNb = document.getElementById('btnExportNb');
  const btnResetSession = document.getElementById('btnResetSession');
  const toastContainer = document.getElementById('toastContainer');
  const agentConnectionStatus = document.getElementById('agentConnectionStatus');

  // ────────────────────────────────────────────────────────────
  // Agent Working State UI Controller
  // ────────────────────────────────────────────────────────────
  function setAgentWorkingUI(isWorking) {
    isAgentAnalyzing = isWorking;

    if (isWorking) {
      btnSend.disabled = false;
      btnSend.classList.add('is-loading');
      btnSend.setAttribute('title', 'Stop execution');
      btnSend.innerHTML = '<span class="btn-stop-icon" title="Stop execution"></span>';
      if (agentConnectionStatus) {
        agentConnectionStatus.classList.add('is-busy');
        const pillText = agentConnectionStatus.querySelector('.pill-text');
        if (pillText) pillText.textContent = 'Agent Computing...';
      }
    } else {
      btnSend.classList.remove('is-loading');
      btnSend.setAttribute('title', 'Send question (Enter)');
      btnSend.innerHTML = `
        <svg class="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="22" y1="2" x2="11" y2="13"/>
          <polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      `;
      if (agentConnectionStatus) {
        agentConnectionStatus.classList.remove('is-busy');
        const pillText = agentConnectionStatus.querySelector('.pill-text');
        if (pillText) pillText.textContent = 'Groq AI Active';
      }
    }
  }

  // ────────────────────────────────────────────────────────────
  // Toast Notifications
  // ────────────────────────────────────────────────────────────
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';

    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3500);
  }

  // ────────────────────────────────────────────────────────────
  // HTTP Fetch Wrapper with Session ID Header
  // ────────────────────────────────────────────────────────────
  async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    options.headers['X-Session-ID'] = sessionId;
    const res = await fetch(url, options);
    return res;
  }

  // ────────────────────────────────────────────────────────────
  // Initialize Session on Load
  // ────────────────────────────────────────────────────────────
  async function initSession() {
    setAgentWorkingUI(false);
    try {
      const res = await apiFetch('/api/session');
      if (!res.ok) return;
      const data = await res.json();

      if (data.loaded && data.tables && data.tables.length > 0) {
        currentDatasets = data.tables;
        renderUploadedFileList(data.tables);
        renderTelemetry(data.profile, data.tables, data.is_multi_dataset);
        renderTableTabs(data.tables);
        loadTableData(data.tables[0].name, 1);
        enableExportButtons(true);
      } else {
        renderUploadedFileList([]);
      }

      if (data.chat_log && data.chat_log.length > 0) {
        welcomeHero.style.display = 'none';
        data.chat_log.forEach(entry => {
          if (entry.role === 'user') {
            appendUserMessage(entry.content, entry.timestamp);
          } else if (entry.role === 'agent' || entry.role === 'assistant') {
            appendAgentMessage({
              answer: entry.content,
              charts: entry.charts || [],
              code: entry.code || [],
              timestamp: entry.timestamp
            });
          }
        });
        enableExportButtons(true);
      }
    } catch (err) {
      console.warn('Session init warning:', err);
    } finally {
      setAgentWorkingUI(false);
    }
  }

  // ────────────────────────────────────────────────────────────
  // Dataset Ingestion (Drag & Drop, Compact Bar, File Picker)
  // ────────────────────────────────────────────────────────────
  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      handleFileUpload(files);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleFileUpload(fileInput.files);
    }
  });

  dropZone.addEventListener('click', (e) => {
    if (e.target !== fileInput) {
      fileInput.click();
    }
  });

  if (btnCompactAdd) {
    btnCompactAdd.addEventListener('click', () => {
      fileInput.click();
    });
  }

  function renderUploadedFileList(tables) {
    if (!tables || tables.length === 0) {
      // Show full drop zone, hide compact bar
      if (dropZone) dropZone.style.display = '';
      if (uploadedCompactBar) uploadedCompactBar.style.display = 'none';
      if (uploadedFilesList) uploadedFilesList.innerHTML = '';
      return;
    }

    // Hide large drop zone, show minimized uploaded file area
    if (dropZone) dropZone.style.display = 'none';
    if (uploadedCompactBar) uploadedCompactBar.style.display = 'flex';
    if (!uploadedFilesList) return;

    uploadedFilesList.innerHTML = '';
    tables.forEach(t => {
      const item = document.createElement('div');
      item.className = 'uploaded-file-item';

      const rowLabel = `${(t.rows || 0).toLocaleString()} rows`;
      const memLabel = t.memory_mb ? `${t.memory_mb} MB` : '';
      const metaText = [rowLabel, memLabel].filter(Boolean).join(' • ');

      item.innerHTML = `
        <div class="uploaded-file-left" title="${t.name}">
          <svg class="uploaded-file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          <span class="uploaded-file-name">${t.name}</span>
          <span class="uploaded-file-meta">${metaText}</span>
        </div>
        <div class="uploaded-file-actions">
          <button type="button" class="btn-file-delete" data-filename="${t.name}" title="Remove ${t.name}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              <line x1="10" y1="11" x2="10" y2="17"/>
              <line x1="14" y1="11" x2="14" y2="17"/>
            </svg>
          </button>
        </div>
      `;

      const deleteBtn = item.querySelector('.btn-file-delete');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          handleFileDelete(t.name);
        });
      }

      uploadedFilesList.appendChild(item);
    });
  }

  async function handleFileDelete(tableName) {
    if (!confirm(`Are you sure you want to remove "${tableName}"?`)) {
      return;
    }

    try {
      const res = await apiFetch(`/api/dataset/${encodeURIComponent(tableName)}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to delete dataset.');
      }

      showToast(`Removed "${tableName}"`, 'info');
      currentDatasets = data.tables || [];

      if (currentDatasets.length > 0) {
        renderUploadedFileList(currentDatasets);
        renderTelemetry(data.profile, currentDatasets, data.is_multi_dataset);
        renderTableTabs(currentDatasets);
        loadTableData(currentDatasets[0].name, 1);
      } else {
        // Zero datasets remaining: restore dropzone, hide tables & metrics
        renderUploadedFileList([]);
        metricsCard.style.display = 'none';
        tablePreviewCard.style.display = 'none';
        enableExportButtons(false);
      }
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function handleFileUpload(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    // If agent is currently analyzing, abort the active SSE stream first
    if (isAgentAnalyzing && activeStreamReader) {
      try {
        await activeStreamReader.cancel();
      } catch (e) {
        // Reader may already be closed
      }
      activeStreamReader = null;
      setAgentWorkingUI(false);
      showToast('Previous analysis aborted — loading new data...', 'info');
    }

    uploadProgressBar.style.display = 'flex';
    progressLabel.textContent = `Ingesting & profiling ${files.length} dataset(s)...`;

    try {
      const res = await apiFetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to upload datasets.');
      }

      showToast(`Successfully loaded ${data.tables.length} dataset(s)!`, 'success');

      currentDatasets = data.tables;
      renderUploadedFileList(data.tables);
      renderTelemetry(data.profile, data.tables, data.is_multi_dataset);
      renderTableTabs(data.tables);
      loadTableData(data.tables[0].name, 1);
      enableExportButtons(true);

      // Clear stale chat messages from previous dataset analysis
      chatTimeline.innerHTML = '';
      chatTimeline.appendChild(welcomeHero);
      welcomeHero.style.display = 'flex';

    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      uploadProgressBar.style.display = 'none';
      fileInput.value = '';
    }
  }

  // ────────────────────────────────────────────────────────────
  // Render Telemetry & Metric Cards
  // ────────────────────────────────────────────────────────────
  function renderTelemetry(profile, tables, isMulti) {
    metricsCard.style.display = 'flex';
    tableCountTag.textContent = `${tables.length} Table${tables.length !== 1 ? 's' : ''}`;

    let html = '';
    if (isMulti) {
      const s = profile.summary || {};
      const totalRows = s.total_rows || tables.reduce((acc, t) => acc + t.rows, 0);
      const totalCols = tables.reduce((acc, t) => acc + t.columns, 0);
      const memMb = s.total_memory_mb || tables.reduce((acc, t) => acc + t.memory_mb, 0);

      html = `
        <div class="metric-tile">
          <span class="metric-val">${tables.length}</span>
          <span class="metric-lbl">Tables Loaded</span>
        </div>
        <div class="metric-tile">
          <span class="metric-val">${totalRows.toLocaleString()}</span>
          <span class="metric-lbl">Total Records</span>
        </div>
        <div class="metric-tile">
          <span class="metric-val">${totalCols}</span>
          <span class="metric-lbl">Total Features</span>
        </div>
        <div class="metric-tile">
          <span class="metric-val">${memMb.toFixed(1)} MB</span>
          <span class="metric-lbl">Memory Usage</span>
        </div>
      `;
    } else {
      const t = tables[0] || {};
      const shape = profile.shape || {};
      const rows = shape.rows || t.rows || 0;
      const cols = shape.columns || t.columns || 0;
      const mem = profile.memory_mb || t.memory_mb || 0;
      const missing = profile.missing_values?.total_missing_percentage ?? 0;

      html = `
        <div class="metric-tile">
          <span class="metric-val">${rows.toLocaleString()}</span>
          <span class="metric-lbl">Records</span>
        </div>
        <div class="metric-tile">
          <span class="metric-val">${cols}</span>
          <span class="metric-lbl">Features</span>
        </div>
        <div class="metric-tile">
          <span class="metric-val">${typeof mem === 'number' ? mem.toFixed(1) : mem} MB</span>
          <span class="metric-lbl">Memory</span>
        </div>
        <div class="metric-tile">
          <span class="metric-val">${typeof missing === 'number' ? missing.toFixed(1) : missing}%</span>
          <span class="metric-lbl">Missing Values</span>
        </div>
      `;
    }

    metricsGrid.innerHTML = html;

    // Relational join keys
    const commonKeys = profile.common_keys_for_joins || [];
    if (commonKeys.length > 0) {
      relationalKeysBox.style.display = 'flex';
      relationalKeysList.innerHTML = commonKeys.map(k => {
        const tbls = k.tables ? k.tables.join(', ') : '';
        return `<span class="rk-badge" title="Shared across ${tbls}">🔗 ${k.column}</span>`;
      }).join('');
    } else {
      relationalKeysBox.style.display = 'none';
    }
  }

  // ────────────────────────────────────────────────────────────
  // Render Table Tabs & Explorer
  // ────────────────────────────────────────────────────────────
  function renderTableTabs(tables) {
    tablePreviewCard.style.display = 'flex';
    tableTabList.innerHTML = '';

    tables.forEach((t, idx) => {
      const btn = document.createElement('button');
      btn.className = `table-tab-btn ${idx === 0 ? 'active' : ''}`;
      btn.textContent = `${t.name} (${t.rows.toLocaleString()})`;
      btn.addEventListener('click', () => {
        document.querySelectorAll('.table-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeTableName = t.name;
        currentTablePage = 1;
        loadTableData(t.name, 1);
      });
      tableTabList.appendChild(btn);
    });

    activeTableName = tables[0].name;
  }

  async function loadTableData(tableName, page = 1, search = '') {
    if (!tableName) return;
    try {
      const query = new URLSearchParams({
        page: page.toString(),
        page_size: tablePageSize.toString(),
        search: search
      });

      const res = await apiFetch(`/api/table/${encodeURIComponent(tableName)}?${query.toString()}`);
      if (!res.ok) return;

      const data = await res.json();
      currentTablePage = data.page;

      // Update headers
      dataGridHead.innerHTML = `<tr>${data.columns.map(col => `<th>${escapeHtml(col)}</th>`).join('')}</tr>`;

      // Update rows
      if (data.rows && data.rows.length > 0) {
        dataGridBody.innerHTML = data.rows.map(row => {
          return `<tr>${data.columns.map(col => `<td title="${escapeHtml(String(row[col] ?? ''))}">${escapeHtml(String(row[col] ?? ''))}</td>`).join('')}</tr>`;
        }).join('');
      } else {
        dataGridBody.innerHTML = `<tr><td colspan="${data.columns.length}" style="text-align:center; padding:1.5rem; color:var(--text-muted);">No matching records found.</td></tr>`;
      }

      // Update pagination
      const start = data.total_filtered > 0 ? (data.page - 1) * data.page_size + 1 : 0;
      const end = Math.min(data.page * data.page_size, data.total_filtered);
      paginationInfo.textContent = `Showing ${start}-${end} of ${data.total_filtered.toLocaleString()}`;
      pageCurrentIndicator.textContent = data.page;

      btnPagePrev.disabled = (data.page <= 1);
      btnPageNext.disabled = (data.page >= data.total_pages);

    } catch (err) {
      console.warn('Failed to load table rows:', err);
    }
  }

  tableSearchInput.addEventListener('input', (e) => {
    clearTimeout(tableSearchDebounceTimer);
    tableSearchDebounceTimer = setTimeout(() => {
      loadTableData(activeTableName, 1, e.target.value.trim());
    }, 300);
  });

  btnPagePrev.addEventListener('click', () => {
    if (currentTablePage > 1) {
      loadTableData(activeTableName, currentTablePage - 1, tableSearchInput.value.trim());
    }
  });

  btnPageNext.addEventListener('click', () => {
    loadTableData(activeTableName, currentTablePage + 1, tableSearchInput.value.trim());
  });

  // ────────────────────────────────────────────────────────────
  // Chat & Real-Time SSE Stream
  // ────────────────────────────────────────────────────────────
  // Auto-expand textarea
  questionInput.addEventListener('input', () => {
    questionInput.style.height = 'auto';
    questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
  });

  // Keyboard shortcut: Enter sends, Shift+Enter new line
  questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event('submit'));
    }
  });

  // Starter prompt chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) {
        questionInput.value = prompt;
        chatForm.dispatchEvent(new Event('submit'));
      }
    });
  });

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // If already analyzing, clicking the button triggers a stop
    if (isAgentAnalyzing) {
      try {
        if (activeStreamReader) {
          await activeStreamReader.cancel();
          activeStreamReader = null;
        }
        await apiFetch('/api/chat/stop', { method: 'POST' });
        showToast('Execution stopped.', 'info');
      } catch (stopErr) {
        console.warn('Error sending stop signal:', stopErr);
      }
      setAgentWorkingUI(false);
      return;
    }

    const question = questionInput.value.trim();
    if (!question) return;

    if (!currentDatasets || currentDatasets.length === 0) {
      showToast('Please upload a dataset (.csv, .xlsx, .json) before asking questions.', 'error');
      return;
    }

    // Hide welcome hero
    welcomeHero.style.display = 'none';
    questionInput.value = '';
    questionInput.style.height = 'auto';

    // Append user message
    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    appendUserMessage(question, nowStr);

    // Create Agent message container with live execution stepper
    const agentMsgCard = createAgentStreamingCard(nowStr);
    chatTimeline.appendChild(agentMsgCard.container);
    scrollToBottom();

    setAgentWorkingUI(true);

    try {
      const response = await apiFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error || `Server responded with status ${response.status}`);
      }

      const reader = response.body.getReader();
      activeStreamReader = reader;  // Store reference so uploads can abort this stream
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep trailing incomplete chunk

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith(':')) continue; // keepalive or empty

          if (trimmed.startsWith('data:')) {
            const jsonStr = trimmed.substring(5).trim();
            try {
              const eventData = JSON.parse(jsonStr);
              handleStreamEvent(eventData, agentMsgCard);
              if (eventData.type === 'final_answer' || eventData.type === 'done' || eventData.type === 'error') {
                setAgentWorkingUI(false);
              }
              if (eventData.type === 'done') {
                break;
              }
            } catch (jsonErr) {
              console.warn('Error parsing SSE event JSON:', jsonErr, jsonStr);
            }
          }
        }
      }

    } catch (err) {
      const isAbort = err.name === 'AbortError' || err.message?.toLowerCase().includes('cancel') || err.message?.toLowerCase().includes('stop');
      if (isAbort) {
        agentMsgCard.updateStatus('⏹️ Analysis stopped by user.', 'info');
      } else {
        agentMsgCard.updateStatus(`❌ ${err.message}`, 'error');
        showToast(err.message, 'error');
      }
    } finally {
      activeStreamReader = null;
      setAgentWorkingUI(false);
      agentMsgCard.finishStreaming();
      enableExportButtons(true);
      scrollToBottom();
    }
  });

  // ────────────────────────────────────────────────────────────
  // Message UI Builders
  // ────────────────────────────────────────────────────────────
  function appendUserMessage(text, timestamp) {
    const card = document.createElement('div');
    card.className = 'chat-msg user';
    card.innerHTML = `
      <div class="msg-body">
        <div class="msg-bubble">${escapeHtml(text)}</div>
        <span class="msg-meta">You • ${timestamp}</span>
      </div>
      <div class="msg-avatar">👤</div>
    `;
    chatTimeline.appendChild(card);
  }

  function createAgentStreamingCard(timestamp) {
    const card = document.createElement('div');
    card.className = 'chat-msg agent is-working';

    card.innerHTML = `
      <div class="msg-avatar">
        <span class="avatar-icon">📊</span>
      </div>
      <div class="msg-body" style="width: 100%;">
        <div class="msg-bubble">
          <!-- Live Reasoning / Sandbox Stepper -->
          <div class="live-stepper is-working" id="stepper">
            <div class="stepper-scanline"></div>
            <div class="stepper-header" id="stepperHeader" style="cursor: pointer;">
              <div class="stepper-header-left">
                <span class="stepper-beacon">
                  <span class="beacon-pulse"></span>
                  <span class="beacon-core"></span>
                </span>
                <span id="stepperTitle" class="stepper-title-text">⚡ Initializing data intelligence runtime...</span>
              </div>
              <div class="stepper-controls" style="display: flex; align-items: center; gap: 8px;">
                <span class="stepper-live-badge" id="stepperLiveBadge">RUNNING</span>
                <div class="stepper-spinner" id="stepperSpinner">
                  <span class="dot dot-1"></span><span class="dot dot-2"></span><span class="dot dot-3"></span>
                </div>
                <span class="stepper-toggle-icon" id="stepperToggleIcon" style="display:none; font-size: 0.72rem; color: var(--text-muted);">▼</span>
              </div>
            </div>
            <div class="stepper-log" id="stepperLog"></div>
          </div>

          <!-- Active Thinking Skeleton / Shimmer (visible while analyzing) -->
          <div class="agent-thinking-wave" id="agentThinkingWave">
            <div class="thinking-header">
              <span class="thinking-sparkle">✨</span>
              <span class="thinking-text" id="thinkingStatusText">Autonomous agent synthesizing data & formulating executive report...</span>
            </div>
            <div class="thinking-skeleton-lines">
              <div class="skeleton-shimmer-bar bar-1"></div>
              <div class="skeleton-shimmer-bar bar-2"></div>
              <div class="skeleton-shimmer-bar bar-3"></div>
            </div>
          </div>

          <!-- Final Markdown Content -->
          <div class="markdown-content" id="reportContent" style="display: none;"></div>

          <!-- Charts Container -->
          <div id="chartsWrapper"></div>

          <!-- Code Audit Trail Accordion -->
          <div id="codeAuditWrapper"></div>
        </div>
        <span class="msg-meta">CSV Insight Agent • Groq Inference • ${timestamp}</span>
      </div>
    `;

    const stepper = card.querySelector('#stepper');
    const stepperHeader = card.querySelector('#stepperHeader');
    const stepperTitle = card.querySelector('#stepperTitle');
    const stepperSpinner = card.querySelector('#stepperSpinner');
    const stepperLiveBadge = card.querySelector('#stepperLiveBadge');
    const stepperToggleIcon = card.querySelector('#stepperToggleIcon');
    const stepperLog = card.querySelector('#stepperLog');
    const agentThinkingWave = card.querySelector('#agentThinkingWave');
    const thinkingStatusText = card.querySelector('#thinkingStatusText');
    const reportContent = card.querySelector('#reportContent');
    const chartsWrapper = card.querySelector('#chartsWrapper');
    const codeAuditWrapper = card.querySelector('#codeAuditWrapper');

    let logCount = 0;
    stepperHeader.addEventListener('click', () => {
      if (stepperToggleIcon.style.display !== 'none') {
        const isHidden = stepperLog.style.display === 'none';
        stepperLog.style.display = isHidden ? 'flex' : 'none';
        stepperToggleIcon.textContent = isHidden ? '▲' : '▼';
      }
    });

    return {
      container: card,
      addLogEntry: (icon, text) => {
        logCount++;
        // Clear active highlighting from prior steps
        stepperLog.querySelectorAll('.step-entry').forEach(el => el.classList.remove('is-active-step'));

        const item = document.createElement('div');
        item.className = 'step-entry step-entry-animate is-active-step';
        item.innerHTML = `<span class="step-icon">${icon}</span><span>${escapeHtml(text)}</span>`;
        stepperLog.appendChild(item);
        scrollToBottom();
      },
      updateStatus: (titleText, type = 'info') => {
        stepperTitle.textContent = titleText;
        if (thinkingStatusText && type !== 'error') {
          thinkingStatusText.textContent = titleText;
        }
      },
      collapseStepper: () => {
        card.classList.remove('is-working');
        stepper.classList.remove('is-working');
        if (agentThinkingWave) agentThinkingWave.style.display = 'none';
        if (stepperSpinner) stepperSpinner.style.display = 'none';
        if (stepperLiveBadge) {
          stepperLiveBadge.className = 'stepper-badge-done';
          stepperLiveBadge.textContent = 'DONE';
        }
        stepperToggleIcon.style.display = 'inline';
        stepperTitle.textContent = `✅ Analysis complete (${logCount} execution steps) • Click to expand`;
        stepperLog.style.display = 'none';
      },
      finishStreaming: () => {
        card.classList.remove('is-working');
        stepper.classList.remove('is-working');
        if (agentThinkingWave) agentThinkingWave.style.display = 'none';
        if (stepperSpinner) stepperSpinner.style.display = 'none';
        if (stepperLiveBadge) {
          stepperLiveBadge.className = 'stepper-badge-done';
          stepperLiveBadge.textContent = 'DONE';
        }
        if (reportContent.style.display === 'block') {
          stepperToggleIcon.style.display = 'inline';
          stepperTitle.textContent = `✅ Analysis complete (${logCount} execution steps) • Click to expand`;
          stepperLog.style.display = 'none';
        } else {
          stepperTitle.textContent = '✅ Analysis & computation complete';
        }
      },
      renderReport: (markdownText) => {
        if (agentThinkingWave) agentThinkingWave.style.display = 'none';
        reportContent.style.display = 'block';
        reportContent.classList.add('report-animated');
        try {
          if (typeof marked !== 'undefined' && markdownText) {
            reportContent.innerHTML = marked.parse(markdownText);
          } else {
            reportContent.textContent = markdownText || 'Analysis completed with findings.';
          }
        } catch (mErr) {
          console.error('Markdown parse error:', mErr);
          reportContent.textContent = markdownText || '';
        }
      },
      renderCharts: (charts) => {
        if (!charts || charts.length === 0) return;
        charts.forEach((c, idx) => {
          try {
            if (!c || c.type === 'unknown') return;

            const chartBox = document.createElement('div');
            chartBox.className = 'chart-container';

            const chartHeader = document.createElement('div');
            chartHeader.className = 'chart-header';
            const chartTitle = (c.figure && c.figure.layout && c.figure.layout.title && (c.figure.layout.title.text || c.figure.layout.title))
              ? String(c.figure.layout.title.text || c.figure.layout.title)
              : `Visual Breakdown ${idx + 1}`;
            chartHeader.innerHTML = `<span>📊 ${escapeHtml(chartTitle)}</span><span class="badge-tag">Empirical Visualization</span>`;
            chartBox.appendChild(chartHeader);

            const hasPlotlyFigure = c.type === 'plotly' && c.figure && typeof Plotly !== 'undefined';
            const imgData = c.data || c.image;

            if (hasPlotlyFigure) {
              const plotDiv = document.createElement('div');
              plotDiv.className = 'plotly-embed';
              const chartDivId = `chart_${Date.now()}_${idx}_${Math.floor(Math.random() * 100000)}`;
              plotDiv.id = chartDivId;
              chartBox.appendChild(plotDiv);
              chartsWrapper.appendChild(chartBox);

              cleanPlotlyFigureClient(c.figure);

              const figure = c.figure;
              figure.layout = figure.layout || {};
              figure.layout.paper_bgcolor = figure.layout.paper_bgcolor || '#12141C';
              figure.layout.plot_bgcolor = figure.layout.plot_bgcolor || '#12141C';
              figure.layout.font = figure.layout.font || { family: 'Inter, sans-serif', color: '#9CA3AF', size: 11 };
              figure.layout.margin = figure.layout.margin || { l: 50, r: 25, t: 40, b: 50 };

              Plotly.newPlot(plotDiv, figure.data, figure.layout, {
                responsive: true,
                displayModeBar: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['sendDataToCloud', 'hoverClosestCartesian', 'hoverCompareCartesian'],
              }).catch(err => {
                console.warn('Plotly render error, switching to static image fallback:', err);
                if (imgData) {
                  plotDiv.remove();
                  const img = document.createElement('img');
                  img.src = imgData;
                  img.className = 'chart-static-img';
                  chartBox.appendChild(img);
                }
              });
            } else if (imgData) {
              const img = document.createElement('img');
              img.src = imgData;
              img.className = 'chart-static-img';
              chartBox.appendChild(img);
              chartsWrapper.appendChild(chartBox);
            }
          } catch (chartErr) {
            console.error('Error rendering chart element:', chartErr);
            if (c && (c.data || c.image)) {
              try {
                const fallbackBox = document.createElement('div');
                fallbackBox.className = 'chart-container';
                const img = document.createElement('img');
                img.src = c.data || c.image;
                img.className = 'chart-static-img';
                fallbackBox.appendChild(img);
                chartsWrapper.appendChild(fallbackBox);
              } catch (e) {}
            }
          }
        });
      },
      renderCodeAudit: (codeSnippets) => {
        if (!codeSnippets || codeSnippets.length === 0) return;
        try {
          const details = document.createElement('details');
          details.className = 'code-audit-accordion';
          
          let snippetsHtml = codeSnippets.map((snip, idx) => {
            let highlighted = escapeHtml(snip);
            if (typeof hljs !== 'undefined') {
              try {
                highlighted = hljs.highlight(snip, { language: 'python' }).value;
              } catch (e) {}
            }
            return `
              <div class="code-snippet-box">
                <button class="btn-copy-code" data-code="${encodeURIComponent(snip)}">Copy</button>
                <pre><code class="language-python">${highlighted}</code></pre>
              </div>
            `;
          }).join('');

          details.innerHTML = `
            <summary>
              <span>⚙️ Executed Python Scripts (${codeSnippets.length} step${codeSnippets.length !== 1 ? 's' : ''})</span>
              <span style="font-size:0.68rem; color:var(--text-muted);">Empirical Sandbox Audit</span>
            </summary>
            ${snippetsHtml}
          `;

          details.querySelectorAll('.btn-copy-code').forEach(btn => {
            btn.addEventListener('click', (e) => {
              e.stopPropagation();
              const code = decodeURIComponent(btn.getAttribute('data-code'));
              navigator.clipboard.writeText(code).then(() => {
                btn.textContent = 'Copied!';
                setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
              });
            });
          });

          codeAuditWrapper.appendChild(details);
        } catch (codeErr) {
          console.error('Error rendering code audit:', codeErr);
        }
      }
    };
  }

  function handleStreamEvent(data, uiCard) {
    if (!data) return;

    if (data.type === 'status') {
      uiCard.updateStatus(data.message);
      if (workingBannerText) workingBannerText.textContent = data.message;
      if (data.stage === 'reasoning') {
        uiCard.addLogEntry('🧠', data.message);
      } else if (data.stage === 'executing') {
        uiCard.addLogEntry('⚙️', data.message);
      } else if (data.stage === 'synthesis') {
        uiCard.addLogEntry('📝', data.message);
      }
    } else if (data.type === 'code') {
      uiCard.addLogEntry('💻', `Generated Step ${data.step} Python script`);
      if (workingBannerText) workingBannerText.textContent = `Generated Step ${data.step} Python code...`;
    } else if (data.type === 'execution') {
      if (data.success) {
        let note = `Step ${data.step} execution successful.`;
        if (data.is_plotly) note += ' (Captured interactive Plotly chart)';
        else if (data.has_chart) note += ' (Captured visualization figure)';
        uiCard.addLogEntry('✅', note);
        if (workingBannerText) workingBannerText.textContent = `Step ${data.step} executed successfully`;
      } else {
        uiCard.addLogEntry('⚠️', `Step ${data.step} error encountered, auto-correcting: ${data.error || 'Syntax error'}`);
        if (workingBannerText) workingBannerText.textContent = `Self-healing error in Step ${data.step}...`;
      }
    } else if (data.type === 'final_answer') {
      setAgentWorkingUI(false);
      uiCard.collapseStepper();
      uiCard.renderReport(data.answer);
      if (data.charts && data.charts.length > 0) {
        uiCard.renderCharts(data.charts);
      }
      if (data.code && data.code.length > 0) {
        uiCard.renderCodeAudit(data.code);
      }
      scrollToBottom();
    } else if (data.type === 'done') {
      setAgentWorkingUI(false);
      uiCard.finishStreaming();
    } else if (data.type === 'error') {
      setAgentWorkingUI(false);
      uiCard.updateStatus(`❌ ${data.error}`, 'error');
      uiCard.addLogEntry('❌', data.error);
      uiCard.finishStreaming();
    }
  }

  function cleanPlotlyFigureClient(figure) {
    if (!figure || !figure.data || !Array.isArray(figure.data)) return;
    figure.data.forEach(trace => {
      if (!trace || typeof trace !== 'object') return;
      ['x', 'y', 'z', 'values', 'labels'].forEach(axis => {
        const val = trace[axis];
        if (val && typeof val === 'object' && !Array.isArray(val) && val.bdata && val.dtype) {
          try {
            const binaryStr = atob(val.bdata);
            const len = binaryStr.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
              bytes[i] = binaryStr.charCodeAt(i);
            }
            let typedArray;
            const dt = String(val.dtype).toLowerCase();
            if (dt === 'i1') typedArray = new Int8Array(bytes.buffer);
            else if (dt === 'u1') typedArray = new Uint8Array(bytes.buffer);
            else if (dt === 'i2') typedArray = new Int16Array(bytes.buffer);
            else if (dt === 'u2') typedArray = new Uint16Array(bytes.buffer);
            else if (dt === 'i4') typedArray = new Int32Array(bytes.buffer);
            else if (dt === 'u4') typedArray = new Uint32Array(bytes.buffer);
            else if (dt === 'f4') typedArray = new Float32Array(bytes.buffer);
            else if (dt === 'f8') typedArray = new Float64Array(bytes.buffer);
            else typedArray = bytes;

            trace[axis] = Array.from(typedArray);
          } catch (e) {
            console.warn('Could not decode bdata on client:', e);
          }
        }
      });
    });
  }

  function appendAgentMessage(entry) {
    const card = createAgentStreamingCard(entry.timestamp || 'Just now');
    card.container.classList.remove('is-working');
    card.finishStreaming();
    chatTimeline.appendChild(card.container);
    card.renderReport(entry.answer);
    if (entry.charts && entry.charts.length > 0) {
      card.renderCharts(entry.charts);
    }
    if (entry.code && entry.code.length > 0) {
      card.renderCodeAudit(entry.code);
    }
  }

  function scrollToBottom() {
    chatTimeline.scrollTop = chatTimeline.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function enableExportButtons(enabled) {
    btnExportPdf.disabled = !enabled;
    btnExportNb.disabled = !enabled;
  }

  // ────────────────────────────────────────────────────────────
  // Deliverables Export Handlers
  // ────────────────────────────────────────────────────────────
  btnExportPdf.addEventListener('click', async () => {
    btnExportPdf.disabled = true;
    showToast('Generating formal 5-section executive PDF report...', 'info');

    try {
      // 1. Verify export readiness with backend
      const checkRes = await apiFetch(`/api/export/check?type=pdf`);
      const checkData = await checkRes.json().catch(() => ({}));
      if (!checkRes.ok || !checkData.ok) {
        throw new Error(checkData.error || 'No completed intelligence analysis or dataset available to generate a PDF report.');
      }

      // 2. Direct browser download via native HTTP attachment
      // Navigating or triggering a download with Content-Disposition: attachment
      // ensures Chrome reads the HTTP header directly, preserving the .pdf extension
      // and Adobe/PDF file associations without premature blob revocation issues.
      const downloadUrl = `/api/export/pdf?session_id=${encodeURIComponent(sessionId)}&t=${Date.now()}`;
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = downloadUrl;
      a.setAttribute('download', '');
      document.body.appendChild(a);
      a.click();
      setTimeout(() => a.remove(), 2000);

      showToast('Executive PDF report downloaded successfully!', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btnExportPdf.disabled = false;
    }
  });

  btnExportNb.addEventListener('click', async () => {
    btnExportNb.disabled = true;
    showToast('Preparing reproducible Jupyter Notebook (.ipynb)...', 'info');

    try {
      const checkRes = await apiFetch(`/api/export/check?type=notebook`);
      const checkData = await checkRes.json().catch(() => ({}));
      if (!checkRes.ok || !checkData.ok) {
        throw new Error(checkData.error || 'No dataset loaded to export into a notebook.');
      }

      const downloadUrl = `/api/export/notebook?session_id=${encodeURIComponent(sessionId)}&t=${Date.now()}`;
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = downloadUrl;
      a.setAttribute('download', '');
      document.body.appendChild(a);
      a.click();
      setTimeout(() => a.remove(), 2000);

      showToast('Jupyter Notebook downloaded successfully!', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btnExportNb.disabled = false;
    }
  });

  // ────────────────────────────────────────────────────────────
  // Session Reset Handler
  // ────────────────────────────────────────────────────────────
  btnResetSession.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to reset the session? All loaded datasets and chat history will be cleared.')) {
      return;
    }

    try {
      await apiFetch('/api/reset', { method: 'POST' });
      
      // Reset UI
      currentDatasets = [];
      renderUploadedFileList([]);
      metricsCard.style.display = 'none';
      tablePreviewCard.style.display = 'none';
      enableExportButtons(false);

      // Clear timeline keeping only welcome hero
      chatTimeline.innerHTML = '';
      welcomeHero.style.display = 'flex';
      chatTimeline.appendChild(welcomeHero);

      showToast('Session reset successfully.', 'info');
    } catch (err) {
      showToast('Failed to reset session: ' + err.message, 'error');
    }
  });

  // Kickoff session initialization
  initSession();

})();
