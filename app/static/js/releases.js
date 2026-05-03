import { TRANSLATIONS } from './i18n.js';
import { state } from './state.js';
import { formatSeasonEp, formatLangs, formatBytes, beautifyHoster, getImdbUrl, renderRatingDots, formatDate } from './helpers.js';
import { renderPagination } from './pagination.js';
import { downloadUrls, deleteReleases, fetchData } from './api.js';
import { showConfirm } from './modals.js';

// ─── Release Card ─────────────────────────────────────────────────────────────

export const createReleaseCard = (rel) => {
    const card = document.createElement('div');
    card.className = `release-card ${rel.is_new ? 'is-new' : ''}`;

    const seasonEp = formatSeasonEp(rel.season, rel.episode);

    const subReleaseBlocks = rel.sub_releases.map((sub) => {
        const providers = {};
        sub.parts.forEach(p => {
            const h = p.hoster || 'Unknown';
            const cleanName = beautifyHoster(h);
            if (!providers[cleanName]) {
                providers[cleanName] = { name: cleanName, partsCount: 0, totalBytes: 0, urls: [], ids: [] };
            }
            providers[cleanName].partsCount++;
            providers[cleanName].totalBytes += (p.size_bytes || 0);
            providers[cleanName].urls.push(p.url);
            providers[cleanName].ids.push(p.id);
        });

        const providerRows = Object.values(providers).map(p => `
            <div class="rel-provider-row ${sub.is_new ? 'is-new' : ''}" title="${sub.raw_title || sub.title || sub.filename}">
                <span class="rel-p-name">${p.name}</span>
                <span class="rel-p-count">${p.partsCount}F</span>
                <span class="rel-p-size">${formatBytes(p.totalBytes)}</span>
                <div class="rel-p-actions">
                    <button class="rel-p-identify" data-ids="${p.ids.join(',')}" data-title="${sub.title || sub.filename}" title="${TRANSLATIONS[state.language].modal_identify_title}">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="rel-p-copy" data-urls="${p.urls.join('\n')}" title="${TRANSLATIONS[state.language].copy_links}">
                        <i class="fas fa-copy"></i>
                    </button>
                    ${(state.config.alldebrid_enabled || state.config.realdebrid_enabled || state.config.bestdebrid_enabled) ? `
                    <button class="rel-p-download" data-urls="${p.urls.join('\n')}" title="${TRANSLATIONS[state.language].download_links}">
                        <i class="fas fa-download"></i>
                    </button>` : ''}
                </div>
            </div>
        `).join('');

        return `<div class="sub-release-block">${providerRows}</div>`;
    }).join('');

    card.innerHTML = `
        <div class="rel-meta-top">
            ${rel.source_url
                ? `<a href="${rel.source_url}" target="_blank" class="rel-source-link"><i class="fas fa-server"></i> ${rel.source || '...'}</a>`
                : `<span class="rel-source-label"><i class="fas fa-server"></i> ${rel.source || '...'}</span>`
            }
            ${rel.is_new ? '<i class="fas fa-star badge-star" title="New release inside"></i>' : ''}
            <i class="fas fa-chevron-down rel-expand-icon"></i>
        </div>
        <div class="rel-tags">
            ${seasonEp ? `<span class="rel-tag rel-tag-se">${seasonEp}</span>` : ''}
            ${rel.language && rel.language !== 'None' ? `<span class="rel-tag rel-tag-lang">${formatLangs(rel.language)}</span>` : ''}
            ${rel.network ? `<span class="rel-tag rel-tag-network">${rel.network}</span>` : ''}
            ${rel.v_quality ? `<span class="rel-tag rel-tag-vquality">${rel.v_quality}</span>` : ''}
            ${rel.quality ? `<span class="rel-tag rel-tag-quality">${rel.quality}</span>` : ''}
            ${rel.codec ? `<span class="rel-tag rel-tag-codec">${rel.codec}</span>` : ''}
        </div>
        <div class="rel-providers">${subReleaseBlocks}</div>
    `;

    card.onclick = () => card.classList.toggle('expanded');

    card.querySelectorAll('.rel-p-identify').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            const ids = btn.getAttribute('data-ids').split(',').map(id => parseInt(id));
            const title = btn.getAttribute('data-title');
            import('./modals.js').then(({ openIdentifyModal }) => openIdentifyModal(ids, title));
        };
    });

    card.querySelectorAll('.rel-p-copy').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const urls = btn.getAttribute('data-urls');
            try {
                await navigator.clipboard.writeText(urls);
                const icon = btn.querySelector('i');
                const originalClass = icon.className;
                icon.className = 'fas fa-check';
                btn.classList.add('success');
                setTimeout(() => { icon.className = originalClass; btn.classList.remove('success'); }, 1000);
            } catch (err) { console.error('Failed to copy!', err); }
        };
    });

    card.querySelectorAll('.rel-p-download').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const urls = btn.getAttribute('data-urls').split('\n');
            const icon = btn.querySelector('i');
            const originalClass = icon.className;
            icon.className = 'fas fa-spinner fa-spin';
            btn.disabled = true;
            try {
                const res = await downloadUrls(urls);
                icon.className = res.ok ? 'fas fa-check' : 'fas fa-times';
                btn.classList.add(res.ok ? 'success' : 'error');
            } catch (err) {
                console.error('Download error:', err);
                icon.className = 'fas fa-times';
                btn.classList.add('error');
            } finally {
                setTimeout(() => { icon.className = originalClass; btn.classList.remove('success', 'error'); btn.disabled = false; }, 2000);
            }
        };
    });

    return card;
};

// ─── Releases ─────────────────────────────────────────────────────────────────

export const renderReleases = (groups) => {
    const container = document.getElementById('releases-container');
    const template = document.getElementById('release-group-template');
    if (!container || !template) return;

    container.innerHTML = '';
    if (!groups || groups.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon"><i class="fas fa-film"></i></div>
                <div class="empty-state-text">${TRANSLATIONS[state.language].msg_no_results}</div>
                <div class="empty-state-subtext">${TRANSLATIONS[state.language].empty_state_subtext}</div>
            </div>`;
        renderPagination('releases');
        return;
    }

    groups.forEach((group, index) => {
        const clone = template.content.cloneNode(true);
        const row = clone.querySelector('.release-group-row');
        row.style.animationDelay = `${index * 0.05}s`;
        if (group.category) row.classList.add(`cat-${group.category}`);

        const titleEl = clone.querySelector('.group-title');
        const titleText = state.language === 'fr'
            ? (group.title_fr || group.official_title || group.title)
            : (group.official_title || group.title);
        titleEl.innerHTML = group.imdb_id
            ? `<a href="${getImdbUrl(group.imdb_id)}" target="_blank" class="imdb-link">${titleText}</a>`
            : titleText;

        const catTag = clone.querySelector('.group-category');
        if (group.category) {
            catTag.textContent = group.category === 'movie'
                ? TRANSLATIONS[state.language].filter_movies
                : TRANSLATIONS[state.language].filter_series;
            catTag.classList.add(`cat-${group.category}`);
        } else {
            catTag.classList.add('hidden');
        }

        clone.querySelector('.group-year').textContent = group.year ? `(${group.year})` : '';

        const posterEl = clone.querySelector('.group-poster');
        const actionsEl = clone.querySelector('.group-actions');

        const btnIdentify = document.createElement('div');
        btnIdentify.className = 'btn-action-round';
        btnIdentify.title = TRANSLATIONS[state.language].modal_identify_title;
        btnIdentify.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i>';
        btnIdentify.onclick = (e) => {
            e.stopPropagation();
            const allLinks = [];
            Object.values(group.resolutions || {}).forEach(relList => {
                relList.forEach(rel => rel.sub_releases.forEach(sub => sub.parts.forEach(p => allLinks.push(p.id))));
            });
            import('./modals.js').then(({ openIdentifyModal }) => openIdentifyModal(allLinks, group.official_title || group.title || ''));
        };
        actionsEl.appendChild(btnIdentify);
        
        const btnDelete = document.createElement('div');
        btnDelete.className = 'btn-action-round btn-danger';
        btnDelete.title = TRANSLATIONS[state.language].btn_delete;
        btnDelete.innerHTML = '<i class="fas fa-trash"></i>';
        btnDelete.onclick = async (e) => {
            e.stopPropagation();
            const allLinks = [];
            Object.values(group.resolutions || {}).forEach(relList => {
                relList.forEach(rel => rel.sub_releases.forEach(sub => sub.parts.forEach(p => allLinks.push(p.id))));
            });
            
            const title = TRANSLATIONS[state.language].btn_delete;
            const msg = TRANSLATIONS[state.language].confirm_delete_release;
            
            if (await showConfirm(title, msg)) {
                try {
                    const res = await deleteReleases(allLinks);
                    if (res.ok) {
                        fetchData('releases');
                    }
                } catch (err) {
                    console.error('Failed to delete release:', err);
                }
            }
        };
        actionsEl.appendChild(btnDelete);


        if (group.poster_path) {
            let pPath = group.poster_path;
            if (pPath.startsWith('static/posters/')) pPath = pPath.replace('static/posters/', 'posters/');
            if (!pPath.startsWith('posters/')) pPath = `posters/${pPath}`;
            if (!pPath.startsWith('/')) pPath = '/' + pPath;
            posterEl.style.backgroundImage = `url(${pPath})`;
            posterEl.classList.add('has-poster');
        }

        const plotEl = clone.querySelector('.group-plot');
        const plot = state.language === 'fr' ? (group.plot_fr || group.plot_en) : (group.plot_en || group.plot_fr);
        if (plot && plot !== 'N/A') plotEl.textContent = plot;

        const ratingEl = clone.querySelector('.group-rating');
        if (group.rating) ratingEl.innerHTML = renderRatingDots(group.rating);
        else ratingEl.classList.add('hidden');

        clone.querySelector('.group-last-updated').textContent = `${TRANSLATIONS[state.language].msg_latest_update}: ${formatDate(group.last_updated)}`;

        const mobileToggle = document.createElement('button');
        mobileToggle.className = 'mobile-toggle-releases';
        mobileToggle.innerHTML = `<span>${TRANSLATIONS[state.language].btn_show_versions}</span> <i class="fas fa-chevron-down"></i>`;
        mobileToggle.onclick = () => {
            const isExpanded = row.classList.toggle('expanded-group');
            mobileToggle.querySelector('span').textContent = isExpanded
                ? TRANSLATIONS[state.language].btn_hide_versions
                : TRANSLATIONS[state.language].btn_show_versions;
        };
        clone.querySelector('.col-main').appendChild(mobileToggle);

        const releasesCol = clone.querySelector('.col-releases');
        const resolutions = group.resolutions || {};
        const resOrder = { '2160p': 5, '4K': 5, '1080p': 4, '720p': 3, '576p': 2, '480p': 1, 'SD': 0, 'HD': -1 };
        const sortedRes = Object.keys(resolutions).sort((a, b) => (resOrder[b] || 0) - (resOrder[a] || 0));

        sortedRes.forEach(res => {
            const resRow = document.createElement('div');
            resRow.className = 'quality-row';
            resRow.innerHTML = `<div class="quality-label">${res}</div>`;

            const seasonGroups = {};
            resolutions[res].forEach(rel => {
                const s = rel.season || 'Other';
                if (!seasonGroups[s]) seasonGroups[s] = [];
                seasonGroups[s].push(rel);
            });

            const sortedSeasons = Object.keys(seasonGroups).sort((a, b) => {
                if (a === 'Other') return 1;
                if (b === 'Other') return -1;
                return parseInt(a) - parseInt(b);
            });

            const seasonsContainer = document.createElement('div');
            seasonsContainer.className = 'seasons-container';
            resRow.appendChild(seasonsContainer);

            sortedSeasons.forEach(s => {
                const seasonDiv = document.createElement('div');
                seasonDiv.className = 'season-group';

                if (group.category === 'series' && s !== 'Other') {
                    const sHeader = document.createElement('div');
                    sHeader.className = 'season-header';
                    sHeader.textContent = `Season ${s.toString().padStart(2, '0')}`;
                    seasonDiv.appendChild(sHeader);
                }

                const grid = document.createElement('div');
                grid.className = 'quality-grid';
                seasonDiv.appendChild(grid);
                seasonGroups[s].forEach(rel => grid.appendChild(createReleaseCard(rel)));
                seasonsContainer.appendChild(seasonDiv);
            });

            releasesCol.appendChild(resRow);
        });

        container.appendChild(clone);
    });

    renderPagination('releases');
};
