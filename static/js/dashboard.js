/**
 * Dashboard.js - Cockpit Operacional
 * Chart.js Doughnut + UI Interactions
 */

document.addEventListener('DOMContentLoaded', () => {
    const data = window.dashboardData;
    const chartCanvas = document.getElementById('statusChart');
    const chartTotal = document.getElementById('chartTotal');
    const chartLegend = document.getElementById('chartLegend');

    if (!data || !chartCanvas) return;

    // Calculate total
    const total = data.values.reduce((a, b) => a + b, 0);
    if (chartTotal) chartTotal.textContent = total;

    // Create Doughnut Chart
    new Chart(chartCanvas, {
        type: 'doughnut',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.values,
                backgroundColor: data.colors,
                borderWidth: 0,
                hoverOffset: 8
            }]
        },
        options: {
            cutout: '75%',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // Custom legend
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: true,
                    boxWidth: 10,
                    boxHeight: 10,
                    boxPadding: 4,
                    callbacks: {
                        label: function (context) {
                            const value = context.parsed;
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return ` ${context.label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            },
            animation: {
                animateRotate: true,
                easing: 'easeOutQuart',
                duration: 800
            }
        }
    });

    // Render Custom Legend
    if (chartLegend && data.labels) {
        chartLegend.innerHTML = data.labels.map((label, i) => `
            <div class="d-flex align-items-center">
                <span class="rounded-circle me-2" style="width: 10px; height: 10px; background: ${data.colors[i]};"></span>
                <small class="text-muted">${label}: <strong>${data.values[i]}</strong></small>
            </div>
        `).join('');
    }
});

/**
 * Theme Change Listener (for Chart.js color updates)
 */
window.addEventListener('theme-changed', (e) => {
    // Chart.js auto-handles most colors, but we could refresh if needed
    console.log('Theme changed to:', e.detail.theme);
});
