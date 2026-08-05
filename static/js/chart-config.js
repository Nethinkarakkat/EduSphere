/**
 * EduSphere Chart.js Configuration
 * Reusable theme configuration for all charts across the application
 */

// Application colors - Standardized palette
const CHART_COLORS = {
    primary: '#6366F1',
    primaryLight: 'rgba(99, 102, 241, 0.2)',
    primaryDark: 'rgba(99, 102, 241, 0.8)',
    success: '#10B981',
    successLight: 'rgba(16, 185, 129, 0.2)',
    successDark: 'rgba(16, 185, 129, 0.8)',
    danger: '#EF4444',
    dangerLight: 'rgba(239, 68, 68, 0.2)',
    dangerDark: 'rgba(239, 68, 68, 0.8)',
    warning: '#F59E0B',
    warningLight: 'rgba(245, 158, 11, 0.2)',
    warningDark: 'rgba(245, 158, 11, 0.8)',
    info: '#3B82F6',
    infoLight: 'rgba(59, 130, 246, 0.2)',
    infoDark: 'rgba(59, 130, 246, 0.8)',
    purple: '#8B5CF6',
    purpleLight: 'rgba(139, 92, 246, 0.2)',
    purpleDark: 'rgba(139, 92, 246, 0.8)'
};

// Chart instance registry for cleanup
const chartInstances = {};

/**
 * Get theme-aware chart configuration
 * @param {string} theme - Current theme ('light' or 'dark')
 * @returns {object} Chart.js options object
 */
function getChartOptions(theme = 'light') {
    const isDark = theme === 'dark';
    
    return {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
            padding: 20
        },
        animation: {
            duration: 800,
            easing: 'easeInOutQuart'
        },
        plugins: {
            legend: {
                display: true,
                position: 'bottom',
                labels: {
                    color: isDark ? 'rgba(255,255,255,0.92)' : 'rgba(0,0,0,0.82)',
                    font: {
                        size: 13,
                        weight: '500',
                        family: "'Inter', system-ui, sans-serif"
                    },
                    padding: 20,
                    usePointStyle: true,
                    pointStyle: 'circle'
                }
            },
            tooltip: {
                backgroundColor: isDark ? '#1f2937' : '#FFFFFF',
                titleColor: isDark ? '#FFFFFF' : '#111827',
                bodyColor: isDark ? '#FFFFFF' : '#111827',
                borderColor: isDark ? '#374151' : '#E5E7EB',
                borderWidth: 1,
                cornerRadius: 8,
                padding: 12,
                titleFont: {
                    size: 13,
                    weight: '600',
                    family: "'Inter', system-ui, sans-serif"
                },
                bodyFont: {
                    size: 12,
                    family: "'Inter', system-ui, sans-serif"
                },
                displayColors: true,
                boxPadding: 4
            }
        },
        scales: {
            x: {
                grid: {
                    display: false
                },
                ticks: {
                    color: isDark ? 'rgba(255,255,255,0.82)' : 'rgba(0,0,0,0.65)',
                    font: {
                        size: 11,
                        family: "'Inter', system-ui, sans-serif"
                    },
                    maxRotation: 0,
                    minRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 10
                },
                border: {
                    display: false
                }
            },
            y: {
                grid: {
                    color: isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.08)',
                    drawBorder: false
                },
                ticks: {
                    color: isDark ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.65)',
                    font: {
                        size: 11,
                        family: "'Inter', system-ui, sans-serif"
                    },
                    padding: 10
                },
                border: {
                    display: false
                },
                beginAtZero: true
            }
        }
    };
}

/**
 * Get bar chart specific options
 * @param {number} dataCount - Number of data points for auto-sizing bars
 * @param {string} theme - Current theme
 * @returns {object} Bar chart options
 */
function getBarChartOptions(dataCount = 1, theme = 'light') {
    const baseOptions = getChartOptions(theme);
    
    // Auto-calculate bar thickness based on data count
    let barThickness, maxBarThickness, categoryPercentage, barPercentage;
    
    if (dataCount === 1) {
        // Single bar - make it wider
        barThickness = 80;
        maxBarThickness = 60;
        categoryPercentage = 0.5;
        barPercentage = 0.6;
    } else if (dataCount <= 2) {
        barThickness = 60;
        maxBarThickness = 60;
        categoryPercentage = 0.6;
        barPercentage = 0.7;
    } else if (dataCount <= 5) {
        barThickness = 50;
        maxBarThickness = 60;
        categoryPercentage = 0.7;
        barPercentage = 0.8;
    } else if (dataCount <= 10) {
        barThickness = 40;
        maxBarThickness = 60;
        categoryPercentage = 0.8;
        barPercentage = 0.85;
    } else {
        barThickness = 30;
        maxBarThickness = 60;
        categoryPercentage = 0.85;
        barPercentage = 0.9;
    }
    
    return {
        ...baseOptions,
        datasets: {
            bar: {
                barThickness: barThickness,
                maxBarThickness: maxBarThickness,
                categoryPercentage: categoryPercentage,
                barPercentage: barPercentage,
                borderRadius: 8,
                borderSkipped: false
            }
        }
    };
}

/**
 * Get doughnut/pie chart specific options
 * @param {string} theme - Current theme
 * @returns {object} Doughnut chart options
 */
function getDoughnutChartOptions(theme = 'light') {
    const baseOptions = getChartOptions(theme);
    
    return {
        ...baseOptions,
        cutout: '65%',
        plugins: {
            ...baseOptions.plugins,
            legend: {
                ...baseOptions.plugins.legend,
                position: 'bottom',
                labels: {
                    ...baseOptions.plugins.legend.labels,
                    padding: 15,
                    usePointStyle: true,
                    pointStyle: 'circle',
                    font: {
                        ...baseOptions.plugins.legend.labels.font,
                        size: 12
                    }
                }
            }
        },
        elements: {
            arc: {
                borderWidth: 0,
                borderRadius: 4
            }
        }
    };
}

/**
 * Create a bar chart with theme configuration
 * @param {string} canvasId - Canvas element ID
 * @param {object} data - Chart.js data object
 * @param {string} theme - Current theme
 * @returns {Chart} Chart instance
 */
function createBarChart(canvasId, data, theme = 'light') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`Canvas element with ID '${canvasId}' not found`);
        return null;
    }
    
    // Destroy existing chart instance
    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }
    
    const options = getBarChartOptions(data.labels?.length || 1, theme);
    
    const chart = new Chart(canvas, {
        type: 'bar',
        data: data,
        options: options
    });
    
    chartInstances[canvasId] = chart;
    return chart;
}

/**
 * Create a doughnut chart with theme configuration
 * @param {string} canvasId - Canvas element ID
 * @param {object} data - Chart.js data object
 * @param {string} theme - Current theme
 * @returns {Chart} Chart instance
 */
function createDoughnutChart(canvasId, data, theme = 'light') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`Canvas element with ID '${canvasId}' not found`);
        return null;
    }
    
    // Destroy existing chart instance
    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }
    
    const options = getDoughnutChartOptions(theme);
    
    const chart = new Chart(canvas, {
        type: 'doughnut',
        data: data,
        options: options
    });
    
    chartInstances[canvasId] = chart;
    return chart;
}

/**
 * Create a line chart with theme configuration
 * @param {string} canvasId - Canvas element ID
 * @param {object} data - Chart.js data object
 * @param {string} theme - Current theme
 * @returns {Chart} Chart instance
 */
function createLineChart(canvasId, data, theme = 'light') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`Canvas element with ID '${canvasId}' not found`);
        return null;
    }
    
    // Destroy existing chart instance
    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }
    
    const options = getChartOptions(theme);
    
    const chart = new Chart(canvas, {
        type: 'line',
        data: data,
        options: {
            ...options,
            elements: {
                line: {
                    tension: 0.3,
                    borderWidth: 3
                },
                point: {
                    radius: 4,
                    hoverRadius: 6
                }
            }
        }
    });
    
    chartInstances[canvasId] = chart;
    return chart;
}

/**
 * Destroy a specific chart instance
 * @param {string} canvasId - Canvas element ID
 */
function destroyChart(canvasId) {
    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
        delete chartInstances[canvasId];
    }
}

/**
 * Destroy all chart instances
 */
function destroyAllCharts() {
    Object.keys(chartInstances).forEach(canvasId => {
        destroyChart(canvasId);
    });
}

/**
 * Update all charts with new theme
 * @param {string} theme - New theme ('light' or 'dark')
 */
function updateChartTheme(theme) {
    Object.values(chartInstances).forEach(chart => {
        if (chart) {
            const newOptions = getChartOptions(theme);
            
            // Update colors based on chart type
            if (chart.config.type === 'bar') {
                const barOptions = getBarChartOptions(chart.data.labels?.length || 1, theme);
                Object.assign(chart.options, barOptions);
            } else if (chart.config.type === 'doughnut' || chart.config.type === 'pie') {
                const doughnutOptions = getDoughnutChartOptions(theme);
                Object.assign(chart.options, doughnutOptions);
            } else {
                Object.assign(chart.options, newOptions);
            }
            
            chart.update();
        }
    });
}

/**
 * Show empty state for chart
 * @param {string} canvasId - Canvas element ID
 * @param {string} message - Optional custom message
 */
function showChartEmptyState(canvasId, message = 'No data available') {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
        canvas.style.display = 'none';
        
        // Check if empty state element exists
        let emptyState = document.getElementById(`${canvasId}-empty`);
        if (!emptyState) {
            emptyState = document.createElement('div');
            emptyState.id = `${canvasId}-empty`;
            emptyState.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--muted);padding:40px;';
            emptyState.innerHTML = `
                <i class="bi bi-bar-chart" style="font-size:48px;margin-bottom:12px;opacity:0.5;"></i>
                <div style="font-size:14px;">${message}</div>
            `;
            canvas.parentNode.appendChild(emptyState);
        } else {
            emptyState.style.display = 'flex';
        }
    }
}

/**
 * Hide empty state for chart
 * @param {string} canvasId - Canvas element ID
 */
function hideChartEmptyState(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
        canvas.style.display = 'block';
        
        const emptyState = document.getElementById(`${canvasId}-empty`);
        if (emptyState) {
            emptyState.style.display = 'none';
        }
    }
}

// Export functions for global use
window.ChartConfig = {
    colors: CHART_COLORS,
    getOptions: getChartOptions,
    getBarOptions: getBarChartOptions,
    getDoughnutOptions: getDoughnutChartOptions,
    createBar: createBarChart,
    createDoughnut: createDoughnutChart,
    createLine: createLineChart,
    destroy: destroyChart,
    destroyAll: destroyAllCharts,
    updateTheme: updateChartTheme,
    showEmpty: showChartEmptyState,
    hideEmpty: hideChartEmptyState
};
