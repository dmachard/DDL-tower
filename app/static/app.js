document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const linksContainer = document.getElementById('links-container');
    const linkTemplate = document.getElementById('link-item-template');
    const scrapedContainer = document.getElementById('scraped-container');
    const scrapedTemplate = document.getElementById('scraped-item-template');
    const searchLinks = document.getElementById('search-links');
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

    // State Configuration
    const CONFIG = {
        views: {
            links: { limit: 50, recent: true, hours: 12 },
            releases: { limit: 20, recent: true, hours: 12 },
            scraped: { limit: 50 }
        },
        filters: {
            links: [
                { type: 'recent', value: 'true', i18n: 'filter_recent', icon: 'fas fa-star tag-star' },
                { type: 'hours', value: '12', label: '12h' },
                { type: 'hours', value: '24', label: '24h' },
                { type: 'hours', value: '48', label: '48h' },
                { type: 'category', value: 'movie', i18n: 'filter_movies', icon: 'fas fa-film' },
                { type: 'category', value: 'series', i18n: 'filter_series', icon: 'fas fa-tv' },
                { type: 'status', value: 'alive', i18n: 'filter_alive', icon: 'fas fa-check-circle' },
                { type: 'status', value: 'dead', i18n: 'filter_dead', icon: 'fas fa-times-circle' },
            ],
            releases: [
                { type: 'recent', value: 'true', i18n: 'filter_recent', icon: 'fas fa-star tag-star' },
                { type: 'hours', value: '12', label: '12h' },
                { type: 'hours', value: '24', label: '24h' },
                { type: 'hours', value: '48', label: '48h' },
                { type: 'category', value: 'movie', i18n: 'filter_movies', icon: 'fas fa-film' },
                { type: 'category', value: 'series', i18n: 'filter_series', icon: 'fas fa-tv' },
            ]
        }
    };

    const TRANSLATIONS = {
        en: {
            nav_releases: "Releases",
            nav_explorer: "Explorer",
            nav_scans: "Scans",
            nav_stats: "Statistics",
            header_status: "Status",
            header_release: "Release",
            header_source: "Source",
            header_size: "Size",
            header_detected: "Added",
            header_title: "Title",
            header_versions: "Available Versions",
            header_visited_url: "Visited URL",
            header_scraper: "Scraper",
            header_frequency: "Frequency",
            header_last_scan: "Last Scan",
            stat_unique_movies: "Unique Movies",
            stat_movie_links: "Movie Links",
            stat_total_volume: "Total Volume",
            stat_unique_series: "Unique Series",
            stat_series_links: "Series Links",
            stat_dead_links: "Dead Links",
            filter_recent: "Recent",
            filter_movies: "Movies",
            filter_series: "Series",
            filter_alive: "Alive",
            filter_dead: "Dead",
            placeholder_scan: "Scan a URL",
            placeholder_search_links: "Search in links...",
            placeholder_search_titles: "Search in titles...",
            placeholder_search_scans: "Search in scans...",
            msg_no_results: "No results found",
            msg_no_history: "No scan history",
            msg_latest_update: "Added",
            badge_unique: "Unique",
            badge_recurring: "Recurring",
            copy_links: "Copy links"
        },
        fr: {
            nav_releases: "Nouveautés",
            nav_explorer: "Explorer",
            nav_scans: "Scans",
            nav_stats: "Statistiques",
            header_status: "Statut",
            header_release: "Fichier",
            header_source: "Source",
            header_size: "Taille",
            header_detected: "Ajouté",
            header_title: "Titre",
            header_versions: "Versions Disponibles",
            header_visited_url: "URL Visitée",
            header_scraper: "Scraper",
            header_frequency: "Fréquence",
            header_last_scan: "Dernier Scan",
            stat_unique_movies: "Films Uniques",
            stat_movie_links: "Liens Films",
            stat_total_volume: "Volume Total",
            stat_unique_series: "Séries Uniques",
            stat_series_links: "Liens Séries",
            stat_dead_links: "Liens Morts",
            filter_recent: "Récent",
            filter_movies: "Films",
            filter_series: "Séries",
            filter_alive: "Vivant",
            filter_dead: "Mort",
            placeholder_scan: "Scanner une URL",
            placeholder_search_links: "Chercher dans les liens...",
            placeholder_search_titles: "Chercher dans les titres...",
            placeholder_search_scans: "Chercher dans l'historique...",
            msg_no_results: "Aucun résultat trouvé",
            msg_no_history: "Aucun historique de scan",
            msg_latest_update: "Ajouté",
            badge_unique: "Unique",
            badge_recurring: "Récurrent",
            copy_links: "Copier les liens"
        }
    };

    const state = {
        currentView: 'releases',
        language: 'fr',
        links: { items: [], page: 1, limit: 50, total: 0, pages: 0, query: '', category: '', status: '', recent: true, hours: 12 },
        releases: { items: [], page: 1, limit: 20, total: 0, pages: 0, query: '', category: '', recent: true, hours: 12 },
        scraped: { items: [], page: 1, limit: 50, total: 0, pages: 0, query: '' }
    };

    // Helpers
    const formatDate = (dateStr) => {
        if (!dateStr) return 'N/A';
        const d = new Date(dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z');
        const locale = state.language === 'fr' ? 'fr-FR' : 'en-US';
        return d.toLocaleString(locale, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: state.language !== 'fr'
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
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    };

    // Rendering
    const renderLinks = (links) => {
        if (!linksContainer) return;
        linksContainer.innerHTML = '';
        if (!links || links.length === 0) {
            linksContainer.innerHTML = `<div class="empty-state">${TRANSLATIONS[state.language].msg_no_results}</div>`;
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
            container.innerHTML = `<div class="empty-state">${TRANSLATIONS[state.language].msg_no_results}</div>`;
            return;
        }

        groups.forEach((group, index) => {
            const clone = template.content.cloneNode(true);
            const row = clone.querySelector('.release-group-row');
            row.style.animationDelay = `${index * 0.05}s`;

            if (group.category) row.classList.add(`cat-${group.category}`);

            clone.querySelector('.group-title').textContent = group.title;
            clone.querySelector('.group-year').textContent = group.year ? `(${group.year})` : '';
            clone.querySelector('.group-last-updated').textContent = `${TRANSLATIONS[state.language].msg_latest_update}: ${formatDate(group.last_updated)}`;

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
                <button class="rel-p-copy" data-urls="${p.urls.join('\n')}" title="${TRANSLATIONS[state.language].copy_links}">
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
            scrapedContainer.innerHTML = `<div class="empty-state">${TRANSLATIONS[state.language].msg_no_history}</div>`;
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
                freqBadge.textContent = item.scrape_once ? TRANSLATIONS[state.language].badge_unique : TRANSLATIONS[state.language].badge_recurring;
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
                    fetchData(type);
                };
                pageNumbers.appendChild(btn);
                lastP = p;
            });
        }
    };

    const fetchData = async (view) => {
        const viewState = state[view];
        if (!viewState) return;

        try {
            const url = new URL(`/api/${view}`, window.location.origin);
            url.searchParams.append('page', viewState.page);
            url.searchParams.append('limit', viewState.limit);
            if (viewState.query) url.searchParams.append('q', viewState.query);
            if (viewState.category) url.searchParams.append('category', viewState.category);
            if (view === 'links' && viewState.status) url.searchParams.append('status', viewState.status);
            if (viewState.recent) url.searchParams.append('recent', 'true');
            if (viewState.hours) url.searchParams.append('hours', viewState.hours);

            const res = await fetch(url);
            const data = await res.json();

            viewState.items = data.items;
            viewState.total = data.total;
            viewState.pages = data.pages;

            const countEl = document.getElementById(`count-${view}`);
            if (countEl) countEl.textContent = data.total;

            if (state.currentView === view) {
                if (view === 'links') renderLinks(data.items);
                else if (view === 'releases') renderReleases(data.items);
                else if (view === 'scraped') renderScraped(data.items);
            }
        } catch (err) {
            console.error(`Error fetching ${view}:`, err);
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
        const view = e.target.id.replace('search-', '');
        if (state[view]) {
            state[view].query = query;
            state[view].page = 1;
            fetchData(view);
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
            if (view === 'stats') fetchStats();
            else fetchData(view);
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
                            fetchData('links');
                            fetchData('scraped');
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

    const updateTagsUI = (containerId, viewState) => {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll('.filter-tag').forEach(tag => {
            const type = tag.getAttribute('data-type');
            const val = tag.getAttribute('data-value');

            let isActive = false;
            if (type === 'recent') {
                isActive = (viewState.recent && val === 'true');
            } else {
                isActive = (String(viewState[type]) === String(val));
            }

            if (isActive) tag.classList.add('active');
            else tag.classList.remove('active');
        });
    };

    const handleTagClick = (e, view) => {
        const tag = e.target.closest('.filter-tag');
        if (!tag) return;

        const type = tag.getAttribute('data-type');
        const value = tag.getAttribute('data-value');
        const viewState = state[view];

        if (type === 'recent') {
            viewState.recent = !viewState.recent;
            if (!viewState.recent) viewState.hours = null;
        } else if (type === 'hours') {
            const h = parseInt(value);
            if (viewState.hours === h) viewState.hours = null;
            else { viewState.hours = h; viewState.recent = true; }
        } else {
            viewState[type] = viewState[type] === value ? '' : value;
        }

        viewState.page = 1;
        updateTagsUI(view === 'links' ? 'filter-tags-links' : 'filter-tags-releases', viewState);
        fetchData(view);
    };

    const setLanguage = (lang) => {
        state.language = lang;
        localStorage.setItem('ddlt_lang', lang);

        // Update All UI Strings
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const text = TRANSLATIONS[lang][key];
            if (text) el.textContent = text;
        });

        // Update Placeholders
        if (directScanInput) directScanInput.placeholder = TRANSLATIONS[lang].placeholder_scan;
        if (searchLinks) searchLinks.placeholder = TRANSLATIONS[lang].placeholder_search_links;
        const searchRel = document.getElementById('search-releases');
        if (searchRel) searchRel.placeholder = TRANSLATIONS[lang].placeholder_search_titles;
        const searchScr = document.getElementById('search-scraped');
        if (searchScr) searchScr.placeholder = TRANSLATIONS[lang].placeholder_search_scans;

        // Update Custom Selector
        const currentLangLabel = document.getElementById('current-lang');
        if (currentLangLabel) currentLangLabel.textContent = lang.toUpperCase();

        // Re-render conditional parts
        ['links', 'releases'].forEach(v => {
            loadFilters(v);
            updateTagsUI(`filter-tags-${v}`, state[v]);
        });

        if (state.currentView === 'releases') renderReleases(state.releases.items);
        else if (state.currentView === 'links') renderLinks(state.links.items);
        else if (state.currentView === 'scraped') renderScraped(state.scraped.items);
        else if (state.currentView === 'stats') fetchStats();
    };

    const loadFilters = (view) => {
        const container = document.getElementById(`filter-tags-${view}`);
        if (!container || !CONFIG.filters[view]) return;

        container.innerHTML = CONFIG.filters[view].map(f => {
            const cls = f.type === 'recent' ? 'filter-tag tag-recent' : 'filter-tag';
            const iconHtml = f.icon ? `<i class="${f.icon}"></i> ` : '';
            const label = f.i18n ? TRANSLATIONS[state.language][f.i18n] : f.label;
            return `<div class="${cls}" data-type="${f.type}" data-value="${f.value}">${iconHtml}${label}</div>`;
        }).join('');
    };

    const initCustomSelect = () => {
        const select = document.getElementById('lang-custom-select');
        if (!select) return;

        const trigger = select.querySelector('.select-trigger');
        const options = select.querySelectorAll('.option');

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            select.classList.toggle('active');
        });

        options.forEach(opt => {
            opt.addEventListener('click', () => {
                const val = opt.getAttribute('data-value');
                setLanguage(val);
                select.classList.remove('active');
            });
        });

        // Click outside to close
        document.addEventListener('click', () => {
            select.classList.remove('active');
        });
    };

    initCustomSelect();

    // Custom fetch for config
    const initApp = async () => {
        try {
            const res = await fetch('/api/config');
            const cfg = await res.json();

            // Priority: LocalStorage > Backend Config > Default 'fr'
            const savedLang = localStorage.getItem('ddlt_lang');
            const initialLang = savedLang || cfg.default_language || 'fr';

            setLanguage(initialLang);
        } catch (err) {
            console.error('Failed to load init config:', err);
            setLanguage('fr');
        }
    };

    document.getElementById('filter-tags-links')?.addEventListener('click', (e) => handleTagClick(e, 'links'));
    document.getElementById('filter-tags-releases')?.addEventListener('click', (e) => handleTagClick(e, 'releases'));

    // Initial Load
    ['links', 'releases'].forEach(v => {
        loadFilters(v);
        updateTagsUI(`filter-tags-${v}`, state[v]);
    });

    ['links', 'releases', 'scraped'].forEach(fetchData);
    initApp(); // Loads language and kicks off remaining UI
    fetchStats();

    // Targeted Refresh
    setInterval(() => {
        ['links', 'releases', 'scraped'].forEach(v => {
            fetchData(v);
        });
    }, 10000);

    setInterval(fetchStats, 60000);
});
