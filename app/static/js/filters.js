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
    if (containerId === 'filter-tags-releases') {
        document.querySelectorAll('.sidebar-cat-btn').forEach(btn => {
            btn.classList.toggle('active', String(viewState.category) === String(btn.getAttribute('data-cat')));
        });
    }
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
    }

    container.innerHTML = html;
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
