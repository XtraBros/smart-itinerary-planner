document.addEventListener("DOMContentLoaded", function() {
    let config;
    let map;
    let marker;
    let colHeaders;
    let deletedRows = [];
    let markers = [];

    // Fetch the current config
    fetch('/get-config')
        .then(response => response.json())
        .then(data => {
            config = data;
            mapboxgl.accessToken = data.MAPBOX_ACCESS_TOKEN;
            map = new mapboxgl.Map({
                container: 'map',
                style: 'mapbox://styles/mapbox/streets-v12',
                center: [103.8198, 1.2528],
                zoom: 15
            });
            for (const key in data) {
                if (data.hasOwnProperty(key)) {
                    const label = document.createElement('label');
                    label.setAttribute('for', key);
                    label.textContent = `${key}:`;
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.id = key;
                    input.name = key;
                    input.value = data[key];
                    input.required = true;
                    document.getElementById('configForm').appendChild(label);
                    document.getElementById('configForm').appendChild(input);
                    document.getElementById('configForm').appendChild(document.createElement('br'));
                    document.getElementById('configForm').appendChild(document.createElement('br'));
                }
            }
        });

    // Update the config
    document.getElementById('updateButton').addEventListener('click', function(e) {
        e.preventDefault();
        const formData = {};
        const inputs = document.querySelectorAll('#configForm input');
        inputs.forEach(function(input) {
            formData[input.name] = input.value;
        });

        fetch('/update-config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        })
        .then(response => response.json())
        .then(response => {
            alert(response.message);
        })
        .catch(error => {
            alert('Error updating config');
        });
    });

    // Open tabs
    window.openTab = function(tabName) {
        document.querySelectorAll('.tab-content').forEach(function(tab) {
            tab.classList.remove('active');
        });
        document.getElementById(tabName).classList.add('active');
        if (tabName === 'poi') {
            loadPOIData();
        } else if (tabName === 'addLocation') {
            mapLocationClick();
        }
    };

    // Load POI Data
    function loadPOIData() {
        fetch('/get-poi')
            .then(response => response.json())
            .then(data => {
                // Clear any existing markers from the map
                markers.forEach(marker => marker.remove());
                markers = [];
    
                // Add POIs to the map as markers
                data.forEach(poi => {
                    // Create a marker for each POI
                    const marker = new mapboxgl.Marker()
                        .setLngLat([poi.longitude, poi.latitude]) // Set longitude and latitude
                        .setPopup(new mapboxgl.Popup().setHTML(
                            `<strong>${poi.name}</strong><br>
                            ${poi.description}<br>
                            Category: ${poi.category}<br>
                            Audience: ${poi.target_audience}<br>
                            Hours: ${poi.operating_hours}`
                        )) // Add a popup with POI details
                        .addTo(map);
                    marker.getElement().addEventListener('click', () => {
                        populateForm(poi); // Call function to populate the form
                    });
                    // Push the marker to the array to manage markers later (for clearing or updating)
                    markers.push(marker);
                });
            })
            .catch(error => {
                console.error('Error loading POI data:', error);
                alert('Failed to load POI data');
            });
    }

    // Add event listener for the save button
    document.getElementById('savePOIButton').addEventListener('click', function() {
        const data = hot.getData();
        const updatedPOIs = data.map((row, index) => {
            const poi = {
                id: index,
                ...row.reduce((obj, value, colIndex) => {
                    obj[colHeaders[colIndex]] = value;
                    return obj;
                }, {})
            };
            return poi;
        });
    
        const hasDeletions = deletedRows.length > 0;
        const hasChanges = hot.getPlugin('undoRedo').isUndoAvailable();
    
        if (!hasDeletions && !hasChanges) {
            alert('No changes to save');
            return;
        }
    
        showLoading();
    
        // Function to handle deletions
        function handleDeletions() {
            if (hasDeletions) {
                return fetch('/delete-poi', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(deletedRows)
                })
                .then(response => response.json())
                .then(deleteResponse => {
                    if (!deleteResponse.success) {
                        throw new Error(deleteResponse.message || 'Error deleting POIs');
                    }
                });
            } else {
                return Promise.resolve();
            }
        }
    
        // Function to handle edits
        function handleEdits() {
            if (hasChanges) {
                return fetch('/edit-poi', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(updatedPOIs)
                })
                .then(response => response.json())
                .then(editResponse => {
                    if (!editResponse.success) {
                        throw new Error(editResponse.message || 'Error updating POIs');
                    }
                });
            } else {
                return Promise.resolve();
            }
        }
    
        // First handle deletions, then handle edits
        handleDeletions()
        .then(handleEdits)
        .then(() => {
            alert('Changes saved successfully');
        })
        .catch(error => {
            console.error(error);
            alert(error.message);
        })
        .finally(() => {
            hideLoading();
            deletedRows = []; // Clear the deletedRows list after processing
        });
    });    
    
    // Handle CSV file upload
    document.getElementById('uploadCSVButton').addEventListener('click', function() {
        const fileInput = document.getElementById('uploadCSV');
        const file = fileInput.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const csvData = e.target.result;
                fetch('/upload-csv', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ csv: csvData })
                })
                .then(response => response.json())
                .then(response => {
                    alert(response.message);
                    loadPOIData(); // Reload the POI data
                })
                .catch(xhr => {
                    const errorMessage = xhr.responseJSON ? xhr.responseJSON.message : 'Error uploading CSV';
                    alert(errorMessage);
                });
            };
            reader.readAsText(file);
        } else {
            alert('Please select a CSV file to upload');
        }
    });

    // Hamburger menu functionality
    document.getElementById('hamburgerMenu').addEventListener('click', function() {
        document.querySelector('.sidebar').classList.add('show');
        document.getElementById("sidebar").style.width = "250px";
        document.getElementById("mainContent").classList.add('shift-right');
    });

    document.getElementById('closeSidebar').addEventListener('click', function() {
        document.querySelector('.sidebar').classList.remove('show');
        document.getElementById("mainContent").classList.remove('shift-right');
    });
    
    // Update the marker when latitude or longitude fields are changed
    document.getElementById('latitude').addEventListener('change', updateMarker);
    document.getElementById('longitude').addEventListener('change', updateMarker);
    
    // Handle add POI
    document.getElementById("location-form").addEventListener("submit", function(e) {
        e.preventDefault();
        showLoading();

        const formData = new FormData(this);
        const poiData = {};
        formData.forEach((value, key) => poiData[key] = value);

        fetch('/add-poi', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(poiData)
        })
        .then(response => {
            if (!response.ok) {
                // If the response is not ok, handle the error
                return response.json().then(errorResponse => {
                    throw new Error(errorResponse.message);
                });
            }
            return response.json();
        })
        .then(response => {
            alert(response.message);
            document.getElementById("location-form").reset();  // Reset the form
            if (marker) {
                marker.remove();
                marker = null;
            }
        })
        .catch(error => {
            console.error('Error adding POI:', error);
            alert(error.message);  // Show the specific error message from the server
        })
        .finally(() => {
            hideLoading();
        });
    });
});

// Helper functions:
function populateForm(poi) {
    document.getElementById('name').value = poi.name || '';
    document.getElementById('longitude').value = poi.longitude || '';
    document.getElementById('latitude').value = poi.latitude || '';
    document.getElementById('description').value = poi.description || '';
    document.getElementById('category').value = poi.category || '';
    document.getElementById('target_audience').value = poi.for || '';
    document.getElementById('operating_hours').value = poi.operating_hours || '';
}

function isWithinBounds(coordinates) {
    const [minLng, minLat] = [103.77861059, 1.39813758];
    const [maxLng, maxLat] = [103.79817716, 1.41032361];
    return coordinates.lng >= minLng && coordinates.lng <= maxLng &&
           coordinates.lat >= minLat && coordinates.lat <= maxLat;
}

// Show loading overlay
function showLoading() {
    document.getElementById('loading-overlay').classList.add('visible');
}

// Hide loading overlay
function hideLoading() {
    document.getElementById('loading-overlay').classList.remove('visible');
}

function mapLocationClick() {
    map.on('click', function(e) {
        const coordinates = e.lngLat;
        document.getElementById('latitude').value = coordinates.lat.toFixed(6);
        document.getElementById('longitude').value = coordinates.lng.toFixed(6);

        // Remove the existing marker if there is one
        if (marker) {
            marker.remove();
        }
        // Add a new marker
        marker = new mapboxgl.Marker()
            .setLngLat(coordinates)
            .addTo(map);

    });
}

function updateMarker() {
    const lat = parseFloat(document.getElementById('latitude').value);
    const lng = parseFloat(document.getElementById('longitude').value);
    const coordinates = new mapboxgl.LngLat(lng, lat);

    if (isNaN(lat) || isNaN(lng)) {
        alert('Please enter valid coordinates.');
        return;
    }

    if (isWithinBounds(coordinates)) {
        // Set the map center to the new coordinates
        map.setCenter(coordinates);

        // Remove the existing marker if there is one
        if (marker) {
            marker.remove();
        }

        // Add a new marker
        marker = new mapboxgl.Marker()
            .setLngLat(coordinates)
            .addTo(map);
    } else {
        alert(`Coordinates are out of bounds. Please enter within the bounds:
            Longitude: ${bounds[0][0]} to ${bounds[1][0]}, 
            Latitude: ${bounds[0][1]} to ${bounds[1][1]}`);
    }
}