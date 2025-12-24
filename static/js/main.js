/**
 * main.js - Global Interactions
 * Handles Dark Mode toggling, Click-to-Copy, Loading States, and Toasts.
 */

document.addEventListener('DOMContentLoaded', () => {
    // --- Dark Mode Toggler ---
    const themeToggleBtn = document.getElementById('theme-toggle');
    const htmlElement = document.documentElement;
    const themeIcon = document.getElementById('theme-icon');

    // Check local storage or system preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    function applyTheme(theme) {
        htmlElement.setAttribute('data-bs-theme', theme);
        if (themeIcon) {
            themeIcon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
        }
    }

    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
        applyTheme('dark');
    } else {
        applyTheme('light');
    }

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = htmlElement.getAttribute('data-bs-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }

    // --- Global Loading State on Submit ---
    document.addEventListener('submit', function (e) {
        const form = e.target;
        // Skip for forms explicitly marked no-loading or search forms that are fast
        if (form.classList.contains('no-loading') || form.method === 'get') return;

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            // Store original content
            if (!submitBtn.dataset.originalContent) {
                submitBtn.dataset.originalContent = submitBtn.innerHTML;
            }

            // Set fixed width to prevent jump
            submitBtn.style.width = `${submitBtn.offsetWidth}px`;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
        }
    });

    // --- Auto-Hide Toasts ---
    // If we use standard Bootstrap toasts, we initialize them here
    const toastElList = [].slice.call(document.querySelectorAll('.toast:not(.show)'));
    toastElList.map(function (toastEl) {
        return new bootstrap.Toast(toastEl, { delay: 5000 }).show();
    });

    // For toasts manually inserted with .show class (like our flash messages), auto-hide
    const shownToasts = document.querySelectorAll('.toast.show');
    shownToasts.forEach(toast => {
        setTimeout(() => {
            // Fade out
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 500); // Remove from DOM after transition
        }, 5000);
    });


    // --- Click to Copy ---
    // Use event delegation for dynamic content support
    document.addEventListener('click', async (e) => {
        // Support both .copy-text and .copy-trigger
        const target = e.target.closest('.copy-text, .copy-trigger');
        if (!target) return;

        // Support data-copy (new) or data-value (old/compat)
        const textToCopy = target.getAttribute('data-copy') || target.getAttribute('data-value') || target.innerText.trim();

        if (!textToCopy) return;

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

            // Optional: Show small toast
            // showToast('Copiado!');

        } catch (err) {
            console.error('Failed to copy text: ', err);
            target.classList.add('text-danger');
            setTimeout(() => {
                target.classList.remove('text-danger');
            }, 1500);
        }
    });
});

