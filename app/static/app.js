document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const linksContainer = document.getElementById('links-container');
    const linkTemplate = document.getElementById('link-item-template');
    const scrapedContainer = document.getElementById('scraped-container');
    const scrapedTemplate = document.getElementById('scraped-item-template');
    const searchLinks = document.getElementById('search-links');
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

    // State
    const state = {
        links: {
            items: [],
            page: 1,
            limit: 50,
            pages: 0,
            total: 0,
            query: '',
            category: '',
            status: ''
        },
        releases: {
            items: [],
            page: 1,
            limit: 20,
            pages: 0,
            total: 0,
            query: '',
            category: ''
        },
        scraped: {
            items: [],
            page: 1,
            limit: 50,
            pages: 0,
            total: 0,
            query: ''
        },
        currentView: 'releases'
    };

    // Helpers
    const formatDate = (dateStr) => {
        if (!dateStr) return 'N/A';
        if (!dateStr.includes('Z') && !dateStr.includes('+')) {
            dateStr += 'Z';
        }
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const formatSeasonEp = (s, e) => {
        if (!s && !e) return '';
        const season = s ? `S${s.toString().padStart(2, '0')}` : '';
        const episode = e ? `E${e.toString().padStart(2, '0')}` : '';
        return `${season}${episode}`;
    };

    const debounce = (func, wait) => {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    // Rendering
    const renderLinks = (links) => {
        if (!linksContainer) return;
        linksContainer.innerHTML = '';
        if (!links || links.length === 0) {
            linksContainer.innerHTML = '<div class="empty-state">No results found</div>';
            return;
        }
        links.forEach((link, index) => {
            const clone = linkTemplate.content.cloneNode(true);
            const row = clone.querySelector('.link-row');

            row.style.animationDelay = `${index * 0.01}s`;
            if (link.category) row.classList.add(`cat-${link.category}`);

            const dot = clone.querySelector('.status-dot');
            if (dot) dot.classList.add(link.status === 'alive' ? 'up' : 'down');

            const titleEl = clone.querySelector('.link-title');
            if (titleEl) titleEl.textContent = link.title || link.filename || link.url;

            if (link.year) {
                const yearSpan = clone.querySelector('.link-year');
                if (yearSpan) yearSpan.textContent = `(${link.year})`;
            }

            const seasonEp = formatSeasonEp(link.season, link.episode);
            const seBadge = clone.querySelector('.link-season-ep');
            if (seasonEp && seBadge) {
                seBadge.textContent = seasonEp;
                seBadge.classList.remove('hidden');
            }

            const resBadge = clone.querySelector('.link-resolution');
            if (resBadge && link.resolution) {
                resBadge.textContent = link.resolution;
                resBadge.classList.remove('hidden');
            }

            const lBadge = clone.querySelector('.link-lang');
            if (lBadge && link.language && link.language !== "None" && link.language !== "") {
                lBadge.textContent = link.language;
                lBadge.classList.remove('hidden');
            }

            const filenameEl = clone.querySelector('.link-filename');
            if (filenameEl) filenameEl.textContent = link.filename || "...";

            const urlCode = clone.querySelector('.link-url-code');
            if (urlCode) urlCode.textContent = link.url;

            const hosterBadge = clone.querySelector('.badge-hoster');
            if (hosterBadge) {
                if (link.source_url) {
                    hosterBadge.innerHTML = `<a href="${link.source_url}" target="_blank" class="badge-source-link">${link.source_name || "Direct-Scan"}</a>`;
                } else {
                    hosterBadge.textContent = link.source_name || "Direct-Scan";
                }
            }

            const sizeCol = clone.querySelector('.col-size');
            if (sizeCol) sizeCol.textContent = link.size || 'N/A';

            const dateCol = clone.querySelector('.col-date');
            if (dateCol) dateCol.textContent = formatDate(link.last_checked);

            linksContainer.appendChild(clone);
        });

        renderPagination('links');
    };

    const renderReleases = (groups) => {
        const container = document.getElementById('releases-container');
        const template = document.getElementById('release-group-template');
        if (!container || !template) return;

        container.innerHTML = '';
        if (!groups || groups.length === 0) {
            container.innerHTML = '<div class="empty-state">No releases found</div>';
            return;
        }

        groups.forEach((group, index) => {
            const clone = template.content.cloneNode(true);
            const row = clone.querySelector('.release-group-row');
            row.style.animationDelay = `${index * 0.05}s`;

            if (group.category) row.classList.add(`cat-${group.category}`);

            clone.querySelector('.group-title').textContent = group.title;
            clone.querySelector('.group-year').textContent = group.year ? `(${group.year})` : '';
            clone.querySelector('.group-last-updated').textContent = `Latest update: ${formatDate(group.last_updated)}`;

            const releasesCol = clone.querySelector('.col-releases');

            const resolutions = group.resolutions || {};
            const resOrder = { '2160p': 5, '4K': 5, '1080p': 4, '720p': 3, '576p': 2, '480p': 1, 'SD': 0, 'HD': -1 };
            const sortedRes = Object.keys(resolutions).sort((a, b) => (resOrder[b] || 0) - (resOrder[a] || 0));

            sortedRes.forEach(res => {
                const resRow = document.createElement('div');
                resRow.className = 'quality-row';
                resRow.innerHTML = `<div class="quality-label">${res}</div>`;

                // Group by season
                const seasonGroups = {};
                resolutions[res].forEach(rel => {
                    const s = rel.season || "Other";
                    if (!seasonGroups[s]) seasonGroups[s] = [];
                    seasonGroups[s].push(rel);
                });

                const sortedSeasons = Object.keys(seasonGroups).sort((a, b) => {
                    if (a === "Other") return 1;
                    if (b === "Other") return -1;
                    return parseInt(a) - parseInt(b);
                });

                const seasonsContainer = document.createElement('div');
                seasonsContainer.className = 'seasons-container';
                resRow.appendChild(seasonsContainer);

                sortedSeasons.forEach(s => {
                    const seasonDiv = document.createElement('div');
                    seasonDiv.className = 'season-group';

                    if (group.category === 'series' && s !== "Other") {
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
                        grid.appendChild(card);
                    });

                    seasonsContainer.appendChild(seasonDiv);
                });

                releasesCol.appendChild(resRow);
            });

            container.appendChild(clone);
        });

        renderPagination('releases');
    };

    const formatBytes = (bytes, decimals = 2) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    };

    const createReleaseCard = (rel) => {
        const card = document.createElement('div');
        card.className = 'release-card';

        const seasonEp = formatSeasonEp(rel.season, rel.episode);

        // Group by Hoster
        const providers = {};
        rel.parts.forEach(p => {
            const h = p.hoster || 'Unknown';
            if (!providers[h]) {
                providers[h] = { name: h, partsCount: 0, totalBytes: 0, urls: [] };
            }
            providers[h].partsCount++;
            providers[h].totalBytes += (p.size_bytes || 0);
            providers[h].urls.push(p.url);
        });

        const providerRows = Object.values(providers).map(p => `
            <div class="rel-provider-row">
                <span class="rel-p-name">${p.name}</span>
                <span class="rel-p-count">${p.partsCount}F</span>
                <span class="rel-p-size">${formatBytes(p.totalBytes)}</span>
                <button class="rel-p-copy" data-urls="${p.urls.join('\n')}" title="Copy links">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
        `).join('');

        card.innerHTML = `
            <div class="rel-meta-top">
                ${rel.source_url ? 
                    `<a href="${rel.source_url}" target="_blank" class="rel-source-link"><i class="fas fa-server"></i> ${rel.source || '...'}</a>` :
                    `<span class="rel-source-label"><i class="fas fa-server"></i> ${rel.source || '...'}</span>`
                }
                ${rel.is_new ? '<i class="fas fa-star badge-star" title="New Release"></i>' : ''}
            </div>
            <div class="rel-tags">
                ${seasonEp ? `<span class="rel-tag rel-tag-se">${seasonEp}</span>` : ''}
                ${rel.language && rel.language !== 'None' ? `<span class="rel-tag rel-tag-lang">${rel.language}</span>` : ''}
            </div>
            <div class="rel-providers">
                ${providerRows}
            </div>
        `;

        // Add copy event listeners
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
                    setTimeout(() => {
                        icon.className = originalClass;
                        btn.classList.remove('success');
                    }, 1000);
                } catch (err) {
                    console.error('Failed to copy!', err);
                }
            };
        });

        return card;
    };

    const renderScraped = (items) => {
        if (!scrapedContainer) return;
        scrapedContainer.innerHTML = '';
        if (!items || items.length === 0) {
            scrapedContainer.innerHTML = '<div class="empty-state">No scan history</div>';
            return;
        }
        items.forEach((item, index) => {
            const clone = scrapedTemplate.content.cloneNode(true);
            const row = clone.querySelector('.link-row');
            row.style.animationDelay = `${index * 0.01}s`;

            const dot = clone.querySelector('.status-dot');
            if (dot) dot.classList.add(item.status === 'success' ? 'up' : 'down');

            const urlCode = clone.querySelector('.link-url-code');
            if (urlCode) urlCode.textContent = item.url;

            const hosterBadge = clone.querySelector('.badge-hoster');
            if (hosterBadge) hosterBadge.textContent = item.source_name;

            const freqBadge = clone.querySelector('.badge-frequency');
            if (freqBadge) {
                freqBadge.textContent = item.scrape_once ? "Unique" : "Recurring";
            }

            const dateCol = clone.querySelector('.col-date');
            if (dateCol) dateCol.textContent = formatDate(item.last_scraped);

            scrapedContainer.appendChild(clone);
        });

        renderPagination('scraped');
    };

    const renderPagination = (type) => {
        const viewState = state[type];
        const container = document.getElementById(`${type}-pagination`);
        if (!container) return;

        if (viewState.pages <= 1) {
            container.classList.add('hidden');
            return;
        }
        container.classList.remove('hidden');

        const prevBtn = document.getElementById(`prev-${type}`);
        const nextBtn = document.getElementById(`next-${type}`);
        const pageNumbers = document.getElementById(`${type}-page-numbers`);

        if (prevBtn) prevBtn.disabled = viewState.page === 1;
        if (nextBtn) nextBtn.disabled = viewState.page === viewState.pages;

        if (pageNumbers) {
            pageNumbers.innerHTML = '';

            // Show first, last, current, and neighbors
            const pagesToShow = new Set([1, viewState.pages, viewState.page, viewState.page - 1, viewState.page + 1]);
            const sortedPages = Array.from(pagesToShow).filter(p => p > 0 && p <= viewState.pages).sort((a, b) => a - b);

            let lastP = 0;
            sortedPages.forEach(p => {
                if (lastP !== 0 && p - lastP > 1) {
                    const dot = document.createElement('span');
                    dot.className = 'pagination-ellipsis';
                    dot.textContent = '...';
                    pageNumbers.appendChild(dot);
                }

                const btn = document.createElement('button');
                btn.className = `page-number ${p === viewState.page ? 'active' : ''}`;
                btn.textContent = p;
                btn.onclick = () => {
                    viewState.page = p;
                    if (type === 'links') fetchLinks();
                    else if (type === 'releases') fetchReleases();
                    else fetchScraped();
                };
                pageNumbers.appendChild(btn);
                lastP = p;
            });
        }
    };

    // Fetching
    const fetchLinks = async () => {
        try {
            const url = new URL('/api/links', window.location.origin);
            url.searchParams.append('page', state.links.page);
            url.searchParams.append('limit', state.links.limit);
            if (state.links.query) url.searchParams.append('q', state.links.query);
            if (state.links.category) url.searchParams.append('category', state.links.category);
            if (state.links.status) url.searchParams.append('status', state.links.status);

            const res = await fetch(url);
            const data = await res.json();

            state.links.items = data.items;
            state.links.total = data.total;
            state.links.pages = data.pages;

            const countEl = document.getElementById('count-links');
            if (countEl) countEl.textContent = data.total;

            if (state.currentView === 'links') {
                renderLinks(data.items);
            }
        } catch (err) {
            console.error('Error fetching links:', err);
        }
    };

    const fetchReleases = async () => {
        try {
            const url = new URL('/api/releases', window.location.origin);
            url.searchParams.append('page', state.releases.page);
            url.searchParams.append('limit', state.releases.limit);
            if (state.releases.query) url.searchParams.append('q', state.releases.query);
            if (state.releases.category) url.searchParams.append('category', state.releases.category);

            const res = await fetch(url);
            const data = await res.json();

            state.releases.items = data.items;
            state.releases.total = data.total;
            state.releases.pages = data.pages;

            const countEl = document.getElementById('count-releases');
            if (countEl) countEl.textContent = data.total;

            if (state.currentView === 'releases') {
                renderReleases(data.items);
            }
        } catch (err) {
            console.error('Error fetching releases:', err);
        }
    };

    const fetchScraped = async () => {
        try {
            const url = new URL('/api/scraped', window.location.origin);
            url.searchParams.append('page', state.scraped.page);
            url.searchParams.append('limit', state.scraped.limit);
            if (state.scraped.query) url.searchParams.append('q', state.scraped.query);

            const res = await fetch(url);
            const data = await res.json();

            state.scraped.items = data.items;
            state.scraped.total = data.total;
            state.scraped.pages = data.pages;

            const countEl = document.getElementById('count-scraped');
            if (countEl) countEl.textContent = data.total;

            if (state.currentView === 'scraped') {
                renderScraped(data.items);
            }
        } catch (err) {
            console.error('Error fetching scraped history:', err);
        }
    };

    const fetchStats = async () => {
        try {
            const res = await fetch('/api/stats');
            const stats = await res.json();
            renderStats(stats);
        } catch (err) {
            console.error('Error fetching stats:', err);
        }
    };

    const renderStats = (stats) => {
        const uniqueMoviesEl = document.getElementById('stats-unique-movies');
        const linksMoviesEl = document.getElementById('stats-links-movies');
        const uniqueSeriesEl = document.getElementById('stats-unique-series');
        const linksSeriesEl = document.getElementById('stats-links-series');
        const sizeEl = document.getElementById('stats-size');
        const sourceContainer = document.getElementById('source-stats-container');

        if (uniqueMoviesEl) uniqueMoviesEl.textContent = stats.unique_movies;
        if (linksMoviesEl) linksMoviesEl.textContent = stats.links_movies;
        if (uniqueSeriesEl) uniqueSeriesEl.textContent = stats.unique_series;
        if (linksSeriesEl) linksSeriesEl.textContent = stats.links_series;
        if (sizeEl) sizeEl.textContent = stats.total_size;

        const deadLinksEl = document.getElementById('stats-dead-links');
        if (deadLinksEl) deadLinksEl.textContent = stats.dead_links;

        if (sourceContainer) {
            sourceContainer.innerHTML = '';
            const sortedSources = Object.keys(stats.size_by_source).sort();
            const totalBytes = stats.total_size_bytes || 1;

            sortedSources.forEach(source => {
                const sizeFmt = stats.size_by_source[source];
                const sizeRaw = stats.size_by_source_raw[source] || 0;
                const percentage = Math.min(100, Math.round((sizeRaw / totalBytes) * 100));

                const item = document.createElement('div');
                item.className = 'source-stat-item';
                item.innerHTML = `
                    <span class="source-name">${source}</span>
                    <div class="source-progress-container">
                        <div class="source-progress-bar" style="width: ${percentage}%"></div>
                    </div>
                    <span class="source-value">${sizeFmt}</span>
                `;
                sourceContainer.appendChild(item);
            });
        }
    };

    // Event Listeners for Pagination
    document.getElementById('prev-links')?.addEventListener('click', () => {
        if (state.links.page > 1) {
            state.links.page--;
            fetchLinks();
        }
    });

    document.getElementById('next-links')?.addEventListener('click', () => {
        if (state.links.page < state.links.pages) {
            state.links.page++;
            fetchLinks();
        }
    });

    document.getElementById('prev-releases')?.addEventListener('click', () => {
        if (state.releases.page > 1) {
            state.releases.page--;
            fetchReleases();
        }
    });

    document.getElementById('next-releases')?.addEventListener('click', () => {
        if (state.releases.page < state.releases.pages) {
            state.releases.page++;
            fetchReleases();
        }
    });

    document.getElementById('prev-scraped')?.addEventListener('click', () => {
        if (state.scraped.page > 1) {
            state.scraped.page--;
            fetchScraped();
        }
    });

    document.getElementById('next-scraped')?.addEventListener('click', () => {
        if (state.scraped.page < state.scraped.pages) {
            state.scraped.page++;
            fetchScraped();
        }
    });

    // Search Logic (Debounced server-side)
    const handleSearch = debounce((e) => {
        const query = e.target.value.toLowerCase();
        if (e.target.id === 'search-scraped') {
            state.scraped.query = query;
            state.scraped.page = 1;
            fetchScraped();
        } else if (e.target.id === 'search-releases') {
            state.releases.query = query;
            state.releases.page = 1;
            fetchReleases();
        } else {
            state.links.query = query;
            state.links.page = 1;
            fetchLinks();
        }
    }, 400);

    document.getElementById('search-links')?.addEventListener('input', handleSearch);
    document.getElementById('search-scraped')?.addEventListener('input', handleSearch);
    document.getElementById('search-releases')?.addEventListener('input', handleSearch);

    // View Switching
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const view = item.getAttribute('data-view');
            if (view === state.currentView) return;

            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            viewSections.forEach(s => {
                if (s.id === `${view}-view`) s.classList.remove('hidden');
                else s.classList.add('hidden');
            });

            state.currentView = view;

            if (view === 'links') fetchLinks();
            else if (view === 'releases') fetchReleases();
            else if (view === 'scraped') fetchScraped();
            else if (view === 'stats') fetchStats();
        });
    });

    // Integrated Scanner Logic
    const directScanInput = document.getElementById('direct-scan-input');
    const scanIndicator = document.getElementById('scan-indicator');

    if (directScanInput) {
        directScanInput.addEventListener('keyup', async (e) => {
            if (e.key === 'Enter') {
                const url = directScanInput.value.trim();
                if (!url) return;

                // Visual feedback
                if (scanIndicator) scanIndicator.classList.remove('hidden');
                directScanInput.disabled = true;
                const originalPlaceholder = directScanInput.placeholder;
                directScanInput.placeholder = 'Scanning started...';

                try {
                    const res = await fetch('/api/scan/direct', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ urls: [url] })
                    });

                    if (res.ok) {
                        directScanInput.value = '';
                        // Refresh links after a delay to show new findings
                        setTimeout(() => {
                            fetchLinks();
                            fetchScraped();
                        }, 5000);
                    }
                } catch (err) {
                    console.error('Scan error:', err);
                } finally {
                    setTimeout(() => {
                        if (scanIndicator) scanIndicator.classList.add('hidden');
                        directScanInput.disabled = false;
                        directScanInput.placeholder = originalPlaceholder;
                    }, 2000);
                }
            }
        });
    }

    // Filter event listeners
    document.getElementById('filter-category')?.addEventListener('change', (e) => {
        state.links.category = e.target.value;
        state.links.page = 1;
        fetchLinks();
    });

    document.getElementById('filter-status')?.addEventListener('change', (e) => {
        state.links.status = e.target.value;
        state.links.page = 1;
        fetchLinks();
    });

    document.getElementById('filter-category-releases')?.addEventListener('change', (e) => {
        state.releases.category = e.target.value;
        state.releases.page = 1;
        fetchReleases();
    });

    // Initial Load
    fetchLinks();
    fetchReleases();
    fetchScraped();
    fetchStats();

    // Targeted Refresh (only counts and stats frequently, current page less frequently)
    setInterval(() => {
        // We only refresh the current view's data
        if (state.currentView === 'releases') fetchReleases();
        else if (state.currentView === 'links') fetchLinks();
        else if (state.currentView === 'scraped') fetchScraped();

        // Always refresh counts for other tabs
        if (state.currentView !== 'links') fetchLinks();
        if (state.currentView !== 'releases') fetchReleases();
        if (state.currentView !== 'scraped') fetchScraped();
    }, 10000); // 10s is enough for background refresh

    setInterval(fetchStats, 60000);
});

