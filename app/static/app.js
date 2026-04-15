import { state } from './js/state.js';
import { debounce } from './js/helpers.js';
import { fetchData, fetchDownloads, fetchStats, fetchConfig, fetchSources, fetchYears, fetchNetworks } from './js/api.js';
import { loadFilters, updateTagsUI, handleTagClick, initCustomSelect } from './js/filters.js';
import { setLanguage } from './js/i18n.js';
import { initModals } from './js/modals.js';
import { initNavigation } from './js/navigation.js';
import { initScanner } from './js/scanner.js';

document.addEventListener('DOMContentLoaded', () => {

    // Reset browser-persisted inputs
    document.querySelectorAll('input').forEach(input => {
        if (input.type === 'text' || input.type === 'search') input.value = '';
    });

    // ── Search ───────────────────────────────────────────────────────────────
    const targetSearch = document.getElementById('target-search');
    const handleSearch = debounce((e) => {
        const query = e.target.value.toLowerCase();
        const view = e.target.id === 'target-search' ? 'releases' : e.target.id.replace('search-', '');
        if (state[view]) {
            state[view].query = query;
            state[view].page = 1;
            fetchData(view);
        }
    }, 400);
    targetSearch?.addEventListener('input', handleSearch);

    // ── Navigation & Scanner ──────────────────────────────────────────────────
    initNavigation();
    initScanner();

    // ── Filter Tags ───────────────────────────────────────────────────────────
    document.getElementById('filter-tags-releases')?.addEventListener('click', (e) => handleTagClick(e, 'releases'));

    // ── Live Refresh Toggle ───────────────────────────────────────────────────
    const liveToggle = document.getElementById('live-toggle');
    if (liveToggle) {
        liveToggle.addEventListener('click', () => {
            state.autoRefresh = !state.autoRefresh;
            liveToggle.classList.toggle('active', state.autoRefresh);
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    initCustomSelect();
    initModals();

    const initApp = async () => {
        try {
            const cfg = await fetchConfig();
            const savedLang = localStorage.getItem('ddlt_lang');
            setLanguage(savedLang || cfg.default_language || 'fr');
            fetchSources(loadFilters, updateTagsUI);
            fetchYears(loadFilters, updateTagsUI);
            fetchNetworks(loadFilters, updateTagsUI);
        } catch (err) {
            console.error('Failed to load init config:', err);
            setLanguage('fr');
        }
    };

    ['releases'].forEach(v => { loadFilters(v); updateTagsUI(`filter-tags-${v}`, state[v]); });
    ['releases'].forEach(fetchData);
    fetchDownloads();
    fetchStats();
    initApp();

    // ── Polling Intervals ─────────────────────────────────────────────────────
    setInterval(() => {
        if (state.autoRefresh && document.visibilityState === 'visible') {
            if (state.currentView === 'releases') fetchData(state.currentView);
            else if (state.currentView === 'downloads') fetchDownloads();
        }
    }, 30000);

    setInterval(() => {
        if (state.autoRefresh && document.visibilityState === 'visible') fetchStats();
    }, 60000);

    setInterval(() => {
        const hasActive = state.downloads.active && Object.keys(state.downloads.active).length > 0;
        if (hasActive && state.currentView === 'downloads' && document.visibilityState === 'visible') fetchDownloads();
    }, 2000);
});
