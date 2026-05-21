import { TRANSLATIONS } from './i18n.js';
import { state } from './state.js';
import { formatBytes, formatDate } from './helpers.js';
import { fetchDownloads } from './api.js';
import { showConfirm } from './modals.js';

// ─── Downloads ────────────────────────────────────────────────────────────────

export const renderActiveDownloads = () => {
    const downloadsContainer = document.getElementById('downloads-container');
    const downloadItemTemplate = document.getElementById('download-item-template');
    const active = state.downloads.active || {};

    Object.keys(active).forEach(groupName => {
        if (groupName === 'detail') return;
        const group = active[groupName];
        if (!group || typeof group !== 'object') return;

        const progress = group.total > 0 ? Math.round((group.downloaded / group.total) * 100) : 0;
        const clone = downloadItemTemplate.content.cloneNode(true);
        const row = clone.querySelector('.link-row');
        row.classList.add('active-download');
        if (group.status === 'error') row.classList.add('error-download');

        clone.querySelector('.download-name').textContent = group.name || groupName;

        const iconEl = clone.querySelector('.file-icon');
        if (group.status === 'error') iconEl.className = 'fas fa-exclamation-triangle error-icon';
        else if (group.status === 'extracting') iconEl.className = 'fas fa-box-open fa-bounce';
        else iconEl.className = 'fas fa-spinner fa-spin';

        const progressContainer = clone.querySelector('.download-progress-container');
        progressContainer.classList.remove('hidden');

        const progressBar = clone.querySelector('.download-progress-bar');
        progressBar.style.width = `${progress}%`;
        if (group.status === 'error') progressBar.style.background = 'var(--error)';

        const progressText = clone.querySelector('.download-progress-text');
        progressText.textContent = group.status === 'error' ? (group.error || 'Error') : `${progress}%`;

        const sizeCol = clone.querySelector('.col-size');
        sizeCol.textContent = group.total > 0 ? formatBytes(group.downloaded) + ' / ' + formatBytes(group.total) : '...';
        sizeCol.setAttribute('data-label', state.language === 'fr' ? 'Taille' : 'Size');

        const dateCol = clone.querySelector('.col-date');
        dateCol.textContent = group.status.toUpperCase();
        dateCol.setAttribute('data-label', state.language === 'fr' ? 'Statut' : 'Status');

        clone.querySelector('.col-actions').setAttribute('data-label', state.language === 'fr' ? 'Actions' : 'Actions');

        if (group.files && Object.keys(group.files).length > 1) {
            const partsInfo = document.createElement('div');
            partsInfo.className = 'download-parts-detail';
            Object.keys(group.files).forEach(fn => {
                const f = group.files[fn];
                const p = document.createElement('div');
                p.className = 'part-line';
                p.innerHTML = `<span>${fn}</span> <span class="part-progress">${f.progress}%</span>`;
                partsInfo.appendChild(p);
            });
            clone.querySelector('.col-content').appendChild(partsInfo);
        }

        const deleteBtn = clone.querySelector('.btn-delete-download');
        const downloadBtn = clone.querySelector('.btn-download-local');

        if (group.status === 'error') {
            deleteBtn.onclick = async () => { 
                try {
                    await fetch(`/api/active-downloads/${encodeURIComponent(groupName)}`, { method: 'DELETE' });
                } catch (e) { console.error('Failed to delete active download:', e); }
                delete state.downloads.active[groupName]; 
                renderDownloads(state.downloads.items); 
            };
        } else {
            deleteBtn.disabled = true;
            deleteBtn.style.opacity = 0.3;
        }
        downloadBtn.classList.add('hidden');
        downloadsContainer.prepend(clone);
    });
};

export const renderDownloads = async (files) => {
    const downloadsContainer = document.getElementById('downloads-container');
    const downloadItemTemplate = document.getElementById('download-item-template');
    if (!downloadsContainer) return;

    downloadsContainer.innerHTML = '';
    const hasFiles = files && files.length > 0;
    const hasActive = state.downloads.active && Object.keys(state.downloads.active).length > 0;

    if (!hasFiles && !hasActive) {
        downloadsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon"><i class="fas fa-download"></i></div>
                <div class="empty-state-text">${TRANSLATIONS[state.language].msg_no_results}</div>
            </div>`;
        return;
    }

    if (hasFiles) {
        const groups = {};
        files.forEach(file => {
            if (state.downloads.active && state.downloads.active[file.name]) return;

            let baseName = file.name;
            const partMatch = file.name.match(/(.*)\\.part\d+\\.rar$/i);
            if (partMatch) baseName = partMatch[1] + '.rar';

            if (!groups[baseName]) {
                groups[baseName] = { name: baseName, parts: [], total_bytes: 0, modified: file.modified, is_dir: file.is_dir && !partMatch };
            }
            groups[baseName].parts.push(file.name);
            groups[baseName].total_bytes += file.size_bytes || 0;
            if (new Date(file.modified) > new Date(groups[baseName].modified)) {
                groups[baseName].modified = file.modified;
            }
        });

        for (const [baseName, group] of Object.entries(groups)) {
            const clone = downloadItemTemplate.content.cloneNode(true);
            const row = clone.querySelector('.link-row');

            const nameEl = clone.querySelector('.download-name');
            nameEl.textContent = group.parts.length > 1 ? `${baseName} (${group.parts.length} parts)` : baseName;

            const iconEl = clone.querySelector('.file-icon');
            if (group.is_dir) iconEl.className = 'fas fa-folder folder-icon';

            const sizeCol = clone.querySelector('.col-size');
            sizeCol.textContent = formatBytes(group.total_bytes);
            sizeCol.setAttribute('data-label', state.language === 'fr' ? 'Taille' : 'Size');

            const dateCol = clone.querySelector('.col-date');
            dateCol.textContent = formatDate(group.modified);
            dateCol.setAttribute('data-label', state.language === 'fr' ? 'Date' : 'Date');

            clone.querySelector('.col-actions').setAttribute('data-label', state.language === 'fr' ? 'Actions' : 'Actions');

            const deleteBtn = clone.querySelector('.btn-delete-download');
            const downloadBtn = clone.querySelector('.btn-download-local');

            if (group.is_dir || group.parts.length > 1) {
                downloadBtn.classList.add('hidden');
            } else {
                downloadBtn.href = `/api/downloads/file/${encodeURIComponent(group.parts[0])}`;
            }

            deleteBtn.onclick = async () => {
                const title = state.language === 'fr' ? 'Confirmation de suppression' : 'Confirm Deletion';
                const msg = group.parts.length > 1
                    ? (state.language === 'fr' ? `Supprimer les ${group.parts.length} parties de ${baseName}?` : `Delete all ${group.parts.length} parts of ${baseName}?`)
                    : (state.language === 'fr' ? `Supprimer ${baseName}?` : `Delete ${baseName}?`);

                if (await showConfirm(title, msg)) {
                    try {
                        await Promise.all(group.parts.map(fn => fetch(`/api/downloads/${encodeURIComponent(fn)}`, { method: 'DELETE' })));
                        fetchDownloads();
                    } catch (err) { console.error('Delete failed:', err); }
                }
            };

            downloadsContainer.appendChild(clone);
        }
    }

    renderActiveDownloads();
};
