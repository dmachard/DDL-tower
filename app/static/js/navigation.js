import { state } from './state.js';
import { fetchData, fetchDownloads, fetchStats, fetchSourcesDashboard, fetchErrors } from './api.js';

export const initNavigation = () => {
    // Dynamically update --header-h to ensure sticky controls stick accurately
    const updateHeaderHeight = () => {
        const header = document.querySelector('.content-header');
        if (header) {
            document.documentElement.style.setProperty('--header-h', `${header.offsetHeight}px`);
        }
    };
    window.addEventListener('resize', updateHeaderHeight);
    updateHeaderHeight();

    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

    const handleViewChange = (view) => {
        if (view === state.currentView) return;

        navItems.forEach(n => {
            if (n.getAttribute('data-view') === view) n.classList.add('active');
            else n.classList.remove('active');
        });

        const mobileNavSelect = document.getElementById('mobile-nav-custom-select');
        if (mobileNavSelect) {
            mobileNavSelect.querySelectorAll('.option').forEach(opt => {
                opt.classList.toggle('active', opt.getAttribute('data-value') === view);
            });
        }

        viewSections.forEach(s => {
            if (s.id === `${view}-view`) s.classList.remove('hidden');
            else s.classList.add('hidden');
        });

        state.currentView = view;
        if (view === 'sources') { fetchStats(); fetchSourcesDashboard(); }
        else if (view === 'errors') { fetchErrors(); }
        else if (view === 'downloads') fetchDownloads();
        else if (view === 'quick-scan') { /* No data to fetch */ }
        else fetchData(view);
    };

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            handleViewChange(item.getAttribute('data-view'));
        });
    });

    const mobileNavSelect = document.getElementById('mobile-nav-custom-select');
    if (mobileNavSelect) {
        const trigger = mobileNavSelect.querySelector('.select-trigger');
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            mobileNavSelect.classList.toggle('active');
        });

        mobileNavSelect.querySelectorAll('.option').forEach(opt => {
            opt.addEventListener('click', () => {
                handleViewChange(opt.getAttribute('data-value'));
                mobileNavSelect.classList.remove('active');
            });
        });

        document.addEventListener('click', () => mobileNavSelect.classList.remove('active'));
    }
};
