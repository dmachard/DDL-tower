import { state } from './state.js';

export const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    let formatted = dateStr.replace(' ', 'T');
    const d = new Date(formatted.endsWith('Z') || formatted.includes('+') ? formatted : formatted + 'Z');
    const locale = state.language === 'fr' ? 'fr-FR' : 'en-US';
    return d.toLocaleString(locale, {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: state.language !== 'fr'
    });
};

export const formatSeasonEp = (s, e) => {
    if (!s && !e) return '';
    const season = s ? `S${s.toString().padStart(2, '0')}` : '';
    const episode = e ? `E${e.toString().padStart(2, '0')}` : '';
    return `${season}${episode}`;
};

export const formatLangs = (langStr) => {
    if (!langStr) return '';
    return langStr.replace(/VOSTFR/gi, 'VOST');
};

export const formatDuration = (ms) => {
    if (ms === null || ms === undefined) return '-';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
};

export const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

const HOSTER_DISPLAY_NAMES = {
    'dailyuploads.net': 'DailyUploads',
    '1fichier.com': '1Fichier',
    'nitroflare.com': 'Nitroflare',
    'rapidgator.net': 'Rapidgator',
    'turbobit.net': 'Turbobit',
};

export const beautifyHoster = (h) => {
    if (!h || h === 'Unknown') return h || 'Unknown';
    if (HOSTER_DISPLAY_NAMES[h.toLowerCase()]) return HOSTER_DISPLAY_NAMES[h.toLowerCase()];
    const name = h.split('.')[0];
    return name.charAt(0).toUpperCase() + name.slice(1);
};

export const debounce = (func, wait) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
};

export const getImdbUrl = (id) => {
    if (!id) return '#';
    return `https://www.imdb.com/title/${id}/?ref_=ext_shr_lnk&language=${state.language === 'fr' ? 'fr-fr' : 'en-us'}`;
};

export const renderRatingDots = (rating) => {
    if (!rating || rating === 'N/A') return '';
    const val = parseFloat(rating);
    if (isNaN(val)) return '';
    let html = `<div class="rating-container"><div class="rating-value"><i class="fas fa-star"></i> ${val}</div><div class="rating-dots">`;
    for (let i = 1; i <= 10; i++) {
        const cls = i <= Math.round(val) ? 'dot filled' : 'dot';
        html += `<span class="${cls}"></span>`;
    }
    html += '</div></div>';
    return html;
};
