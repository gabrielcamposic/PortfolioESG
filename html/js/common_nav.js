// /Users/gabrielcampos/Documents/Prog/PortfolioESG_public/html/js/common_nav.js

let navFetchInterval;
let navbarLoaded = false; // Guard variable to ensure the navbar is loaded only once.

// --- Helper function to set text content safely ---
function setTextForNav(id, value, defaultValue = 'N/A') {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = (value !== undefined && value !== null && value !== '') ? String(value) : defaultValue;
    }
}

// --- Helper function to format dates for the navbar ---
function formatDateForNav(dateString) {
    if (!dateString || dateString === "N/A") return "N/A";
    try {
        const dateObj = new Date(dateString.includes(' ') ? dateString.replace(' ', 'T') : dateString + 'T00:00:00Z');
        if (isNaN(dateObj.getTime())) return dateString;

        const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const useLocalGetters = dateString.includes(' ') && !dateString.endsWith('Z') && !(typeof dateString === 'string' && dateString.match(/[+-]\d{2}:\d{2}$/));

        const dayName = useLocalGetters ? days[dateObj.getDay()] : days[dateObj.getUTCDay()];
        const dayOfMonth = String(useLocalGetters ? dateObj.getDate() : dateObj.getUTCDate()).padStart(2, '0');
        const monthName = useLocalGetters ? months[dateObj.getMonth()] : months[dateObj.getUTCMonth()];
        const year = useLocalGetters ? dateObj.getFullYear() : dateObj.getUTCFullYear();
        const hours = String(useLocalGetters ? dateObj.getHours() : dateObj.getUTCHours()).padStart(2, '0');
        const minutes = String(useLocalGetters ? dateObj.getMinutes() : dateObj.getUTCMinutes()).padStart(2, '0');

        return `${dayName}, ${dayOfMonth}/${monthName}/${year} - ${hours}:${minutes}`;
    } catch (e) {
        console.warn("Could not format date for nav:", dateString, e);
        return dateString;
    }
}

// --- Helper function to set text and status class for the main status message in nav ---
function setTextAndStatusClassForNav(id, value, statusClassSuffix, defaultValue = 'N/A') {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = (value !== undefined && value !== null && value !== '') ? String(value) : defaultValue;
        const classesToRemove = ['status-pending', 'status-running', 'status-completed', 'status-error', 'status-inactive'];
        element.classList.remove(...classesToRemove);
        if (statusClassSuffix) {
            element.classList.add(statusClassSuffix);
        }
    }
}

// --- Function to apply status class to the nav pipeline status block ---
function setNavPipelineBlockStatusClass(statusClassSuffix) {
    const navStatusBlock = document.getElementById('nav-pipeline-status-details');
    if (navStatusBlock) {
        const classesToRemove = ['status-pending', 'status-running', 'status-completed', 'status-error', 'status-inactive'];
        navStatusBlock.classList.remove(...classesToRemove);
        if (statusClassSuffix) {
            navStatusBlock.classList.add(statusClassSuffix);
        }
    }
}

// --- Fetches progress.json and updates the navbar status section ---
async function updateNavbarStatus() {
    const progressJsonPath = '/html/progress.json';

    try {
        const response = await fetch('pipeline_progress.json?t=' + new Date().getTime());
        if (!response.ok) {
            console.warn(`Failed to fetch ${progressJsonPath} for navbar: ${response.status}`);
            setTextAndStatusClassForNav('pipeline-status-message', 'Error fetching status', 'status-error');
            setNavPipelineBlockStatusClass('status-error');
            return;
        }
        const data = await response.json();

        if (data.pipeline_run_status) {
            const pipeline = data.pipeline_run_status;
            let pipelineStatusCssClass = 'status-pending';

            if (pipeline.status_message) {
                const msg = pipeline.status_message.toLowerCase();
                if (msg.includes('running') || msg.includes('started') || msg.includes('initializing')) {
                    pipelineStatusCssClass = 'status-running';
                } else if (msg.includes('completed') || msg.includes('finished')) {
                    pipelineStatusCssClass = 'status-completed';
                } else if (msg.includes('failed') || msg.includes('error')) {
                    pipelineStatusCssClass = 'status-error';
                }
            }

            setTextAndStatusClassForNav('pipeline-status-message', pipeline.status_message, pipelineStatusCssClass);
            setTextForNav('pipeline-start-time', formatDateForNav(pipeline.start_time));
            setTextForNav('pipeline-end-time-nav', formatDateForNav(pipeline.end_time));
            setTextForNav('pipeline-current-stage', pipeline.current_stage);
            setNavPipelineBlockStatusClass(pipelineStatusCssClass);

        } else {
            setTextAndStatusClassForNav('pipeline-status-message', 'Status unavailable', 'status-pending');
            setNavPipelineBlockStatusClass('status-pending');
        }
    } catch (error) {
        console.error('Error updating navbar status:', error);
        setTextAndStatusClassForNav('pipeline-status-message', 'Error updating status', 'status-error');
        setNavPipelineBlockStatusClass('status-error');
    }
}

// --- Initializes the navbar status updates (fetching progress.json periodically) ---
function initializeNavbarStatusUpdates() {
    if (navFetchInterval) {
        clearInterval(navFetchInterval);
    }
    updateNavbarStatus();
    navFetchInterval = setInterval(updateNavbarStatus, 7000);
}

// --- Loads the navbar template and then initializes status updates ---
async function loadNavbar() {
    // --- FINAL FIX: Make the function idempotent ---
    if (navbarLoaded) {
        return; // Do not run again if already loaded
    }
    navbarLoaded = true; // Set the guard immediately

    try {
        const repoName = 'PortfolioESG';
        let navTemplatePath;
        const currentHostname = window.location.hostname;
        const currentPathname = window.location.pathname;

        if (currentHostname.includes('github.io')) {
            navTemplatePath = `/${repoName}/html/nav_template.html`;
        } else {
            if (currentPathname.endsWith('/') || currentPathname.endsWith('/index.html')) {
                navTemplatePath = 'html/nav_template.html';
            } else {
                navTemplatePath = 'nav_template.html';
            }
        }

        const response = await fetch(navTemplatePath + '?t=' + new Date().getTime());
        if (!response.ok) {
            throw new Error(`Failed to load ${navTemplatePath}: ${response.status}`);
        }
        const navbarHtml = await response.text();
        const navbarPlaceholder = document.getElementById('navbar-placeholder');
        if (navbarPlaceholder) {
            const parser = new DOMParser();
            const doc = parser.parseFromString(navbarHtml, 'text/html');
            const navElement = doc.querySelector('nav#top-navbar');

            if (navElement) {
                const isIndexPage = currentPathname === `/${repoName}/` || currentPathname === `/${repoName}/index.html` || currentPathname === '/' || currentPathname.endsWith('index.html');

                if (isIndexPage) {
                    // Customizations for index.html
                    const logoLink = navElement.querySelector('.nav-logo a');
                    if (logoLink) logoLink.setAttribute('href', '#overview');
                    
                    const navLinksUl = navElement.querySelector('.nav-links');
                    if (navLinksUl) navLinksUl.innerHTML = ''; // Clear template links

                    const statusWidget = navElement.querySelector('.nav-status-widget');
                    if (statusWidget) statusWidget.style.display = 'none';

                    navbarPlaceholder.appendChild(navElement);

                } else {
                    // For all other pages
                    navbarPlaceholder.appendChild(navElement);
                    const scriptElement = doc.querySelector('script');
                    if (scriptElement) {
                        const newScript = document.createElement('script');
                        newScript.textContent = scriptElement.textContent;
                        document.body.appendChild(newScript);
                    }
                    initializeNavbarStatusUpdates();
                }
            } else {
                // Fallback
                Array.from(doc.body.childNodes).forEach(node => {
                    navbarPlaceholder.appendChild(node.cloneNode(true));
                });
            }
        }
    } catch (error) {
        console.error('Error loading navbar:', error);
        const navbarPlaceholder = document.getElementById('navbar-placeholder');
        if(navbarPlaceholder) navbarPlaceholder.innerHTML = "<p style='color:red;text-align:center;'>Error loading navigation.</p>";
    }
}

// --- Auto-load navbar when the script is executed ---
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadNavbar);
} else {
    loadNavbar();
}
