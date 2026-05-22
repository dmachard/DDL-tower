import { state } from './state.js';
import { formatDate } from './helpers.js';
import { TRANSLATIONS } from './i18n.js';

export const renderErrors = (errors) => {
    const container = document.getElementById('errors-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!errors || errors.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon"><i class="fas fa-check-circle" style="color: var(--success)"></i></div>
                <div class="empty-state-text">No Errors Found</div>
                <div class="empty-state-subtext">The scraper seems to be running perfectly!</div>
            </div>`;
        return;
    }
    
    errors.forEach((err, index) => {
        const row = document.createElement('div');
        row.className = 'link-row downloads-grid';
        row.style.animationDelay = `${index * 0.05}s`;
        
        row.innerHTML = `
            <div class="col-status">
                <i class="fas fa-exclamation-triangle" style="color: var(--accent-red)"></i>
            </div>
            <div class="col-content">
                <span class="download-name" style="font-size: 13px;">${err.source || 'Unknown'}</span>
                <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">
                    <a href="${err.url}" target="_blank" style="color: var(--accent); text-decoration: none;">${err.url}</a>
                </div>
                <div style="font-size: 11px; color: var(--accent-red); margin-top: 4px; font-family: monospace;">
                    ${err.error}
                </div>
            </div>
            <div class="col-date">${formatDate(err.date)}</div>
        `;
        container.appendChild(row);
    });
};
