/**
 * main.js - Global Interactions
 * Handles Dark Mode, Loading States, Toasts, Command Palette & Smart Paste
 */

document.addEventListener('DOMContentLoaded', () => {
    // --- 1. Dark Mode Toggler (Corrigido ID) ---
    const themeToggleBtn = document.getElementById('themeToggle'); // ID corrigido para bater com base.html
    const htmlElement = document.documentElement;

    // Check local storage or system preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    function applyTheme(theme) {
        htmlElement.setAttribute('data-bs-theme', theme);
        // Dispatch event for charts (Chart.js needs to know when theme changes)
        window.dispatchEvent(new CustomEvent('theme-changed', { detail: { theme: theme } }));
    }

    // Init Logic
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

    // --- 2. Global Loading State on Submit ---
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (form.classList.contains('no-loading') || form.method === 'get') return;

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.disabled) {
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

    // --- 3. Auto-Hide Toasts ---
    // --- 3. Auto-Hide Toasts ---
    document.addEventListener("DOMContentLoaded", function () {
        var toastElList = [].slice.call(document.querySelectorAll('.toast'));
        var toastList = toastElList.map(function (toastEl) {
            return new bootstrap.Toast(toastEl, { delay: 5000 });
        });
        toastList.forEach(toast => toast.show());
    });

    // --- 4. Command Palette Logic (Ctrl + K) ---
    const commandModalEl = document.getElementById('commandPalette');
    if (commandModalEl) {
        const commandModal = new bootstrap.Modal(commandModalEl);
        const commandInput = document.getElementById('commandInput');
        const commandResults = document.getElementById('commandResults');
        let activeIndex = 0;

        const commands = [
            { title: 'Dashboard', url: '/operacional/', icon: 'bi-speedometer2', keywords: 'home inicio' },
            { title: 'Novo Chamado', url: '/operacional/chamados', icon: 'bi-plus-circle', keywords: 'criar adicionar' }, // Ajuste a URL se necessário
            { title: 'Lista de Chamados', url: '/operacional/chamados', icon: 'bi-clipboard-check', keywords: 'ver buscar consultar' },
            { title: 'Técnicos', url: '/operacional/tecnicos', icon: 'bi-people', keywords: 'equipe staff' },
            { title: 'Pagamentos', url: '/financeiro/pagamentos', icon: 'bi-cash-stack', keywords: 'financeiro dinheiro' },
            { title: 'Controle de Estoque', url: '/stock/controle', icon: 'bi-box-seam', keywords: 'materiais peças almoxarifado' }
        ];

        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                commandModal.show();
            }
        });

        commandModalEl.addEventListener('shown.bs.modal', () => {
            commandInput.value = '';
            commandInput.focus();
            renderResults(commands);
        });

        commandInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            let filtered = [];

            if (term.startsWith('fsa') || term.startsWith('cha')) {
                // Smart Search Redirect
                const cleanTerm = term.replace(/[^a-z0-9-]/g, '');
                filtered.push({
                    title: `Buscar Chamado: "${cleanTerm.toUpperCase()}"`,
                    url: `/operacional/chamados?search=${cleanTerm}`,
                    icon: 'bi-search',
                    keywords: ''
                });
            } else {
                filtered = commands.filter(c =>
                    c.title.toLowerCase().includes(term) ||
                    c.keywords.includes(term)
                );
            }
            renderResults(filtered);
        });

        function renderResults(list) {
            commandResults.innerHTML = '';
            if (list.length === 0) {
                commandResults.innerHTML = '<li class="list-group-item bg-transparent text-white-50 text-center py-3">Nenhum resultado</li>';
                return;
            }
            list.forEach((cmd, index) => {
                const li = document.createElement('li');
                li.className = `list-group-item bg-transparent text-white border-0 py-2 px-3 command-item ${index === 0 ? 'active-command' : ''}`;
                li.style.cursor = 'pointer';
                li.dataset.url = cmd.url;
                li.innerHTML = `<div class="d-flex align-items-center"><i class="bi ${cmd.icon} me-3 fs-5 opacity-75"></i><span>${cmd.title}</span></div>`;

                li.addEventListener('click', () => window.location.href = cmd.url);
                li.addEventListener('mouseenter', () => setActive(index));
                commandResults.appendChild(li);
            });
            activeIndex = 0;
        }

        commandInput.addEventListener('keydown', (e) => {
            const items = document.querySelectorAll('.command-item');
            if (items.length === 0) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); setActive((activeIndex + 1) % items.length); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((activeIndex - 1 + items.length) % items.length); }
            else if (e.key === 'Enter') {
                e.preventDefault();
                if (items[activeIndex]) window.location.href = items[activeIndex].dataset.url;
            }
        });

        function setActive(index) {
            activeIndex = index;
            document.querySelectorAll('.command-item').forEach((item, i) => {
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

// --- Global Delete Modal Handler ---
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.btn-delete-global');
    if (!btn) return;

    e.preventDefault();

    const deleteModalEl = document.getElementById('globalDeleteModal');
    if (!deleteModalEl) return;

    const modal = new bootstrap.Modal(deleteModalEl);
    const href = btn.dataset.href || btn.getAttribute('href');
    const message = btn.dataset.message || 'Tem certeza que deseja excluir este item?';

    document.getElementById('globalDeleteMessage').textContent = message;
    document.getElementById('globalDeleteForm').action = href;

    modal.show();
});



