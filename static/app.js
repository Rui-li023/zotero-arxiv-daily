// === State ===
const state = {
  dates: [],
  currentDate: null,
  papers: [],
  selectedPaper: null,
  chatHistory: [],  // per-paper chat: { role, content }
  chatHistories: {}, // arxiv_id -> [messages]
  streaming: false,
  serverLlm: { hasLlm: false, needsPassword: false },
  settings: {
    mode: 'server', // 'server' | 'client'
    serverPassword: '',
    apiKey: '',
    apiBase: '',
    model: '',
  },
};

// === DOM refs ===
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
  detailPanel: $('#detailPanel'),
  detailPlaceholder: $('#detailPlaceholder'),
  detailContent: $('#detailContent'),
  detailClose: $('#detailClose'),
  detailTitle: $('#detailTitle'),
  detailAuthors: $('#detailAuthors'),
  detailAffiliations: $('#detailAffiliations'),
  detailLinks: $('#detailLinks'),
  detailStars: $('#detailStars'),
  detailTldr: $('#detailTldr'),
  chatMessages: $('#chatMessages'),
  chatInput: $('#chatInput'),
  chatSend: $('#chatSend'),
  newPaperInput: $('#newPaperInput'),
  newPaperBtn: $('#newPaperBtn'),
  settingsBtn: $('#settingsBtn'),
  settingsModal: $('#settingsModal'),
  settingsClose: $('#settingsClose'),
  settingsSave: $('#settingsSave'),
};

// === Init ===
async function init() {
  loadSettings();
  bindEvents();
  await checkLlmStatus();
  await loadDates();
}

async function checkLlmStatus() {
  try {
    const resp = await fetch('/api/llm/status');
    const data = await resp.json();
    state.serverLlm.hasLlm = data.has_server_llm;
    state.serverLlm.needsPassword = data.needs_password;
    updateServerHint();
  } catch {}
}

function updateServerHint() {
  const hint = $('#serverHint');
  const pwField = $('#serverPassword');
  if (!state.serverLlm.hasLlm) {
    hint.textContent = 'No server LLM configured. Use client mode instead.';
    hint.style.color = 'var(--error)';
  } else if (state.serverLlm.needsPassword) {
    hint.textContent = 'Password required to use server LLM.';
    hint.style.color = '';
  } else {
    hint.textContent = 'Server LLM available (no password needed).';
    hint.style.color = 'var(--success)';
    pwField.style.display = 'none';
  }
}

// === Settings ===
function loadSettings() {
  try {
    const saved = localStorage.getItem('llmSettings');
    if (saved) {
      Object.assign(state.settings, JSON.parse(saved));
    }
  } catch {}
  applySettingsToForm();
}

function applySettingsToForm() {
  const modeRadios = $$('input[name="llmMode"]');
  modeRadios.forEach(r => { r.checked = r.value === state.settings.mode; });
  $('#serverPassword').value = state.settings.serverPassword || '';
  $('#apiKey').value = state.settings.apiKey || '';
  $('#apiBase').value = state.settings.apiBase || '';
  $('#modelName').value = state.settings.model || '';
  toggleClientSettings();
  updateServerHint();
}

function toggleClientSettings() {
  const clientSection = $('#clientSettings');
  const serverSection = $('#serverSettings');
  const mode = $('input[name="llmMode"]:checked')?.value || 'server';
  clientSection.classList.toggle('hidden', mode !== 'client');
  serverSection.classList.toggle('hidden', mode !== 'server');
}

function saveSettings() {
  const mode = $('input[name="llmMode"]:checked')?.value || 'server';
  state.settings = {
    mode,
    serverPassword: $('#serverPassword').value.trim(),
    apiKey: $('#apiKey').value.trim(),
    apiBase: $('#apiBase').value.trim(),
    model: $('#modelName').value.trim(),
  };
  // Save to localStorage (password is stored locally only, never sent to git)
  localStorage.setItem('llmSettings', JSON.stringify(state.settings));
  dom.settingsModal.classList.remove('visible');
}

// === Events ===
function bindEvents() {
  dom.dateSelect.addEventListener('change', () => {
    loadPapers(dom.dateSelect.value);
  });

  dom.prevDate.addEventListener('click', () => {
    const idx = state.dates.indexOf(state.currentDate);
    if (idx < state.dates.length - 1) {
      dom.dateSelect.value = state.dates[idx + 1];
      loadPapers(state.dates[idx + 1]);
    }
  });

  dom.nextDate.addEventListener('click', () => {
    const idx = state.dates.indexOf(state.currentDate);
    if (idx > 0) {
      dom.dateSelect.value = state.dates[idx - 1];
      loadPapers(state.dates[idx - 1]);
    }
  });

  dom.detailClose.addEventListener('click', closeDetail);

  dom.chatSend.addEventListener('click', sendChat);
  dom.chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });

  dom.newPaperBtn.addEventListener('click', addNewPaper);
  dom.newPaperInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addNewPaper();
  });

  dom.settingsBtn.addEventListener('click', () => {
    applySettingsToForm();
    dom.settingsModal.classList.add('visible');
  });
  dom.settingsClose.addEventListener('click', () => {
    dom.settingsModal.classList.remove('visible');
  });
  dom.settingsModal.addEventListener('click', (e) => {
    if (e.target === dom.settingsModal) dom.settingsModal.classList.remove('visible');
  });
  dom.settingsSave.addEventListener('click', saveSettings);

  $$('input[name="llmMode"]').forEach(r => {
    r.addEventListener('change', toggleClientSettings);
  });
}

// === API ===
async function api(path, options = {}) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return resp;
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

    state.dates.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      dom.dateSelect.appendChild(opt);
    });

    loadPapers(state.dates[0]);
  } catch (e) {
    console.error('Failed to load dates:', e);
    showEmpty();
  }
}

// === Papers ===
async function loadPapers(date) {
  state.currentDate = date;
  dom.loadingState.classList.remove('hidden');
  dom.emptyState.classList.add('hidden');
  clearPaperCards();

  try {
    const resp = await api(`/api/papers?date=${encodeURIComponent(date)}`);
    const data = await resp.json();
    state.papers = data.papers || [];

    dom.loadingState.classList.add('hidden');

    if (state.papers.length === 0) {
      showEmpty();
      return;
    }

    dom.paperCount.textContent = `${state.papers.length} papers`;
    renderPaperCards();
  } catch (e) {
    dom.loadingState.classList.add('hidden');
    showEmpty();
    console.error('Failed to load papers:', e);
  }
}

function clearPaperCards() {
  // Remove paper cards but keep loading/empty states
  dom.paperList.querySelectorAll('.paper-card').forEach(el => el.remove());
}

function showEmpty() {
  dom.loadingState.classList.add('hidden');
  dom.emptyState.classList.remove('hidden');
  dom.paperCount.textContent = '0 papers';
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
  card.style.animationDelay = `${idx * 30}ms`;
  card.dataset.arxivId = paper.arxiv_id;

  const authors = Array.isArray(paper.authors) ? paper.authors : [];
  let authorStr = authors.slice(0, 5).join(', ');
  if (authors.length > 8) {
    authorStr += ', ..., ' + authors.slice(-3).join(', ');
  } else if (authors.length > 5) {
    authorStr += ', ...';
  }

  const affiliations = paper.affiliations
    ? (Array.isArray(paper.affiliations) ? paper.affiliations.join(', ') : paper.affiliations)
    : '';

  const stars = getStarsText(paper.score);

  card.innerHTML = `
    <span class="card-rank">#${idx + 1}</span>
    <div class="card-title">${escapeHtml(paper.title)}</div>
    <div class="card-authors">${escapeHtml(authorStr)}</div>
    ${affiliations ? `<div class="card-affiliations">${escapeHtml(affiliations)}</div>` : ''}
    ${paper.highlight ? `<div class="card-highlight">${escapeHtml(paper.highlight)}</div>` : ''}
    <div class="card-footer">
      <span class="card-stars">${stars}</span>
      <span class="card-id">${escapeHtml(paper.arxiv_id)}</span>
    </div>
  `;

  card.addEventListener('click', () => openDetail(paper));
  return card;
}

function getStarsText(score) {
  if (!score || score <= 6) return '';
  const low = 6, high = 8;
  if (score >= high) return '\u2B50'.repeat(5);
  const interval = (high - low) / 10;
  const num = Math.ceil((score - low) / interval);
  const full = Math.floor(num / 2);
  const half = num % 2;
  return '\u2B50'.repeat(full) + (half ? '\u00BD' : '');
}

// === Detail Panel ===
function openDetail(paper) {
  state.selectedPaper = paper;

  // Mark active card
  dom.paperList.querySelectorAll('.paper-card').forEach(c => c.classList.remove('active'));
  const activeCard = dom.paperList.querySelector(`[data-arxiv-id="${paper.arxiv_id}"]`);
  if (activeCard) activeCard.classList.add('active');

  // Fill detail
  dom.detailTitle.textContent = paper.title;

  const authors = Array.isArray(paper.authors) ? paper.authors : [];
  let authorStr = authors.slice(0, 5).join(', ');
  if (authors.length > 8) {
    authorStr += ', ..., ' + authors.slice(-3).join(', ');
  } else if (authors.length > 5) {
    authorStr += ', ...';
  }
  dom.detailAuthors.textContent = authorStr;

  const affiliations = paper.affiliations
    ? (Array.isArray(paper.affiliations) ? paper.affiliations.join(', ') : paper.affiliations)
    : '';
  dom.detailAffiliations.textContent = affiliations;

  // Links
  let linksHtml = `<a class="detail-link" href="${escapeHtml(paper.pdf_url)}" target="_blank">PDF</a>`;
  linksHtml += `<a class="detail-link" href="https://arxiv.org/abs/${escapeHtml(paper.arxiv_id)}" target="_blank">${escapeHtml(paper.arxiv_id)}</a>`;
  if (paper.code_url) {
    linksHtml += `<a class="detail-link" href="${escapeHtml(paper.code_url)}" target="_blank">Code</a>`;
  }
  dom.detailLinks.innerHTML = linksHtml;

  // Stars
  dom.detailStars.textContent = getStarsText(paper.score);

  // TLDR
  dom.detailTldr.innerHTML = paper.tldr || '<p style="color:var(--text-muted)">No analysis available</p>';

  // Show detail
  dom.detailPlaceholder.classList.add('hidden');
  dom.detailContent.classList.remove('hidden');
  dom.detailPanel.classList.add('open'); // for mobile

  // Chat: restore or init
  loadChatForPaper(paper);
}

function closeDetail() {
  dom.detailPlaceholder.classList.remove('hidden');
  dom.detailContent.classList.add('hidden');
  dom.detailPanel.classList.remove('open');
  dom.paperList.querySelectorAll('.paper-card').forEach(c => c.classList.remove('active'));
  state.selectedPaper = null;
}

// === Chat ===
function loadChatForPaper(paper) {
  const id = paper.arxiv_id;
  if (!state.chatHistories[id]) {
    state.chatHistories[id] = [];
    // Auto-send initial analysis request
    dom.chatMessages.innerHTML = '';
    autoAnalyze(paper);
  } else {
    // Restore chat display
    dom.chatMessages.innerHTML = '';
    state.chatHistories[id].forEach(msg => {
      appendChatBubble(msg.role, msg.content);
    });
  }
}

async function autoAnalyze(paper) {
  const systemMsg = {
    role: 'system',
    content: `You are an expert AI research assistant. The user is reading an arXiv paper. Help them understand the paper and answer questions about it. Be concise and insightful. Use the paper info provided for context.

Paper Title: ${paper.title}
Paper Abstract: ${paper.summary || ''}
ArXiv ID: ${paper.arxiv_id}`
  };

  const userMsg = {
    role: 'user',
    content: `Please provide a brief, insightful analysis of this paper. Focus on: 1) The key innovation 2) How it differs from prior work 3) Potential impact. Keep it concise (3-4 paragraphs).`
  };

  const id = paper.arxiv_id;
  state.chatHistories[id] = [systemMsg, userMsg];

  appendChatBubble('user', 'Analyze this paper');
  await streamChat(id);
}

async function sendChat() {
  if (state.streaming || !state.selectedPaper) return;
  const text = dom.chatInput.value.trim();
  if (!text) return;

  const id = state.selectedPaper.arxiv_id;
  const userMsg = { role: 'user', content: text };
  state.chatHistories[id].push(userMsg);

  appendChatBubble('user', text);
  dom.chatInput.value = '';
  dom.chatInput.style.height = 'auto';

  await streamChat(id);
}

async function streamChat(arxivId) {
  state.streaming = true;
  dom.chatSend.disabled = true;

  const bubble = appendChatBubble('assistant', '');
  bubble.classList.add('streaming-cursor');

  const messages = state.chatHistories[arxivId];

  const body = { messages };
  if (state.settings.mode === 'client' && state.settings.apiKey) {
    body.api_key = state.settings.apiKey;
    body.base_url = state.settings.apiBase || undefined;
    body.model = state.settings.model || undefined;
  } else if (state.settings.mode === 'server' && state.settings.serverPassword) {
    body.server_password = state.settings.serverPassword;
  }

  let fullText = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
            bubble.innerHTML = renderMarkdown(fullText);
            scrollChatToBottom();
          }
        } catch (parseErr) {
          if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr;
        }
      }
    }
  } catch (e) {
    if (!fullText) {
      bubble.classList.add('error');
      bubble.textContent = `Error: ${e.message}`;
    } else {
      const errBubble = appendChatBubble('assistant', '');
      errBubble.classList.add('error');
      errBubble.textContent = `Stream interrupted: ${e.message}`;
    }
  }

  bubble.classList.remove('streaming-cursor');
  state.streaming = false;
  dom.chatSend.disabled = false;

  // Save assistant message
  if (fullText) {
    state.chatHistories[arxivId].push({ role: 'assistant', content: fullText });
  }
}

function appendChatBubble(role, content) {
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  if (role === 'system') return div; // don't display system messages
  div.innerHTML = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);
  dom.chatMessages.appendChild(div);
  scrollChatToBottom();
  return div;
}

function scrollChatToBottom() {
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

// === New Paper ===
async function addNewPaper() {
  const input = dom.newPaperInput.value.trim();
  if (!input) return;

  dom.newPaperBtn.classList.add('loading');
  dom.newPaperBtn.disabled = true;

  try {
    const resp = await api('/api/paper/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arxiv_input: input }),
    });
    const data = await resp.json();
    const paper = data.paper;

    // Add to current papers and render
    state.papers.unshift(paper);
    const card = createPaperCard(paper, 0);
    // Re-number existing cards
    dom.paperList.querySelectorAll('.paper-card .card-rank').forEach((el, i) => {
      el.textContent = `#${i + 2}`;
    });
    const firstCard = dom.paperList.querySelector('.paper-card');
    if (firstCard) {
      dom.paperList.insertBefore(card, firstCard);
    } else {
      dom.emptyState.classList.add('hidden');
      dom.paperList.appendChild(card);
    }
    dom.paperCount.textContent = `${state.papers.length} papers`;
    dom.newPaperInput.value = '';

    // Auto-open detail
    openDetail(paper);
  } catch (e) {
    alert(`Failed to add paper: ${e.message}`);
  } finally {
    dom.newPaperBtn.classList.remove('loading');
    dom.newPaperBtn.disabled = false;
  }
}

// === Utilities ===
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function renderMarkdown(text) {
  if (!text) return '';
  // Simple markdown: bold, italic, code, paragraphs
  let html = escapeHtml(text);
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code style="background:var(--bg-primary);padding:1px 5px;border-radius:3px;font-size:0.9em">$1</code>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Line breaks to paragraphs
  html = html.replace(/\n\n+/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');
  html = '<p>' + html + '</p>';
  return html;
}

// === Boot ===
init();
