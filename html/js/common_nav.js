// /Users/gabrielcampos/Documents/Prog/PortfolioESG_public/html/js/common_nav.js

let navFetchInterval;

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
    // Determine the correct path to progress.json
    const isIndexPage = window.location.pathname === '/' || window.location.pathname.endsWith('/index.html');
    const progressJsonPath = isIndexPage ? 'html/progress.json' : 'progress.json';

    try {
        const response = await fetch(progressJsonPath + '?t=' + new Date().getTime());
        if (!response.ok) {
            console.warn(`Failed to fetch ${progressJsonPath} for navbar: ${response.status}`);
            setTextAndStatusClassForNav('pipeline-status-message', 'Error fetching status', 'status-error');
            setNavPipelineBlockStatusClass('status-error');
            return;
        }
        const data = await response.json();

        if (data.pipeline_run_status) {
            const pipeline = data.pipeline_run_status;
            let pipelineStatusCssClass = 'status-pending'; // Default

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
    updateNavbarStatus(); // Initial fetch
    navFetchInterval = setInterval(updateNavbarStatus, 7000); // Update nav status every 7 seconds
}

// --- Loads the navbar template and then initializes status updates ---
async function loadNavbar() {
    try {
        const repoName = 'PortfolioESG'; // Your GitHub repository name
        let navTemplatePath; 
        const currentHostname = window.location.hostname;
        const currentPathname = window.location.pathname;

        console.log('[NAV DEBUG] Hostname:', currentHostname);
        console.log('[NAV DEBUG] Pathname:', currentPathname);

        if (currentHostname.includes('github.io')) {
            navTemplatePath = `/${repoName}/html/nav_template.html`; // Absolute path from site root for GitHub Pages
            console.log('[NAV DEBUG] GitHub Pages. navTemplatePath set to:', navTemplatePath);
        } else { 
            // Logic for local (Mac) and RPi server
            console.log('[NAV DEBUG] RPi/Local environment detected.');
             // Logic for local (Mac) and RPi server
            if (currentPathname.endsWith('/') || currentPathname.endsWith('/index.html')) {
                // This is index.html (likely on Mac dev environment, served from project root)
                // or the root of a site.
                navTemplatePath = 'html/nav_template.html';
                console.log('[NAV DEBUG] RPi/Local. Path ends with / or /index.html. navTemplatePath set to:', navTemplatePath);
            } else {
                // This is for other pages like pipeline.html, esgportfolio.html, etc.
                // On Mac, currentPathname is /PortfolioESG_public/html/pipeline.html, nav_template.html is a sibling.
                // On RPi, currentPathname is /pipeline.html, nav_template.html is a sibling.
                navTemplatePath = 'nav_template.html';
                console.log('[NAV DEBUG] RPi/Local. Path does NOT end with / or /index.html. navTemplatePath set to:', navTemplatePath);
            }
        } 

        const response = await fetch(navTemplatePath + '?t=' + new Date().getTime());
        if (!response.ok) {
            console.error(`Failed to load ${navTemplatePath}: ${response.status}`);
            throw new Error(`Failed to load ${navTemplatePath}: ${response.status}`);
        }
        const navbarHtml = await response.text();
        const navbarPlaceholder = document.getElementById('navbar-placeholder');
        if (navbarPlaceholder) {
            // Use DOMParser to handle the HTML and its script
            const parser = new DOMParser();
            const doc = parser.parseFromString(navbarHtml, 'text/html');
            
            // Append the <nav> element (or whatever the main content is)
            const navElement = doc.querySelector('nav#top-navbar'); // Assuming your main nav element has this ID
            if (navElement) {
                // Define isIndexPage based on the current path and repository name
                const currentPathname = window.location.pathname;
                // Check against the base path for the repo and index.html specifically
                const isIndexPage = currentPathname === `/${repoName}/` || currentPathname === `/${repoName}/index.html`;

                if (isIndexPage) {
                    // Customize for index.html
                    const logoLink = navElement.querySelector('.nav-logo a');
                    if (logoLink) {
                        // Point to the top of the index page or a specific section like #overview
                        logoLink.setAttribute('href', '#overview'); 
                    }

                    // Find the existing hamburger toggle from the parsed navElement
                    const existingNavToggle = navElement.querySelector('.nav-toggle');
                    const navLinksUl = navElement.querySelector('.nav-links');
                    if (navLinksUl) {
                        navLinksUl.innerHTML = ''; // Clear existing links from nav_template.html
                        const indexPageLinks = [
                            { href: '#overview', text: 'Visão Geral' },
                            { href: '#how-it-works', text: 'Como Funciona' },
                            { href: '#features', text: 'Funcionalidades' },
                            { href: '#technology', text: 'Tecnologia' },
                            { href: '#project-previews', text: 'Pré-visualizações' }, // Default text, will be translated
                            { href: '#status-future', text: 'Status e Futuro' },
                            { href: '#contact', text: 'Contato' }
                        ];
                        indexPageLinks.forEach(linkInfo => {
                            const li = document.createElement('li');
                            const a = document.createElement('a');
                            a.setAttribute('href', linkInfo.href);
                            a.textContent = linkInfo.text;
                            li.appendChild(a);
                            navLinksUl.appendChild(li);
                        });

                        // Attach event listener to the EXISTING toggle if found
                        if (existingNavToggle) {
                            existingNavToggle.addEventListener('click', () => {
                                navLinksUl.classList.toggle('nav-links-active');
                                existingNavToggle.setAttribute('aria-expanded', navLinksUl.classList.contains('nav-links-active'));
                            });
                        }

                    }

                    const statusWidget = navElement.querySelector('.nav-status-widget');
                    if (statusWidget) {
                        statusWidget.style.display = 'none'; // Hide status widget
                    }
                    
                    // Append the modified navElement without executing its original script
                    navbarPlaceholder.appendChild(navElement);
                    // DO NOT call initializeNavbarStatusUpdates() for index.html
                    // Call a function to update link text if it exists (defined in index.html's script)
                    if (typeof window.updateIndexNavbarLinksText === 'function') {
                        window.updateIndexNavbarLinksText(); // It will use its own translations
                    }

                } else {
                    // For other pages (pipeline.html, esgportfolio.html, etc.)
                    navbarPlaceholder.appendChild(navElement); // Append the original nav element

                    // Find and execute the script tag from nav_template.html
                    // By appending it here, it executes in the context of the main document
                    // after navElement is part of the DOM.
                    const scriptElement = doc.querySelector('script');
                    if (scriptElement) {
                        const newScript = document.createElement('script');
                        newScript.textContent = scriptElement.textContent; // Copy the script content
                        navbarPlaceholder.appendChild(newScript); // Append to placeholder to execute
                    }
                    // Translate links in the loaded navElement for non-index pages
                    // This assumes 'translations' and 'currentLanguage' are globally available on the page (e.g., pipeline.html)
                    if (navElement && typeof translations !== 'undefined' && typeof currentLanguage !== 'undefined' && translations[currentLanguage]) {
                        const langTrans = translations[currentLanguage];
                        navElement.querySelectorAll('a[data-translate-key]').forEach(a => {
                            const key = a.getAttribute('data-translate-key');
                            if (langTrans[key]) {
                                a.textContent = langTrans[key];
                            }
                        });
                    }
                    initializeNavbarStatusUpdates(); // Start updating status only for non-index pages
                }
            } else {
                // Fallback if the structure is different, append all body children
                Array.from(doc.body.childNodes).forEach(node => {
                    navbarPlaceholder.appendChild(node.cloneNode(true)); // cloneNode to avoid issues if node is script
                });
                // Define isIndexPage here as well if it wasn't defined before this fallback
                const currentPathnameForFallback = window.location.pathname;
                const isIndexPageForFallback = currentPathnameForFallback === `/${repoName}/` || currentPathnameForFallback === `/${repoName}/index.html`;

                if (!isIndexPageForFallback) {
                    initializeNavbarStatusUpdates(); // Still initialize if fallback used on non-index page
                }
            }
        } else {
            console.error('Navbar placeholder #navbar-placeholder not found.');
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
    loadNavbar(); // DOMContentLoaded has already fired
}
