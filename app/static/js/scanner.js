import { fetchData, startDirectScan, extractText } from './api.js';

export const initScanner = () => {
    const directScanInput = document.getElementById('direct-scan-input');
    const scanIndicator = document.getElementById('scan-indicator');
    const btnDirectScan = document.getElementById('btn-direct-scan');

    const doScan = async () => {
        if (!directScanInput) return;
        const input = directScanInput.value.trim();
        if (!input) return;

        const force = document.getElementById('direct-scan-force')?.checked || false;

        if (scanIndicator) scanIndicator.classList.remove('hidden');
        directScanInput.disabled = true;
        if (btnDirectScan) btnDirectScan.disabled = true;
        const originalPlaceholder = directScanInput.placeholder;
        directScanInput.placeholder = 'Processing...';

        try {
            let res;
            const resultsArea = document.getElementById('direct-scan-results');
            const messageSpan = document.getElementById('direct-scan-message');

            if (input.startsWith('http') && !input.includes('\n') && !input.includes(' ')) {
                const response = await startDirectScan(input, force);
                res = await response.json();
            } else {
                const response = await extractText(input, force);
                res = await response.json();
            }

            if (res) {
                directScanInput.value = '';
                if (resultsArea && messageSpan) {
                    resultsArea.classList.remove('hidden');
                    messageSpan.innerText = res.message;
                    setTimeout(() => resultsArea.classList.add('hidden'), 5000);
                }
                if (res.new > 0 || force) {
                    fetchData('releases');
                    fetchDownloads();
                }
            }
        } catch (err) {
            console.error('Scan error:', err);
        } finally {
            setTimeout(() => {
                if (scanIndicator) scanIndicator.classList.add('hidden');
                directScanInput.disabled = false;
                if (btnDirectScan) btnDirectScan.disabled = false;
                directScanInput.placeholder = originalPlaceholder;
            }, 2000);
        }
    };

    if (directScanInput) {
        directScanInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') doScan();
        });
    }

    if (btnDirectScan) {
        btnDirectScan.addEventListener('click', doScan);
    }
};
