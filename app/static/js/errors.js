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
        row.className = 'error-row';
        row.style.animationDelay = `${index * 0.05}s`;
        
        row.innerHTML = `
            <div class="col-status">
                <i class="fas fa-exclamation-triangle" style="font-size: 1.2rem; color: var(--accent-red)"></i>
            </div>
            <div class="col-content">
                <span class="download-name" style="font-size: 14px; font-weight: 700; color: var(--text-primary);">${err.source || 'Unknown'}</span>
                <div style="font-size: 12px; color: var(--text-dim); margin-top: 4px; word-break: break-all;">
                    <a href="${err.url}" target="_blank" style="color: var(--accent); text-decoration: none;">${err.url}</a>
                </div>
                <div style="font-size: 12px; color: var(--error); margin-top: 6px; font-family: monospace; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 6px;">
                    ${err.error === "failed" ? "Unknown error (legacy log)" : err.error}
                </div>
            </div>
            <div class="col-date" style="text-align: right; white-space: nowrap;">${formatDate(err.date)}</div>
        `;
        container.appendChild(row);
    });
};

export const initErrors = () => {
    const clearBtn = document.getElementById('clear-errors-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            if (confirm('Are you sure you want to clear all errors?')) {
                try {
                    await fetch('/api/errors', { method: 'DELETE' });
                    // Trigger a re-fetch of errors by calling fetchErrors from api.js
                    // Since we have circular dependencies if we import api.js directly here,
                    // we'll dispatch a custom event that api.js or main app.js can listen to,
                    // or just reload the view by modifying state and calling render.
                    // An easier way is to just clear the DOM immediately and let the next poll fetch it.
                    renderErrors([]);
                } catch (e) {
                    console.error('Failed to clear errors', e);
                }
            }
        });
    }
};
