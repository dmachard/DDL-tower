import { state } from './state.js';
import { fetchData } from './api.js';

export const renderPagination = (type) => {
    const viewState = state[type];
    const containers = [
        document.getElementById(`${type}-pagination`),
        document.getElementById(`${type}-pagination-top`)
    ].filter(el => el !== null);

    if (viewState.pages <= 1) {
        containers.forEach(container => {
            container.classList.remove('hidden');
            container.innerHTML = '';
        });
        return;
    }

    containers.forEach(container => {
        container.classList.remove('hidden');
        container.innerHTML = '';

        const prevBtn = document.createElement('button');
        prevBtn.className = 'btn-prev';
        prevBtn.disabled = viewState.page === 1;
        prevBtn.innerHTML = `<i class="fas fa-chevron-left"></i> ${state.language === 'fr' ? 'Précédent' : 'Previous'}`;
        prevBtn.onclick = () => {
            if (viewState.page > 1) {
                viewState.page--;
                fetchData(type);
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        };

        const pageNumbers = document.createElement('div');
        pageNumbers.className = 'page-numbers';

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
            btn.onclick = (e) => {
                e.preventDefault();
                viewState.page = p;
                fetchData(type);
                window.scrollTo({ top: 0, behavior: 'smooth' });
            };
            pageNumbers.appendChild(btn);
            lastP = p;
        });

        const nextBtn = document.createElement('button');
        nextBtn.className = 'btn-next';
        nextBtn.disabled = viewState.page === viewState.pages;
        nextBtn.innerHTML = `${state.language === 'fr' ? 'Suivant' : 'Next'} <i class="fas fa-chevron-right"></i>`;
        nextBtn.onclick = (e) => {
            e.preventDefault();
            if (viewState.page < viewState.pages) {
                viewState.page++;
                fetchData(type);
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        };

        container.appendChild(prevBtn);
        container.appendChild(pageNumbers);
        container.appendChild(nextBtn);
    });
};
