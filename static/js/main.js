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

    // --- Table Density Toggle ---
    const densityBtn = document.getElementById('btnDensityToggle');
    const table = document.querySelector('.table');

    if (densityBtn && table) {
        // Load state
        const isCompact = localStorage.getItem('tableDensity') === 'compact';
        if (isCompact) {
            table.classList.add('table-compact');
            densityBtn.classList.add('active');
        }

        // Toggle
        densityBtn.addEventListener('click', () => {
            table.classList.toggle('table-compact');
            const isActive = table.classList.contains('table-compact');

            densityBtn.classList.toggle('active', isActive);
            localStorage.setItem('tableDensity', isActive ? 'compact' : 'normal');
        });
    }
    // --- Command Palette Logic ---
    const commandModalEl = document.getElementById('commandPalette');
    if (commandModalEl) {
        const commandModal = new bootstrap.Modal(commandModalEl);
        const commandInput = document.getElementById('commandInput');
        const commandResults = document.getElementById('commandResults');
        let activeIndex = 0;

        // Commands Definitions
        const commands = [
            { title: 'Dashboard', url: '/operacional/', icon: 'bi-speedometer2', keywords: 'home inicio' },
            { title: 'Novo Chamado', url: '/chamados/novo', icon: 'bi-plus-circle', keywords: 'criar adicionar' },
            { title: 'Lista de Chamados', url: '/operacional/chamados', icon: 'bi-clipboard-check', keywords: 'ver buscar consultar' },
            { title: 'Novo Técnico', url: '/tecnicos/novo', icon: 'bi-person-plus', keywords: 'cadastrar' },
            { title: 'Lista de Técnicos', url: '/operacional/tecnicos', icon: 'bi-people', keywords: 'equipe staff' },
            { title: 'Pagamentos', url: '/financeiro/pagamentos', icon: 'bi-cash-stack', keywords: 'financeiro dinheiro' },
            { title: 'Conta Corrente (Ledger)', url: '/financeiro/ledger', icon: 'bi-wallet-fill', keywords: 'extrato saldo' },
            { title: 'Estoque / Almoxarifado', url: '/stock/controle', icon: 'bi-box-seam', keywords: 'materiais peças' },
            { title: 'Auditoria', url: '/admin/auditoria', icon: 'bi-shield-check', keywords: 'logs segurança history' }
        ];

        // Shortcut Listener (Ctrl+K)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                commandModal.show();
            }
        });

        // Focus Input on Show
        commandModalEl.addEventListener('shown.bs.modal', () => {
            commandInput.value = '';
            commandInput.focus();
            renderResults(commands); // Show all initially
        });

        // Input Filter
        commandInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            let filtered = [];

            // Smart Search Detectors
            if (term.startsWith('fsa-') || term.startsWith('fsa')) {
                filtered.push({
                    title: `Buscar Chamado: "${term.toUpperCase()}"`,
                    url: `/operacional/chamados?search=${term}`,
                    icon: 'bi-search',
                    keywords: ''
                });
            } else if (term.length > 2) {
                // Generic search across commands + dynamic suggestion
                filtered = commands.filter(c =>
                    c.title.toLowerCase().includes(term) ||
                    c.keywords.includes(term)
                );
            } else {
                filtered = commands;
            }

            renderResults(filtered);
        });

        // Render Function
        function renderResults(list) {
            commandResults.innerHTML = '';
            if (list.length === 0) {
                commandResults.innerHTML = '<li class="list-group-item bg-transparent text-white-50 text-center py-3">Nenhum resultado encontrado</li>';
                return;
            }

            list.forEach((cmd, index) => {
                const li = document.createElement('li');
                li.className = `list-group-item bg-transparent text-white border-0 py-2 px-3 command-item ${index === 0 ? 'active-command' : ''}`;
                li.style.cursor = 'pointer';
                li.dataset.url = cmd.url;
                li.innerHTML = `
                    <div class="d-flex align-items-center">
                        <i class="bi ${cmd.icon} me-3 fs-5 opacity-75"></i>
                        <span>${cmd.title}</span>
                    </div>
                `;
                li.addEventListener('click', () => window.location.href = cmd.url);
                li.addEventListener('mouseenter', () => setActive(index));
                commandResults.appendChild(li);
            });
            activeIndex = 0;
        }

        // Keyboard Navigation in Input
        commandInput.addEventListener('keydown', (e) => {
            const items = document.querySelectorAll('.command-item');
            if (items.length === 0) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive((activeIndex + 1) % items.length);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive((activeIndex - 1 + items.length) % items.length);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const activeItem = items[activeIndex];
                if (activeItem) {
                    window.location.href = activeItem.dataset.url;
                }
            }
        });

        function setActive(index) {
            activeIndex = index;
            const items = document.querySelectorAll('.command-item');
            items.forEach((item, i) => {
                if (i === index) {
                    item.classList.add('active-command');
                    item.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                    item.scrollIntoView({ block: 'nearest' });
                } else {
                    item.classList.remove('active-command');
                    item.style.backgroundColor = 'transparent';
                }
            });
        }
    }
});

