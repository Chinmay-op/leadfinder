/* ═══════════════════════════════════════════════════════════════════
   Lead Finder — Chat UI Application Logic
   Flow: Keyword → ICP → Approve → LinkedIn Scrape → Contacts → Done
   ═══════════════════════════════════════════════════════════════════ */

// ── Utils ─────────────────────────────────────────────────────────
const API_BASE_URL = 'http://leadscribeai.centralindia.cloudapp.azure.com:8000'; // Update port to 80/443 if you use Nginx/Caddy

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function scrollToBottom() {
  const thread = document.getElementById('chat-thread');
  if (thread) {
    requestAnimationFrame(() => {
      thread.scrollTop = thread.scrollHeight;
    });
  }
}

function scoreTier(score) {
  score = parseInt(score) || 0;
  if (score >= 80) return 'perfect';
  if (score >= 60) return 'good';
  if (score >= 40) return 'possible';
  return 'poor';
}

function initials(name) {
  if (!name) return '?';
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

// ── State ─────────────────────────────────────────────────────────
const state = {
  phase: 'idle', // idle | generating_icp | awaiting_approval | scraping | finding_contacts | enriching | done
  icp: null,
  leads: [],
  pipelineRunning: false,
  viewMode: 'list',
  sessionId: null, // Tracks current pipeline run to filter results
  token: localStorage.getItem('lf_token') || null,
  role: null,
  username: null
};

// ── Auth Handling ─────────────────────────────────────────────────
function setAuth(token, role, username) {
  state.token = token;
  state.role = role;
  state.username = username;
  if (token) localStorage.setItem('lf_token', token);
  else localStorage.removeItem('lf_token');
  
  if (token) {
    document.getElementById('login-overlay').style.display = 'none';
    const profile = document.getElementById('user-profile');
    profile.style.display = 'flex';
    profile.style.alignItems = 'center';
    document.getElementById('user-name').textContent = username || 'User';
    document.getElementById('user-role-badge').textContent = role || 'user';
    initSSE(); // Connect SSE only when authenticated
    loadSessions(); // Load history sidebar
  } else {
    document.getElementById('login-overlay').style.display = 'flex';
    document.getElementById('user-profile').style.display = 'none';
    if (eventSource) { eventSource.close(); eventSource = null; }
  }
}

// ── Session History ───────────────────────────────────────────────
async function loadSessions() {
  try {
    const data = await fetchJSON('/sessions');
    renderSessionList(data.sessions || []);
  } catch (err) {
    console.error('Failed to load sessions', err);
  }
}

function renderSessionList(sessions) {
  const container = document.getElementById('session-list');
  if (!container) return;
  container.innerHTML = '';
  
  if (sessions.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px;">No previous searches.</div>';
    return;
  }
  
  sessions.forEach(s => {
    const div = document.createElement('div');
    div.className = 'session-item';
    if (s.session_id === state.sessionId) div.classList.add('active');
    
    // Create a title from keywords or fallback
    let title = 'New Search';
    if (s.search_keywords && s.search_keywords.length > 0) {
      title = s.search_keywords[0];
    } else if (s.source_pipeline) {
      title = s.source_pipeline;
    }
    
    // Format date
    const date = new Date(s.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    
    div.innerHTML = `
      <div class="session-title" title="${esc(title)}">${esc(title)}</div>
      <div class="session-meta">${date} · ${s.stats?.total_companies || 0} leads</div>
    `;
    
    div.onclick = () => loadSessionData(s.session_id);
    container.appendChild(div);
  });
}

async function loadSessionData(sid) {
  try {
    if (state.pipelineRunning) return;
    
    // Clear chat thread
    document.getElementById('chat-thread').innerHTML = '';
    state.sessionId = sid;
    
    const url = new URL(window.location);
    url.searchParams.set('session_id', sid);
    window.history.pushState({}, '', url);
    
    addAIMessage('Loading session data...');
    
    const data = await fetchJSON(`/sessions/${sid}`);
    
    document.getElementById('chat-thread').innerHTML = '';
    
    // Re-render sidebar to highlight active
    loadSessions();
    
    // Show summary message
    let keywords = (data.search_keywords || []).join(', ');
    let html = `Loaded previous search: <strong>${esc(keywords || 'Unknown')}</strong><br>`;
    html += `Found ${data.stats?.total_companies || 0} companies, ${data.stats?.emails_found || 0} emails.<br><br>`;
    html += `<button class="btn" onclick="displayLeads()">View Leads</button>`;
    
    addAIMessage(html);
    
    // Replace state leads
    state.leads = data.companies || [];
    state.phase = 'done';
    
    updateStatus('Ready', false);
    
  } catch (err) {
    console.error('Failed to load session data', err);
    addAIMessage(`Error loading session: ${err.message}`);
  }
}

function startNewSearch() {
  if (state.pipelineRunning) return;
  state.sessionId = null;
  state.phase = 'idle';
  state.leads = [];
  state.icp = null;
  
  const url = new URL(window.location);
  url.searchParams.delete('session_id');
  window.history.pushState({}, '', url);

  document.getElementById('chat-thread').innerHTML = '';
  addAIMessage("Welcome! Describe your target customers or enter a keyword, and I'll find matching companies with decision-maker contacts.");
  
  setInputEnabled(true);
  updateStatus('Ready', false);
  loadSessions(); // to remove active highlight
  
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = '';
    input.focus();
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const u = document.getElementById('login-username').value;
  const p = document.getElementById('login-password').value;
  const err = document.getElementById('login-error');
  err.style.display = 'none';
  
  const form = new URLSearchParams();
  form.append('username', u);
  form.append('password', p);
  
  try {
    const res = await fetch(API_BASE_URL + '/api/auth/login', {
      method: 'POST',
      body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
    if (!res.ok) {
      throw new Error('Invalid username or password');
    }
    const data = await res.json();
    setAuth(data.access_token, data.role, u);
    document.getElementById('login-password').value = '';
    
    // Check if we need to load anything on initial load
    // Not needed, initial load has nothing unless they query manually
  } catch(error) {
    err.textContent = error.message;
    err.style.display = 'block';
  }
}

function handleLogout() {
  setAuth(null, null, null);
}

async function verifyAuthOnLoad() {
  if (!state.token) {
    setAuth(null, null, null);
    return false;
  }
  try {
    const data = await fetchJSON('/api/auth/me');
    setAuth(state.token, data.role, data.username);
    return true;
  } catch (err) {
    setAuth(null, null, null);
    return false;
  }
}

// ── Message Rendering ─────────────────────────────────────────────
function addUserMessage(text) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'msg msg-user';
  div.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  thread.appendChild(div);
  scrollToBottom();
}

function addAIMessage(html) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'msg msg-ai';
  div.innerHTML = `
    <div class="avatar">✦</div>
    <div class="bubble">${html}</div>
  `;
  thread.appendChild(div);
  scrollToBottom();
  return div.querySelector('.bubble');
}

function addStatusMessage(text, type = 'loading') {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'status-msg';
  
  const inner = type === 'loading'
    ? `<div class="spinner"></div>${esc(text)}`
    : esc(text);
  
  const cls = type === 'done' ? 'status-bubble done'
    : type === 'error' ? 'status-bubble error'
    : 'status-bubble';
  
  div.innerHTML = `<div class="${cls}">${inner}</div>`;
  thread.appendChild(div);
  scrollToBottom();
  return div;
}

function updateStatusMessage(el, text, type = 'loading') {
  if (!el) return;
  const bubble = el.querySelector('.status-bubble');
  if (!bubble) return;
  
  bubble.className = type === 'done' ? 'status-bubble done'
    : type === 'error' ? 'status-bubble error'
    : 'status-bubble';
  
  const inner = type === 'loading'
    ? `<div class="spinner"></div>${esc(text)}`
    : esc(text);
  bubble.innerHTML = inner;
  scrollToBottom();
}

// ── ICP Card Rendering ────────────────────────────────────────────
function renderICPCard(icp) {
  const roles = icp.target_roles || [];
  let rolesHtml = '<div class="icp-roles-list" style="display:flex; flex-direction:column; gap:6px;">';
  roles.forEach((role, idx) => {
    rolesHtml += `
      <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
        <input type="checkbox" class="icp-role-cb" value="${esc(role)}" checked />
        <span style="font-size:13px;">${esc(role)}</span>
      </label>
    `;
  });
  rolesHtml += '</div>';

  const industries = (icp.target_industries || []).join(', ');
  const keywords = (icp.search_keywords || []).join(', ');
  const pains = (icp.pain_points || []).join(', ');
  const exclusions = (icp.exclusions || []).join(', ');

  const html = `
    Here's the Ideal Customer Profile I generated:
    <div class="icp-card">
      <div class="icp-card-title">Ideal Customer Profile</div>
      <div class="icp-grid">
        <div style="grid-column: 1 / -1;">
          <div class="icp-field-label">Target Roles</div>
          <div class="icp-field-value" style="margin-top:6px;">${rolesHtml}</div>
        </div>
        <div>
          <div class="icp-field-label">Industries</div>
          <div class="icp-field-value">${esc(industries) || '—'}</div>
        </div>
        <div>
          <div class="icp-field-label">Company Size</div>
          <div class="icp-field-value">${icp.company_size_min || 50}–${icp.company_size_max || 5000} employees</div>
        </div>
        <div>
          <div class="icp-field-label">Search Keywords</div>
          <div class="icp-field-value">${esc(keywords) || '—'}</div>
        </div>
        <div>
          <div class="icp-field-label">Pain Points</div>
          <div class="icp-field-value">${esc(pains) || '—'}</div>
        </div>
        <div>
          <div class="icp-field-label">Exclusions</div>
          <div class="icp-field-value">${esc(exclusions) || '—'}</div>
        </div>
      </div>
      ${icp.value_proposition ? `<div style="margin-top:10px;font-size:12px;color:var(--text-muted)"><em>${esc(icp.value_proposition)}</em></div>` : ''}
      <div class="icp-actions">
        <button class="btn btn-primary" id="btn-approve-icp" style="width: 100%; font-weight: bold;">Start Lead Generation</button>
      </div>
    </div>
  `;
  
  const bubble = addAIMessage(html);
  
  // Bind button
  bubble.querySelector('#btn-approve-icp').onclick = () => {
    // Gather selected roles
    const checkedRoles = Array.from(bubble.querySelectorAll('.icp-role-cb:checked')).map(cb => cb.value);
    icp.target_roles = checkedRoles;
    
    // Disable button to prevent double-clicks
    bubble.querySelector('#btn-approve-icp').disabled = true;
    bubble.querySelector('#btn-approve-icp').textContent = 'Starting...';
    
    approveICP(icp);
  };
}

// ── View Switching & Rendering ─────────────────────────────────────
function switchView(resultId, mode) {
  state.viewMode = mode;
  
  // Update toggle buttons in DOM within the specific view toggle parent
  const contentDiv = document.getElementById(resultId);
  if (!contentDiv) return;

  const toggleContainer = contentDiv.previousElementSibling;
  if (toggleContainer) {
    toggleContainer.querySelectorAll('.btn-toggle').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  }
  
  if (mode === 'kanban') {
    contentDiv.innerHTML = generateKanbanViewHtml(state.leads);
  } else {
    contentDiv.innerHTML = generateListViewHtml(state.leads);
  }
}

function renderResults(leads) {
  state.leads = leads; // store in state for view switching
  const resultId = 'results-' + Date.now();

  const html = `
    Found <strong>${leads.length}</strong> companies. Here are your leads:
    <div class="view-toggle" style="margin-top: 12px;">
      <button class="btn btn-sm btn-toggle ${state.viewMode === 'list' ? 'active' : ''}" data-mode="list" onclick="switchView('${resultId}', 'list')">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
        List
      </button>
      <button class="btn btn-sm btn-toggle ${state.viewMode === 'kanban' ? 'active' : ''}" data-mode="kanban" onclick="switchView('${resultId}', 'kanban')">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="18" rx="2"></rect><rect x="14" y="3" width="7" height="18" rx="2"></rect></svg>
        Kanban
      </button>
    </div>
    <div id="${resultId}" class="results-content-area">
      ${state.viewMode === 'kanban' ? generateKanbanViewHtml(leads) : generateListViewHtml(leads)}
    </div>
  `;
  
  const bubble = addAIMessage(html);
  setTimeout(() => {
    if (bubble && bubble.parentElement) {
      bubble.parentElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, 100);
}

function generateKanbanViewHtml(leads) {
  const columns = {
    perfect: { label: 'Perfect Match (80-100)', color: 'var(--score-perfect)', leads: [] },
    good: { label: 'Good Fit (60-79)', color: 'var(--score-good)', leads: [] },
    possible: { label: 'Possible Fit (40-59)', color: 'var(--score-possible)', leads: [] },
    poor: { label: 'Poor Fit (0-39)', color: 'var(--score-poor)', leads: [] }
  };

  leads.forEach((lead, i) => {
    // We inject the original index into the lead object temporarily so openModal works
    lead._originalIndex = i;
    const score = parseInt(lead.icp_match_score) || parseInt(lead.fit_score) || 0;
    const tier = scoreTier(score);
    if (columns[tier]) columns[tier].leads.push(lead);
  });

  let html = '<div class="kanban-board">';
  
  for (const [tier, col] of Object.entries(columns)) {
    if (col.leads.length === 0 && tier === 'poor') continue; // Hide empty poor column to save space
    
    html += `
      <div class="kanban-column">
        <div class="kanban-column-header" style="border-top: 3px solid ${col.color}">
          <span>${col.label}</span>
          <span class="kanban-column-count">${col.leads.length}</span>
        </div>
        <div class="kanban-column-body">
    `;
    
    col.leads.forEach(lead => {
      html += generateSingleCompanyCardHtml(lead, lead._originalIndex);
    });
    
    html += `
        </div>
      </div>
    `;
  }
  
  html += '</div>';
  return html;
}

function generateListViewHtml(leads) {
  let cardsHtml = '<div class="results-container">';
  leads.forEach((lead, i) => {
    cardsHtml += generateSingleCompanyCardHtml(lead, i);
  });
  cardsHtml += '</div>';
  return cardsHtml;
}

function generateSingleCompanyCardHtml(lead, index) {
  const score = parseInt(lead.icp_match_score) || parseInt(lead.fit_score) || 0;
  const tier = scoreTier(score);
  const contacts = lead.contacts || [];
  
  let contactsHtml = '';
  if (contacts.length > 0) {
    contactsHtml = '<div class="contacts-list">';
    contacts.forEach(c => {
      const name = c.full_name || c.name || `${c.first_name || ''} ${c.last_name || ''}`.trim() || 'Unknown';
      const title = c.title || c.position || '';
      const email = c.email || '';
      const phone = c.phone || '';
      const li = c.linkedin_url || '';
      
      contactsHtml += `
        <div class="contact-chip">
          <div class="contact-chip-icon">${esc(initials(name))}</div>
          <div class="contact-chip-info">
            <div class="contact-chip-name">${esc(name)}</div>
            ${title ? `<div class="contact-chip-title">${esc(title)}</div>` : ''}
          </div>
          <div class="contact-chip-details">
            ${email ? `<span class="contact-chip-email">✉ ${esc(email)}</span>` : ''}
            ${phone ? `<span class="contact-chip-phone">📞 ${esc(phone)}</span>` : ''}
            ${li ? `<span class="contact-chip-linkedin" style="margin-left:6px;"><a href="${esc(li)}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;">🔗 LinkedIn</a></span>` : ''}
          </div>
        </div>
      `;
    });
    contactsHtml += '</div>';
  }
  
  // Fallback: if no structured contacts, show top-level email/phone
  if (contacts.length === 0 && (lead.email || lead.phone)) {
    contactsHtml = '<div class="contacts-list">';
    contactsHtml += `
      <div class="contact-chip">
        <div class="contact-chip-icon">✉</div>
        <div class="contact-chip-info">
          <div class="contact-chip-name">Company Contact</div>
        </div>
        <div class="contact-chip-details">
          ${lead.email ? `<span class="contact-chip-email">✉ ${esc(lead.email)}</span>` : ''}
          ${lead.phone ? `<span class="contact-chip-phone">📞 ${esc(lead.phone)}</span>` : ''}
        </div>
      </div>
    `;
    contactsHtml += '</div>';
  }
  
  const meta = [lead.industry, lead.company_size, lead.location].filter(Boolean).join(' · ');
  
  return `
    <div class="company-card" data-index="${index}" onclick="openModal(${index})">
      <div class="company-card-header">
        <div>
          <div class="company-card-name">${esc(lead.company_name || 'Unknown')}</div>
          ${meta ? `<div class="company-card-meta">${esc(meta)}</div>` : ''}
        </div>
        ${score > 0 ? `<div class="score-badge score-${tier}">${score}</div>` : ''}
      </div>
      ${lead.fit_reason || lead.icp_match_reason ? `<div class="company-card-reason">${esc(lead.icp_match_reason || lead.fit_reason)}</div>` : ''}
      ${contactsHtml ? `
        <div class="company-card-actions" style="margin-top: 12px;">
          <button class="btn btn-sm" style="font-size: 12px; padding: 4px 12px; font-weight: 500;" onclick="event.stopPropagation(); const c = this.parentElement.nextElementSibling; if (c.style.display === 'none') { c.style.display = 'block'; this.textContent = 'Hide Contacts'; } else { c.style.display = 'none'; this.textContent = 'Show Contacts'; }">
            Show Contacts
          </button>
        </div>
        <div class="inline-contacts-container" style="display: none; margin-top: 12px; border-top: 1px solid var(--border-color); padding-top: 12px;">
          ${contactsHtml}
        </div>
      ` : ''}
    </div>
  `;
}

function renderSummary(leads) {
  const total = leads.length;
  const emailCount = leads.filter(l => {
    if (l.email) return true;
    if (l.contacts && l.contacts.some(c => c.email)) return true;
    return false;
  }).length;
  const phoneCount = leads.filter(l => {
    if (l.phone) return true;
    if (l.contacts && l.contacts.some(c => c.phone)) return true;
    return false;
  }).length;
  const contactCount = leads.reduce((sum, l) => sum + (l.contacts ? l.contacts.length : 0), 0);

  const html = `
    Pipeline complete!
    <div class="summary-card">
      <div class="summary-stats">
        <div class="summary-stat">
          <div class="summary-stat-num">${total}</div>
          <div class="summary-stat-label">Companies</div>
        </div>
        <div class="summary-stat">
          <div class="summary-stat-num">${contactCount}</div>
          <div class="summary-stat-label">Contacts</div>
        </div>
        <div class="summary-stat">
          <div class="summary-stat-num">${emailCount}</div>
          <div class="summary-stat-label">With Emails</div>
        </div>
        <div class="summary-stat">
          <div class="summary-stat-num">${phoneCount}</div>
          <div class="summary-stat-label">With Phones</div>
        </div>
      </div>
      <div class="summary-actions">
        <button class="btn btn-primary" onclick="exportXLSX()">↓ Export XLSX</button>
        <button class="btn" onclick="startNewSearch()">+ New Search</button>
      </div>
    </div>
  `;
  addAIMessage(html);
}

function displayLeads() {
  if (state.leads && state.leads.length > 0) {
    renderResults(state.leads);
  } else {
    addAIMessage('No leads loaded. Try running a new search.');
  }
}

// ── Modal ─────────────────────────────────────────────────────────
function openModal(index) {
  const lead = state.leads[index];
  if (!lead) return;
  
  const score = parseInt(lead.icp_match_score) || parseInt(lead.fit_score) || 0;
  const tier = scoreTier(score);
  
  document.getElementById('modal-strip').className = `modal-score-strip ${tier}`;
  document.getElementById('modal-title').textContent = lead.company_name || 'Unknown';
  
  // Body
  const body = document.getElementById('modal-body');
  let html = '';
  
  const fields = [
    ['🏢', lead.industry],
    ['📍', lead.location],
    ['🌐', lead.website, true],
    ['👥', lead.company_size],
    ['📊', score > 0 ? `Score: ${score}/100` : null],
  ];
  fields.forEach(([icon, val, isLink]) => {
    if (!val) return;
    const display = isLink
      ? `<a href="${val.startsWith('http') ? val : 'http://' + val}" target="_blank" rel="noopener">${esc(val)}</a>`
      : esc(String(val));
    html += `<div class="modal-field"><span class="modal-field-icon">${icon}</span><span class="modal-field-value">${display}</span></div>`;
  });
  
  if (lead.description) {
    html += `<div class="modal-description">${esc(lead.description)}</div>`;
  }
  
  if (lead.icp_match_reason || lead.fit_reason) {
    html += `<div class="modal-description" style="font-style:italic">${esc(lead.icp_match_reason || lead.fit_reason)}</div>`;
  }
  
  // Contacts
  const contacts = lead.contacts || [];
  if (contacts.length > 0) {
    html += '<div class="modal-contacts-title">Contacts</div>';
    contacts.forEach(c => {
      const name = c.full_name || c.name || `${c.first_name || ''} ${c.last_name || ''}`.trim() || 'Unknown';
      const title = c.title || c.position || '';
      const email = c.email || '';
      const phone = c.phone || '';
      const li = c.linkedin_url || '';
      
      html += `<div class="modal-contact-item">
        <span class="modal-contact-name">${esc(name)}</span>
        ${title ? `<span class="modal-contact-title">· ${esc(title)}</span>` : ''}
        ${c.seniority ? `<span class="modal-contact-title">· ${esc(c.seniority)}</span>` : ''}
        ${email ? `<div class="modal-contact-detail">✉ ${esc(email)}</div>` : ''}
        ${phone ? `<div class="modal-contact-detail">📞 ${esc(phone)}</div>` : ''}
        ${li ? `<div class="modal-contact-detail">🔗 <a href="${esc(li)}" target="_blank" style="color:var(--accent)">LinkedIn</a></div>` : ''}
      </div>`;
    });
  }
  
  body.innerHTML = html;
  
  // Footer
  const footer = document.getElementById('modal-footer');
  footer.innerHTML = '';
  if (lead.website) {
    footer.innerHTML += `<a class="btn" href="${lead.website.startsWith('http') ? lead.website : 'http://' + lead.website}" target="_blank" rel="noopener">🌐 Website</a>`;
  }
  if (lead.linkedin_url) {
    footer.innerHTML += `<a class="btn" href="${esc(lead.linkedin_url)}" target="_blank" rel="noopener">🔗 LinkedIn</a>`;
  }
  
  document.getElementById('modal-overlay').classList.add('open');
  document.getElementById('modal-overlay').setAttribute('aria-hidden', 'false');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.getElementById('modal-overlay').setAttribute('aria-hidden', 'true');
}

async function fetchJSON(url, opts = {}) {
  if (url.startsWith('/api/')) {
    url = API_BASE_URL + url;
  }
  const fetchOpts = { 
    headers: { 
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache'
    } 
  };
  if (state.token) {
    fetchOpts.headers['Authorization'] = `Bearer ${state.token}`;
  }
  if (opts.method) fetchOpts.method = opts.method;
  if (opts.body) fetchOpts.body = JSON.stringify(opts.body);
  
  // Prevent browser caching for auth checks
  fetchOpts.cache = 'no-store';
  
  const res = await fetch(url, fetchOpts);
  if (res.status === 401) {
    setAuth(null, null, null); // Token expired or invalid
    throw new Error(`Unauthorized (401)`);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Pipeline Orchestration ────────────────────────────────────────
async function handleUserInput(text) {
  if (!text.trim() || state.pipelineRunning) return;
  
  addUserMessage(text);
  state.pipelineRunning = true;
  setInputEnabled(false);
  
  // Step 1: Generate ICP
  state.phase = 'generating_icp';
  updateStatus('Generating ICP…', true);
  const statusEl = addStatusMessage('Generating Ideal Customer Profile…');
  
  try {
    await fetchJSON('/api/icp/generate', {
      method: 'POST',
      body: { description: text.trim() },
    });
    // Wait for ICP to be generated (SSE will deliver it)
    // The SSE handler will pick up the ICP and render it
  } catch (err) {
    updateStatusMessage(statusEl, `Error: ${err.message}`, 'error');
    updateStatus('Error', false);
    state.pipelineRunning = false;
    setInputEnabled(true);
  }
}

async function approveICP(icp) {
  // Disable the approve/edit buttons
  const approveBtn = document.getElementById('btn-approve-icp');
  const editBtn = document.getElementById('btn-edit-icp');
  if (approveBtn) { approveBtn.disabled = true; approveBtn.textContent = '✓ Approved'; }
  if (editBtn) editBtn.remove();
  
  addUserMessage('Approved! Start searching.');
  
  try {
    // Save the ICP
    await fetchJSON('/api/icp/approve', {
      method: 'POST',
      body: icp,
    });
    
    // Step 2: Scrape LinkedIn
    state.phase = 'scraping';
    updateStatus('Scraping LinkedIn…', true);
    const scrapeStatus = addStatusMessage('Searching LinkedIn for companies…');
    
    const isTestMode = document.getElementById('test-mode-toggle').checked;
    await fetchJSON(`/api/scrape/linkedin?test_mode=${isTestMode}`, { method: 'POST' });
    // SSE will handle progress; __DONE__ triggers next step
    
  } catch (err) {
    addAIMessage(`Something went wrong: <strong>${esc(err.message)}</strong>`);
    updateStatus('Error', false);
    state.pipelineRunning = false;
    setInputEnabled(true);
  }
}

function editICP(icp) {
  // Simple: let user edit in input bar
  const input = document.getElementById('chat-input');
  input.value = JSON.stringify(icp, null, 2);
  input.focus();
  addAIMessage('Edit the ICP JSON in the input box below and send it to approve.');
  
  // Change the input handler temporarily
  state.phase = 'editing_icp';
}

async function continueAfterContacts() {
  // Step 4: Enrich emails via website scraping (fallback)
  state.phase = 'enriching';
  updateStatus('Enriching emails…', true);
  addStatusMessage('Scraping company websites for additional emails and phone numbers…');
  
  try {
    const result = await fetchJSON('/api/enrich/email', { method: 'POST' });
    if (result.error) {
      addAIMessage(`Email enrichment skipped: <strong>${esc(result.error)}</strong>`);
      await finishPipeline();
    }
    // SSE will handle progress
  } catch (err) {
    addAIMessage(`Email enrichment failed: <strong>${esc(err.message)}</strong>`);
    await finishPipeline();
  }
}

async function finishPipeline() {
  state.phase = 'done';
  updateStatus('Ready', false);
  
  // Load final leads — filtered to current session only
  try {
    const url = state.sessionId
      ? `/api/leads?session_id=${encodeURIComponent(state.sessionId)}`
      : '/api/leads';
    const data = await fetchJSON(url);
    state.leads = data.leads || [];
    
    if (state.leads.length > 0) {
      renderResults(state.leads);
      renderSummary(state.leads);
    } else {
      addAIMessage('No companies were found in this search. Try a different keyword.');
    }
  } catch (err) {
    addAIMessage(`Could not load results: ${esc(err.message)}`);
  }
  
  loadSessions(); // Update the sidebar with the new completed session
  state.pipelineRunning = false;
  setInputEnabled(true);
}

// Duplicate startNewSearch removed

// ── Export ─────────────────────────────────────────────────────────
async function exportXLSX() {
  try {
    const exportUrl = state.sessionId
      ? `${API_BASE_URL}/api/export?session_id=${encodeURIComponent(state.sessionId)}`
      : `${API_BASE_URL}/api/export`;
    const res = await fetch(exportUrl);
    if (!res.ok) throw new Error('No data to export');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'final_leads.xlsx';
    document.body.appendChild(a); a.click();
    URL.revokeObjectURL(url); a.remove();
    addStatusMessage('✓ Excel file downloaded', 'done');
  } catch (err) {
    addStatusMessage(`Export failed: ${err.message}`, 'error');
  }
}

// ── SSE ───────────────────────────────────────────────────────────
let eventSource = null;
let lastStatusEl = null;

function initSSE() {
  if (eventSource) eventSource.close();
  if (!state.token) return;
  eventSource = new EventSource(API_BASE_URL + '/api/progress?token=' + encodeURIComponent(state.token));
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.keepalive) return;
      
      const msg = data.message || '';
      
      // Status transitions
      if (msg.startsWith('__STATUS__:')) {
        const newStatus = msg.split(':')[1];
        handleStatusTransition(newStatus);
        return;
      }
      
      // Done signal
      if (msg === '__DONE__') {
        handleDoneSignal();
        return;
      }
      
      // ICP generated event (JSON message)
      if (msg.startsWith('{')) {
        try {
          const parsed = JSON.parse(msg);
          if (parsed.type === 'icp_generated' && parsed.icp) {
            state.icp = parsed.icp;
            state.phase = 'awaiting_approval';
            updateStatus('Awaiting ICP approval', false);
            // Remove the loading status
            if (lastStatusEl) {
              updateStatusMessage(lastStatusEl, '✓ ICP generated', 'done');
              lastStatusEl = null;
            }
            renderICPCard(parsed.icp);
            return;
          }
          if (parsed.type === 'session_id' && parsed.session_id) {
            state.sessionId = parsed.session_id;
            const url = new URL(window.location);
            url.searchParams.set('session_id', parsed.session_id);
            window.history.pushState({}, '', url);
            return;
          }
        } catch (e) { /* not JSON, treat as regular message */ }
      }
      
      // Regular progress messages — show as status updates
      if (msg.includes('Error') || msg.includes('error') || msg.includes('failed')) {
        addStatusMessage(msg, 'error');
        lastStatusEl = null;
      } else if (msg.includes('Session saved')) {
        // Silently ignore session saved messages in the chat
      } else if (msg.startsWith('Found:') || msg.includes('companies found') || msg.match(/^Found \d+/)) {
        // Company discovery messages — show each as a separate done item
        if (lastStatusEl) {
          updateStatusMessage(lastStatusEl, msg, 'done');
          lastStatusEl = null;
        } else {
          addStatusMessage(msg, 'done');
        }
      } else if (msg.includes('Saved') || msg.includes('complete')) {
        if (lastStatusEl) {
          updateStatusMessage(lastStatusEl, msg, 'done');
          lastStatusEl = null;
        } else {
          addStatusMessage(msg, 'done');
        }
      } else {
        // Other progress messages — update existing status or create new one
        if (lastStatusEl) {
          updateStatusMessage(lastStatusEl, msg);
        } else {
          lastStatusEl = addStatusMessage(msg);
        }
      }
      
    } catch (e) {
      // Ignore malformed
    }
  };
  
  eventSource.onerror = () => {
    setTimeout(() => {
      if (eventSource.readyState === EventSource.CLOSED) initSSE();
    }, 3000);
  };
}

function handleStatusTransition(status) {
  if (status === 'idle') {
    // Pipeline step finished
  } else if (status === 'generating_icp') {
    updateStatus('Generating ICP…', true);
  } else if (status === 'awaiting_icp_approval') {
    updateStatus('Awaiting approval', false);
    state.phase = 'awaiting_approval';
  } else if (status === 'scraping') {
    updateStatus('Scraping LinkedIn…', true);
    lastStatusEl = addStatusMessage('Scraping LinkedIn companies…');
  } else if (status === 'finding_contacts') {
    updateStatus('Finding contacts via Apify…', true);
    lastStatusEl = addStatusMessage('Running Apify LinkedIn employee scraper…');
  } else if (status === 'enriching') {
    updateStatus('Enriching emails…', true);
    lastStatusEl = addStatusMessage('Scraping company websites for emails…');
  }
}

function handleDoneSignal() {
  if (lastStatusEl) {
    updateStatusMessage(lastStatusEl, '✓ Step completed', 'done');
    lastStatusEl = null;
  }
  
  // Progress pipeline — sequential flow:
  // Scraping + Apify contacts run as one backend task, then enrichment
  if (state.phase === 'scraping' || state.phase === 'finding_contacts') {
    continueAfterContacts();
  } else if (state.phase === 'enriching') {
    finishPipeline();
  }
}

// ── UI Helpers ────────────────────────────────────────────────────
function updateStatus(text, isActive) {
  const dot = document.getElementById('status-dot');
  const textEl = document.getElementById('status-text');
  if (dot) dot.className = `status-dot ${isActive ? 'active' : 'idle'}`;
  if (textEl) textEl.textContent = text;
}

function setInputEnabled(enabled) {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('btn-send');
  if (input) input.disabled = !enabled;
  if (btn) btn.disabled = !enabled;
}

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  await verifyAuthOnLoad();
  
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('btn-send');
  
  document.getElementById('login-form').addEventListener('submit', handleLogin);
  document.getElementById('btn-logout').addEventListener('click', handleLogout);
  
  // New Search button
  const newSearchBtn = document.getElementById('btn-new-search');
  if (newSearchBtn) {
    newSearchBtn.addEventListener('click', startNewSearch);
  }
  
  const params = new URLSearchParams(window.location.search);
  const sid = params.get('session_id');
  if (sid && state.token) {
    loadSessionData(sid);
  } else {
    startNewSearch(); // Initialize welcome message
  }
  
  function send() {
    const text = input.value.trim();
    if (!text) return;
    
    if (state.phase === 'editing_icp') {
      // Try to parse as ICP JSON
      try {
        const icp = JSON.parse(text);
        input.value = '';
        approveICP(icp);
      } catch (e) {
        addAIMessage('That doesn\'t look like valid JSON. Please edit the ICP fields and try again.');
      }
      return;
    }
    
    input.value = '';
    input.style.height = 'auto';
    handleUserInput(text);
  }
  
  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  
  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
  
  // Export button in top bar
  document.getElementById('btn-export').addEventListener('click', exportXLSX);
  
  // Modal
  document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
}

document.addEventListener('DOMContentLoaded', init);
