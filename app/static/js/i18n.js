import { state } from './state.js';
import { renderReleases } from './releases.js';
import { fetchStats, fetchSourcesDashboard } from './api.js';
import { loadFilters, updateTagsUI } from './filters.js';

export const TRANSLATIONS = {
    en: {
        nav_releases: "Explorer",
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
        header_duration: "Duration",
        header_last_scan: "Last Scan",
        stat_unique_movies: "Unique Movies",
        stat_total_links: "Total Links",
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
        copy_links: "Copy links",
        filter_all_sources: "All sources",
        filter_all_qualities: "All qualities",
        filter_all_years: "All years",
        placeholder_search_source: "Search source...",
        placeholder_search_year: "Search year...",
        placeholder_search_downloads: "Search in downloads...",
        no_source_found: "No source found",
        no_year_found: "No year found",
        empty_state_subtext: "Try adjusting your filters or search query",
        nav_downloads: "Downloads",
        header_filename: "File",
        header_date: "Date",
        header_actions: "Actions",
        copy_links: "Copy links",
        download_links: "Download via AllDebrid",
        btn_show_versions: "Show versions",
        btn_hide_versions: "Hide versions",
        modal_identify_title: "Identify Release",
        btn_cancel: "Cancel",
        btn_confirm: "Confirm",
        nav_sources: "Sources",
        nav_quick_scan: "Scanner",
        scan_url_title: "Scan a Page",
        scan_url_subtitle: "Enter a URL to visit and crawl for links automatically",
        quick_scan_title: "Quick Extract",
        quick_scan_subtitle: "Paste text containing download links (1fichier, Rapidgator, etc.)",
        quick_scan_placeholder: "Paste your text here...",
        btn_extract: "Scan",
        btn_clear: "Clear",
        help_scan_enter: "Press Enter to start crawling",
        modal_view_links_title: "Available Links"
    },
    fr: {
        nav_releases: "Explorer",
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
        header_duration: "Durée",
        header_last_scan: "Dernier Scan",
        stat_unique_movies: "Films Uniques",
        stat_total_links: "Liens Totaux",
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
        copy_links: "Copier les liens",
        filter_all_sources: "Toutes les sources",
        filter_all_qualities: "Toutes les qualités",
        filter_all_years: "Toutes les années",
        placeholder_search_source: "Chercher une source...",
        placeholder_search_year: "Chercher une année...",
        placeholder_search_downloads: "Chercher dans les téléchargements...",
        no_source_found: "Aucune source trouvée",
        no_year_found: "Aucune année trouvée",
        empty_state_subtext: "Essayez d'ajuster vos filtres ou votre recherche",
        nav_downloads: "Téléchargements",
        header_filename: "Fichier",
        header_date: "Date",
        header_actions: "Actions",
        copy_links: "Copier les liens",
        download_links: "Télécharger via AllDebrid",
        btn_show_versions: "Voir les versions",
        btn_hide_versions: "Masquer les versions",
        modal_identify_title: "Identifier la release",
        btn_cancel: "Annuler",
        btn_confirm: "Confirmer",
        nav_sources: "Sources",
        nav_quick_scan: "Scanner",
        scan_url_title: "Scanner une Page",
        scan_url_subtitle: "Entrez une URL pour visiter et extraire les liens automatiquement",
        quick_scan_title: "Extraction Rapide",
        quick_scan_subtitle: "Collez du texte contenant des liens (1fichier, Rapidgator, etc.)",
        quick_scan_placeholder: "Collez votre texte ici...",
        btn_extract: "Scanner",
        btn_clear: "Effacer",
        help_scan_enter: "Appuyez sur Entrée pour lancer le crawl",
        modal_view_links_title: "Liens Disponibles"
    }
};

export const setLanguage = (lang) => {
    state.language = lang;
    localStorage.setItem('ddlt_lang', lang);

    // Update all static i18n strings
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const text = TRANSLATIONS[lang][key];
        if (!text) return;

        // Don't set textContent on inputs/textareas as it fills the actual value
        if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
            el.placeholder = text;
        } else {
            el.textContent = text;
        }
    });

    // Update language label
    const currentLangLabel = document.getElementById('current-lang');
    if (currentLangLabel) currentLangLabel.textContent = lang.toUpperCase();

    // Re-render filters
    ['releases'].forEach(v => {
        loadFilters(v);
        updateTagsUI(`filter-tags-${v}`, state[v]);
    });

    // Re-render current view
    if (state.currentView === 'releases') renderReleases(state.releases.items);
    else if (state.currentView === 'sources') { fetchStats(); fetchSourcesDashboard(); }
};
