document.addEventListener("DOMContentLoaded", () => {

    /* ============================================================
       LINE CHART HELPER (existing code, unchanged)
    ============================================================ */

    function createChart(
        apiUrl,
        elementId,
        label,
        yTitle,
        lineColor = "rgba(54,162,235,1)",
        pointColor = "rgba(54,162,235,1)"
    ) {
        fetch(apiUrl)
            .then(res => res.json())
            .then(data => {
                const labels = Array.from({ length: 30 }, (_, i) => {
                    const date = new Date();
                    date.setDate(date.getDate() - (29 - i));
                    return `${date.getMonth() + 1}/${date.getDate()}`;
                });

                const skipped = (ctx, value) =>
                    ctx.p0.skip || ctx.p1.skip ? value : undefined;

                const ctx = document.getElementById(elementId).getContext("2d");

                const chart = new Chart(ctx, {
                    type: "line",
                    data: {
                        labels,
                        datasets: [{
                            label,
                            data,
                            fill: false,
                            spanGaps: true,
                            borderColor: lineColor,
                            pointBackgroundColor: pointColor,
                            pointBorderColor: pointColor,
                            segment: {
                                borderColor: ctx => skipped(ctx, "rgba(0,0,0,0.2)"),
                                borderDash: ctx => skipped(ctx, [6, 6]),
                            },
                        }],
                    },
                    options: {
                        plugins: {
                            title: { display: false },
                            datalabels: { display: false },
                        },
                        radius: 5,
                        interaction: { intersect: false },
                        scales: {
                            x: { display: true },
                            y: {
                                beginAtZero: true,
                                title: { display: true, text: yTitle },
                                ticks: {
                                    callback: value =>
                                        Number.isInteger(value) ? value : null,
                                },
                            },
                        },
                    },
                });

                window[`myChart_${elementId}`] = chart;
            })
            .catch(err => console.error(`Error fetching ${label} data:`, err));
    }

    /* ============================================================
       BAR CHART HELPER (NEW)
    ============================================================ */

    function createBarChartFromApi(
        apiUrl,
        elementId,
        label = "Errors by type",
        yTitle = "Number of errors"
    ) {
        fetch(apiUrl)
            .then(res => res.json())
            .then(data => {
                if (!Array.isArray(data) || data.length === 0) {
                    console.warn("No error data available");
                    return;
                }

                // Sort by count (descending)
                data.sort((a, b) => b.count - a.count);

                const labels = data.map(item => item.type);
                const counts = data.map(item => item.count);

                // Dynamic colors
                const colors = labels.map(
                    (_, i) => `hsl(${(i * 45) % 360}, 70%, 60%)`
                );

                const ctx = document.getElementById(elementId).getContext("2d");

                const chart = new Chart(ctx, {
                    type: "bar",
                    data: {
                        labels,
                        datasets: [{
                            label,
                            data: counts,
                            backgroundColor: colors,
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: yTitle
                                }
                            },
                            x: {
                                ticks: {
                                    maxRotation: 45,
                                    minRotation: 30
                                }
                            }
                        },
                        plugins: {
                            legend: { display: true },
                            tooltip: {
                                callbacks: {
                                    label: ctx => ` ${ctx.parsed.y} errors`
                                }
                            }
                        }
                    }
                });

                window[`myChart_${elementId}`] = chart;
            })
            .catch(err => console.error("Error loading error bar chart:", err));
    }

    /* ============================================================
       CREATE LINE CHARTS (existing)
    ============================================================ */

    createChart(
        window.URL_PREFIX + "/api/notification_count",
        "lineChartNotif",
        "Documents received (last 30 days)",
        "Number of Notifications",
        "rgba(255, 159, 64, 1)",
        "rgba(255, 205, 86, 1)"
    );

    createChart(
        window.URL_PREFIX + "/api/mention_count",
        "lineChartMention",
        "Mentions received (last 30 days)",
        "Number of Mentions",
        "rgba(75, 192, 192, 1)",
        "rgba(75, 192, 192, 1)"
    );

    createChart(
        window.URL_PREFIX + "/api/accepted_count",
        "lineChartMentionAccepted",
        "Mentions accepted (last 30 days)",
        "Number of Mentions",
        "rgba(54, 162, 235, 1)",
        "rgba(54, 162, 235, 1)"
    );

    createChart(
        window.URL_PREFIX + "/api/rejected_count",
        "lineChartMentionRejected",
        "Mentions rejected (last 30 days)",
        "Number of Mentions",
        "rgba(255, 99, 132, 1)",
        "rgba(255, 99, 132, 1)"
    );

    /* ============================================================
       CREATE BAR CHART (NEW)
    ============================================================ */

    createBarChartFromApi(
        window.URL_PREFIX + "/api/document_failed_count",
        "barChartErrors",
        "Errors by type",
        "Number of errors"
    );

});
