export const CONFIG = {
    views: {
        releases: { limit: 20, recent: false, hours: null }
    },
    filters: {
        releases: [
            { type: 'category', value: 'movie', i18n: 'filter_movies', icon: 'fas fa-film' },
            { type: 'category', value: 'series', i18n: 'filter_series', icon: 'fas fa-tv' },
            { type: 'local', value: 'true', i18n: 'filter_local', icon: 'fas fa-map-marker-alt' },
            { type: 'resolution', value: '2160p', label: '2160p' },
            { type: 'resolution', value: '1080p', label: '1080p' },
        ]
    }
};

export const state = {
    currentView: 'releases',
    language: 'fr',
    releases: { items: [], rows: [], page: 1, limit: 20, total: 0, pages: 0, query: '', category: 'movie', source: '', resolution: '', year: '', network: '', recent: false, hours: null, local: '' },
    downloads: { items: [], active: {}, query: '' },
    errors: { items: [], page: 1, limit: 20, total: 0, pages: 0 },
    sources: [],
    years: [],
    networks: [],
    config: { alldebrid_enabled: false, realdebrid_enabled: false, bestdebrid_enabled: false }
};
