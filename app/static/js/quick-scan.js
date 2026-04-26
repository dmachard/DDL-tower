import { state } from './state.js';
import { fetchData, fetchDownloads, fetchStats, extractText } from './api.js';

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
            const response = await extractText(text);
            const data = await response.json();
            
            // Show results
            resultsArea.classList.remove('hidden');
            messageSpan.innerText = data.message;
            
            // Reset state
            if (data.new > 0) {
                textarea.value = '';
                // Refresh data if we added something
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
