import { state } from './state.js';
import { renderReleases } from './releases.js';
import { renderDownloads } from './downloads.js';
import { renderStats, renderSourcesDashboard } from './sources.js';
import { renderPagination } from './pagination.js';
import { renderErrors } from './errors.js';

export const fetchData = async (view) => {
    const viewState = state[view];
    if (!viewState) return;

    try {
        const url = new URL(`/api/${view}`, window.location.origin);
        url.searchParams.append('page', viewState.page);
        url.searchParams.append('limit', viewState.limit);
        if (viewState.query) url.searchParams.append('q', viewState.query);
        if (viewState.category) url.searchParams.append('category', viewState.category);
        if (view === 'releases' && viewState.source) url.searchParams.append('source', viewState.source);
        if (view === 'releases' && viewState.resolution) url.searchParams.append('resolution', viewState.resolution);
        if (view === 'releases' && viewState.year) url.searchParams.append('year', viewState.year);
        if (view === 'releases' && viewState.network) url.searchParams.append('network', viewState.network);
        if (view === 'releases' && viewState.local) url.searchParams.append('local', viewState.local);
        if (viewState.recent) url.searchParams.append('recent', 'true');
        if (viewState.hours) url.searchParams.append('hours', viewState.hours);

        const res = await fetch(url);
        const data = await res.json();

        viewState.items = data.items;
        viewState.total = data.total;
        viewState.pages = data.pages;

        const countEl = document.getElementById(`count-${view}`);
        if (countEl) countEl.textContent = data.total;
        const mobCountEl = document.getElementById(`mobile-count-${view}`);
        if (mobCountEl) mobCountEl.textContent = data.total;

        if (state.currentView === view) {
            if (view === 'releases') renderReleases(data.items);
            else if (view === 'errors') {
                renderErrors(data.items);
                renderPagination('errors');
            }
        }
    } catch (err) {
        console.error(`Error fetching ${view}:`, err);
    }
};

export const fetchDownloads = async () => {
    try {
        const [filesRes, activeRes] = await Promise.all([
            fetch('/api/downloads'),
            fetch('/api/active-downloads')
        ]);

        const files = filesRes.ok ? await filesRes.json() : [];
        const active = activeRes.ok ? await activeRes.json() : {};

        state.downloads.items = Array.isArray(files) ? files : [];
        state.downloads.active = (active && !active.detail) ? active : {};

        const activeCount = Object.keys(state.downloads.active).length;
        const diskCount = state.downloads.items.filter(f => !state.downloads.active[f.name]).length;

        const totalDownloads = diskCount + activeCount;
        const countEl = document.getElementById('count-downloads');
        if (countEl) countEl.textContent = totalDownloads;
        const mobCountEl = document.getElementById('mobile-count-downloads');
        if (mobCountEl) mobCountEl.textContent = totalDownloads;

        if (state.currentView === 'downloads') {
            renderDownloads(state.downloads.items);
        }
    } catch (err) {
        console.error('Error fetching downloads:', err);
    }
};

export const fetchStats = async () => {
    try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        state.stats_by_source = stats.size_by_source || {};
        renderStats(stats);
    } catch (err) {
        console.error('Error fetching stats:', err);
    }
};

export const fetchSourcesDashboard = async () => {
    try {
        const res = await fetch('/api/sources/dashboard');
        const data = await res.json();
        renderSourcesDashboard(data);
    } catch (err) {
        console.error('Error fetching sources dashboard:', err);
    }
};

export const fetchErrors = async () => {
    await fetchData('errors');
};

export const fetchSources = async (loadFilters, updateTagsUI) => {
    try {
        const res = await fetch('/api/sources');
        state.sources = await res.json();
        loadFilters('releases');
        updateTagsUI('filter-tags-releases', state.releases);
    } catch (err) {
        console.error('Failed to fetch sources:', err);
    }
};

export const fetchYears = async (loadFilters, updateTagsUI) => {
    try {
        state.years = [2026, 2025, 2024];
        loadFilters('releases');
        updateTagsUI('filter-tags-releases', state.releases);
    } catch (err) {
        console.error('Failed to fetch years:', err);
    }
};

export const fetchNetworks = async (loadFilters, updateTagsUI) => {
    try {
        state.networks = ['Netflix', 'Disney+', 'HBO', 'Apple TV', 'Amazon'];
        loadFilters('releases');
        updateTagsUI('filter-tags-releases', state.releases);
    } catch (err) {
        console.error('Failed to fetch networks:', err);
    }
};

export const fetchConfig = async () => {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    state.config = cfg;
    return cfg;
};

export const startDirectScan = async (url) => {
    return fetch('/api/scan/direct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: [url] })
    });
};

export const extractText = async (text) => {
    return fetch('/api/scan/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    });
};

export const downloadUrls = async (urls) => {
    return fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls })
    });
};

export const deleteReleases = async (ids) => {
    return fetch('/api/releases', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids })
    });
};

export const checkUrls = async (urls) => {
    return fetch('/api/check-links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls })
    });
};
