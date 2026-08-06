/**
 * EduSphere Chart.js Configuration
 * ONE centralized, standardized theme configuration shared by every chart
 * in the app: Admin → Reports, Faculty → Analytics, Faculty Dashboard.
 *
 * No page/template should define its own chart colors, fonts, legend
 * position, grid styling, tooltip styling, padding, border radius, bar
 * thickness, doughnut cutout, or animation. Everything comes from here.
 */

// Application colors - Standardized palette (dataset fill colors; unrelated
// to text/label theming below)
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

// Chart instance registry for cleanup + live theme refresh
const chartInstances = {};

// Shared font family/weights - identical across every chart, every element
const CHART_FONT_FAMILY = "'Inter', system-ui, sans-serif";
const CHART_FONT_WEIGHT_REGULAR = '500';
const CHART_FONT_WEIGHT_BOLD = '600';

/**
 * LIGHT MODE
 * Titles:            #0F172A
 * Legend Labels:      #475569
 * Axis Labels:        #475569
 * Axis Tick Labels:   #64748B
 * Grid:               rgba(148,163,184,0.18)
 */
const LIGHT_THEME = {
    titleColor: '#0F172A',
    legendColor: '#475569',
    axisLabelColor: '#475569',
    axisTickColor: '#64748B',
    gridColor: 'rgba(148,163,184,0.18)',
    tooltipBg: '#FFFFFF',
    tooltipText: '#111827',
    tooltipBorder: '#E5E7EB'
};

/**
 * DARK MODE - unchanged design, only ensuring labels are legible/white.
 * Legend labels:  #FFFFFF
 * Axis labels:    rgba(255,255,255,0.92)
 * Tick labels:    rgba(255,255,255,0.82)
 * Grid:           rgba(255,255,255,0.12)
 */
const DARK_THEME = {
    titleColor: '#FFFFFF',
    legendColor: '#FFFFFF',
    axisLabelColor: 'rgba(255,255,255,0.92)',
    axisTickColor: 'rgba(255,255,255,0.82)',
    gridColor: 'rgba(255,255,255,0.12)',
    tooltipBg: '#1f2937',
    tooltipText: '#FFFFFF',
    tooltipBorder: '#374151'
};

/**
 * Get theme-aware chart configuration. This is the single source of truth
 * for title, legend, axis, tick, grid, and tooltip styling - every chart
 * in the app must be created through createBarChart/createDoughnutChart
 * (or getChartOptions directly) rather than defining its own options.
 *
 * @param {string} theme - Current theme ('light' or 'dark')
 * @returns {object} Chart.js options object
 */
function getChartOptions(theme = 'light') {
    const themeConfig = theme === 'dark' ? DARK_THEME : LIGHT_THEME;

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
        // Chart.js falls back to this root color for any element that
        // doesn't have an explicit color set - keeping it theme-correct
        // is a safety net on top of the explicit colors below.
        color: themeConfig.legendColor,
        plugins: {
            // Off by default (current charts use an HTML <h5> above the
            // canvas for titles, so this doesn't change layout) but fully
            // themed so any chart that turns it on inherits the same look.
            title: {
                display: false,
                color: themeConfig.titleColor,
                font: {
                    size: 15,
                    weight: CHART_FONT_WEIGHT_BOLD,
                    family: CHART_FONT_FAMILY
                },
                padding: { bottom: 16 }
            },
            legend: {
                display: true,
                position: 'bottom',
                labels: {
                    color: themeConfig.legendColor,
                    font: {
                        size: 13,
                        weight: CHART_FONT_WEIGHT_REGULAR,
                        family: CHART_FONT_FAMILY
                    },
                    padding: 20,
                    usePointStyle: true,
                    pointStyle: 'circle'
                }
            },
            tooltip: {
                backgroundColor: themeConfig.tooltipBg,
                titleColor: themeConfig.tooltipText,
                bodyColor: themeConfig.tooltipText,
                borderColor: themeConfig.tooltipBorder,
                borderWidth: 1,
                cornerRadius: 8,
                padding: 12,
                titleFont: {
                    size: 13,
                    weight: CHART_FONT_WEIGHT_BOLD,
                    family: CHART_FONT_FAMILY
                },
                bodyFont: {
                    size: 12,
                    family: CHART_FONT_FAMILY
                },
                displayColors: true,
                boxPadding: 4
            }
        },
        scales: {
            x: {
                display: true,
                title: {
                    display: false,
                    color: themeConfig.axisLabelColor,
                    font: {
                        size: 12,
                        weight: CHART_FONT_WEIGHT_REGULAR,
                        family: CHART_FONT_FAMILY
                    }
                },
                grid: {
                    display: true,
                    color: themeConfig.gridColor,
                    drawBorder: false
                },
                ticks: {
                    color: themeConfig.axisTickColor,
                    font: {
                        size: 11,
                        family: CHART_FONT_FAMILY
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
                display: true,
                title: {
                    display: false,
                    color: themeConfig.axisLabelColor,
                    font: {
                        size: 12,
                        weight: CHART_FONT_WEIGHT_REGULAR,
                        family: CHART_FONT_FAMILY
                    }
                },
                grid: {
                    color: themeConfig.gridColor,
                    drawBorder: false
                },
                ticks: {
                    color: themeConfig.axisTickColor,
                    font: {
                        size: 11,
                        family: CHART_FONT_FAMILY
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

    // Auto-calculate bar thickness based on data count (unchanged - do not
    // modify bar width/spacing behavior)
    let barThickness, maxBarThickness, categoryPercentage, barPercentage;

    if (dataCount === 1) {
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
                borderRadius: 6,
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
        cutout: '65%', // unchanged
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

    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }

    const options = getBarChartOptions(data.labels?.length || 1, theme);

    const chart = new Chart(canvas, {
        type: 'bar',
        data: data,
        options: options
    });

    chart._eduSphereType = 'bar';
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

    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }

    const options = getDoughnutChartOptions(theme);

    const chart = new Chart(canvas, {
        type: 'doughnut',
        data: data,
        options: options
    });

    chart._eduSphereType = 'doughnut';
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

    chart._eduSphereType = 'line';
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
 * Update all live chart instances with a new theme's colors, in place,
 * without destroying/recreating them. This is what keeps every chart in
 * sync with a light/dark toggle even when the page isn't reloaded - see
 * the 'themeChanged' listener registered at the bottom of this file.
 * @param {string} theme - New theme ('light' or 'dark')
 */
function updateChartTheme(theme) {
    Object.keys(chartInstances).forEach(canvasId => {
        const chart = chartInstances[canvasId];
        if (!chart) return;

        const dataCount = chart.data?.labels?.length || 1;
        let newOptions;
        if (chart._eduSphereType === 'bar') {
            newOptions = getBarChartOptions(dataCount, theme);
        } else if (chart._eduSphereType === 'doughnut') {
            newOptions = getDoughnutChartOptions(theme);
        } else {
            newOptions = getChartOptions(theme);
        }

        // Replace the theme-relevant option branches wholesale so no stale
        // color from the previous theme lingers.
        chart.options.color = newOptions.color;
        chart.options.plugins.title = newOptions.plugins.title;
        chart.options.plugins.legend = newOptions.plugins.legend;
        chart.options.plugins.tooltip = newOptions.plugins.tooltip;
        if (newOptions.scales) {
            chart.options.scales = newOptions.scales;
        }

        chart.update();
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

// Keep every chart in sync with the theme toggle automatically - this is
// what makes the theme "centralized": no template needs to listen for
// theme changes itself or re-create its charts.
window.addEventListener('themeChanged', function (e) {
    const newTheme = (e && e.detail && e.detail.theme) ||
        document.documentElement.getAttribute('data-theme') || 'light';
    updateChartTheme(newTheme);
});
