import { state } from './js/state.js';
import { debounce } from './js/helpers.js';
import { fetchData, fetchDownloads, fetchStats, fetchConfig, fetchSources, fetchYears, fetchNetworks, fetchErrors } from './js/api.js';
import { loadFilters, updateTagsUI, handleTagClick, initCustomSelect } from './js/filters.js';
import { setLanguage } from './js/i18n.js';
import { initModals } from './js/modals.js';
import { initNavigation } from './js/navigation.js';
import { initScanner } from './js/scanner.js';
import { initQuickScan } from './js/quick-scan.js';
import { initErrors } from './js/errors.js';

// ─── Splash Screen Controller ────────────────────────────────────────────────
const splash = {
    el: null,
    bar: null,
    status: null,
    total: 0,
    done: 0,
    lang: (localStorage.getItem('ddlt_lang') || 'fr'),
    labels: {
        fr: { loading: 'Chargement...', ready: 'Prêt !', config: 'Configuration chargée', configDefault: 'Configuration (défaut)', releases: 'Releases chargées', downloads: 'Downloads chargés', errors: 'Erreurs chargées', stats: 'Statistiques chargées' },
        en: { loading: 'Loading...', ready: 'Ready!', config: 'Config loaded', configDefault: 'Config (default)', releases: 'Releases loaded', downloads: 'Downloads loaded', errors: 'Errors loaded', stats: 'Stats loaded' }
    },
    t(key) { return (this.labels[this.lang] || this.labels.fr)[key] || key; },
    init(totalSteps) {
        this.el = document.getElementById('loading-splash');
        this.bar = document.getElementById('splash-progress-bar');
        this.status = document.getElementById('splash-status');
        this.total = totalSteps;
        this.done = 0;
        if (this.status) this.status.textContent = this.t('loading');
    },
    step(key) {
        this.done++;
        const pct = Math.round((this.done / this.total) * 100);
        if (this.bar) this.bar.style.width = `${pct}%`;
        if (this.status) this.status.textContent = this.t(key);
        if (this.done >= this.total) this.hide();
    },
    hide() {
        if (this.status) this.status.textContent = this.t('ready');
        if (this.bar) this.bar.style.width = '100%';
        setTimeout(() => {
            if (this.el) this.el.classList.add('hidden');
        }, 400);
    }
};

document.addEventListener('DOMContentLoaded', () => {

    // Reset browser-persisted inputs
    document.querySelectorAll('input').forEach(input => {
        if (input.type === 'text' || input.type === 'search') input.value = '';
    });

    // ── Search & Deep Linking ───────────────────────────────────────────────
    const urlParams = new URLSearchParams(window.location.search);
    const initialQuery = urlParams.get('q');
    
    const targetSearch = document.getElementById('target-search');
    if (initialQuery && targetSearch) {
        state.releases.query = initialQuery;
        targetSearch.value = initialQuery;
    }

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
    initQuickScan();
    initErrors();

    document.addEventListener('errors-updated', () => {
        fetchErrors();
    });

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

    // ── Show All Toggle ───────────────────────────────────────────────────────
    const showAllToggle = document.getElementById('show-all-toggle');
    if (showAllToggle) {
        showAllToggle.addEventListener('click', () => {
            state.releases.showAllVersions = !state.releases.showAllVersions;
            showAllToggle.classList.toggle('active', state.releases.showAllVersions);
            fetchData('releases');
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    initCustomSelect();
    initModals();

    // ── Initial Data Load with Splash Progress ────────────────────────────────
    splash.init(5); // 5 steps: config, releases, downloads, errors, stats

    ['releases'].forEach(v => { loadFilters(v); updateTagsUI(`filter-tags-${v}`, state[v]); });

    const initApp = async () => {
        try {
            const cfg = await fetchConfig();
            splash.step('config');

            const savedLang = localStorage.getItem('ddlt_lang');
            setLanguage(savedLang || cfg.default_language || 'fr');
            fetchSources(loadFilters, updateTagsUI);
            fetchYears(loadFilters, updateTagsUI);
            fetchNetworks(loadFilters, updateTagsUI);
        } catch (err) {
            console.error('Failed to load init config:', err);
            setLanguage('fr');
            splash.step('configDefault');
        }
    };

    // Launch all fetches in parallel, track progress
    Promise.resolve(fetchData('releases')).then(() => splash.step('releases'));
    Promise.resolve(fetchDownloads()).then(() => splash.step('downloads'));
    Promise.resolve(fetchErrors()).then(() => splash.step('errors'));
    Promise.resolve(fetchStats()).then(() => splash.step('stats'));
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

