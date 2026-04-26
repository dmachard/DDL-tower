import { fetchData, startDirectScan, extractText } from './api.js';

export const initScanner = () => {
    const directScanInput = document.getElementById('direct-scan-input');
    const scanIndicator = document.getElementById('scan-indicator');

    if (directScanInput) {
        directScanInput.addEventListener('keyup', async (e) => {
            if (e.key !== 'Enter') return;
            const input = directScanInput.value.trim();
            if (!input) return;

            if (scanIndicator) scanIndicator.classList.remove('hidden');
            directScanInput.disabled = true;
            const originalPlaceholder = directScanInput.placeholder;
            directScanInput.placeholder = 'Processing...';

            try {
                let res;
                const resultsArea = document.getElementById('direct-scan-results');
                const messageSpan = document.getElementById('direct-scan-message');

                if (input.startsWith('http') && !input.includes('\n') && !input.includes(' ')) {
                    const response = await startDirectScan(input);
                    res = await response.json();
                } else {
                    const response = await extractText(input);
                    res = await response.json();
                }

                if (res) {
                    directScanInput.value = '';
                    if (resultsArea && messageSpan) {
                        resultsArea.classList.remove('hidden');
                        messageSpan.innerText = res.message;
                        setTimeout(() => resultsArea.classList.add('hidden'), 5000);
                    }
                    if (res.new > 0) {
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
                    directScanInput.placeholder = originalPlaceholder;
                }, 2000);
            }
        });
    }
};
