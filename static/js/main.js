/**
 * main.js - Global Interactions
 * Handles Dark Mode toggling and Click-to-Copy functionality.
 */

document.addEventListener('DOMContentLoaded', () => {
    // --- Dark Mode Toggler ---
    const themeToggleBtn = document.getElementById('theme-toggle');
    const htmlElement = document.documentElement;

    // Check local storage or system preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
        htmlElement.setAttribute('data-bs-theme', 'dark');
        if (themeToggleBtn) themeToggleBtn.innerHTML = '<i class="bi bi-sun-fill"></i>';
    } else {
        htmlElement.setAttribute('data-bs-theme', 'light');
        if (themeToggleBtn) themeToggleBtn.innerHTML = '<i class="bi bi-moon-fill"></i>';
    }

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = htmlElement.getAttribute('data-bs-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

            htmlElement.setAttribute('data-bs-theme', newTheme);
            localStorage.setItem('theme', newTheme);

            // Update Icon
            themeToggleBtn.innerHTML = newTheme === 'dark'
                ? '<i class="bi bi-sun-fill"></i>'
                : '<i class="bi bi-moon-fill"></i>';
        });
    }

    // --- Click to Copy ---
    // Use event delegation for dynamic content support
    document.addEventListener('click', async (e) => {
        // Support both .copy-text and .copy-trigger
        const target = e.target.closest('.copy-text, .copy-trigger');
        if (!target) return;

        // Support data-copy (new) or data-value (old/compat)
        const textToCopy = target.getAttribute('data-copy') || target.getAttribute('data-value') || target.innerText;

        try {
            await navigator.clipboard.writeText(textToCopy);

            // Visual Feedback
            // If it has an icon inside, we can toggle it
            const icon = target.querySelector('i');
            if (icon) {
                const originalClass = icon.className;
                icon.className = 'bi bi-check-lg text-success';
                setTimeout(() => {
                    icon.className = originalClass;
                }, 2000);
            } else {
                target.classList.add('text-success');
                setTimeout(() => {
                    target.classList.remove('text-success');
                }, 1500);
            }

        } catch (err) {
            console.error('Failed to copy text: ', err);
            target.classList.add('text-danger');
            setTimeout(() => {
                target.classList.remove('text-danger');
            }, 1500);
        }
    });
});

