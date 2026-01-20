/**
 * Dashboard.js - Privacy Toggle and Utilities
 * 
 * Clean dashboard without charts.
 * Only privacy toggle functionality for financial values.
 */

document.addEventListener('DOMContentLoaded', function () {
    initGreeting();
});

/**
 * Dynamic greeting based on time of day
 */
function initGreeting() {
    const hour = new Date().getHours();
    let greeting = 'Olá';

    if (hour >= 5 && hour < 12) greeting = 'Bom dia';
    else if (hour >= 12 && hour < 18) greeting = 'Boa tarde';
    else greeting = 'Boa noite';

    console.log(`${greeting} - Dashboard loaded at ${new Date().toLocaleTimeString()}`);
}

/**
 * Toggle privacy blur on click
 * @param {HTMLElement} element - The privacy-value wrapper element
 */
function togglePrivacy(element) {
    const blurEl = element.querySelector('.privacy-blur');
    const iconEl = element.querySelector('.privacy-icon');

    if (blurEl) {
        blurEl.classList.toggle('visible');
    }

    if (iconEl) {
        // Toggle icon between eye and eye-slash
        if (blurEl.classList.contains('visible')) {
            iconEl.classList.remove('bi-eye');
            iconEl.classList.add('bi-eye-slash');
        } else {
            iconEl.classList.remove('bi-eye-slash');
            iconEl.classList.add('bi-eye');
        }
    }

    // Toggle wrapper class for styling
    element.classList.toggle('visible');
}

/**
 * Reveal all privacy values at once (optional shortcut)
 */
function revealAllPrivacy() {
    document.querySelectorAll('.privacy-blur').forEach(el => {
        el.classList.add('visible');
    });
    document.querySelectorAll('.privacy-value').forEach(el => {
        el.classList.add('visible');
    });
}

/**
 * Hide all privacy values (reset)
 */
function hideAllPrivacy() {
    document.querySelectorAll('.privacy-blur').forEach(el => {
        el.classList.remove('visible');
    });
    document.querySelectorAll('.privacy-value').forEach(el => {
        el.classList.remove('visible');
    });
}
