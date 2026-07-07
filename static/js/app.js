/**
 * Lead Finder — Frontend Application Logic (Impeccable Overhaul)
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── Global State ───────────────────────────────────────────────────────────
    const state = {
        mode: 'description', // 'description' or 'keywords'
        keywords: [],
        leads: [],
        filteredLeads: [],
        sortCol: 'fit_score',
        sortDesc: true,
        filterTier: 'all',
        searchQuery: '',
        pipelineStatus: 'idle',
        sessionId: null
    };

    let eventSource = null;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ── DOM Elements ───────────────────────────────────────────────────────────
    const els = {
        navItems: document.querySelectorAll('.nav-item'),
        views: document.querySelectorAll('.view'),
        modeBtns: document.querySelectorAll('#mode-desc, #mode-kw'),
        formDesc: document.getElementById('form-description'),
        formKw: document.getElementById('form-keywords'),
        descInput: document.getElementById('service-desc'),
        kwInput: document.getElementById('manual-keyword'),
        btnGenKw: document.getElementById('btn-generate-keywords'),
        kwContainer: document.getElementById('keywords-container'),
        kwChips: document.getElementById('keyword-chips'),
        btnScrape: document.getElementById('btn-start-scrape'),
        progContainer: document.getElementById('progress-container'),
        progConsole: document.getElementById('progress-console'),
        statusDot: document.getElementById('status-dot'),
        statusText: document.getElementById('status-text'),
        leadsTbody: document.getElementById('leads-tbody'),
        searchLeads: document.getElementById('search-leads'),
        filterBtns: document.querySelectorAll('.filter-chip'),
        sortHeaders: document.querySelectorAll('th[data-sort]'),
        btnEnrich: document.getElementById('btn-enrich'),
        btnExport: document.getElementById('btn-export'),
        toastContainer: document.getElementById('toast-container')
    };

    init();

    function init() {
        setupEventListeners();
        connectSSE();
        fetchStatus();
        fetchLeads();
        
        const savedDesc = localStorage.getItem('lf_description');
        if (savedDesc) els.descInput.value = savedDesc;
    }

    function setupEventListeners() {
        // Navigation
        els.navItems.forEach(item => {
            item.addEventListener('click', () => switchView(item.dataset.view));
        });

        // Search Mode Toggle
        document.getElementById('mode-desc').addEventListener('click', (e) => {
            setMode('description', e.target);
        });
        document.getElementById('mode-kw').addEventListener('click', (e) => {
            setMode('keywords', e.target);
        });

        function setMode(mode, targetBtn) {
            els.modeBtns.forEach(btn => {
                btn.style.borderColor = 'var(--border)';
                btn.style.color = 'var(--ink)';
            });
            targetBtn.style.borderColor = 'var(--primary)';
            targetBtn.style.color = 'var(--primary)';
            
            state.mode = mode;
            if (mode === 'description') {
                els.formDesc.style.display = 'block';
                els.formKw.style.display = 'none';
                if (state.keywords.length > 0) els.kwContainer.style.display = 'block';
            } else {
                els.formDesc.style.display = 'none';
                els.formKw.style.display = 'block';
                els.kwContainer.style.display = 'none';
            }
        }

        // Generate Keywords
        els.btnGenKw.addEventListener('click', async () => {
            const desc = els.descInput.value.trim();
            if (!desc) return showToast('Context required to extract keywords', 'error');
            
            localStorage.setItem('lf_description', desc);
            setLoading(els.btnGenKw, true);
            
            try {
                const res = await fetch('/api/keywords', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ description: desc })
                });
                const data = await res.json();
                if (data.keywords?.length > 0) {
                    state.keywords = data.keywords;
                    renderKeywords();
                    els.kwContainer.style.display = 'block';
                }
            } catch (err) {
                showToast('Failed to connect to backend', 'error');
            } finally {
                setLoading(els.btnGenKw, false, 'Extract Keywords');
            }
        });

        // Start Pipeline
        els.btnScrape.addEventListener('click', async () => {
            let payload = { mode: state.mode };
            
            if (state.mode === 'description') {
                if (state.keywords.length === 0) {
                    const desc = els.descInput.value.trim();
                    if (!desc) return showToast('Context required', 'error');
                    payload.description = desc;
                    payload.keywords = [];
                } else {
                    payload.keywords = state.keywords;
                }
            } else {
                const kw = els.kwInput.value.trim();
                if (!kw) return showToast('Keyword required', 'error');
                payload.keywords = [kw];
            }

            state.sessionId = Date.now().toString();
            payload.session_id = state.sessionId;

            setLoading(els.btnScrape, true);
            try {
                const res = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (res.ok) {
                    els.progContainer.style.display = 'block';
                    els.progConsole.innerHTML = '';
                } else {
                    const data = await res.json();
                    showToast(data.error || 'Pipeline initiation failed', 'error');
                    setLoading(els.btnScrape, false, 'Execute Scrape Pipeline');
                }
            } catch (err) {
                showToast('Backend connection error', 'error');
                setLoading(els.btnScrape, false, 'Execute Scrape Pipeline');
            }
        });

        // Start Enrichment
        els.btnEnrich.addEventListener('click', async () => {
            setLoading(els.btnEnrich, true);
            try {
                const res = await fetch('/api/enrich', { method: 'POST' });
                if (res.ok) {
                    switchView('search-view');
                    els.progContainer.style.display = 'block';
                    els.progConsole.innerHTML = '';
                } else {
                    const data = await res.json();
                    showToast(data.error || 'Enrichment failed', 'error');
                    setLoading(els.btnEnrich, false, 'Run Apollo Enrichment');
                }
            } catch (err) {
                showToast('Backend connection error', 'error');
                setLoading(els.btnEnrich, false, 'Run Apollo Enrichment');
            }
        });

        // Export Excel
        els.btnExport.addEventListener('click', async () => {
            setLoading(els.btnExport, true);
            try {
                const url = state.sessionId ? `/api/export?session_id=${state.sessionId}` : '/api/export';
                const res = await fetch(url);
                if (!res.ok) {
                    const data = await res.json();
                    showToast(data.error || 'No data to export', 'error');
                    return;
                }
                const blob = await res.blob();
                
                // Extract filename from Content-Disposition if present, or use default
                let filename = 'final_leads.xlsx';
                const disposition = res.headers.get('Content-Disposition');
                if (disposition && disposition.indexOf('filename=') !== -1) {
                    const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
                    if (matches != null && matches[1]) {
                        filename = matches[1].replace(/['"]/g, '');
                    }
                }

                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                showToast('Export successful', 'success');
            } catch (err) {
                showToast('Failed to download export', 'error');
            } finally {
                setLoading(els.btnExport, false, 'Export XLSX');
            }
        });

        // Table Filters
        els.searchLeads.addEventListener('input', (e) => {
            state.searchQuery = e.target.value.toLowerCase();
            applyFilters();
        });

        els.filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                els.filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.filterTier = btn.dataset.filter;
                applyFilters();
            });
        });

        els.sortHeaders.forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.sort;
                if (state.sortCol === col) {
                    state.sortDesc = !state.sortDesc;
                } else {
                    state.sortCol = col;
                    state.sortDesc = col === 'fit_score';
                }
                applyFilters();
            });
        });
    }

    // ── API & Data ─────────────────────────────────────────────────────────────

    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            updatePipelineUI(data.status);
        } catch (e) {
            console.error('Failed to fetch status');
        }
    }

    async function fetchLeads() {
        try {
            const url = state.sessionId ? `/api/leads?session_id=${state.sessionId}` : '/api/leads';
            const res = await fetch(url);
            const data = await res.json();
            state.leads = data.leads || [];
            applyFilters();
            updateDashboard(state.leads);
        } catch (e) {
            console.error('Failed to fetch leads');
        }
    }

    function connectSSE() {
        if (eventSource) eventSource.close();
        
        eventSource = new EventSource('/api/progress');
        
        eventSource.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.keepalive) return;
            
            const msg = data.message;
            if (msg.startsWith('__STATUS__:')) {
                updatePipelineUI(msg.split(':')[1]);
            } else if (msg === '__DONE__') {
                updatePipelineUI('idle');
                fetchLeads();
                showToast('Pipeline execution complete', 'success');
                switchView('leads-view');
            } else {
                appendLog(msg);
            }
        };

        eventSource.onerror = () => {
            setTimeout(connectSSE, 5000);
        };
    }

    // ── UI Updates ─────────────────────────────────────────────────────────────

    function updatePipelineUI(status) {
        state.pipelineStatus = status;
        const isBusy = status !== 'idle';
        
        els.statusDot.className = `status-dot ${isBusy ? 'busy' : (status === 'idle' ? '' : 'active')}`;
        els.statusText.textContent = status === 'idle' ? 'System Idle' : `Executing: ${status}`;
        
        if (isBusy) {
            setLoading(els.btnScrape, true);
            setLoading(els.btnEnrich, true);
            els.progContainer.style.display = 'block';
        } else {
            setLoading(els.btnScrape, false, 'Execute Scrape Pipeline');
            setLoading(els.btnEnrich, false, 'Run Apollo Enrichment');
        }
    }

    function switchView(viewId) {
        els.views.forEach(v => {
            v.classList.remove('active');
            v.style.display = 'none';
        });
        
        els.navItems.forEach(n => {
            if (n.dataset.view === viewId) n.classList.add('active');
            else n.classList.remove('active');
        });
        
        const activeView = document.getElementById(viewId);
        activeView.style.display = 'block';
        // Small delay to allow display block to take effect before setting opacity
        requestAnimationFrame(() => {
            activeView.classList.add('active');
        });

        if (viewId === 'export-view') updateDashboard(state.leads);
    }

    function renderKeywords() {
        els.kwChips.innerHTML = '';
        state.keywords.forEach((kw, index) => {
            const chip = document.createElement('div');
            chip.className = 'badge badge-perfect';
            chip.style.cursor = 'pointer';
            chip.innerHTML = `${kw} &times;`;
            chip.addEventListener('click', () => {
                state.keywords.splice(index, 1);
                renderKeywords();
                if (state.keywords.length === 0) els.kwContainer.style.display = 'none';
            });
            els.kwChips.appendChild(chip);
        });
    }

    function appendLog(msg) {
        const line = document.createElement('div');
        line.className = 'console-line';
        
        const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
        let msgClass = 'console-msg';
        
        if (msg.includes('Error') || msg.includes('Failed')) msgClass += ' error';
        if (msg.includes('Found:')) msgClass += ' success';
        if (msg.includes('Saved')) msgClass += ' info';

        const urlRegex = /(https?:\/\/[^\s]+)/g;
        const linkedMsg = msg.replace(urlRegex, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
        line.innerHTML = `<span class="console-time">${time}</span><span class="${msgClass}">${linkedMsg}</span>`;
        els.progConsole.appendChild(line);
        els.progConsole.scrollTop = els.progConsole.scrollHeight;
    }

    // ── Table Logic ────────────────────────────────────────────────────────────

    function applyFilters() {
        let filtered = state.leads;

        if (state.searchQuery) {
            filtered = filtered.filter(l => 
                (l.company_name || '').toLowerCase().includes(state.searchQuery) ||
                (l.industry || '').toLowerCase().includes(state.searchQuery)
            );
        }

        if (state.filterTier !== 'all') {
            filtered = filtered.filter(l => {
                const score = l.fit_score || 0;
                if (state.filterTier === 'perfect') return score >= 80;
                if (state.filterTier === 'good') return score >= 60 && score < 80;
                if (state.filterTier === 'possible') return score >= 40 && score < 60;
                return score < 40;
            });
        }

        filtered.sort((a, b) => {
            let valA = a[state.sortCol] || '';
            let valB = b[state.sortCol] || '';

            if (typeof valA === 'string') valA = valA.toLowerCase();
            if (typeof valB === 'string') valB = valB.toLowerCase();

            if (valA < valB) return state.sortDesc ? 1 : -1;
            if (valA > valB) return state.sortDesc ? -1 : 1;
            return 0;
        });

        state.filteredLeads = filtered;
        renderTable();
    }

    function renderTable() {
        els.leadsTbody.innerHTML = '';
        
        if (state.filteredLeads.length === 0) {
            els.leadsTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 48px; color: var(--muted);">No records found.</td></tr>`;
            return;
        }

        state.filteredLeads.forEach(lead => {
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            
            const score = lead.fit_score || 0;
            let scoreClass = 'poor';
            if (score >= 80) scoreClass = 'perfect';
            else if (score >= 60) scoreClass = 'good';
            else if (score >= 40) scoreClass = 'possible';

            let contactsHtml = '';
            if (lead.contacts && lead.contacts.length > 0) {
                lead.contacts.forEach(c => {
                    contactsHtml += `<div style="margin-bottom: 8px;">`;
                    if (c.title) contactsHtml += `<div style="font-size: 0.8em; color: var(--muted); text-transform: uppercase;">${c.title}</div>`;
                    if (c.full_name) contactsHtml += `<div style="font-weight: 500; font-size: 0.9em;">${c.full_name}</div>`;
                    if (c.email) contactsHtml += `<div class="text-mono" style="font-size: 0.9em; color: var(--accent);">${c.email}</div>`;
                    if (c.phone) contactsHtml += `<div class="text-mono" style="font-size: 0.9em;">${c.phone}</div>`;
                    contactsHtml += `</div>`;
                });
            } else {
                if (lead.email) contactsHtml += `<div class="text-mono">${lead.email}</div>`;
                if (lead.phone) contactsHtml += `<div class="text-mono">${lead.phone}</div>`;
            }
            if (!contactsHtml) contactsHtml = `<span class="text-muted">-</span>`;

            tr.innerHTML = `
                <td>
                    <div style="font-weight: 500;">${lead.company_name || 'Unknown'}</div>
                    <div class="text-muted">${lead.location || ''}</div>
                </td>
                <td>
                    <div>${lead.industry || '-'}</div>
                    <div class="text-muted">${lead.company_size || ''}</div>
                </td>
                <td>
                    ${lead.website ? `<a href="${lead.website.startsWith('http') ? lead.website : 'http://'+lead.website}" target="_blank" onclick="event.stopPropagation()">${lead.website.replace(/^https?:\/\//,'')}</a>` : '-'}
                </td>
                <td>
                    <div class="badge badge-${scoreClass}">${score}</div>
                </td>
                <td>
                    ${contactsHtml}
                </td>
            `;

            // Expandable Row
            const detailRow = document.createElement('tr');
            detailRow.className = 'detail-row';
            detailRow.style.display = 'none';
            detailRow.innerHTML = `
                <td colspan="5">
                    <div class="detail-content">
                        <div class="detail-grid">
                            <div>
                                <div class="detail-label">Context</div>
                                <div class="text-body">${lead.description || 'No description available.'}</div>
                            </div>
                            <div>
                                <div class="detail-label">AI Rationale</div>
                                <div class="text-body">${lead.fit_reason || 'No reasoning provided.'}</div>
                            </div>
                        </div>
                    </div>
                </td>
            `;

            tr.addEventListener('click', () => {
                const isHidden = detailRow.style.display === 'none';
                document.querySelectorAll('.detail-row').forEach(el => el.style.display = 'none');
                if (isHidden) detailRow.style.display = 'table-row';
            });

            els.leadsTbody.appendChild(tr);
            els.leadsTbody.appendChild(detailRow);
        });
    }

    // ── Dashboard Logic ────────────────────────────────────────────────────────

    function updateDashboard(leads) {
        const total = leads.length;
        if (total === 0) return;

        const scores = leads.map(l => l.fit_score || 0);
        const avg = Math.round(scores.reduce((a, b) => a + b, 0) / total);
        const emails = leads.filter(l => l.email).length;

        if (!reducedMotion) {
            animateValue(document.getElementById('stat-total'), 0, total, 600);
            animateValue(document.getElementById('stat-avg'), 0, avg, 600);
            animateValue(document.getElementById('stat-emails'), 0, emails, 600);
        } else {
            document.getElementById('stat-total').innerText = total;
            document.getElementById('stat-avg').innerText = avg;
            document.getElementById('stat-emails').innerText = emails;
        }
    }

    // ── Utils ──────────────────────────────────────────────────────────────────

    function setLoading(btn, isLoading, originalText = '') {
        if (isLoading) {
            btn.disabled = true;
            btn.textContent = 'Processing...';
        } else {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast`;
        if (type === 'error') toast.style.backgroundColor = 'var(--status-poor-ink)';
        if (type === 'success') toast.style.backgroundColor = 'var(--status-perfect-ink)';
        
        toast.textContent = message;
        els.toastContainer.appendChild(toast);
        
        setTimeout(() => toast.remove(), 4000);
    }

    function animateValue(obj, start, end, duration) {
        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            // Ease out quint
            const easeProgress = 1 - Math.pow(1 - progress, 5);
            obj.innerHTML = Math.floor(easeProgress * (end - start) + start);
            if (progress < 1) {
                window.requestAnimationFrame(step);
            }
        };
        window.requestAnimationFrame(step);
    }
});
