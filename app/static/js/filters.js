import { TRANSLATIONS } from './i18n.js';
import { state, CONFIG } from './state.js';
import { fetchData } from './api.js';

export const updateTagsUI = (containerId, viewState) => {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.querySelectorAll('.filter-tag').forEach(tag => {
        const type = tag.getAttribute('data-type');
        const val = tag.getAttribute('data-value');
        let isActive = false;
        if (type === 'recent') isActive = (viewState.recent && val === 'true');
        else if (type === 'source') return;
        else if (type === 'resolution') isActive = (String(viewState.resolution) === String(val));
        else isActive = (String(viewState[type]) === String(val));
        tag.classList.toggle('active', isActive);
    });
};

export const handleTagClick = (e, view) => {
    const tag = e.target.closest('.filter-tag');
    if (!tag) return;

    const type = tag.getAttribute('data-type');
    const value = tag.getAttribute('data-value');
    const viewState = state[view];

    if (type === 'recent') {
        viewState.recent = !viewState.recent;
        if (!viewState.recent) viewState.hours = null;
    } else if (type === 'hours') {
        const h = parseInt(value);
        if (viewState.hours === h) viewState.hours = null;
        else { viewState.hours = h; viewState.recent = true; }
    } else if (type === 'year' || type === 'network') {
        viewState[type] = String(viewState[type]) === String(value) ? '' : value;
    } else {
        viewState[type] = viewState[type] === value ? '' : value;
    }

    viewState.page = 1;
    updateTagsUI('filter-tags-releases', viewState);
    fetchData(view);
};

export const initSourceSelect = () => {
    const select = document.getElementById('source-custom-select');
    if (!select) return;

    const trigger = select.querySelector('.select-trigger');

    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelectorAll('.custom-select').forEach(s => { if (s !== select) s.classList.remove('active'); });
        select.classList.toggle('active');

        if (select.classList.contains('active')) {
            const searchInput = select.querySelector('.select-search-input');
            if (searchInput) {
                searchInput.value = '';
                searchInput.focus();
                select.querySelectorAll('.option').forEach(opt => opt.classList.remove('hidden'));
                const empty = select.querySelector('.options-empty');
                if (empty) empty.classList.add('hidden');
            }
        }
    });

    const searchInput = select.querySelector('.select-search-input');
    if (searchInput) {
        searchInput.addEventListener('click', (e) => e.stopPropagation());
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            const options = select.querySelectorAll('.option');
            let found = false;
            options.forEach(opt => {
                const text = opt.textContent.toLowerCase();
                const isGlobalAll = opt.getAttribute('data-value') === '';
                if (isGlobalAll || text.includes(term)) {
                    opt.classList.remove('hidden');
                    if (!isGlobalAll) found = true;
                } else {
                    opt.classList.add('hidden');
                }
            });
            const empty = select.querySelector('.options-empty');
            if (empty) {
                if (!found && term !== '') empty.classList.remove('hidden');
                else empty.classList.add('hidden');
            }
        });
    }

    select.querySelectorAll('.option').forEach(opt => {
        opt.addEventListener('click', () => {
            const val = opt.getAttribute('data-value');
            state.releases.source = val;
            state.releases.page = 1;
            const labelEl = document.getElementById('current-source-label');
            if (labelEl) labelEl.textContent = val || TRANSLATIONS[state.language].filter_all_sources;
            select.classList.remove('active');
            updateTagsUI('filter-tags-releases', state.releases);
            fetchData('releases');
        });
    });
};

export const loadFilters = (view) => {
    const container = document.getElementById(`filter-tags-${view}`);
    if (!container || !CONFIG.filters[view]) return;

    let html = CONFIG.filters[view].map(f => {
        const cls = f.type === 'recent' ? 'filter-tag tag-recent' : 'filter-tag';
        const iconHtml = f.icon ? `<i class="${f.icon}"></i> ` : '';
        const label = f.i18n ? TRANSLATIONS[state.language][f.i18n] : f.label;
        return `<div class="${cls}" data-type="${f.type}" data-value="${f.value}">${iconHtml}${label}</div>`;
    }).join('');

    if (view === 'releases') {
        if (state.years.length > 0) {
            html += '<div class="filter-separator"></div>';
            state.years.slice(0, 10).forEach(yr => {
                html += `<div class="filter-tag" data-type="year" data-value="${yr}">${yr}</div>`;
            });
        }

        if (state.networks.length > 0) {
            html += '<div class="filter-separator"></div>';
            state.networks.forEach(net => {
                html += `<div class="filter-tag" data-type="network" data-value="${net}">${net}</div>`;
            });
        }

        if (state.sources.length > 0) {
            const currentSource = state.releases.source || TRANSLATIONS[state.language].filter_all_sources;
            const selectHtml = `
                <div class="custom-select source-select" id="source-custom-select">
                    <div class="select-trigger">
                        <i class="fas fa-server"></i>
                        <span id="current-source-label">${currentSource}</span>
                        <i class="fas fa-chevron-down"></i>
                    </div>
                    <div class="select-options">
                        <div class="select-search">
                            <input type="text" class="select-search-input" placeholder="${TRANSLATIONS[state.language].placeholder_search_source}">
                        </div>
                        <div class="option ${!state.releases.source ? 'active' : ''}" data-value="">${TRANSLATIONS[state.language].filter_all_sources}</div>
                        <div id="source-options-list">
                            ${state.sources.map(src => `<div class="option ${state.releases.source === src ? 'active' : ''}" data-value="${src}">${src}</div>`).join('')}
                        </div>
                        <div class="options-empty hidden">${TRANSLATIONS[state.language].no_source_found}</div>
                    </div>
                </div>
            `;
            html += selectHtml;
        }
    }

    container.innerHTML = html;
    if (view === 'releases') initSourceSelect();
};

export const initCustomSelect = () => {
    const select = document.getElementById('lang-custom-select');
    if (!select) return;

    const trigger = select.querySelector('.select-trigger');
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        select.classList.toggle('active');
    });

    select.querySelectorAll('.option').forEach(opt => {
        opt.addEventListener('click', () => {
            const val = opt.getAttribute('data-value');
            import('./i18n.js').then(({ setLanguage }) => setLanguage(val));
            select.classList.remove('active');
        });
    });

    document.addEventListener('click', () => select.classList.remove('active'));
};
