// Utility functions for the Chemical Inventory System
const ChemUtils = {
    /**
     * Shows an alert message in the designated alert element
     * @param {string} message - The message to display
     * @param {number} [timeout=10000] - Time in ms before the alert disappears
     */
    showAlert: function(message, timeout = 10000) {
        const alertElem = document.getElementById("scan-alert");
        if (alertElem) {
            alertElem.textContent = message;
            alertElem.style.display = "block";
            setTimeout(() => {
                alertElem.style.display = "none";
            }, timeout);
        }
    },

    /**
     * Formats a date string
     * @param {string} dateStr - The date string to format
     * @returns {string} Formatted date string
     */
    formatDate: function(dateStr) {
        return luxon.DateTime.fromISO(dateStr).toFormat('yyyy-MM-dd HH:mm:ss');
    }
};

// Make utilities available globally
window.ChemUtils = ChemUtils;
