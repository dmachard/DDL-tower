import { TRANSLATIONS } from './i18n.js';
import { state } from './state.js';
import { formatSeasonEp, formatLangs, formatBytes, beautifyHoster, getImdbUrl, renderRatingDots, formatDate } from './helpers.js';
import { renderPagination } from './pagination.js';
import { downloadUrls, deleteReleases, fetchData, updateReleaseSource } from './api.js';
import { showConfirm } from './modals.js';

// ─── Release Card ─────────────────────────────────────────────────────────────

const syncGroupCheckResults = (group, data) => {
    if (!group || !group.resolutions) return;
    const nowIso = new Date().toISOString();
    Object.values(group.resolutions).forEach(relList => {
        relList.forEach(rel => {
            (rel.sub_releases || []).forEach(sub => {
                (sub.parts || []).forEach(p => {
                    const info = data[p.url];
                    if (info && (info.status === 'alive' || info.status === 'dead')) {
                        p.status = info.status;
                        p.last_checked = nowIso;
                        if (activeDetailContext) activeDetailContext.dirty = true;
                    }
                });
            });
        });
    });
};

const applyProviderCheckResult = (pRow, checkBtn, isDead, hasError, restoreIconClass = 'fa-heartbeat') => {
    const icon = checkBtn.querySelector('i');
    if (isDead) {
        icon.className = 'fas fa-heart-broken';
        checkBtn.style.color = 'var(--accent-red)';
        pRow.style.opacity = '0.5';
        pRow.style.borderLeft = '3px solid var(--accent-red)';
        pRow.classList.add('is-dead');
    } else if (hasError) {
        icon.className = 'fas fa-exclamation-triangle';
        checkBtn.style.color = 'var(--warning)';
        setTimeout(() => { icon.className = restoreIconClass; checkBtn.style.color = ''; }, 3000);
        pRow.classList.remove('is-dead');
        pRow.style.opacity = '';
        pRow.style.borderLeft = '';
    } else {
        icon.className = 'fas fa-check';
        checkBtn.style.color = '';
        checkBtn.classList.add('success');
        setTimeout(() => { icon.className = restoreIconClass; checkBtn.classList.remove('success'); }, 2000);
        pRow.classList.remove('is-dead');
        pRow.style.opacity = '';
        pRow.style.borderLeft = '';
    }

    if (isDead || !hasError) {
        const nowFormatted = formatDate(new Date().toISOString());
        let checkedEl = pRow.querySelector('.rel-p-checked');
        if (!checkedEl) {
            checkedEl = document.createElement('span');
            checkedEl.className = 'rel-p-checked';
            checkedEl.title = 'Last checked';
            const sizeEl = pRow.querySelector('.rel-p-size');
            if (sizeEl) pRow.insertBefore(checkedEl, sizeEl);
        }
        checkedEl.textContent = nowFormatted;
    }
};

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
                providers[cleanName] = { name: cleanName, partsCount: 0, totalBytes: 0, urls: [], ids: [], statuses: [], lastChecked: null };
            }
            providers[cleanName].partsCount++;
            providers[cleanName].totalBytes += (p.size_bytes || 0);
            providers[cleanName].urls.push(p.url);
            providers[cleanName].ids.push(p.id);
            if (p.status) providers[cleanName].statuses.push(p.status);
            if (p.last_checked && (!providers[cleanName].lastChecked || p.last_checked > providers[cleanName].lastChecked)) {
                providers[cleanName].lastChecked = p.last_checked;
            }
        });

        const providerRows = Object.values(providers).map(p => {
            const hasDead = p.statuses.includes('dead');
            const hasError = p.statuses.includes('error');

            let rowExtraClass = '';
            let rowStyle = '';
            let checkIconClass = 'fa-heartbeat';
            let checkIconStyle = '';
            let checkTitle = 'Check links';

            if (hasDead) {
                rowExtraClass = 'is-dead';
                rowStyle = 'opacity: 0.5; border-left: 3px solid var(--accent-red);';
                checkIconClass = 'fa-heart-broken';
                checkIconStyle = 'color: var(--accent-red);';
                checkTitle = 'Dead link(s)';
            } else if (hasError) {
                rowStyle = 'border-left: 3px solid var(--warning);';
                checkIconClass = 'fa-exclamation-triangle';
                checkIconStyle = 'color: var(--warning);';
                checkTitle = 'Hoster error';
            }

            return `
            <div class="rel-provider-row ${sub.is_new ? 'is-new' : ''} ${rowExtraClass}" style="${rowStyle}" title="${sub.raw_title || sub.title || sub.filename}">
                <span class="rel-p-name">${p.name} ${hasError ? '<i class="fas fa-exclamation-circle" style="color: var(--warning); font-size: 11px; margin-left: 4px;" title="Hoster check error"></i>' : ''}</span>
                ${p.partsCount > 1 ? `<span class="rel-p-count">${p.partsCount}F</span>` : ''}
                ${p.lastChecked ? `<span class="rel-p-checked" title="Last checked">${formatDate(p.lastChecked)}</span>` : ''}
                <span class="rel-p-size">${formatBytes(p.totalBytes)}</span>
                <div class="rel-p-actions">
                    <button class="rel-p-identify" data-ids="${p.ids.join(',')}" data-title="${sub.title || sub.filename}" title="${TRANSLATIONS[state.language].modal_identify_title}">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="rel-p-check" data-urls="${p.urls.join('\n')}" style="${checkIconStyle}" title="${checkTitle}">
                        <i class="fas ${checkIconClass}"></i>
                    </button>
                    <button class="rel-p-copy-title" data-title="${sub.raw_title || sub.title || sub.filename}" title="${TRANSLATIONS[state.language].copy_release_name || 'Copy release name'}">
                        <i class="fas fa-tag"></i>
                    </button>
                    <button class="rel-p-copy" data-urls="${p.urls.join('\n')}" title="${TRANSLATIONS[state.language].copy_links}">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button class="rel-p-delete" data-ids="${p.ids.join(',')}" title="${TRANSLATIONS[state.language].btn_delete || 'Delete'}">
                        <i class="fas fa-trash"></i>
                    </button>
                    ${(state.config.alldebrid_enabled || state.config.realdebrid_enabled || state.config.bestdebrid_enabled) ? `
                    <button class="rel-p-download" data-urls="${p.urls.join('\n')}" title="${TRANSLATIONS[state.language].download_links}">
                        <i class="fas fa-download"></i>
                    </button>` : ''}
                </div>
            </div>
        `;
        }).join('');

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
            ${rel.source ? `<span class="rel-tag rel-tag-source">${rel.source_url ? `<a href="${rel.source_url}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${rel.source}</a>` : rel.source}</span>` : ''}
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

    card.querySelectorAll('.rel-p-copy-title').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const title = btn.getAttribute('data-title');
            try {
                await navigator.clipboard.writeText(title);
                const icon = btn.querySelector('i');
                const originalClass = icon.className;
                icon.className = 'fas fa-check';
                btn.classList.add('success');
                setTimeout(() => { icon.className = originalClass; btn.classList.remove('success'); }, 1000);
            } catch (err) { console.error('Failed to copy title!', err); }
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

    card.querySelectorAll('.rel-p-check').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const urls = btn.getAttribute('data-urls').split('\n');
            const icon = btn.querySelector('i');
            const originalClass = icon.className;
            icon.className = 'fas fa-spinner fa-spin';
            btn.disabled = true;
            try {
                const res = await import('./api.js').then(m => m.checkUrls(urls));
                if (res.ok) {
                    const data = await res.json();
                    let isDead = false;
                    let hasError = false;
                    for (const url of urls) {
                        const s = data[url] ? data[url].status : 'unknown';
                        if (s === 'dead') isDead = true;
                        if (s === 'error' || s === 'unknown') hasError = true;
                    }
                    const pRow = btn.closest('.rel-provider-row');
                    applyProviderCheckResult(pRow, btn, isDead, hasError, originalClass);
                    if (activeDetailContext?.group) {
                        syncGroupCheckResults(activeDetailContext.group, data);
                        activeDetailContext.refreshTabs?.();
                    }
                    
                    const cardElement = btn.closest('.release-card');
                    if (cardElement) {
                        const pRows = cardElement.querySelectorAll('.rel-provider-row');
                        const deadRows = cardElement.querySelectorAll('.rel-provider-row.is-dead');
                        if (pRows.length > 0 && pRows.length === deadRows.length) {
                            cardElement.style.border = '2px solid var(--accent-red)';
                            cardElement.style.opacity = '0.6';
                        } else {
                            cardElement.style.border = '';
                            cardElement.style.opacity = '';
                        }
                    }
                } else {
                    icon.className = 'fas fa-times';
                    btn.classList.add('error');
                    setTimeout(() => { icon.className = originalClass; btn.classList.remove('error'); }, 2000);
                }
            } catch (err) {
                console.error('Check error:', err);
                icon.className = 'fas fa-times';
                btn.classList.add('error');
                setTimeout(() => { icon.className = originalClass; btn.classList.remove('error'); }, 2000);
            } finally {
                btn.disabled = false;
            }
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

    card.querySelectorAll('.rel-p-delete').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const ids = btn.getAttribute('data-ids').split(',').map(id => parseInt(id));
            const title = TRANSLATIONS[state.language].btn_delete || 'Delete';
            const msg = TRANSLATIONS[state.language].confirm_delete_release || 'Are you sure?';
            
            if (await showConfirm(title, msg)) {
                try {
                    const res = await deleteReleases(ids);
                    if (res.ok) {
                        fetchData('releases');
                    }
                } catch (err) {
                    console.error('Failed to delete link:', err);
                }
            }
        };
    });

    return card;
};

// ─── Helpers for Netflix UI ───────────────────────────────────────────────────

const resolvePosterUrl = (posterPath) => {
    if (!posterPath) return null;
    let p = posterPath;
    if (p.startsWith('static/posters/')) p = p.replace('static/posters/', 'posters/');
    if (!p.startsWith('posters/')) p = `posters/${p}`;
    if (!p.startsWith('/')) p = '/' + p;
    return p;
};

const getGroupTitle = (group) => (
    state.language === 'fr'
        ? (group.title_fr || group.official_title || group.title)
        : (group.official_title || group.title)
);

const collectGroupIds = (group) => {
    const ids = [];
    Object.values(group.resolutions || {}).forEach(relList => {
        relList.forEach(rel => rel.sub_releases.forEach(sub => sub.parts.forEach(p => ids.push(p.id))));
    });
    return ids;
};

const filterSubParts = (sub, mode) => {
    const parts = sub.parts || [];
    if (mode === 'dead') return parts.filter(p => p.status === 'dead');
    if (mode === 'new' || mode === true) return sub.is_new ? parts.filter(p => p.status !== 'dead') : [];
    return parts.filter(p => p.status !== 'dead');
};

const countSubReleases = (group, mode = 'all') => {
    if (!group.resolutions) {
        if (mode === 'dead') return 0;
        return (mode === 'new' || mode === true) ? (group.new_count || 0) : (group.all_count ?? group.count ?? 0);
    }
    let count = 0;
    Object.values(group.resolutions).forEach(relList => {
        relList.forEach(rel => {
            rel.sub_releases.forEach(sub => {
                if (filterSubParts(sub, mode).length > 0) count++;
            });
        });
    });
    return count;
};

const renderResolutionList = (targetEl, group, mode) => {
    targetEl.innerHTML = '';
    const resolutions = group.resolutions || {};
    const resOrder = { '2160p': 5, '4K': 5, '1080p': 4, '720p': 3, '576p': 2, '480p': 1, 'SD': 0, 'HD': -1 };
    const sortedRes = Object.keys(resolutions).sort((a, b) => (resOrder[b] || 0) - (resOrder[a] || 0));

    let renderedCount = 0;

    sortedRes.forEach(res => {
        const filteredCards = [];
        resolutions[res].forEach(rel => {
            const matchingSubs = rel.sub_releases
                .map(s => ({ ...s, parts: filterSubParts(s, mode) }))
                .filter(s => s.parts.length > 0);
            if (matchingSubs.length > 0) {
                filteredCards.push({ ...rel, sub_releases: matchingSubs });
            }
        });

        if (filteredCards.length === 0) return;
        renderedCount += filteredCards.length;

        const resRow = document.createElement('div');
        resRow.className = 'quality-row';
        resRow.innerHTML = `<div class="quality-label">${res}</div>`;

        const seasonGroups = {};
        filteredCards.forEach(rel => {
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
            seasonGroups[s].forEach(rel => {
                const card = createReleaseCard(rel);
                card.classList.add('expanded');
                grid.appendChild(card);
            });
            seasonsContainer.appendChild(seasonDiv);
        });

        targetEl.appendChild(resRow);
    });

    if (renderedCount === 0) {
        targetEl.innerHTML = `<div class="detail-empty-links">${TRANSLATIONS[state.language].no_new_links}</div>`;
    }
};

// ─── Detail Modal ─────────────────────────────────────────────────────────────

let detailModalBound = false;
let activeDetailContext = null;

const bindDetailModalClose = () => {
    if (detailModalBound) return;
    detailModalBound = true;
    const modal = document.getElementById('release-detail-modal');
    const closeBtn = document.getElementById('close-detail-modal');
    if (!modal) return;
    const close = () => {
        const shouldRefresh = activeDetailContext?.dirty;
        modal.classList.remove('active');
        activeDetailContext = null;
        if (shouldRefresh) fetchData('releases');
    };
    closeBtn?.addEventListener('click', close);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) close();
    });
    window.addEventListener('release-identified', (e) => {
        if (!modal.classList.contains('active') || !activeDetailContext) return;
        const detail = { ...e.detail };
        if (detail.poster_path) {
            detail.poster_path = `${detail.poster_path}?t=${Date.now()}`;
        }
        Object.assign(activeDetailContext.group, detail);
        openReleaseModal(activeDetailContext.group, activeDetailContext.currentSource);
    });
};

export const openReleaseModal = (group, currentSource = '') => {
    bindDetailModalClose();
    activeDetailContext = { group, currentSource };
    const modal = document.getElementById('release-detail-modal');
    if (!modal) return;

    const titleText = getGroupTitle(group);
    const posterUrl = resolvePosterUrl(group.poster_path);

    const heroBg = document.getElementById('detail-hero-bg');
    const posterEl = document.getElementById('detail-poster');
    if (posterUrl) {
        heroBg.style.backgroundImage = `url("${posterUrl}")`;
        posterEl.style.backgroundImage = `url("${posterUrl}")`;
        posterEl.classList.add('has-poster');
    } else {
        heroBg.style.backgroundImage = '';
        posterEl.style.backgroundImage = '';
        posterEl.classList.remove('has-poster');
    }

    const titleEl = document.getElementById('detail-title');
    titleEl.innerHTML = group.imdb_id
        ? `<a href="${getImdbUrl(group.imdb_id)}" target="_blank" class="imdb-link">${titleText} <i class="fas fa-external-link-alt" style="font-size: 0.7em; opacity: 0.6;"></i></a>`
        : titleText;

    const catEl = document.getElementById('detail-category');
    if (group.category) {
        catEl.textContent = group.category === 'movie'
            ? TRANSLATIONS[state.language].filter_movies
            : TRANSLATIONS[state.language].filter_series;
        catEl.className = `group-category cat-${group.category}`;
    } else {
        catEl.className = 'group-category hidden';
    }

    document.getElementById('detail-year').textContent = group.year ? `(${group.year})` : '';

    const ratingEl = document.getElementById('detail-rating');
    if (group.rating) {
        ratingEl.innerHTML = renderRatingDots(group.rating);
        ratingEl.classList.remove('hidden');
    } else {
        ratingEl.classList.add('hidden');
    }

    const plotEl = document.getElementById('detail-plot');
    const plot = state.language === 'fr' ? (group.plot_fr || group.plot_en) : (group.plot_en || group.plot_fr);
    plotEl.textContent = (plot && plot !== 'N/A') ? plot : '';

    document.getElementById('detail-updated').textContent = `${TRANSLATIONS[state.language].msg_latest_update}: ${formatDate(group.last_updated)}`;

    // Group-level action buttons
    const actionsEl = document.getElementById('detail-hero-actions');
    actionsEl.innerHTML = '';

    const btnIdentify = document.createElement('button');
    btnIdentify.type = 'button';
    btnIdentify.className = 'btn-action-round';
    btnIdentify.title = TRANSLATIONS[state.language].modal_identify_title;
    btnIdentify.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i>';
    btnIdentify.onclick = () => {
        import('./modals.js').then(({ openIdentifyModal }) =>
            openIdentifyModal(collectGroupIds(group), group.official_title || group.title || '')
        );
    };
    actionsEl.appendChild(btnIdentify);

    const btnCheckAll = document.createElement('button');
    btnCheckAll.type = 'button';
    btnCheckAll.className = 'btn-action-round';
    btnCheckAll.title = 'Vérifier tous les liens';
    btnCheckAll.innerHTML = '<i class="fas fa-heartbeat"></i>';
    btnCheckAll.onclick = async () => {
        const icon = btnCheckAll.querySelector('i');
        const originalClass = icon.className;
        icon.className = 'fas fa-spinner fa-spin';
        btnCheckAll.disabled = true;

        const linksBody = document.getElementById('detail-links-body');
        const allUrls = [];
        Object.values(group.resolutions || {}).forEach(relList => {
            relList.forEach(rel => {
                (rel.sub_releases || []).forEach(sub => {
                    (sub.parts || []).forEach(p => {
                        if (p.url && p.status !== 'dead' && !allUrls.includes(p.url)) allUrls.push(p.url);
                    });
                });
            });
        });

        const urlMappings = [];
        linksBody.querySelectorAll('.rel-provider-row:not(.is-dead)').forEach(pRow => {
            const checkBtn = pRow.querySelector('.rel-p-check');
            if (checkBtn) {
                const urls = checkBtn.getAttribute('data-urls').split('\n');
                urls.forEach(u => { if (u && !allUrls.includes(u)) allUrls.push(u); });
                urlMappings.push({ pRow, urls, checkBtn });
            }
        });

        if (allUrls.length === 0) {
            icon.className = originalClass;
            btnCheckAll.disabled = false;
            return;
        }

        try {
            const res = await import('./api.js').then(m => m.checkUrls(allUrls));
            if (res.ok) {
                const data = await res.json();
                syncGroupCheckResults(group, data);
                urlMappings.forEach(mapping => {
                    let isDead = false;
                    let hasError = false;
                    mapping.urls.forEach(url => {
                        const s = data[url] ? data[url].status : 'unknown';
                        if (s === 'dead') isDead = true;
                        if (s === 'error' || s === 'unknown') hasError = true;
                    });
                    applyProviderCheckResult(mapping.pRow, mapping.checkBtn, isDead, hasError, 'fas fa-heartbeat');
                });
                activeDetailContext?.refreshTabs?.();
            }
        } catch (err) {
            console.error(err);
        } finally {
            icon.className = originalClass;
            btnCheckAll.disabled = false;
        }
    };
    actionsEl.appendChild(btnCheckAll);

    const btnCopyMd = document.createElement('button');
    btnCopyMd.type = 'button';
    btnCopyMd.className = 'btn-action-round';
    btnCopyMd.title = TRANSLATIONS[state.language].copy_all_markdown || 'Copier le résumé Markdown';
    btnCopyMd.innerHTML = '<i class="fab fa-markdown"></i>';
    btnCopyMd.onclick = async () => {
        let md = `# ${titleText} ${group.year ? `(${group.year})` : ''}\n\n`;
        const resolutions = group.resolutions || {};
        const resOrder = { '2160p': 5, '4K': 5, '1080p': 4, '720p': 3, '576p': 2, '480p': 1, 'SD': 0, 'HD': -1 };
        Object.keys(resolutions).sort((a, b) => (resOrder[b] || 0) - (resOrder[a] || 0)).forEach(res => {
            md += `## ${res}\n\n`;
            resolutions[res].forEach(rel => {
                rel.sub_releases.forEach(sub => {
                    md += `* **${sub.raw_title || sub.title || sub.filename}**\n`;
                    sub.parts.forEach(p => { md += `  * [${p.hoster || 'Link'}](${p.url})\n`; });
                });
            });
            md += `\n`;
        });
        try {
            await navigator.clipboard.writeText(md.trim());
            const icon = btnCopyMd.querySelector('i');
            const orig = icon.className;
            icon.className = 'fas fa-check';
            btnCopyMd.classList.add('success');
            setTimeout(() => { icon.className = orig; btnCopyMd.classList.remove('success'); }, 1000);
        } catch (err) { console.error(err); }
    };
    actionsEl.appendChild(btnCopyMd);

    const btnDelete = document.createElement('button');
    btnDelete.type = 'button';
    btnDelete.className = 'btn-action-round btn-danger';
    btnDelete.title = TRANSLATIONS[state.language].btn_delete;
    btnDelete.innerHTML = '<i class="fas fa-trash"></i>';
    btnDelete.onclick = async () => {
        const title = TRANSLATIONS[state.language].btn_delete;
        const msg = TRANSLATIONS[state.language].confirm_delete_release;
        if (await showConfirm(title, msg)) {
            const res = await deleteReleases(collectGroupIds(group));
            if (res.ok) {
                modal.classList.remove('active');
                fetchData('releases');
            }
        }
    };
    actionsEl.appendChild(btnDelete);

    if (state.sources && state.sources.length > 0) {
        const srcSelect = document.createElement('select');
        srcSelect.className = 'detail-source-select';
        srcSelect.title = 'Changer la source';
        const detectedSource = currentSource || (() => {
            for (const list of Object.values(group.resolutions || {})) {
                if (list.length && list[0].source) return list[0].source;
            }
            return '';
        })();

        const optEmpty = document.createElement('option');
        optEmpty.value = '';
        optEmpty.textContent = detectedSource || 'Source...';
        srcSelect.appendChild(optEmpty);

        state.sources.forEach(src => {
            const opt = document.createElement('option');
            opt.value = src;
            opt.textContent = src;
            if (src === detectedSource) opt.selected = true;
            srcSelect.appendChild(opt);
        });

        srcSelect.onchange = async () => {
            const newSource = srcSelect.value;
            if (!newSource || newSource === detectedSource) return;
            const ids = collectGroupIds(group);
            if (!ids.length) return;
            srcSelect.disabled = true;
            try {
                const res = await updateReleaseSource(ids, newSource);
                if (res.ok) {
                    modal.classList.remove('active');
                    fetchData('releases');
                }
            } catch (err) {
                console.error('Failed to update source:', err);
            } finally {
                srcSelect.disabled = false;
            }
        };
        actionsEl.appendChild(srcSelect);
    }

    const tabNew = document.getElementById('detail-tab-new');
    const tabAll = document.getElementById('detail-tab-all');
    const tabDead = document.getElementById('detail-tab-dead');
    const linksBody = document.getElementById('detail-links-body');

    const initTabs = () => {
        const updateCounts = () => {
            const newCount = countSubReleases(group, 'new');
            const allCount = countSubReleases(group, 'all');
            const deadCount = countSubReleases(group, 'dead');
            document.getElementById('detail-new-count').textContent = newCount;
            document.getElementById('detail-all-count').textContent = allCount;
            document.getElementById('detail-dead-count').textContent = deadCount;
            return { newCount, allCount, deadCount };
        };

        const setMode = (mode) => {
            if (activeDetailContext) activeDetailContext.mode = mode;
            tabNew.classList.toggle('active', mode === 'new');
            tabAll.classList.toggle('active', mode === 'all');
            tabDead?.classList.toggle('active', mode === 'dead');
            renderResolutionList(linksBody, group, mode);
        };

        if (activeDetailContext) {
            activeDetailContext.refreshTabs = () => {
                updateCounts();
                setMode(activeDetailContext.mode || 'all');
            };
        }

        const { newCount, allCount } = updateCounts();
        tabNew.onclick = () => setMode('new');
        tabAll.onclick = () => setMode('all');
        if (tabDead) tabDead.onclick = () => setMode('dead');
        setMode(newCount > 0 ? 'new' : (allCount > 0 ? 'all' : 'dead'));
    };

    modal.classList.add('active');

    if (!group.resolutions) {
        document.getElementById('detail-new-count').textContent = group.new_count || 0;
        document.getElementById('detail-all-count').textContent = group.all_count ?? group.count ?? 0;
        document.getElementById('detail-dead-count').textContent = 0;
        linksBody.innerHTML = '<div class="detail-empty-links"><i class="fas fa-spinner fa-spin"></i></div>';

        const url = new URL('/api/releases/detail', window.location.origin);
        if (group.imdb_id && !group.imdb_id.startsWith('local')) {
            url.searchParams.append('imdb_id', group.imdb_id);
        } else {
            if (group.title) url.searchParams.append('title', group.title);
            if (group.year) url.searchParams.append('year', String(group.year));
            if (group.category) url.searchParams.append('category', group.category);
        }
        fetch(url)
            .then(r => r.json())
            .then(data => {
                group.resolutions = data.resolutions || {};
                initTabs();
            })
            .catch(err => {
                console.error('Failed to load release detail:', err);
                linksBody.innerHTML = `<div class="detail-empty-links">${TRANSLATIONS[state.language].msg_no_results}</div>`;
            });
    } else {
        initTabs();
    }
};

// ─── Poster Card ──────────────────────────────────────────────────────────────

const createPosterCard = (group, showCatBadge = true, sourceName = '') => {
    const card = document.createElement('div');
    const posterUrl = resolvePosterUrl(group.poster_path);
    const newCount = countSubReleases(group, true);
    const allCount = countSubReleases(group, false);
    const titleText = getGroupTitle(group);
    const catClass = group.category ? `cat-${group.category}` : '';

    card.className = `poster-card ${catClass} ${posterUrl ? 'has-poster' : 'no-poster'} ${newCount > 0 ? 'has-new' : ''}`;

    const catLabel = group.category === 'movie'
        ? TRANSLATIONS[state.language].filter_movies
        : (group.category === 'series' ? TRANSLATIONS[state.language].filter_series : '');
    const catIcon = group.category === 'movie' ? 'fa-film' : (group.category === 'series' ? 'fa-tv' : '');

    const addedDate = group.last_updated ? formatDate(group.last_updated) : '';
    const countBadgeHtml = newCount > 0
        ? `<span class="poster-badge-new" title="${newCount} ${TRANSLATIONS[state.language].tab_new_links || 'nouveautés'}">+${newCount}</span>`
        : (allCount > 0
            ? `<span class="poster-badge-count" title="${allCount} ${TRANSLATIONS[state.language].tab_all_links || 'liens'}">${allCount}</span>`
            : `<span class="poster-badge-dead" title="${TRANSLATIONS[state.language].tab_dead_links || 'Liens morts'}">0</span>`);

    card.innerHTML = `
        ${posterUrl ? `<img class="poster-img" src="${posterUrl}" loading="lazy" alt="">` : ''}
        <div class="poster-top-badges">
            ${countBadgeHtml}
            ${(showCatBadge && catLabel) ? `<span class="poster-badge-cat cat-${group.category}"><i class="fas ${catIcon}"></i> ${catLabel}</span>` : ''}
        </div>
        ${!posterUrl ? `
            <div class="poster-typo-body">
                <div class="poster-typo-title">${titleText}</div>
                <div class="poster-typo-meta">
                    <span>${group.year || ''}</span>
                    ${addedDate ? `<span class="poster-added-date">${addedDate}</span>` : ''}
                </div>
            </div>
        ` : `
            <div class="poster-overlay">
                <div class="poster-title">${titleText}</div>
                <div class="poster-sub">
                    <span>${group.year || ''}</span>
                    ${addedDate ? `<span class="poster-added-date">${addedDate}</span>` : ''}
                </div>
            </div>
        `}
    `;

    card.onclick = () => openReleaseModal(group, sourceName);
    return card;
};

// ─── Releases (Netflix Source Rows + Grid Fallback) ───────────────────────────

const createCarousel = (items, source, category, showCatBadge = false) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'carousel-wrapper';

    const track = document.createElement('div');
    track.className = 'carousel-track';
    items.forEach(group => track.appendChild(createPosterCard(group, showCatBadge, source)));

    let page = 1;
    let loading = false;
    let hasMore = items.length >= 25;

    const loadMore = async () => {
        if (loading || !hasMore || !source) return;
        loading = true;
        const loader = document.createElement('div');
        loader.className = 'carousel-loader';
        loader.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        track.appendChild(loader);

        try {
            const url = new URL('/api/releases', window.location.origin);
            url.searchParams.append('page', String(page + 1));
            url.searchParams.append('limit', '25');
            url.searchParams.append('source', source);
            if (category) url.searchParams.append('category', category);
            if (state.releases.resolution) url.searchParams.append('resolution', state.releases.resolution);
            if (state.releases.year) url.searchParams.append('year', state.releases.year);
            if (state.releases.network) url.searchParams.append('network', state.releases.network);
            if (state.releases.local) url.searchParams.append('local', state.releases.local);
            if (state.releases.recent) url.searchParams.append('recent', 'true');
            if (state.releases.hours) url.searchParams.append('hours', state.releases.hours);

            const res = await fetch(url);
            const data = await res.json();
            loader.remove();

            const nextItems = data.items || [];
            if (nextItems.length > 0) {
                page += 1;
                nextItems.forEach(group => track.appendChild(createPosterCard(group, showCatBadge, source)));
                hasMore = page < (data.pages || 0);
            } else {
                hasMore = false;
            }
        } catch (err) {
            console.error('Carousel loadMore error:', err);
            loader.remove();
            hasMore = false;
        } finally {
            loading = false;
        }
    };

    track.addEventListener('scroll', () => {
        if (hasMore && !loading && track.scrollLeft + track.clientWidth >= track.scrollWidth - 400) {
            loadMore();
        }
    }, { passive: true });

    const btnLeft = document.createElement('button');
    btnLeft.type = 'button';
    btnLeft.className = 'carousel-arrow carousel-arrow-left';
    btnLeft.innerHTML = '<i class="fas fa-chevron-left"></i>';
    btnLeft.onclick = () => track.scrollBy({ left: -Math.max(track.clientWidth * 0.8, 300), behavior: 'smooth' });

    const btnRight = document.createElement('button');
    btnRight.type = 'button';
    btnRight.className = 'carousel-arrow carousel-arrow-right';
    btnRight.innerHTML = '<i class="fas fa-chevron-right"></i>';
    btnRight.onclick = () => {
        track.scrollBy({ left: Math.max(track.clientWidth * 0.8, 300), behavior: 'smooth' });
        if (hasMore && !loading && track.scrollLeft + track.clientWidth >= track.scrollWidth - 600) {
            loadMore();
        }
    };

    wrapper.appendChild(btnLeft);
    wrapper.appendChild(track);
    wrapper.appendChild(btnRight);
    return wrapper;
};

const renderSourceRows = (container, rows) => {
    const catOrder = { movie: 0, series: 1 };
    const sortedRows = [...rows].sort((a, b) => {
        if (a.source === b.source) return (catOrder[a.category] ?? 2) - (catOrder[b.category] ?? 2);
        return 0;
    });

    sortedRows.forEach((row) => {
        const section = document.createElement('section');
        section.className = `source-section ${row.category ? `cat-${row.category}` : ''}`;

        const catIcon = row.category === 'movie' ? 'fa-film' : (row.category === 'series' ? 'fa-tv' : 'fa-server');

        const sourceHtml = row.source_url
            ? `<a href="${row.source_url}" target="_blank" rel="noopener noreferrer" class="source-row-link">${row.source} <i class="fas fa-external-link-alt"></i></a>`
            : `<span>${row.source}</span>`;

        const itemCount = row.total_items ?? row.total ?? 0;
        const newCount = row.new_items ?? 0;
        const upCount = row.alive_links ?? 0;
        const downCount = row.dead_links ?? 0;

        const header = document.createElement('div');
        header.className = 'source-row-header';
        header.innerHTML = `
            <div class="source-row-title">
                <i class="fas ${catIcon} source-row-icon"></i>
                ${sourceHtml}
                <div class="source-row-stats">
                    <span class="source-row-stat">${itemCount} ${itemCount > 1 ? 'items' : 'item'}</span>
                    <span class="source-row-stat ${newCount > 0 ? 'stat-new' : 'stat-muted'}">${newCount} new</span>
                    <span class="source-row-stat stat-up">${upCount} up</span>
                    <span class="source-row-stat ${downCount > 0 ? 'stat-down' : 'stat-muted'}">${downCount} down</span>
                    <button type="button" class="source-row-check-btn" title="Vérifier les 50 plus anciens liens"><i class="fas fa-heartbeat"></i></button>
                </div>
            </div>
        `;
        const srcCheckBtn = header.querySelector('.source-row-check-btn');
        if (srcCheckBtn) {
            srcCheckBtn.onclick = async () => {
                const icon = srcCheckBtn.querySelector('i');
                icon.className = 'fas fa-spinner fa-spin';
                srcCheckBtn.disabled = true;
                try {
                    const res = await fetch('/api/sources/check-links', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ source: row.source, category: row.category || null, limit: 50 }),
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'empty') {
                            icon.className = 'fas fa-heartbeat';
                            srcCheckBtn.disabled = false;
                            return;
                        }
                        const statusUrl = `/api/sources/check-links/status?source=${encodeURIComponent(row.source)}${row.category ? `&category=${encodeURIComponent(row.category)}` : ''}`;
                        const poll = setInterval(async () => {
                            try {
                                const sr = await fetch(statusUrl);
                                if (sr.ok) {
                                    const sd = await sr.json();
                                    if (!sd.running) {
                                        clearInterval(poll);
                                        fetchData('releases');
                                    }
                                }
                            } catch (_) {
                                clearInterval(poll);
                                icon.className = 'fas fa-heartbeat';
                                srcCheckBtn.disabled = false;
                            }
                        }, 3000);
                        return;
                    }
                } catch (err) {
                    console.error(err);
                }
                icon.className = 'fas fa-heartbeat';
                srcCheckBtn.disabled = false;
            };
        }

        section.appendChild(header);
        section.appendChild(createCarousel(row.items, row.source, row.category));
        container.appendChild(section);
    });
};

export const renderReleases = (groups) => {
    const container = document.getElementById('releases-container');
    const paginationEl = document.getElementById('releases-pagination');
    if (!container) return;

    container.innerHTML = '';

    const isCarouselMode = !state.releases.query;
    if (isCarouselMode) {
        const rows = state.releases.rows || [];
        if (rows.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"><i class="fas fa-film"></i></div>
                    <div class="empty-state-text">${TRANSLATIONS[state.language].msg_no_results}</div>
                    <div class="empty-state-subtext">${TRANSLATIONS[state.language].empty_state_subtext}</div>
                </div>`;
        } else {
            renderSourceRows(container, rows);
        }
        if (paginationEl) paginationEl.innerHTML = '';
        return;
    }

    // Grid mode (search)
    if (!groups || groups.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.innerHTML = `
            <div class="empty-state-icon"><i class="fas fa-film"></i></div>
            <div class="empty-state-text">${TRANSLATIONS[state.language].msg_no_results}</div>
            <div class="empty-state-subtext">${TRANSLATIONS[state.language].empty_state_subtext}</div>
        `;
        container.appendChild(empty);
        renderPagination('releases');
        return;
    }

    const grid = document.createElement('div');
    grid.className = 'poster-grid';
    groups.forEach(group => grid.appendChild(createPosterCard(group)));
    container.appendChild(grid);

    renderPagination('releases');
};
