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
    try {
      const res = await apiFetch('/api/session');
      if (!res.ok) return;
      const data = await res.json();

      if (data.loaded && data.tables && data.tables.length > 0) {
        currentDatasets = data.tables;
        renderTelemetry(data.profile, data.tables, data.is_multi_dataset);
        renderTableTabs(data.tables);
        loadTableData(data.tables[0].name, 1);
        enableExportButtons(true);
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
    }
  }

  // ────────────────────────────────────────────────────────────
  // Dataset Ingestion (Drag & Drop and File Picker)
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

  async function handleFileUpload(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
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
      renderTelemetry(data.profile, data.tables, data.is_multi_dataset);
      renderTableTabs(data.tables);
      loadTableData(data.tables[0].name, 1);
      enableExportButtons(true);

      // Add welcoming agent prompt tip in chat
      if (chatTimeline.children.length <= 1) {
        welcomeHero.style.display = 'flex';
      }

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
    const question = questionInput.value.trim();
    if (!question || isAgentAnalyzing) return;

    if (!currentDatasets || currentDatasets.length === 0) {
      showToast('Please upload a dataset (.csv, .xlsx, .parquet, .json) before asking questions.', 'error');
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

    isAgentAnalyzing = true;
    btnSend.disabled = true;

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
            } catch (jsonErr) {
              console.warn('Error parsing SSE event JSON:', jsonErr, jsonStr);
            }
          }
        }
      }

    } catch (err) {
      agentMsgCard.updateStatus(`❌ ${err.message}`, 'error');
      showToast(err.message, 'error');
    } finally {
      isAgentAnalyzing = false;
      btnSend.disabled = false;
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
    card.className = 'chat-msg agent';

    card.innerHTML = `
      <div class="msg-avatar">📊</div>
      <div class="msg-body" style="width: 100%;">
        <div class="msg-bubble">
          <!-- Live Reasoning / Sandbox Stepper -->
          <div class="live-stepper" id="stepper">
            <div class="stepper-header" id="stepperHeader" style="cursor: pointer;">
              <span id="stepperTitle">⚡ Initializing data intelligence runtime...</span>
              <div class="stepper-controls" style="display: flex; align-items: center; gap: 6px;">
                <div class="stepper-spinner" id="stepperSpinner">
                  <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                </div>
                <span class="stepper-toggle-icon" id="stepperToggleIcon" style="display:none; font-size: 0.72rem; color: var(--text-muted);">▼</span>
              </div>
            </div>
            <div class="stepper-log" id="stepperLog"></div>
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
    const stepperToggleIcon = card.querySelector('#stepperToggleIcon');
    const stepperLog = card.querySelector('#stepperLog');
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
        const item = document.createElement('div');
        item.className = 'step-entry';
        item.innerHTML = `<span class="step-icon">${icon}</span><span>${escapeHtml(text)}</span>`;
        stepperLog.appendChild(item);
        scrollToBottom();
      },
      updateStatus: (titleText, type = 'info') => {
        stepperTitle.textContent = titleText;
      },
      collapseStepper: () => {
        stepperSpinner.style.display = 'none';
        stepperToggleIcon.style.display = 'inline';
        stepperTitle.textContent = `✅ Analysis complete (${logCount} execution steps) • Click to expand`;
        stepperLog.style.display = 'none';
      },
      finishStreaming: () => {
        stepperSpinner.style.display = 'none';
        if (reportContent.style.display === 'block') {
          stepperToggleIcon.style.display = 'inline';
          stepperTitle.textContent = `✅ Analysis complete (${logCount} execution steps) • Click to expand`;
          stepperLog.style.display = 'none';
        } else {
          stepperTitle.textContent = '✅ Analysis & computation complete';
        }
      },
      renderReport: (markdownText) => {
        reportContent.style.display = 'block';
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
            const chartBox = document.createElement('div');
            chartBox.className = 'chart-container';

            const chartHeader = document.createElement('div');
            chartHeader.className = 'chart-header';
            chartHeader.innerHTML = `<span>📊 Visual Breakdown ${idx + 1}</span><span class="badge-tag">Interactive Plotly / Canvas</span>`;
            chartBox.appendChild(chartHeader);

            if (c.type === 'plotly' && c.figure && typeof Plotly !== 'undefined') {
              const plotDiv = document.createElement('div');
              plotDiv.className = 'plotly-embed';
              plotDiv.id = `chart_${Date.now()}_${idx}`;
              chartBox.appendChild(plotDiv);
              chartsWrapper.appendChild(chartBox);

              const figure = c.figure;
              figure.layout = figure.layout || {};
              figure.layout.paper_bgcolor = '#12141C';
              figure.layout.plot_bgcolor = '#12141C';
              figure.layout.font = { family: 'Inter, sans-serif', color: '#9CA3AF', size: 11 };
              figure.layout.margin = { l: 50, r: 25, t: 40, b: 50 };

              Plotly.newPlot(plotDiv.id, figure.data, figure.layout, {
                responsive: true,
                displayModeBar: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['sendDataToCloud', 'hoverClosestCartesian', 'hoverCompareCartesian'],
              });
            } else if (c.type === 'image' && c.data) {
              const img = document.createElement('img');
              img.src = c.data;
              img.className = 'chart-static-img';
              chartBox.appendChild(img);
              chartsWrapper.appendChild(chartBox);
            }
          } catch (chartErr) {
            console.error('Error rendering chart element:', chartErr);
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
      if (data.stage === 'reasoning') {
        uiCard.addLogEntry('🧠', data.message);
      } else if (data.stage === 'executing') {
        uiCard.addLogEntry('⚙️', data.message);
      } else if (data.stage === 'synthesis') {
        uiCard.addLogEntry('📝', data.message);
      }
    } else if (data.type === 'code') {
      uiCard.addLogEntry('💻', `Generated Step ${data.step} Python script`);
    } else if (data.type === 'execution') {
      if (data.success) {
        let note = `Step ${data.step} execution successful.`;
        if (data.is_plotly) note += ' (Captured interactive Plotly chart)';
        else if (data.has_chart) note += ' (Captured visualization figure)';
        uiCard.addLogEntry('✅', note);
      } else {
        uiCard.addLogEntry('⚠️', `Step ${data.step} error encountered, auto-correcting: ${data.error || 'Syntax error'}`);
      }
    } else if (data.type === 'final_answer') {
      uiCard.collapseStepper();
      uiCard.renderReport(data.answer);
      if (data.charts && data.charts.length > 0) {
        uiCard.renderCharts(data.charts);
      }
      if (data.code && data.code.length > 0) {
        uiCard.renderCodeAudit(data.code);
      }
      scrollToBottom();
    } else if (data.type === 'error') {
      uiCard.updateStatus(`❌ ${data.error}`, 'error');
      uiCard.addLogEntry('❌', data.error);
    }
  }

  function appendAgentMessage(entry) {
    const card = createAgentStreamingCard(entry.timestamp || 'Just now');
    card.finishStreaming();
    card.renderReport(entry.answer);
    if (entry.charts && entry.charts.length > 0) {
      card.renderCharts(entry.charts);
    }
    if (entry.code && entry.code.length > 0) {
      card.renderCodeAudit(entry.code);
    }
    chatTimeline.appendChild(card.container);
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
