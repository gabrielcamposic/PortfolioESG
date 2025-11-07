/**
 * A collection of common utility functions used across the project's frontend.
 * This is the single source of truth for formatting and DOM manipulation.
 */

// --- Global Chart Colors ---
const CHART_COLORS_SOLID = [
    'rgba(54, 162, 235, 1)',   // Blue
    'rgba(255, 99, 132, 1)',    // Red
    'rgba(75, 192, 192, 1)',    // Green
    'rgba(255, 206, 86, 1)',    // Yellow
    'rgba(153, 102, 255, 1)',  // Purple
    'rgba(255, 159, 64, 1)',   // Orange
    'rgba(99, 255, 132, 1)',   // Lime
    'rgba(235, 54, 162, 1)',   // Pink
    'rgba(86, 255, 206, 1)',   // Aqua
    'rgba(102, 153, 255, 1)',  // Light Blue
    'rgba(255, 64, 159, 1)',   // Magenta
    'rgba(192, 75, 192, 1)'    // Violet
];

const CHART_COLORS_ALPHA = CHART_COLORS_SOLID.map(color => color.replace(', 1)', ', 0.7)'));

// --- DOM Manipulation ---

/**
 * Safely sets the text content of an element by its ID.
 * @param {string} id The ID of the element.
 * @param {string|number|null|undefined} text The text to set. Defaults to 'N/A'.
 */
function setText(id, text) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = (text === null || text === undefined || text === '') ? 'N/A' : text;
    } else {
        console.warn(`Element with ID '${id}' not found.`);
    }
}

/**
 * Updates the status pill for a pipeline stage.
 * @param {string} elementId The ID of the status pill element.
 * @param {string} status The status string (e.g., "Running", "Completed", "Failed").
 */
function setStageStatus(elementId, status) {
    const element = document.getElementById(elementId);
    if (!element) {
        console.warn(`Status pill with ID '${elementId}' not found.`);
        return;
    }
    const statusText = status || 'Pending';
    element.textContent = statusText;
    // Remove all potential status classes before adding the new one
    element.classList.remove('status-running', 'status-completed', 'status-failed', 'status-pending');
    // Add the appropriate class based on the status text (e.g., "Running: Initializing..." becomes "status-running")
    element.classList.add(`status-${statusText.toLowerCase().split(':')[0].trim()}`);
}

/**
 * Updates the width of a progress bar.
 * @param {string} elementId The ID of the inner progress bar element.
 * @param {number} percentage The progress percentage (0-100).
 */
function updateProgressBar(elementId, percentage) {
    const element = document.getElementById(elementId);
    if (element) {
        const validPercentage = Math.max(0, Math.min(100, percentage || 0));
        element.style.width = `${validPercentage}%`;
    } else {
        console.warn(`Progress bar with ID '${elementId}' not found.`);
    }
}

// --- Data Fetching ---

/**
 * Fetches and parses a CSV file into an array of objects.
 * Handles quoted fields containing commas.
 * @param {string} filePath The path to the CSV file.
 * @returns {Promise<Array<Object>>} A promise that resolves to the parsed data.
 */
async function fetchAndParseCsv(filePath) {
    const response = await fetch(`${filePath}?t=${new Date().getTime()}`);
    if (!response.ok) {
        throw new Error(`Failed to load ${filePath}. Status: ${response.status}`);
    }
    const csvData = await response.text();
    const lines = csvData.trim().split('\n');
    if (lines.length < 2) return []; // Return empty if only header or empty file

    const header = lines[0].split(',').map(h => h.trim());
    // This regex correctly handles commas inside of quoted fields.
    const csvRowRegex = /,(?=(?:(?:[^"]*"){2})*[^"]*$)/;

    return lines.slice(1).map(line => {
        const values = line.split(csvRowRegex);
        const obj = {};
        header.forEach((key, i) => {
            let value = values[i] ? values[i].trim() : '';
            // Remove quotes from the start and end of the value if they exist
            if (value.startsWith('"') && value.endsWith('"')) {
                value = value.substring(1, value.length - 1).replace(/""/g, '"');
            }
            obj[key] = value;
        });
        return obj;
    });
}

// --- Formatting Functions ---

/**
 * A generic value formatter that dispatches to specific formatting functions.
 * @param {string|number|null|undefined} value The value to format.
 * @param {string} [format='decimal'] The format type ('percent', 'decimal', etc.).
 * @param {string} [defaultValue='--'] The default value to return for invalid inputs.
 * @returns {string} The formatted value as a string.
 */
function formatValue(value, format = 'decimal', defaultValue = '--') {
    if (value === null || value === undefined || value === '' || isNaN(parseFloat(value))) {
        return defaultValue;
    }
    const num = parseFloat(value);
    switch (format) {
        case 'percent':
            return `${(num * 100).toFixed(2)}%`;
        case 'decimal':
            return num.toFixed(2);
        default:
            return num.toFixed(2); // Default to decimal format
    }
}

/**
 * Formats a number to a fixed number of decimal places.
 * @param {string|number|null|undefined} value The value to format.
 * @param {number} [decimals=2] The number of decimal places.
 * @returns {string} The formatted number as a string, or 'N/A'.
 */
function formatNumber(value, decimals = 2) {
    if (value === null || value === undefined || value === '') return 'N/A';
    const num = parseFloat(value);
    if (isNaN(num)) return 'N/A';
    return num.toFixed(decimals);
}

/**
 * Formats a date string into a readable format (e.g., "Mon, 01/Jan/2024 - 14:30").
 * @param {string} dateString - The date string to format.
 * @returns {string} The formatted date string.
 */
function formatDate(dateString) {
    if (!dateString || dateString === "N/A" || dateString.toLowerCase() === "calculating...") return dateString;
    try {
        const dateObj = new Date(dateString.includes(' ') && !dateString.includes('T') ? dateString.replace(' ', 'T') : dateString.includes('T') || dateString.includes('Z') ? dateString : dateString + 'T00:00:00Z');
        if (isNaN(dateObj.getTime())) return dateString;

        const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const useLocalGetters = dateString.includes(' ') && !dateString.endsWith('Z') && !dateString.match(/[+-]\\d{2}:\\d{2}$/);

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
 * Formats a duration string (e.g., "HH:MM:SS.micros") into "X day(s) and HH:MM:SS".
 * @param {string} durationString - The duration string to format.
 * @returns {string} The formatted duration string.
 */
function formatDuration(durationString) {
    if (!durationString || durationString === "N/A") return "N/A";
    if (durationString.includes("day")) return durationString; // Already formatted

    if (durationString.includes(':')) {
         const parts = durationString.split(':');
         if (parts.length === 3) {
            const secondsAndMs = parts[2].split('.');
            let totalSeconds = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(secondsAndMs[0]);
            if (isNaN(totalSeconds)) return durationString;

            const finalDays = Math.floor(totalSeconds / 86400);
            let remSec = totalSeconds % 86400;
            const finalHours = Math.floor(remSec / 3600); remSec %= 3600;
            const finalMinutes = Math.floor(remSec / 60);
            const finalSeconds = Math.floor(remSec % 60);
            return `${finalDays > 0 ? `${finalDays} day${finalDays > 1 ? 's' : ''} and ` : ''}${String(finalHours).padStart(2, '0')}:${String(finalMinutes).padStart(2, '0')}:${String(finalSeconds).padStart(2, '0')}`;
         }
    }
    return durationString;
}

/**
 * Formats a duration in seconds into "Xd HH:MM:SS" format.
 * @param {string|number} secondsStr - The duration in seconds.
 * @returns {string} The formatted duration string.
 */
function formatSecondsToHMS(secondsStr) {
    if (!secondsStr || secondsStr === "N/A" || isNaN(parseFloat(secondsStr))) return "N/A";
    let totalSeconds = parseFloat(secondsStr);
    const finalDays = Math.floor(totalSeconds / 86400);
    let remSec = totalSeconds % 86400;
    const finalHours = Math.floor(remSec / 3600); remSec %= 3600;
    const finalMinutes = Math.floor(remSec / 60);
    const finalSeconds = Math.floor(remSec % 60);
    return `${finalDays > 0 ? `${finalDays}d ` : ''}${String(finalHours).padStart(2, '0')}:${String(finalMinutes).padStart(2, '0')}:${String(finalSeconds).padStart(2, '0')}`;
}

/**
 * Formats a number (representing seconds) to a string with two decimal places.
 * @param {string|number} secondsStr - The number of seconds.
 * @returns {string} The formatted string.
 */
function formatSeconds(secondsStr) {
    if (!secondsStr || secondsStr === "N/A" || isNaN(parseFloat(secondsStr))) return "N/A";
    return parseFloat(secondsStr).toFixed(2);
}

/**
 * Generates a random RGB color string.
 * @param {number} [alpha=1] - The alpha transparency value (0 to 1).
 * @returns {string} An RGBA color string.
 */
function getRandomColor(alpha = 1) {
    return `rgba(${Math.floor(Math.random() * 200)}, ${Math.floor(Math.random() * 200)}, ${Math.floor(Math.random() * 200)}, ${alpha})`;
}