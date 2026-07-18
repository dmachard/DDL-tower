import { state } from './state.js';
import { formatDate } from './helpers.js';
import { TRANSLATIONS } from './i18n.js';
import { rescanError } from './api.js';

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
                    ${err.url.startsWith('source:')
                ? (err.source_url
                    ? `<a href="${err.source_url}" target="_blank" style="color: var(--accent); text-decoration: none;">${err.url}</a>`
                    : `<span>${err.url}</span>`)
                : `<a href="${err.url}" target="_blank" style="color: var(--accent); text-decoration: none;">${err.url}</a>`
            }
                </div>
                <div style="font-size: 12px; color: var(--error); margin-top: 6px; font-family: monospace; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 6px;">
                    ${err.error === "failed" ? "Unknown error (legacy log)" : err.error}
                </div>
                ${(err.screenshot_path || err.html_path) ? `
                <div style="display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap;">
                    ${err.screenshot_path ? `
                        <a href="${err.screenshot_path}" target="_blank" class="btn-error-dump" style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 8px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: var(--text-secondary); font-size: 11px; font-weight: 700; text-decoration: none; text-transform: uppercase; letter-spacing: 0.5px; transition: var(--transition);" onmouseover="this.style.background='rgba(255,255,255,0.08)'; this.style.borderColor='rgba(255,255,255,0.15)'; this.style.color='var(--text-primary)'" onmouseout="this.style.background='rgba(255,255,255,0.03)'; this.style.borderColor='rgba(255,255,255,0.08)'; this.style.color='var(--text-secondary)'">
                            <i class="fas fa-camera" style="color: var(--accent);"></i> Screenshot
                        </a>
                    ` : ''}
                    ${err.html_path ? `
                        <a href="${err.html_path}" target="_blank" class="btn-error-dump" style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 8px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: var(--text-secondary); font-size: 11px; font-weight: 700; text-decoration: none; text-transform: uppercase; letter-spacing: 0.5px; transition: var(--transition);" onmouseover="this.style.background='rgba(255,255,255,0.08)'; this.style.borderColor='rgba(255,255,255,0.15)'; this.style.color='var(--text-primary)'" onmouseout="this.style.background='rgba(255,255,255,0.03)'; this.style.borderColor='rgba(255,255,255,0.08)'; this.style.color='var(--text-secondary)'">
                            <i class="fas fa-code" style="color: var(--warning);"></i> HTML Dump
                        </a>
                    ` : ''}
                </div>
                ` : ''}
            </div>
            <div class="col-date" style="text-align: right; white-space: nowrap; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; align-self: stretch; justify-content: space-between;">
                <div>${formatDate(err.date)}</div>
                <div style="display: flex; gap: 6px;">
                    ${(err.source && err.source !== 'Unknown') ? `
                    <button class="btn-rescan-error" data-url="${encodeURIComponent(err.url)}" style="background: rgba(59, 130, 246, 0.05); border: 1px solid rgba(59, 130, 246, 0.15); color: var(--text-secondary); cursor: pointer; padding: 6px 10px; border-radius: 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 6px; transition: var(--transition); font-weight: 700; font-family: inherit;" onmouseover="this.style.background='rgba(59, 130, 246, 0.15)'; this.style.borderColor='rgba(59, 130, 246, 0.3)'; this.style.color='var(--accent)'" onmouseout="this.style.background='rgba(59, 130, 246, 0.05)'; this.style.borderColor='rgba(59, 130, 246, 0.15)'; this.style.color='var(--text-secondary)'" title="${TRANSLATIONS[state.language]?.btn_rescan || 'Rescan'}">
                        <i class="fas fa-sync-alt"></i> <span class="btn-text">${TRANSLATIONS[state.language]?.btn_rescan || 'Rescan'}</span>
                    </button>
                    ` : ''}
                    <button class="btn-delete-error" data-url="${encodeURIComponent(err.url)}" style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.15); color: var(--text-secondary); cursor: pointer; padding: 6px 10px; border-radius: 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 6px; transition: var(--transition); font-weight: 700; font-family: inherit;" onmouseover="this.style.background='rgba(239, 68, 68, 0.15)'; this.style.borderColor='rgba(239, 68, 68, 0.3)'; this.style.color='var(--accent-red)'" onmouseout="this.style.background='rgba(239, 68, 68, 0.05)'; this.style.borderColor='rgba(239, 68, 68, 0.15)'; this.style.color='var(--text-secondary)'" title="${TRANSLATIONS[state.language]?.btn_delete || 'Delete'}">
                        <i class="fas fa-trash-alt"></i> <span class="btn-text">${TRANSLATIONS[state.language]?.btn_delete || 'Delete'}</span>
                    </button>
                </div>
            </div>
        `;
        container.appendChild(row);
    });

    // Add click event listeners to each individual delete button
    container.querySelectorAll('.btn-delete-error').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const targetUrl = decodeURIComponent(btn.getAttribute('data-url'));
            const confirmMsg = state.language === 'fr'
                ? 'Voulez-vous vraiment supprimer cette erreur ?'
                : 'Are you sure you want to delete this error?';
            if (confirm(confirmMsg)) {
                try {
                    const res = await fetch(`/api/errors?url=${encodeURIComponent(targetUrl)}`, { method: 'DELETE' });
                    if (res.ok) {
                        const row = btn.closest('.error-row');
                        if (row) {
                            row.style.opacity = '0';
                            row.style.transform = 'translateX(20px)';
                            setTimeout(() => {
                                row.remove();
                                // Decrement badges
                                const countEl = document.getElementById('count-errors');
                                const mobCountEl = document.getElementById('mobile-count-errors');
                                if (countEl) {
                                    const newVal = Math.max(0, parseInt(countEl.textContent || '0') - 1);
                                    countEl.textContent = newVal;
                                    if (mobCountEl) mobCountEl.textContent = newVal;
                                }
                                // If list becomes empty, show empty state
                                if (container.querySelectorAll('.error-row').length === 0) {
                                    container.innerHTML = `
                                        <div class="empty-state">
                                            <div class="empty-state-icon"><i class="fas fa-check-circle" style="color: var(--success)"></i></div>
                                            <div class="empty-state-text">No Errors Found</div>
                                            <div class="empty-state-subtext">The scraper seems to be running perfectly!</div>
                                        </div>`;
                                }
                                document.dispatchEvent(new CustomEvent('errors-updated'));
                            }, 300);
                        }
                    }
                } catch (err) {
                    console.error('Failed to ignore single error', err);
                }
            }
        });
    });

    // Add click event listeners to each individual rescan button
    container.querySelectorAll('.btn-rescan-error').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const targetUrl = decodeURIComponent(btn.getAttribute('data-url'));

            // Disable button & change icon to spinner to show loading state
            const originalHTML = btn.innerHTML;
            btn.disabled = true;
            btn.style.opacity = '0.7';
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${state.language === 'fr' ? 'Scan...' : 'Scanning...'}`;

            try {
                const res = await rescanError(targetUrl);
                if (res.ok) {
                    if (targetUrl.startsWith('source:')) {
                        alert(state.language === 'fr' ? 'Scan de la source lancé en arrière-plan.' : 'Source scan triggered in background.');
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.innerHTML = originalHTML;
                        return;
                    }
                    const row = btn.closest('.error-row');
                    if (row) {
                        row.style.opacity = '0';
                        row.style.transform = 'translateX(20px)';
                        setTimeout(() => {
                            row.remove();
                            // Decrement badges
                            const countEl = document.getElementById('count-errors');
                            const mobCountEl = document.getElementById('mobile-count-errors');
                            if (countEl) {
                                const newVal = Math.max(0, parseInt(countEl.textContent || '0') - 1);
                                countEl.textContent = newVal;
                                if (mobCountEl) mobCountEl.textContent = newVal;
                            }
                            // If list becomes empty, show empty state
                            if (container.querySelectorAll('.error-row').length === 0) {
                                container.innerHTML = `
                                    <div class="empty-state">
                                        <div class="empty-state-icon"><i class="fas fa-check-circle" style="color: var(--success)"></i></div>
                                        <div class="empty-state-text">No Errors Found</div>
                                        <div class="empty-state-subtext">The scraper seems to be running perfectly!</div>
                                    </div>`;
                            }
                            document.dispatchEvent(new CustomEvent('errors-updated'));
                        }, 300);
                    }
                } else {
                    const data = await res.json();
                    alert((state.language === 'fr' ? 'Échec du scan : ' : 'Scan failed: ') + (data.detail || 'Unknown error'));
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.innerHTML = originalHTML;
                }
            } catch (err) {
                console.error('Failed to rescan error', err);
                alert(state.language === 'fr' ? 'Une erreur est survenue lors du rescan.' : 'An error occurred during rescan.');
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.innerHTML = originalHTML;
            }
        });
    });
};

export const initErrors = () => {
    const clearBtn = document.getElementById('clear-errors-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            if (confirm('Are you sure you want to clear all errors?')) {
                try {
                    await fetch('/api/errors', { method: 'DELETE' });
                    state.errors.page = 1;
                    document.dispatchEvent(new CustomEvent('errors-updated'));
                } catch (e) {
                    console.error('Failed to clear errors', e);
                }
            }
        });
    }
};
