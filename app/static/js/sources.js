import { state } from './state.js';
import { formatDate } from './helpers.js';

// ─── Stats ────────────────────────────────────────────────────────────────────

export const renderStats = (stats) => {
    const els = {
        uniqueMovies: document.getElementById('stats-unique-movies'),
        size: document.getElementById('stats-size'),
        deadLinks: document.getElementById('stats-dead-links'),
        totalLinks: document.getElementById('stats-total-links'),
    };

    if (els.uniqueMovies) els.uniqueMovies.textContent = stats.unique_movies;
    if (els.size) els.size.textContent = stats.total_size;
    if (els.deadLinks) els.deadLinks.textContent = stats.dead_links;
    if (els.totalLinks) els.totalLinks.textContent = (stats.links_movies || 0) + (stats.links_series || 0);
};

// ─── Sources Dashboard ────────────────────────────────────────────────────────

export const renderSourcesDashboard = (data) => {
    const container = document.getElementById('sources-dashboard-container');
    if (!container) return;

    container.innerHTML = `
        <div class="table-container fade-in">
            <table class="sources-table">
                <thead>
                    <tr>
                        <th style="width: 40px"></th>
                        <th>${state.language === 'fr' ? 'Source' : 'Source'}</th>
                        <th style="text-align: right">${state.language === 'fr' ? 'Volume' : 'Volume'}</th>
                        <th style="text-align: center">${state.language === 'fr' ? 'Items' : 'Items'}</th>
                        <th>${state.language === 'fr' ? 'Dernier Scan' : 'Last Scan'}</th>
                        <th>${state.language === 'fr' ? 'Dernier Ajout' : 'Last Addition'}</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.sources.map(s => {
                        const lastLink = s.last_item || {};
                        const statusIcon = s.last_status === 'success' ? 'fa-check-circle' : 'fa-exclamation-triangle';
                        const statusClass = s.last_status === 'success' ? 'status-up' : 'status-down';
                        const sourceVolume = (state.stats_by_source && state.stats_by_source[s.name]) ? state.stats_by_source[s.name] : '-';
                        return `
                            <tr>
                                <td class="col-status"><i class="fas ${statusIcon} ${statusClass}"></i></td>
                                <td class="col-source" data-label="Source"><a href="${s.entry_url || '#'}" target="_blank" class="source-link-bold">${s.name}</a></td>
                                <td class="col-volume" data-label="Volume" style="text-align: right; font-weight: bold; color: var(--text-pure);">${sourceVolume}</td>
                                <td class="col-items" data-label="Items" style="text-align: center"><span class="source-count-badge">${s.total_items}</span></td>
                                <td class="col-scan" data-label="Scan"><span class="source-date-dim">${s.last_scan ? formatDate(s.last_scan) : '-'}</span></td>
                                <td class="col-last" data-label="Last Addition">${lastLink.title
                                    ? `<div class="last-addition-row"><a href="${lastLink.url}" target="_blank" class="last-link-title">${lastLink.title}</a><span class="last-date-badge">${formatDate(lastLink.date)}</span></div>`
                                    : '<span class="empty-val">-</span>'}</td>
                            </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
};
