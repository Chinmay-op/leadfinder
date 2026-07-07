const fs = require('fs');

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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

function run() {
  const data = JSON.parse(fs.readFileSync('d:/leadOs/sessions/55cc7130-c5aa-41ad-9295-a985346c4237.json', 'utf8'));
  const leads = data.companies;
  let html = '';
  leads.forEach((l, i) => {
    html += generateSingleCompanyCardHtml(l, i);
  });
  console.log("SUCCESS. Generated HTML length:", html.length);
}

try {
  run();
} catch (e) {
  console.error(e);
}
