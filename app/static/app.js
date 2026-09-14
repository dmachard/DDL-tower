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
import { initDownloads } from './js/downloads.js';

// ─── Splash Screen Controller ────────────────────────────────────────────────
let initialLang = 'fr';
try { initialLang = localStorage.getItem('ddlt_lang') || 'fr'; } catch (e) {}

const splash = {
    el: null,
    bar: null,
    status: null,
    retryBtn: null,
    total: 0,
    done: 0,
    safetyTimer: null,
    lang: initialLang,
    labels: {
        fr: { loading: 'Chargement...', ready: 'Prêt !', config: 'Configuration chargée', configDefault: 'Configuration (défaut)', releases: 'Releases chargées', downloads: 'Downloads chargés', errors: 'Erreurs chargées', stats: 'Statistiques chargées', error: 'Erreur au chargement' },
        en: { loading: 'Loading...', ready: 'Ready!', config: 'Config loaded', configDefault: 'Config (default)', releases: 'Releases loaded', downloads: 'Downloads loaded', errors: 'Errors loaded', stats: 'Stats loaded', error: 'Loading error' }
    },
    t(key) { return (this.labels[this.lang] || this.labels.fr)[key] || key; },
    init(totalSteps) {
        this.el = document.getElementById('loading-splash');
        this.bar = document.getElementById('splash-progress-bar');
        this.status = document.getElementById('splash-status');
        this.retryBtn = document.getElementById('splash-retry-btn');
        this.total = totalSteps;
        this.done = 0;
        if (this.status) this.status.textContent = this.t('loading');

        if (this.retryBtn) {
            this.retryBtn.addEventListener('click', () => window.location.reload(true));
        }

        // Safety fallback: auto-dismiss splash after 6s even if an API call hangs
        clearTimeout(this.safetyTimer);
        this.safetyTimer = setTimeout(() => {
            if (this.el && !this.el.classList.contains('hidden')) {
                console.warn('[PWA] Splash timeout reached, auto-dismissing.');
                this.hide();
            }
        }, 6000);
    },
    step(key) {
        this.done++;
        const pct = Math.round((this.done / this.total) * 100);
        if (this.bar) this.bar.style.width = `${pct}%`;
        if (this.status) this.status.textContent = this.t(key);
        if (this.done >= this.total) this.hide();
    },
    error(msg) {
        if (this.status) this.status.textContent = msg || this.t('error');
        if (this.retryBtn) this.retryBtn.classList.remove('hidden');
    },
    hide() {
        clearTimeout(this.safetyTimer);
        if (this.status) this.status.textContent = this.t('ready');
        if (this.bar) this.bar.style.width = '100%';
        setTimeout(() => {
            if (this.el) this.el.classList.add('hidden');
        }, 400);
    }
};

// Global error catcher during boot
window.addEventListener('error', (e) => {
    console.error('[BOOT ERROR]', e.message);
    splash.error(splash.t('error'));
}, { once: true });

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
        const query = (e.target.value || '').trim().toLowerCase();
        const view = e.target.id === 'target-search' ? 'releases' : e.target.id.replace('search-', '');
        if (state[view]) {
            state[view].query = query;
            state[view].page = 1;
            if (view === 'releases' && state.currentView !== 'releases' && query) {
                document.querySelector('.nav-item[data-view="releases"]')?.click();
            }
            fetchData(view);
        }
    }, 300);
    targetSearch?.addEventListener('input', handleSearch);
    targetSearch?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const query = (targetSearch.value || '').trim().toLowerCase();
            state.releases.query = query;
            state.releases.page = 1;
            if (state.currentView !== 'releases') {
                document.querySelector('.nav-item[data-view="releases"]')?.click();
            }
            fetchData('releases');
        }
    });

    // ── Navigation & Scanner ──────────────────────────────────────────────────
    initNavigation();
    initScanner();
    initQuickScan();
    initErrors();
    initDownloads();

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

    // Launch all fetches in parallel, track progress (finally ensures step advances even on failure)
    Promise.resolve(fetchData('releases')).finally(() => splash.step('releases'));
    Promise.resolve(fetchDownloads()).finally(() => splash.step('downloads'));
    Promise.resolve(fetchErrors()).finally(() => splash.step('errors'));
    Promise.resolve(fetchStats()).finally(() => splash.step('stats'));
    initApp();

    // ── Service Worker Registration (PWA) ─────────────────────────────────────
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .then((registration) => {
                    // Check for updates periodically and on load
                    registration.update();
                })
                .catch((err) => {
                    console.debug('[PWA] ServiceWorker registration skipped/failed:', err);
                });
        });
    }

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


