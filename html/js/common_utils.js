// /Users/gabrielcampos/Documents/Prog/PortfolioESG_public/html/js/common_utils.js

/**
 * Formats a date string into a readable format (e.g., "Mon, 01/Jan/2024 - 14:30").
 * Handles various input date string formats, including those with/without time, and UTC/local indicators.
 * @param {string} dateString - The date string to format.
 * @returns {string} The formatted date string, or the original string if formatting fails or input is invalid.
 */
function formatDate(dateString) {
    if (!dateString || dateString === "N/A" || dateString.toLowerCase() === "calculating...") return dateString;
    try {
        // Attempt to parse the date string. Handles "YYYY-MM-DD HH:MM:SS" by replacing space with 'T'.
        // Assumes UTC if only date is provided (e.g., "YYYY-MM-DD" becomes "YYYY-MM-DDT00:00:00Z").
        const dateObj = new Date(dateString.includes(' ') && !dateString.includes('T') ? dateString.replace(' ', 'T') : dateString.includes('T') || dateString.includes('Z') ? dateString : dateString + 'T00:00:00Z');
        if (isNaN(dateObj.getTime())) return dateString;

        const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

        // Determine if to use local or UTC getters based on original string format
        const useLocalGetters = dateString.includes(' ') && !dateString.endsWith('Z') && !dateString.match(/[+-]\d{2}:\d{2}$/);

        const dayName = useLocalGetters ? days[dateObj.getDay()] : days[dateObj.getUTCDay()];
        const dayOfMonth = String(useLocalGetters ? dateObj.getDate() : dateObj.getUTCDate()).padStart(2, '0');
        const monthName = useLocalGetters ? months[dateObj.getMonth()] : months[dateObj.getUTCMonth()];
        const year = useLocalGetters ? dateObj.getFullYear() : dateObj.getUTCFullYear();
        const hours = String(useLocalGetters ? dateObj.getHours() : dateObj.getUTCHours()).padStart(2, '0');
        const minutes = String(useLocalGetters ? dateObj.getMinutes() : dateObj.getUTCMinutes()).padStart(2, '0');
        return `${dayName}, ${dayOfMonth}/${monthName}/${year} - ${hours}:${minutes}`;
    } catch (e) {
        console.warn("Could not format date in common_utils.js:", dateString, e);
        return dateString;
    }
}

/**
 * Formats a duration string (e.g., "HH:MM:SS.micros" or "X days and HH:MM:SS") into a standardized "X day(s) and HH:MM:SS" format.
 * @param {string} durationString - The duration string to format.
 * @returns {string} The formatted duration string, or "N/A" if input is invalid.
 */
function formatDuration(durationString) {
    if (!durationString || durationString === "N/A") return "N/A";
    
    if (durationString.includes("day")) { // Already well-formatted
        return durationString;
    }

    if (durationString.includes(':')) {
         const parts = durationString.split(':');
         if (parts.length === 3) {
            const secondsAndMs = parts[2].split('.');
            let totalSeconds = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(secondsAndMs[0]);
            if (isNaN(totalSeconds)) return durationString;

            const finalDays = Math.floor(totalSeconds / 86400);
            let remSec = totalSeconds % 86400;
            const finalHours = Math.floor(remSec / 3600); remSec %= 3600;
            const finalMinutes = Math.floor(remSec / 60); const finalSeconds = Math.floor(remSec % 60);
            return `${finalDays > 0 ? `${finalDays} day${finalDays > 1 ? 's' : ''} and ` : ''}${String(finalHours).padStart(2, '0')}:${String(finalMinutes).padStart(2, '0')}:${String(finalSeconds).padStart(2, '0')}`;
         }
    }
    return durationString; 
}

/**
 * Formats a duration given in seconds (as a string or number) into "Xd HH:MM:SS" format.
 * @param {string|number} secondsStr - The duration in seconds.
 * @returns {string} The formatted duration string, or "N/A" if input is invalid.
 */
function formatSecondsToHMS(secondsStr) {
    if (!secondsStr || secondsStr === "N/A" || isNaN(parseFloat(secondsStr))) return "N/A";
    let totalSeconds = parseFloat(secondsStr);
    const finalDays = Math.floor(totalSeconds / 86400);
    let remSec = totalSeconds % 86400;
    const finalHours = Math.floor(remSec / 3600); remSec %= 3600;
    const finalMinutes = Math.floor(remSec / 60); const finalSeconds = Math.floor(remSec % 60);
    return `${finalDays > 0 ? `${finalDays}d ` : ''}${String(finalHours).padStart(2, '0')}:${String(finalMinutes).padStart(2, '0')}:${String(finalSeconds).padStart(2, '0')}`;
}

/**
 * Formats a number (representing seconds) to a string with two decimal places.
 * @param {string|number} secondsStr - The number of seconds.
 * @returns {string} The formatted string, or "N/A" if input is invalid.
 */
function formatSeconds(secondsStr) {
    if (!secondsStr || secondsStr === "N/A" || isNaN(parseFloat(secondsStr))) return "N/A";
    return parseFloat(secondsStr).toFixed(2);
}

/**
 * Generates a random RGB color string.
 * @param {number} [alpha=1] - The alpha transparency value (0 to 1).
 * @returns {string} An RGBA color string (e.g., "rgba(123, 234, 56, 0.5)").
 */
function getRandomColor(alpha = 1) {
    return `rgba(${Math.floor(Math.random() * 200)}, ${Math.floor(Math.random() * 200)}, ${Math.floor(Math.random() * 200)}, ${alpha})`;
}
