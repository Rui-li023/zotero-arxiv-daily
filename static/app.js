// ============================================================
// arXiv Daily — Frontend Application
// ============================================================

// === State ===
let currentAbortController = null;  // AbortController for cancelling in-flight chat streams
let currentStreamPaperId = null;    // arxiv_id of the paper currently being streamed
let userScrolledUp = false;         // true when user has scrolled away from bottom during streaming

const state = {
  dates: [],
  currentDate: null,
  papers: [],
  selectedPaper: null,
  focusedIndex: -1,
  chatHistories: {}, // arxiv_id -> [messages]
  streaming: false,
  searchQuery: '',
  serverLlm: { hasLlm: false, needsPassword: false, serverModel: '' },
  starred: {}, // arxiv_id -> {paper_data, starred_date, notes}
  viewingStarred: false,
  zoteroConfigured: false,
  subscriptions: [], // [{keyword, weight, enabled}]
  settings: {
    mode: 'server',
    serverPassword: '',
    apiKey: '',
    apiBase: '',
    model: '',
    chatModel: '',
    theme: 'dark',
  },
  prompts: {
    systemPrompt: 'You are an expert AI research assistant. The user is reading an arXiv paper. Help them understand the paper and answer questions about it. Be concise and insightful. Use the paper info provided for context.\n\nPaper Title: {title}\nPaper Abstract: {summary}\nArXiv ID: {arxiv_id}',
    autoAnalyzePrompt: 'Please provide a brief, insightful analysis of this paper. Focus on: 1) The key innovation 2) How it differs from prior work 3) Potential impact. Keep it concise (3-4 paragraphs).',
  },
};

// === Configure marked.js ===
if (typeof marked !== 'undefined') {
  marked.setOptions({ breaks: true, gfm: true });
}

// === DOM Refs ===
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  dateSelect: $('#dateSelect'),
  prevDate: $('#prevDate'),
  nextDate: $('#nextDate'),
  paperList: $('#paperList'),
  paperCount: $('#paperCount'),
  loadingState: $('#loadingState'),
  emptyState: $('#emptyState'),
  searchInput: $('#searchInput'),
  // Detail
  detailPanel: $('#detailPanel'),
  detailPlaceholder: $('#detailPlaceholder'),
  detailContent: $('#detailContent'),
  detailClose: $('#detailClose'),
  chatHeaderTitle: $('#chatHeaderTitle'),
  detailTitle: $('#detailTitle'),
  detailAuthors: $('#detailAuthors'),
  detailAffiliations: $('#detailAffiliations'),
  detailLinks: $('#detailLinks'),
  detailStars: $('#detailStars'),
  detailTldr: $('#detailTldr'),
  detailUpper: $('#detailUpper'),
  readingProgress: $('#readingProgress'),
  // Chat
  chatMessages: $('#chatMessages'),
  chatInput: $('#chatInput'),
  chatSend: $('#chatSend'),
  chatModelInput: $('#chatModelInput'),
  // Settings
  settingsBtn: $('#settingsBtn'),
  settingsModal: $('#settingsModal'),
  settingsClose: $('#settingsClose'),
  settingsSave: $('#settingsSave'),
  sendNowBtn: $('#sendNowBtn'),
  // Add Paper
  addPaperBtn: $('#addPaperBtn'),
  addPaperModal: $('#addPaperModal'),
  addPaperClose: $('#addPaperClose'),
  newPaperInput: $('#newPaperInput'),
  newPaperSubmit: $('#newPaperSubmit'),
  // Stats
  statsBtn: $('#statsBtn'),
  statsModal: $('#statsModal'),
  statsClose: $('#statsClose'),
  // Toast
  toastContainer: $('#toastContainer'),
};

// === Setup ===
async function checkSetup() {
  try {
    const resp = await fetch('/api/setup/status');
    const data = await resp.json();
    if (data.needs_setup) {
      showSetupOverlay();
      return true;
    }
  } catch {}
  return false;
}

function showSetupOverlay() {
  const overlay = document.getElementById('setupOverlay');
  if (overlay) overlay.classList.remove('hidden');
  // Hide main app
  const appEl = document.querySelector('.app > header');
  const mainEl = document.querySelector('.app > main');
  if (appEl) appEl.style.display = 'none';
  if (mainEl) mainEl.style.display = 'none';

  const form = document.getElementById('setupForm');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('setupSubmit');
      const btnText = btn.querySelector('.btn-text');
      const btnLoader = btn.querySelector('.btn-loader');
      btnText.textContent = 'Saving...';
      if (btnLoader) btnLoader.classList.remove('hidden');
      btn.disabled = true;

      const payload = {
        OPENAI_API_KEY: document.getElementById('setupApiKey').value.trim(),
        OPENAI_API_BASE: document.getElementById('setupApiBase').value.trim() || 'https://api.openai.com/v1',
        MODEL_NAME: document.getElementById('setupModel').value.trim() || 'gpt-4o',
        LANGUAGE: document.getElementById('setupLanguage').value.trim() || 'Chinese',
        ARXIV_QUERY: document.getElementById('setupArxivQuery').value.trim() || 'cat:cs.AI+cat:cs.CV+cat:cs.LG+cat:cs.CL+cat:cs.RO',
        MAX_PAPER_NUM: document.getElementById('setupMaxPapers').value.trim() || '25',
        SMTP_SERVER: document.getElementById('setupSmtpServer').value.trim(),
        SMTP_PORT: document.getElementById('setupSmtpPort').value.trim() || '465',
        SENDER: document.getElementById('setupSender').value.trim(),
        SENDER_PASSWORD: document.getElementById('setupSenderPassword').value.trim(),
        RECEIVER: document.getElementById('setupReceiver').value.trim(),
        ZOTERO_ID: document.getElementById('setupZoteroId').value.trim(),
        ZOTERO_KEY: document.getElementById('setupZoteroKey').value.trim(),
        SERVER_LLM_PASSWORD: document.getElementById('setupServerPassword').value.trim(),
      };

      try {
        const resp = await fetch('/api/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) throw new Error('Setup failed');
        // Show success and prompt reload
        btnText.textContent = 'Done! Reloading...';
        if (btnLoader) btnLoader.classList.add('hidden');
        setTimeout(() => window.location.reload(), 1000);
      } catch (err) {
        btnText.textContent = 'Error — try again';
        if (btnLoader) btnLoader.classList.add('hidden');
        btn.disabled = false;
      }
    });
  }
}

// === Init ===
async function init() {
  loadSettings();
  const needsSetup = await checkSetup();
  if (needsSetup) return;
  bindEvents();
  await Promise.all([checkLlmStatus(), loadPrompts(), loadEmailConfig(), loadStarred(), checkZoteroStatus(), loadSubscriptions()]);
  await loadDates();
}

// === Toast Notifications ===
function showToast(message, type = 'info', duration = 3000) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  dom.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-out');
    toast.addEventListener('animationend', () => toast.remove());
  }, duration);
}

// === API Helper ===
async function api(path, options = {}) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return resp;
}

// === LLM Status ===
async function checkLlmStatus() {
  try {
    const resp = await fetch('/api/llm/status');
    const data = await resp.json();
    state.serverLlm.hasLlm = data.has_server_llm;
    state.serverLlm.needsPassword = data.needs_password;
    state.serverLlm.serverModel = data.server_model || '';
    updateChatModelPlaceholder();
    updateServerHint();
  } catch {}
}

function updateChatModelPlaceholder() {
  if (dom.chatModelInput) {
    const model = state.serverLlm.serverModel;
    dom.chatModelInput.placeholder = model ? model : 'server default';
  }
}

function updateServerHint() {
  const hint = $('#serverHint');
  if (!hint) return;
  if (!state.serverLlm.hasLlm) {
    hint.textContent = 'No server LLM configured. Use client mode.';
    hint.style.color = 'var(--error)';
  } else if (state.serverLlm.needsPassword) {
    const cached = state.settings.serverPassword ? ' (cached)' : '';
    hint.textContent = cached ? 'Password loaded from cache.' : 'Password required to use server LLM.';
    hint.style.color = cached ? 'var(--success)' : '';
  } else {
    hint.textContent = 'Server LLM available (no password needed).';
    hint.style.color = 'var(--success)';
  }
}

// === Prompts ===
async function loadPrompts() {
  try {
    const resp = await fetch('/api/config/prompts');
    const data = await resp.json();
    if (data.chat_system_prompt) state.prompts.systemPrompt = data.chat_system_prompt;
    if (data.chat_auto_analyze_prompt) state.prompts.autoAnalyzePrompt = data.chat_auto_analyze_prompt;
  } catch {}
}

// === Email Config ===
async function loadEmailConfig() {
  try {
    const resp = await fetch('/api/config/email');
    const data = await resp.json();
    const el = (id) => document.getElementById(id);
    if (el('emailReceivers')) el('emailReceivers').value = (data.email_receivers || []).join(', ');
    if (el('emailHour')) el('emailHour').value = data.email_schedule_hour ?? 9;
    if (el('emailMinute')) el('emailMinute').value = data.email_schedule_minute ?? 0;
    const hint = $('#smtpHint');
    if (hint) {
      hint.textContent = data.smtp_configured
        ? 'SMTP configured on server.'
        : 'SMTP not configured. Set env vars on server.';
      hint.style.color = data.smtp_configured ? 'var(--success)' : 'var(--text-muted)';
    }
  } catch {}
}

// === Settings ===
function loadSettings() {
  try {
    const saved = localStorage.getItem('llmSettings');
    if (saved) Object.assign(state.settings, JSON.parse(saved));
  } catch {}
  applyTheme(state.settings.theme || 'dark');
  applySettingsToForm();
  // Restore chat model input from saved settings
  if (dom.chatModelInput && state.settings.chatModel) {
    dom.chatModelInput.value = state.settings.chatModel;
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

function applySettingsToForm() {
  $$('input[name="llmMode"]').forEach(r => { r.checked = r.value === state.settings.mode; });
  $$('input[name="themeMode"]').forEach(r => { r.checked = r.value === (state.settings.theme || 'dark'); });
  const el = (id) => document.getElementById(id);
  if (el('serverPassword')) el('serverPassword').value = state.settings.serverPassword || '';
  if (el('apiKey')) el('apiKey').value = state.settings.apiKey || '';
  if (el('apiBase')) el('apiBase').value = state.settings.apiBase || '';
  if (el('modelName')) el('modelName').value = state.settings.model || '';
  toggleModeSettings();
  updateServerHint();
}

function toggleModeSettings() {
  const mode = $('input[name="llmMode"]:checked')?.value || 'server';
  const server = $('#serverSettings');
  const client = $('#clientSettings');
  if (server) server.classList.toggle('hidden', mode !== 'server');
  if (client) client.classList.toggle('hidden', mode !== 'client');
}

function saveSettings() {
  const mode = $('input[name="llmMode"]:checked')?.value || 'server';
  const theme = $('input[name="themeMode"]:checked')?.value || 'dark';
  state.settings = {
    mode,
    serverPassword: ($('#serverPassword')?.value || '').trim(),
    apiKey: ($('#apiKey')?.value || '').trim(),
    apiBase: ($('#apiBase')?.value || '').trim(),
    model: ($('#modelName')?.value || '').trim(),
    chatModel: (dom.chatModelInput?.value || '').trim(),
    theme,
  };
  localStorage.setItem('llmSettings', JSON.stringify(state.settings));
  applyTheme(theme);

  // Save email config
  const emailReceivers = ($('#emailReceivers')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
  const emailHour = parseInt($('#emailHour')?.value) || 9;
  const emailMinute = parseInt($('#emailMinute')?.value) || 0;

  fetch('/api/config/email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email_receivers: emailReceivers,
      email_schedule_hour: emailHour,
      email_schedule_minute: emailMinute,
    }),
  }).catch(() => {});

  closeModal(dom.settingsModal);
  showToast('Settings saved', 'success');
}

// === Events ===
function bindEvents() {
  // Date navigation
  dom.dateSelect.addEventListener('change', () => loadPapers(dom.dateSelect.value));
  dom.prevDate.addEventListener('click', () => navigateDate(1));
  dom.nextDate.addEventListener('click', () => navigateDate(-1));

  // Detail
  dom.detailClose.addEventListener('click', closeDetail);

  // Chat
  dom.chatSend.addEventListener('click', sendChat);
  dom.chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
  // Auto-resize chat input
  dom.chatInput.addEventListener('input', () => {
    dom.chatInput.style.height = 'auto';
    dom.chatInput.style.height = Math.min(dom.chatInput.scrollHeight, 120) + 'px';
  });

  // Search
  dom.searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase();
    filterPapers();
  });

  // Settings modal
  dom.settingsBtn.addEventListener('click', () => {
    applySettingsToForm();
    openModal(dom.settingsModal);
  });
  dom.settingsClose.addEventListener('click', () => { saveSettings(); closeModal(dom.settingsModal); });
  dom.settingsModal.addEventListener('click', (e) => {
    if (e.target === dom.settingsModal) { saveSettings(); closeModal(dom.settingsModal); }
  });
  dom.settingsSave.addEventListener('click', () => { saveSettings(); closeModal(dom.settingsModal); showToast('Settings saved', 'success'); });
  $$('input[name="llmMode"]').forEach(r => r.addEventListener('change', toggleModeSettings));
  $$('input[name="themeMode"]').forEach(r => r.addEventListener('change', (e) => applyTheme(e.target.value)));

  // Persist chat model selection on change
  if (dom.chatModelInput) {
    dom.chatModelInput.addEventListener('change', () => {
      state.settings.chatModel = dom.chatModelInput.value.trim();
      localStorage.setItem('llmSettings', JSON.stringify(state.settings));
    });
  }

  // Send now
  dom.sendNowBtn.addEventListener('click', async () => {
    try {
      await api('/api/email/send-now', { method: 'POST' });
      showToast('Pipeline started', 'success');
    } catch (e) {
      showToast('Failed: ' + e.message, 'error');
    }
  });

  // Add paper modal
  dom.addPaperBtn.addEventListener('click', () => {
    openModal(dom.addPaperModal);
    setTimeout(() => dom.newPaperInput.focus(), 100);
  });
  dom.addPaperClose.addEventListener('click', () => closeModal(dom.addPaperModal));
  dom.addPaperModal.addEventListener('click', (e) => {
    if (e.target === dom.addPaperModal) closeModal(dom.addPaperModal);
  });
  dom.newPaperSubmit.addEventListener('click', addNewPaper);
  dom.newPaperInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addNewPaper();
  });

  // Track user scroll in chat messages
  dom.chatMessages.addEventListener('scroll', () => {
    if (state.streaming) {
      userScrolledUp = !isNearBottom(dom.chatMessages);
      updateScrollToBottomBtn();
    }
  });

  // Reading progress (no-op if detailUpper is hidden)
  if (dom.detailUpper) dom.detailUpper.addEventListener('scroll', updateReadingProgress);

  // Keyboard shortcuts
  document.addEventListener('keydown', handleKeyboard);

  // Stats modal
  dom.statsBtn.addEventListener('click', openStatsModal);
  dom.statsClose.addEventListener('click', () => closeModal(dom.statsModal));
  dom.statsModal.addEventListener('click', (e) => {
    if (e.target === dom.statsModal) closeModal(dom.statsModal);
  });

  // Subscription management
  const addSubBtn = document.getElementById('addSubBtn');
  if (addSubBtn) {
    addSubBtn.addEventListener('click', addSubscription);
    document.getElementById('newSubKeyword')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') addSubscription();
    });
  }

  // Resize handles
  initHorizontalResize();
  initVerticalResize();
}

function navigateDate(direction) {
  const idx = state.dates.indexOf(state.currentDate);
  const newIdx = idx + direction;
  if (newIdx >= 0 && newIdx < state.dates.length) {
    dom.dateSelect.value = state.dates[newIdx];
    loadPapers(state.dates[newIdx]);
  }
}

// === Modal helpers ===
function openModal(overlay) {
  overlay.classList.add('visible');
}

function closeModal(overlay) {
  overlay.classList.remove('visible');
}

// === Keyboard Shortcuts ===
function handleKeyboard(e) {
  // Don't trigger when typing in inputs
  const tag = document.activeElement?.tagName;
  const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

  // Escape: close modals or detail
  if (e.key === 'Escape') {
    if (dom.settingsModal.classList.contains('visible')) {
      closeModal(dom.settingsModal);
      return;
    }
    if (dom.addPaperModal.classList.contains('visible')) {
      closeModal(dom.addPaperModal);
      return;
    }
    if (isInput) {
      document.activeElement.blur();
      return;
    }
    // Collapse any expanded card
    const expandedCard = dom.paperList.querySelector('.paper-card.expanded');
    if (expandedCard) {
      expandedCard.classList.remove('expanded');
      state.selectedPaper = null;
      return;
    }
    if (state.selectedPaper) {
      closeDetail();
      return;
    }
  }

  if (isInput) return;

  // / : Focus search
  if (e.key === '/') {
    e.preventDefault();
    dom.searchInput.focus();
    return;
  }

  // n : Open add paper
  if (e.key === 'n') {
    e.preventDefault();
    openModal(dom.addPaperModal);
    setTimeout(() => dom.newPaperInput.focus(), 100);
    return;
  }

  // j/k or arrow keys: Navigate papers
  if (e.key === 'j' || e.key === 'ArrowDown') {
    e.preventDefault();
    navigatePaperFocus(1);
    return;
  }
  if (e.key === 'k' || e.key === 'ArrowUp') {
    e.preventDefault();
    navigatePaperFocus(-1);
    return;
  }

  // Enter: Toggle expand focused paper card
  if (e.key === 'Enter' && state.focusedIndex >= 0) {
    e.preventDefault();
    const visiblePapers = getVisiblePapers();
    const paper = visiblePapers[state.focusedIndex];
    if (paper) {
      const card = dom.paperList.querySelector(`[data-arxiv-id="${paper.arxiv_id}"]`);
      if (card) toggleCardExpand(card, paper);
    }
    return;
  }
}

function getVisiblePapers() {
  if (!state.searchQuery) return state.papers;
  return state.papers.filter(p => matchesSearch(p));
}

function matchesSearch(paper) {
  const q = state.searchQuery;
  if (!q) return true;
  const title = (paper.title || '').toLowerCase();
  const authors = (Array.isArray(paper.authors) ? paper.authors.join(' ') : '').toLowerCase();
  const highlight = (paper.highlight || '').toLowerCase();
  const affiliations = (Array.isArray(paper.affiliations) ? paper.affiliations.join(' ') : '').toLowerCase();
  return title.includes(q) || authors.includes(q) || highlight.includes(q) || affiliations.includes(q);
}

function navigatePaperFocus(direction) {
  const visible = getVisiblePapers();
  if (visible.length === 0) return;

  state.focusedIndex += direction;
  if (state.focusedIndex < 0) state.focusedIndex = 0;
  if (state.focusedIndex >= visible.length) state.focusedIndex = visible.length - 1;

  // Update visual focus
  dom.paperList.querySelectorAll('.paper-card').forEach(c => c.classList.remove('focused'));
  const paper = visible[state.focusedIndex];
  if (paper) {
    const card = dom.paperList.querySelector(`[data-arxiv-id="${paper.arxiv_id}"]`);
    if (card) {
      card.classList.add('focused');
      card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }
}

// === Dates ===
async function loadDates() {
  try {
    const resp = await api('/api/papers/dates');
    const data = await resp.json();
    state.dates = data.dates || [];

    dom.dateSelect.innerHTML = '';
    if (state.dates.length === 0) {
      dom.dateSelect.innerHTML = '<option>No data</option>';
      showEmpty();
      return;
    }

    // Add "Starred" virtual option
    const starOpt = document.createElement('option');
    starOpt.value = '__starred__';
    starOpt.textContent = '\u2605 Starred';
    dom.dateSelect.appendChild(starOpt);

    state.dates.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      dom.dateSelect.appendChild(opt);
    });

    // Default to first real date
    dom.dateSelect.value = state.dates[0];
    loadPapers(state.dates[0]);
  } catch (e) {
    console.error('Failed to load dates:', e);
    showEmpty();
  }
}

// === Papers ===
async function loadPapers(date) {
  state.currentDate = date;
  state.focusedIndex = -1;
  state.searchQuery = '';
  dom.searchInput.value = '';
  dom.loadingState.classList.remove('hidden');
  dom.emptyState.classList.add('hidden');
  clearPaperCards();

  // Handle starred virtual date
  if (date === '__starred__') {
    state.viewingStarred = true;
    dom.loadingState.classList.add('hidden');
    await loadStarred();
    const starred = state.starred;
    // Convert starred papers into a flat list, grouped by starred_date
    const papers = [];
    for (const [id, entry] of Object.entries(starred)) {
      const pd = entry.paper_data || {};
      pd._starred_date = entry.starred_date;
      papers.push(pd);
    }
    // Sort by starred date desc
    papers.sort((a, b) => (b._starred_date || '').localeCompare(a._starred_date || ''));
    state.papers = papers;
    if (papers.length === 0) { showEmpty(); return; }
    updatePaperCount();
    renderPaperCards();
    return;
  }

  state.viewingStarred = false;
  try {
    const resp = await api(`/api/papers?date=${encodeURIComponent(date)}`);
    const data = await resp.json();
    state.papers = data.papers || [];

    dom.loadingState.classList.add('hidden');

    if (state.papers.length === 0) {
      showEmpty();
      return;
    }

    updatePaperCount();
    renderPaperCards();
  } catch (e) {
    dom.loadingState.classList.add('hidden');
    showEmpty();
    console.error('Failed to load papers:', e);
  }
}

function clearPaperCards() {
  dom.paperList.querySelectorAll('.paper-card').forEach(el => el.remove());
}

function showEmpty() {
  dom.loadingState.classList.add('hidden');
  dom.emptyState.classList.remove('hidden');
  dom.paperCount.textContent = '0 papers';
}

function updatePaperCount() {
  const visible = getVisiblePapers();
  const total = state.papers.length;
  if (visible.length === total) {
    dom.paperCount.textContent = `${total} papers`;
  } else {
    dom.paperCount.textContent = `${visible.length}/${total}`;
  }
}

function renderPaperCards() {
  state.papers.forEach((paper, idx) => {
    const card = createPaperCard(paper, idx);
    dom.paperList.appendChild(card);
  });
}

function createPaperCard(paper, idx) {
  const card = document.createElement('div');
  card.className = 'paper-card';
  card.style.animationDelay = `${idx * 25}ms`;
  card.dataset.arxivId = paper.arxiv_id;

  const authors = Array.isArray(paper.authors) ? paper.authors : [];
  let authorStr = authors.slice(0, 5).join(', ');
  if (authors.length > 8) {
    authorStr += ', ..., ' + authors.slice(-3).join(', ');
  } else if (authors.length > 5) {
    authorStr += ', ...';
  }

  const affiliations = paper.affiliations
    ? (Array.isArray(paper.affiliations) ? paper.affiliations.join(' · ') : paper.affiliations)
    : '';

  const scoreHtml = getScoreHtml(paper.score);
  const tldrContent = paper.tldr || '';

  // Build links HTML for the expanded section
  let linksHtml = `<a class="detail-link" href="${escapeHtml(paper.pdf_url)}" target="_blank" onclick="event.stopPropagation()">PDF</a>`;
  linksHtml += `<a class="detail-link" href="https://arxiv.org/abs/${escapeHtml(paper.arxiv_id)}" target="_blank" onclick="event.stopPropagation()">${escapeHtml(paper.arxiv_id)}</a>`;
  if (paper.code_url) {
    linksHtml += `<a class="detail-link" href="${escapeHtml(paper.code_url)}" target="_blank" onclick="event.stopPropagation()">Code</a>`;
  }

  const isStarred = !!state.starred[paper.arxiv_id];
  const starClass = isStarred ? 'star-btn active' : 'star-btn';

  // Build export button HTML (only if Zotero is configured)
  const exportBtnHtml = state.zoteroConfigured
    ? `<button class="card-expand-export-btn" data-arxiv-id="${escapeHtml(paper.arxiv_id)}" title="Export to Zotero">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Zotero
      </button>`
    : '';

  card.innerHTML = `
    <span class="card-rank">#${idx + 1}</span>
    <button class="${starClass}" data-arxiv-id="${escapeHtml(paper.arxiv_id)}" title="Star this paper">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="${isStarred ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
    </button>
    <div class="card-title">${escapeHtml(paper.title)}</div>
    <div class="card-authors">${escapeHtml(authorStr)}</div>
    ${affiliations ? `<div class="card-affiliations">${escapeHtml(affiliations)}</div>` : ''}
    ${paper.highlight ? `<div class="card-highlight">${escapeHtml(paper.highlight)}</div>` : ''}
    <div class="card-footer">
      <span class="card-stars">${scoreHtml}</span>
      <span class="card-id">${escapeHtml(paper.arxiv_id)}</span>
    </div>
    <div class="card-expand">
      <div class="card-expand-links">
        ${linksHtml}
        <button class="card-expand-chat-btn" data-arxiv-id="${escapeHtml(paper.arxiv_id)}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          Chat
        </button>
        ${exportBtnHtml}
      </div>
      <div class="card-expand-tldr">${tldrContent || '<p class="no-tldr">No analysis available</p>'}</div>
    </div>
  `;

  card.addEventListener('click', (e) => {
    // Don't toggle if clicking a link or button inside expanded area
    if (e.target.closest('a') || e.target.closest('.card-expand-chat-btn') || e.target.closest('.card-expand-export-btn') || e.target.closest('.star-btn')) return;
    toggleCardExpand(card, paper);
  });

  // Star button
  const starBtn = card.querySelector('.star-btn');
  starBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleStar(paper, starBtn);
  });

  // Chat button inside the expanded card
  const chatBtn = card.querySelector('.card-expand-chat-btn');
  chatBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    openDetail(paper);
  });

  // Export to Zotero button
  const exportBtn = card.querySelector('.card-expand-export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      exportToZotero(paper);
    });
  }

  return card;
}

// === Accordion: toggle card expand ===
function toggleCardExpand(card, paper) {
  const isExpanded = card.classList.contains('expanded');

  // Collapse all other cards (accordion)
  dom.paperList.querySelectorAll('.paper-card.expanded').forEach(c => {
    c.classList.remove('expanded');
  });

  // Toggle this card
  if (!isExpanded) {
    card.classList.add('expanded');
    state.selectedPaper = paper;
    // Scroll expanded card into view
    setTimeout(() => card.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 50);
  } else {
    state.selectedPaper = null;
  }
}

function getScoreHtml(score) {
  if (!score || score <= 6) return '';
  const low = 6, high = 8;
  let num;
  if (score >= high) {
    num = 10;
  } else {
    const interval = (high - low) / 10;
    num = Math.ceil((score - low) / interval);
  }
  const full = Math.floor(num / 2);
  const half = num % 2;
  const empty = 5 - full - half;
  let stars = '<span style="color:var(--star)">'.concat('★'.repeat(full));
  if (half) stars += '★'; // half star shown as full for simplicity
  stars += '</span>';
  if (empty > 0) stars += '<span style="color:var(--text-muted);opacity:0.3">' + '★'.repeat(empty) + '</span>';
  stars += `<span class="card-score-num">${score.toFixed(1)}</span>`;
  return stars;
}

// === Search / Filter ===
function filterPapers() {
  const cards = dom.paperList.querySelectorAll('.paper-card');
  cards.forEach(card => {
    const arxivId = card.dataset.arxivId;
    const paper = state.papers.find(p => p.arxiv_id === arxivId);
    if (paper && matchesSearch(paper)) {
      card.classList.remove('hidden-by-search');
    } else {
      card.classList.add('hidden-by-search');
    }
  });
  state.focusedIndex = -1;
  updatePaperCount();
}

// === Detail Panel ===
function openDetail(paper) {
  state.selectedPaper = paper;

  // Record paper view
  fetch(`/api/paper/${encodeURIComponent(paper.arxiv_id)}/view`, { method: 'POST' }).catch(() => {});

  // Update focused index
  const visible = getVisiblePapers();
  state.focusedIndex = visible.indexOf(paper);

  // Mark active card
  dom.paperList.querySelectorAll('.paper-card').forEach(c => {
    c.classList.remove('active');
    c.classList.remove('focused');
  });
  const activeCard = dom.paperList.querySelector(`[data-arxiv-id="${paper.arxiv_id}"]`);
  if (activeCard) activeCard.classList.add('active');

  // Set compact chat header title
  dom.chatHeaderTitle.textContent = paper.title;

  // Show detail
  dom.detailPlaceholder.classList.add('hidden');
  dom.detailContent.classList.remove('hidden');
  dom.detailPanel.classList.add('open'); // mobile

  // Chat
  loadChatForPaper(paper);
}

function closeDetail() {
  dom.detailPlaceholder.classList.remove('hidden');
  dom.detailContent.classList.add('hidden');
  dom.detailPanel.classList.remove('open');
  dom.paperList.querySelectorAll('.paper-card').forEach(c => c.classList.remove('active'));
  state.selectedPaper = null;
}

function updateReadingProgress() {
  const el = dom.detailUpper;
  if (el.scrollHeight <= el.clientHeight) {
    dom.readingProgress.style.width = '100%';
    return;
  }
  const pct = (el.scrollTop / (el.scrollHeight - el.clientHeight)) * 100;
  dom.readingProgress.style.width = `${Math.min(pct, 100)}%`;
}

// === Chat ===
async function loadChatForPaper(paper) {
  const id = paper.arxiv_id;

  // If currently streaming for this same paper, don't reset
  if (currentStreamPaperId === id && state.streaming) {
    return;
  }

  // If we already have it in memory (with assistant response), just render
  if (state.chatHistories[id] && state.chatHistories[id].some(m => m.role === 'assistant')) {
    dom.chatMessages.innerHTML = '';
    state.chatHistories[id].forEach(msg => appendChatBubble(msg.role, msg.content));
    return;
  }

  // Try loading from server
  try {
    const resp = await fetch(`/api/chat/history/${encodeURIComponent(id)}`);
    if (resp.ok) {
      const data = await resp.json();
      if (data.messages && data.messages.length > 0) {
        state.chatHistories[id] = data.messages;
        dom.chatMessages.innerHTML = '';
        data.messages.forEach(msg => appendChatBubble(msg.role, msg.content));
        return;
      }
    }
  } catch {}

  // No history — start fresh with auto-analyze
  state.chatHistories[id] = [];
  dom.chatMessages.innerHTML = '';
  autoAnalyze(paper);
}

async function saveChatHistory(arxivId) {
  const messages = state.chatHistories[arxivId];
  if (!messages || messages.length === 0) return;
  try {
    await fetch(`/api/chat/history/${encodeURIComponent(arxivId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    });
  } catch {}
}

async function autoAnalyze(paper) {
  const id = paper.arxiv_id;

  // 尝试获取论文内容（优先HTML全文，其次PDF）
  let paperContent = null;
  try {
    const resp = await fetch(`/api/paper/${encodeURIComponent(id)}/content`);
    if (resp.ok) {
      paperContent = await resp.json();
      console.log(`Got paper content: type=${paperContent.type}, length=${paperContent.content?.length || 0}`);
    }
  } catch (e) {
    console.log('Failed to fetch paper content:', e);
  }

  // 构建系统提示
  let systemContent = normalizePrompt(state.prompts.systemPrompt)
    .replace('{title}', paper.title)
    .replace('{summary}', paper.summary || '')
    .replace('{arxiv_id}', paper.arxiv_id);

  // 根据内容类型构建消息
  let systemMsg;
  if (paperContent?.type === 'pdf') {
    // PDF作为文件传递给支持视觉的模型
    systemMsg = {
      role: 'system',
      content: [
        { type: 'text', text: systemContent },
        {
          type: 'file',
          file: {
            filename: `${id.replace('/', '_')}.pdf`,
            file_data: `data:application/pdf;base64,${paperContent.content}`
          }
        }
      ]
    };
  } else {
    // 没有PDF，只用摘要
    systemMsg = { role: 'system', content: systemContent };
  }

  const userMsg = { role: 'user', content: normalizePrompt(state.prompts.autoAnalyzePrompt) };

  state.chatHistories[id] = [systemMsg, userMsg];

  appendChatBubble('user', normalizePrompt(state.prompts.autoAnalyzePrompt));
  await streamChat(id);
}

/** Replace literal backslash-n sequences with real newlines.
 *  JSON already decodes \n, but if the user edited config with \\n
 *  or pasted from a non-JSON source, we handle it here. */
function normalizePrompt(text) {
  if (!text) return '';
  return text.replace(/\\n/g, '\n');
}

async function sendChat() {
  if (state.streaming || !state.selectedPaper) return;
  const text = dom.chatInput.value.trim();
  if (!text) return;

  const id = state.selectedPaper.arxiv_id;
  state.chatHistories[id].push({ role: 'user', content: text });

  appendChatBubble('user', text);
  dom.chatInput.value = '';
  dom.chatInput.style.height = 'auto';

  await streamChat(id);
}

async function regenerateLastResponse() {
  if (state.streaming || !state.selectedPaper) return;
  const id = state.selectedPaper.arxiv_id;
  const history = state.chatHistories[id];
  if (!history || history.length === 0) return;

  // Remove last assistant message from history
  while (history.length > 0 && history[history.length - 1].role === 'assistant') {
    history.pop();
  }
  if (history.length === 0) return;

  // Remove last assistant bubble(s) from DOM
  const bubbles = dom.chatMessages.querySelectorAll('.chat-msg.assistant');
  if (bubbles.length > 0) {
    bubbles[bubbles.length - 1].remove();
  }

  await streamChat(id);
}

async function streamChat(arxivId) {
  // Abort any in-flight stream for a different paper
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }

  const abortController = new AbortController();
  currentAbortController = abortController;
  currentStreamPaperId = arxivId;

  state.streaming = true;
  userScrolledUp = false;
  dom.chatSend.disabled = true;

  // Create assistant bubble with typing indicator
  const bubble = appendChatBubble('assistant', '');
  const bubbleContent = bubble.querySelector('.chat-msg-content');
  const bubbleActions = bubble.querySelector('.chat-msg-actions');
  if (bubbleActions) bubbleActions.style.display = 'none';
  bubbleContent.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

  const messages = state.chatHistories[arxivId];
  const body = { messages };

  const chatModel = dom.chatModelInput?.value?.trim() || state.settings.chatModel || '';
  if (state.settings.mode === 'client' && state.settings.apiKey) {
    body.api_key = state.settings.apiKey;
    body.base_url = state.settings.apiBase || undefined;
    body.model = chatModel || state.settings.model || undefined;
  } else if (state.settings.mode === 'server') {
    if (state.settings.serverPassword) body.server_password = state.settings.serverPassword;
    if (chatModel) body.model = chatModel;
  }

  let fullText = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: abortController.signal,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Chat request failed');
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') continue;

        try {
          const data = JSON.parse(payload);
          if (data.error) throw new Error(data.error);
          if (data.token) {
            fullText += data.token;
            // Only update DOM if this stream is still for the active paper
            if (currentStreamPaperId === arxivId && bubble.isConnected) {
              bubble.classList.add('streaming-cursor');
              bubbleContent.innerHTML = renderMarkdown(fullText);
              scrollChatToBottom();
            }
          }
        } catch (parseErr) {
          if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr;
        }
      }
    }
  } catch (e) {
    // Silently ignore aborted requests (user switched papers)
    if (e.name === 'AbortError') {
      // Still save partial text if we have any
      if (fullText) {
        state.chatHistories[arxivId].push({ role: 'assistant', content: fullText });
        saveChatHistory(arxivId);
      }
      return;
    }
    if (bubble.isConnected) {
      if (!fullText) {
        bubble.classList.remove('streaming-cursor');
        bubble.classList.add('error');
        bubbleContent.textContent = `Error: ${e.message}`;
      } else {
        const errBubble = appendChatBubble('assistant', '');
        errBubble.classList.add('error');
        const errContent = errBubble.querySelector('.chat-msg-content');
        if (errContent) errContent.textContent = `Stream interrupted: ${e.message}`;
      }
    }
  }

  if (bubble.isConnected) {
    bubble.classList.remove('streaming-cursor');
    // Show action buttons and store raw content
    if (fullText) {
      bubble.dataset.rawContent = fullText;
      if (bubbleActions) bubbleActions.style.display = '';
    }
  }

  // Clean up
  if (currentAbortController === abortController) {
    currentAbortController = null;
    currentStreamPaperId = null;
  }
  state.streaming = false;
  userScrolledUp = false;
  dom.chatSend.disabled = false;
  updateScrollToBottomBtn();

  if (fullText) {
    state.chatHistories[arxivId].push({ role: 'assistant', content: fullText });
    saveChatHistory(arxivId);
  }
}

function appendChatBubble(role, content) {
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  if (role === 'system') return div; // don't display

  if (role === 'assistant') {
    // Wrap content in a container so action buttons sit below
    const contentDiv = document.createElement('div');
    contentDiv.className = 'chat-msg-content';
    contentDiv.innerHTML = renderMarkdown(content);
    div.appendChild(contentDiv);
    div.dataset.rawContent = content; // store raw markdown for "copy original"

    const actions = document.createElement('div');
    actions.className = 'chat-msg-actions';
    actions.innerHTML = `
      <button class="chat-action-btn" data-action="copy" title="Copy">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        <span>Copy</span>
      </button>
      <button class="chat-action-btn" data-action="copy-raw" title="Copy Markdown">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <span>Copy Markdown</span>
      </button>
      <button class="chat-action-btn" data-action="regenerate" title="Regenerate">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        <span>Regenerate</span>
      </button>
    `;
    div.appendChild(actions);

    actions.addEventListener('click', (e) => {
      const btn = e.target.closest('.chat-action-btn');
      if (!btn) return;
      const action = btn.dataset.action;
      const msgEl = btn.closest('.chat-msg');
      if (action === 'copy') {
        const content = msgEl.querySelector('.chat-msg-content');
        copyToClipboard(content ? content.innerText : '').then(() => showToast('Copied'));
      } else if (action === 'copy-raw') {
        copyToClipboard(msgEl.dataset.rawContent || '').then(() => showToast('Markdown copied'));
      } else if (action === 'regenerate') {
        regenerateLastResponse();
      }
    });
  } else {
    div.innerHTML = escapeHtml(content).replace(/\n/g, '<br>');
  }

  dom.chatMessages.appendChild(div);
  scrollChatToBottom();
  return div;
}

function isNearBottom(el, threshold = 60) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function scrollChatToBottom(force = false) {
  if (force || !userScrolledUp) {
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
  }
  updateScrollToBottomBtn();
}

function updateScrollToBottomBtn() {
  const btn = document.getElementById('scrollToBottomBtn');
  if (!btn) return;
  if (userScrolledUp && state.streaming) {
    btn.classList.add('visible');
  } else {
    btn.classList.remove('visible');
  }
}

// === Add New Paper ===
async function addNewPaper() {
  const input = dom.newPaperInput.value.trim();
  if (!input) return;

  const submitBtn = dom.newPaperSubmit;
  const btnText = submitBtn.querySelector('.btn-text');
  const btnLoader = submitBtn.querySelector('.btn-loader');
  const formGroup = document.getElementById('addPaperFormGroup');
  const loadingEl = document.getElementById('addPaperLoading');
  const loadingText = document.getElementById('addPaperLoadingText');

  // Show loading state
  btnText.classList.add('hidden');
  btnLoader.classList.remove('hidden');
  submitBtn.disabled = true;
  formGroup.classList.add('hidden');
  loadingEl.classList.remove('hidden');
  loadingText.textContent = 'Fetching paper metadata from arXiv...';

  // Animate loading text to show progress
  const loadingSteps = [
    { text: 'Downloading PDF...', delay: 3000 },
    { text: 'Analyzing paper with AI...', delay: 6000 },
    { text: 'Generating summary...', delay: 12000 },
    { text: 'Almost done...', delay: 25000 },
  ];
  const timers = loadingSteps.map(step =>
    setTimeout(() => { loadingText.textContent = step.text; }, step.delay)
  );

  try {
    const resp = await api('/api/paper/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arxiv_input: input }),
    });
    const data = await resp.json();
    const paper = data.paper;

    // Add to papers
    state.papers.unshift(paper);

    // Re-render cards
    clearPaperCards();
    renderPaperCards();
    updatePaperCount();

    dom.newPaperInput.value = '';
    closeModal(dom.addPaperModal);
    showToast('Paper added successfully', 'success');

    // Auto-expand the new card
    const newCard = dom.paperList.querySelector(`[data-arxiv-id="${paper.arxiv_id}"]`);
    if (newCard) toggleCardExpand(newCard, paper);
  } catch (e) {
    showToast(`Failed: ${e.message}`, 'error');
  } finally {
    timers.forEach(clearTimeout);
    btnText.classList.remove('hidden');
    btnLoader.classList.add('hidden');
    submitBtn.disabled = false;
    formGroup.classList.remove('hidden');
    loadingEl.classList.add('hidden');
  }
}

// === Utilities ===
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  // Fallback for non-HTTPS (e.g. HTTP localhost)
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  return Promise.resolve();
}

function renderMarkdown(text) {
  if (!text) return '';

  // Extract <think>...</think> blocks
  let thinkBlocks = [];
  let cleaned = text.replace(/<think>([\s\S]*?)<\/think>/gi, (_, content) => {
    const idx = thinkBlocks.length;
    thinkBlocks.push(content.trim());
    // Use HTML comment as placeholder (won't be parsed by markdown)
    return `\n\n<!--THINK_BLOCK_${idx}-->\n\n`;
  });

  // Handle unclosed <think> (streaming)
  let pendingThink = '';
  const openMatch = cleaned.match(/<think>([\s\S]*)$/i);
  if (openMatch) {
    pendingThink = openMatch[1].trim();
    cleaned = cleaned.replace(/<think>[\s\S]*$/i, '');
  }

  // Render markdown
  let html;
  if (typeof marked !== 'undefined') {
    html = marked.parse(cleaned);
  } else {
    html = escapeHtml(cleaned);
    html = html.replace(/\n\n+/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    html = '<p>' + html + '</p>';
  }

  // Replace think placeholders (HTML comments are preserved by marked)
  html = html.replace(/<!--THINK_BLOCK_(\d+)-->/g, (match, idx) => {
    const content = thinkBlocks[parseInt(idx)];
    if (content === undefined) return match;
    return `<details class="thinking-block"><summary>Thinking</summary><div class="thinking-content">${escapeHtml(content)}</div></details>`;
  });

  // Pending thinking block
  if (pendingThink) {
    const thinkHtml = `<details class="thinking-block" open><summary>Thinking...</summary><div class="thinking-content">${escapeHtml(pendingThink)}</div></details>`;
    html = thinkHtml + html;
  }

  return html;
}

// === Horizontal Resize ===
function initHorizontalResize() {
  const handle = document.getElementById('resizeHandle');
  const paperSection = document.getElementById('paperListSection');
  const mainEl = document.querySelector('.main');

  if (!handle || !paperSection || !mainEl) return;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paperSection.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.classList.add('resizing-h');

    const onMouseMove = (e) => {
      const diff = e.clientX - startX;
      const newWidth = startWidth + diff;
      const mainWidth = mainEl.getBoundingClientRect().width;
      const pct = (newWidth / mainWidth) * 100;
      if (pct >= 20 && pct <= 70) {
        paperSection.style.width = pct + '%';
      }
    };

    const onMouseUp = () => {
      handle.classList.remove('dragging');
      document.body.classList.remove('resizing-h');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}

// === Vertical Resize ===
function initVerticalResize() {
  const handle = document.getElementById('resizeHandleV');
  const upper = document.getElementById('detailUpper');
  const content = document.getElementById('detailContent');

  if (!handle || !upper || !content) return;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = upper.getBoundingClientRect().height;
    handle.classList.add('dragging');
    document.body.classList.add('resizing-v');

    const onMouseMove = (e) => {
      const diff = e.clientY - startY;
      const newHeight = startHeight + diff;
      const totalHeight = content.getBoundingClientRect().height;
      const pct = (newHeight / totalHeight) * 100;
      if (pct >= 10 && pct <= 80) {
        upper.style.height = pct + '%';
      }
    };

    const onMouseUp = () => {
      handle.classList.remove('dragging');
      document.body.classList.remove('resizing-v');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}

// === Starred Papers ===
async function loadStarred() {
  try {
    const resp = await fetch('/api/starred');
    const data = await resp.json();
    state.starred = data.starred || {};
  } catch {}
}

async function toggleStar(paper, btn) {
  const id = paper.arxiv_id;
  const isStarred = !!state.starred[id];
  try {
    if (isStarred) {
      await api(`/api/paper/${encodeURIComponent(id)}/star`, { method: 'DELETE' });
      delete state.starred[id];
      btn.classList.remove('active');
      btn.querySelector('svg').setAttribute('fill', 'none');
      showToast('Unstarred', 'info');
    } else {
      await api(`/api/paper/${encodeURIComponent(id)}/star`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_data: paper, notes: '' }),
      });
      state.starred[id] = { paper_data: paper, starred_date: new Date().toISOString().slice(0, 10) };
      btn.classList.add('active');
      btn.querySelector('svg').setAttribute('fill', 'currentColor');
      showToast('Starred!', 'success');
    }
  } catch (e) {
    showToast('Failed: ' + e.message, 'error');
  }
}

// === Zotero Export ===
async function checkZoteroStatus() {
  try {
    const resp = await fetch('/api/zotero/status');
    const data = await resp.json();
    state.zoteroConfigured = data.configured;
  } catch {}
}

async function exportToZotero(paper) {
  try {
    await api(`/api/paper/${encodeURIComponent(paper.arxiv_id)}/export-zotero`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: paper.title,
        authors: paper.authors || [],
        abstract: paper.summary || '',
        url: paper.pdf_url || '',
        date: '',
      }),
    });
    showToast('Exported to Zotero!', 'success');
  } catch (e) {
    showToast('Zotero export failed: ' + e.message, 'error');
  }
}

// === Stats ===
async function openStatsModal() {
  openModal(dom.statsModal);
  try {
    const resp = await fetch('/api/stats/summary');
    const data = await resp.json();
    document.getElementById('statToday').textContent = data.today_views;
    document.getElementById('statWeek').textContent = data.week_views;
    document.getElementById('statMonth').textContent = data.month_views;
    document.getElementById('statTotal').textContent = data.total_papers;
    document.getElementById('statChatted').textContent = data.total_chatted;
    document.getElementById('statViews').textContent = data.total_views;
  } catch {}
}

// === Subscriptions ===
async function loadSubscriptions() {
  try {
    const resp = await fetch('/api/subscriptions');
    const data = await resp.json();
    state.subscriptions = data.subscriptions || [];
    renderSubscriptions();
  } catch {}
}

function renderSubscriptions() {
  const list = document.getElementById('subscriptionList');
  if (!list) return;
  list.innerHTML = '';
  state.subscriptions.forEach((sub, i) => {
    const row = document.createElement('div');
    row.className = 'subscription-row';
    row.innerHTML = `
      <label class="sub-toggle">
        <input type="checkbox" ${sub.enabled !== false ? 'checked' : ''} data-idx="${i}">
      </label>
      <span class="sub-keyword">${escapeHtml(sub.keyword)}</span>
      <span class="sub-weight">w:${sub.weight || 1}</span>
      <button class="sub-delete-btn" data-idx="${i}" title="Remove">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    `;
    // Toggle enabled
    row.querySelector('input[type=checkbox]').addEventListener('change', (e) => {
      state.subscriptions[i].enabled = e.target.checked;
      saveSubscriptions();
    });
    // Delete
    row.querySelector('.sub-delete-btn').addEventListener('click', () => {
      state.subscriptions.splice(i, 1);
      saveSubscriptions();
      renderSubscriptions();
    });
    list.appendChild(row);
  });
}

function addSubscription() {
  const kwInput = document.getElementById('newSubKeyword');
  const wInput = document.getElementById('newSubWeight');
  const keyword = kwInput.value.trim();
  if (!keyword) return;
  const weight = parseInt(wInput.value) || 1;
  state.subscriptions.push({ keyword, weight, enabled: true });
  saveSubscriptions();
  renderSubscriptions();
  kwInput.value = '';
  wInput.value = '1';
}

async function saveSubscriptions() {
  try {
    await fetch('/api/subscriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscriptions: state.subscriptions }),
    });
  } catch {}
}

// Also save subscriptions when saving settings
const _origSaveSettings = saveSettings;
saveSettings = function() {
  _origSaveSettings();
  saveSubscriptions();
};

// === Boot ===
init();
