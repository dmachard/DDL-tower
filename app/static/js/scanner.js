import { fetchData, startDirectScan } from './api.js';

export const initScanner = () => {
    const directScanInput = document.getElementById('direct-scan-input');
    const scanIndicator = document.getElementById('scan-indicator');

    if (directScanInput) {
        directScanInput.addEventListener('keyup', async (e) => {
            if (e.key !== 'Enter') return;
            const url = directScanInput.value.trim();
            if (!url) return;

            if (scanIndicator) scanIndicator.classList.remove('hidden');
            directScanInput.disabled = true;
            const originalPlaceholder = directScanInput.placeholder;
            directScanInput.placeholder = 'Scanning started...';

            try {
                const res = await startDirectScan(url);
                if (res.ok) {
                    directScanInput.value = '';
                    setTimeout(() => { fetchData('releases'); }, 5000);
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
        });
    }
};
