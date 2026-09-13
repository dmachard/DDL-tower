import { state } from './state.js?v=7';
import { fetchData, fetchDownloads, fetchStats, extractText } from './api.js?v=7';

export function initQuickScan() {
    const textarea = document.getElementById('quick-scan-textarea');
    const btnScan = document.getElementById('btn-quick-scan');
    const btnClear = document.getElementById('btn-quick-scan-clear');
    const resultsArea = document.getElementById('quick-scan-results');
    const messageSpan = document.getElementById('quick-scan-message');

    if (!btnScan) return;

    btnScan.addEventListener('click', async () => {
        const text = textarea.value.trim();
        if (!text) return;

        btnScan.disabled = true;
        btnScan.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Extracting...';

        try {
            const force = document.getElementById('quick-scan-force')?.checked || false;
            const response = await extractText(text, force);
            const data = await response.json();
            
            // Show results
            resultsArea.classList.remove('hidden');
            messageSpan.innerText = data.message;
            
            // Reset state
            if (data.new > 0 || force) {
                textarea.value = '';
                // Refresh data if we added or updated something
                fetchData('releases');
                fetchDownloads();
                fetchStats();
            }

            // Hide message after 5s
            setTimeout(() => {
                resultsArea.classList.add('hidden');
            }, 5000);

        } catch (err) {
            console.error('Quick scan failed:', err);
            alert('Error during extraction. Check console.');
        } finally {
            btnScan.disabled = false;
            btnScan.innerHTML = '<i class="fas fa-magic"></i> Extract & Add Links';
        }
    });

    btnClear.addEventListener('click', () => {
        textarea.value = '';
        resultsArea.classList.add('hidden');
    });
}
