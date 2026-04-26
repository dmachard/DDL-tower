import { TRANSLATIONS } from './i18n.js';
import { state } from './state.js';
import { fetchData } from './api.js';

let identifyTargetLinks = [];

export const openIdentifyModal = (linkIds, title) => {
    identifyTargetLinks = linkIds;
    const modal = document.getElementById('identify-modal');
    const input = document.getElementById('identify-search-input');
    const results = document.getElementById('identify-results');
    input.value = title;
    results.innerHTML = '';
    modal.classList.add('active');
    input.focus();
};

export const showConfirm = (title, message) => {
    return new Promise((resolve) => {
        const confirmModal = document.getElementById('confirm-modal');
        const confirmTitle = document.getElementById('confirm-title');
        const confirmMessage = document.getElementById('confirm-message');
        const btnConfirmOk = document.getElementById('btn-confirm-ok');
        const btnConfirmCancel = document.getElementById('btn-confirm-cancel');
        const closeConfirmModal = document.getElementById('close-confirm-modal');

        confirmTitle.textContent = title;
        confirmMessage.textContent = message;
        btnConfirmOk.textContent = TRANSLATIONS[state.language].btn_confirm;
        btnConfirmCancel.textContent = TRANSLATIONS[state.language].btn_cancel;
        confirmModal.classList.add('active');

        const outsideClick = (e) => { if (e.target === confirmModal) cleanup(false); };

        const cleanup = (result) => {
            confirmModal.classList.remove('active');
            btnConfirmOk.onclick = null;
            btnConfirmCancel.onclick = null;
            closeConfirmModal.onclick = null;
            window.removeEventListener('click', outsideClick);
            resolve(result);
        };

        btnConfirmOk.onclick = () => cleanup(true);
        btnConfirmCancel.onclick = () => cleanup(false);
        closeConfirmModal.onclick = () => cleanup(false);
        window.addEventListener('click', outsideClick);
    });
};

const renderIdentifyResults = (results) => {
    const identifyResults = document.getElementById('identify-results');
    if (!results || results.length === 0) {
        identifyResults.innerHTML = '<div style="padding:20px;text-align:center;">No results found.</div>';
        return;
    }

    identifyResults.innerHTML = results.map(res => `
        <div class="result-item" data-tmdb-id="${res.id}" data-title="${res.title}" data-year="${res.year}">
            <img src="${res.poster_path || 'static/img/no-poster.svg'}" class="result-poster">
            <div class="result-info">
                <div class="result-title">${res.title}</div>
                <div class="result-meta">${res.year}</div>
            </div>
        </div>
    `).join('');

    identifyResults.querySelectorAll('.result-item').forEach(item => {
        item.onclick = async () => {
            const tmdb_id = item.getAttribute('data-tmdb-id');
            const title = item.getAttribute('data-title');
            const year = item.getAttribute('data-year');

            const titleConfirm = state.language === 'fr' ? 'Confirmation' : 'Confirmation';
            const confirmMsg = state.language === 'fr'
                ? `Identifier cette release comme "${title} (${year})"?`
                : `Identify this release as "${title} (${year})"?`;

            if (await showConfirm(titleConfirm, confirmMsg)) {
                item.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Identifying...';
                try {
                    const catSelect = document.getElementById('identify-category-select');
                    const selectedCat = catSelect ? catSelect.value : 'movie';
                    const res = await fetch('/api/releases/identify', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            tmdb_id: parseInt(tmdb_id),
                            title,
                            year: parseInt(year) || null,
                            category: selectedCat,
                            lang: state.language,
                            link_ids: identifyTargetLinks
                        })
                    });
                    if (res.ok) {
                        document.getElementById('identify-modal').classList.remove('active');
                        fetchData('releases');
                    }
                } catch (err) {
                    console.error('Failed to identify release.', err);
                }
            }
        };
    });
};

export const initModals = () => {
    const identifyModal = document.getElementById('identify-modal');
    const identifySearchInput = document.getElementById('identify-search-input');
    const identifyResults = document.getElementById('identify-results');
    const btnDoIdentifySearch = document.getElementById('btn-do-identify-search');
    const closeIdentifyModal = document.getElementById('close-identify-modal');
    
    if (closeIdentifyModal) closeIdentifyModal.onclick = () => identifyModal.classList.remove('active');

    if (btnDoIdentifySearch) {
        btnDoIdentifySearch.onclick = async () => {
            const query = identifySearchInput.value.trim();
            if (!query) return;

            identifyResults.innerHTML = '<div style="padding:20px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> Searching...</div>';
            try {
                const catSelect = document.getElementById('identify-category-select');
                const selectedCat = catSelect ? catSelect.value : 'movie';
                const res = await fetch(`/api/tmdb/search?query=${encodeURIComponent(query)}&type=${selectedCat === 'series' ? 'tv' : 'movie'}&lang=${state.language}`);
                const data = await res.json();
                renderIdentifyResults(data);
            } catch (err) {
                identifyResults.innerHTML = '<div style="color:var(--accent-red);padding:20px;">Search failed.</div>';
            }
        };
    }

    if (identifySearchInput) {
        identifySearchInput.onkeypress = (e) => {
            if (e.key === 'Enter') btnDoIdentifySearch.click();
        };
    }

    window.addEventListener('click', (event) => {
        if (event.target == identifyModal) identifyModal.classList.remove('active');
    });
};
