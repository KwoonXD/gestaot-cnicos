document.addEventListener('DOMContentLoaded', function () {
    const styles = getComputedStyle(document.documentElement);
    const primaryColor = styles.getPropertyValue('--bs-primary').trim();
    const successColor = styles.getPropertyValue('--bs-success').trim();
    const warningColor = styles.getPropertyValue('--bs-warning').trim();
    const infoColor = styles.getPropertyValue('--bs-info').trim();
    const dangerColor = styles.getPropertyValue('--bs-danger').trim();
    const secondaryColor = styles.getPropertyValue('--bs-secondary').trim();

    // Helper to add opacity
    function hexToRgba(hex, alpha) {
        // Handle hex with or without #
        hex = hex.replace('#', '');
        if (hex.length === 3) {
            hex = hex.split('').map(char => char + char).join('');
        }
        if (hex.length !== 6) return `rgba(0,0,0,${alpha})`; // Fallback

        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    // --- 1. Gráfico de Evolução (Linha/Barra Mista) ---
    fetch('/api/dashboard/evolucao')
        .then(r => r.json())
        .then(data => {
            const ctx = document.getElementById('evolutionChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Custo Total (R$)',
                            data: data.custos,
                            type: 'line',
                            borderColor: primaryColor,
                            backgroundColor: hexToRgba(primaryColor, 0.05),
                            borderWidth: 2,
                            yAxisID: 'y',
                            tension: 0.3,
                            fill: true,
                            pointRadius: 3
                        },
                        {
                            label: 'Volume (Qtd)',
                            data: data.volume,
                            type: 'bar',
                            backgroundColor: successColor,
                            borderRadius: 4,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { type: 'linear', display: true, position: 'left', beginAtZero: true, grid: { borderDash: [2, 2] } },
                        y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false }, beginAtZero: true },
                        x: { grid: { display: false } }
                    },
                    plugins: { legend: { display: true, position: 'bottom' } }
                }
            });
        });

    // --- 2. Top Técnicos HE (Barra Horizontal) ---
    fetch('/api/dashboard/top_tecnicos_he')
        .then(r => r.json())
        .then(data => {
            const ctx = document.getElementById('topTecnicosChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                indexAxis: 'y', // Horizontal
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'Valor HE (R$)',
                        data: data.valores,
                        backgroundColor: dangerColor,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { borderDash: [2, 2] } },
                        y: { grid: { display: false } }
                    }
                }
            });
        });

    // --- 3. Top Técnicos Volume (Doughnut) ---
    fetch('/api/dashboard/top_tecnicos_volume')
        .then(r => r.json())
        .then(data => {
            const ctx = document.getElementById('topVolumeChart').getContext('2d');
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.valores,
                        backgroundColor: [primaryColor, successColor, infoColor, warningColor, secondaryColor],
                        hoverOffset: 4,
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '70%',
                    plugins: {
                        legend: { position: 'right', labels: { boxWidth: 10, usePointStyle: true } }
                    }
                }
            });
        });

    // --- 4. Status dos Chamados (Doughnut) ---
    const statusCtx = document.getElementById('chartChamadosStatus');
    if (statusCtx) {
        new Chart(statusCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Concluído', 'Pendente', 'Em Andamento', 'Cancelado'],
                datasets: [{
                    data: [65, 20, 10, 5],
                    backgroundColor: [successColor, warningColor, primaryColor, dangerColor],
                    borderWidth: 0,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                cutout: '60%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, padding: 12, font: { size: 11 } }
                    }
                }
            }
        });
    }
});
