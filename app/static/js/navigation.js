import { state } from './state.js';
import { fetchData, fetchDownloads, fetchStats, fetchSourcesDashboard } from './api.js';

export const initNavigation = () => {
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

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
            if (view === 'sources') { fetchStats(); fetchSourcesDashboard(); }
            else if (view === 'downloads') fetchDownloads();
            else if (view === 'quick-scan') { /* No data to fetch */ }
            else fetchData(view);
        });
    });
};
