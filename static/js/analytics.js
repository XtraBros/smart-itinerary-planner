// analytics.js
let userActivityChartInstance = null;
let poiPieChartInstance = null;
function initAnalytics() {
    const hourLabels = Array.from({ length: 24 }, (_, i) => `${i}:00`);
    const userActivityData = [
      1, 0, 0, 0, 0, 2, 4, 10, 12, 15, 14, 12,
      9, 6, 4, 5, 8, 11, 13, 10, 6, 3, 2, 1
    ];
  
    // === User Activity Bar Chart ===
    new Chart(document.getElementById("userActivityChart"), {
      type: 'bar',
      data: {
        labels: hourLabels,
        datasets: [{
          label: 'User Activity (by Hour)',
          data: userActivityData,
          backgroundColor: 'rgba(54, 162, 235, 0.6)',
          borderColor: 'rgba(54, 162, 235, 1)',
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 }
          }
        },
        plugins: {
          title: {
            display: true,
            text: 'Number of Users Per Hour'
          },
          legend: { display: false }
        }
      }
    });
  
    // === Load Mapbox Token First ===
    fetch("/config")
      .then((res) => res.json())
      .then((data) => {
        Plotly.setPlotConfig({ mapboxAccessToken: data.config.MAPBOX_ACCESS_TOKEN });
        console.log("Calling fetchAndRenderPOIData now...");
        fetchAndRenderPOIData();
      })
      .catch((err) => {
        console.error("Failed to fetch config:", err);
      });
  
    function fetchAndRenderPOIData() {
      fetch("/api/pois")
        .then((res) => res.json())
        .then((poiData) => {  
          const labels = poiData.map((p) => p.name);
          const clicks = poiData.map((p) => p.clicks ?? Math.floor(Math.random() * 100) + 1);
  
          // === PIE CHART ===
          new Chart(document.getElementById("poiPieChart"), {
            type: 'pie',
            data: {
              labels: labels,
              datasets: [{
                data: clicks,
                backgroundColor: [
                  "#ff6384", "#36a2eb", "#ffce56", "#4bc0c0",
                  "#9966ff", "#ff9f40", "#c9cbcf", "#66bb6a",
                  "#e67e22", "#3498db", "#9b59b6", "#2ecc71"
                ]
              }]
            },
            options: {
              responsive: true,
              plugins: {
                title: {
                  display: true,
                  text: 'Click Share per POI'
                }
              }
            }
          });
  
          // === HEATMAP ===
          const latitudes = poiData.map(p => p.latitude);
          const longitudes = poiData.map(p => p.longitude);
          const names = poiData.map(p => p.name);
  
          const heatmap = [{
            type: "densitymapbox",
            lat: latitudes,
            lon: longitudes,
            z: clicks,
            radius: 30,
            text: names,
            hoverinfo: 'text+z',
            colorscale: "YlOrRd"
          }];
  
          const layout = {
            mapbox: {
              style: "carto-positron",
              center: { lat: 1.30, lon: 103.84 },
              zoom: 11
            },
            margin: { t: 0, b: 0, l: 0, r: 0 },
            height: 400
          };
  
          Plotly.newPlot("poiHeatmap", heatmap, layout, { responsive: true });
        })
        .catch((err) => {
          console.error("Failed to load POI data:", err);
        });
    }

  // Save a replot function on window (optional)
    window.replotAnalytics = () => {
        if (userActivityChartInstance) userActivityChartInstance.resize();
        if (poiPieChartInstance) poiPieChartInstance.resize();
        Plotly.Plots.resize(document.getElementById("poiHeatmap"));
    }
}