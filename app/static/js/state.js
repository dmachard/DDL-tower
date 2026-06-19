export const CONFIG = {
    views: {
        releases: { limit: 20, recent: true, hours: 12 }
    },
    filters: {
        releases: [
            { type: 'recent', value: 'true', i18n: 'filter_recent', icon: 'fas fa-star tag-star' },
            { type: 'hours', value: '12', label: '12h' },
            { type: 'hours', value: '24', label: '24h' },
            { type: 'hours', value: '48', label: '48h' },
            { type: 'category', value: 'movie', i18n: 'filter_movies', icon: 'fas fa-film' },
            { type: 'category', value: 'series', i18n: 'filter_series', icon: 'fas fa-tv' },
            { type: 'local', value: 'true', i18n: 'filter_local', icon: 'fas fa-map-marker-alt' },
            { type: 'resolution', value: '2160p', label: '2160p' },
            { type: 'resolution', value: '1080p', label: '1080p' },
            { type: 'resolution', value: '720p', label: '720p' },
        ]
    }
};

export const state = {
    currentView: 'releases',
    language: 'fr',
    autoRefresh: false,
    releases: { items: [], page: 1, limit: 20, total: 0, pages: 0, query: '', category: '', source: '', resolution: '', year: '', network: '', recent: true, hours: 12, local: '' },
    downloads: { items: [], active: {}, query: '' },
    errors: { items: [], page: 1, limit: 20, total: 0, pages: 0 },
    sources: [],
    years: [],
    networks: [],
    config: { alldebrid_enabled: false, realdebrid_enabled: false, bestdebrid_enabled: false }
};
