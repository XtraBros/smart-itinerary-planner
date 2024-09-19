document.addEventListener("DOMContentLoaded", function() {
    let config;
    let map;
    let marker;
    let colHeaders;
    let deletedRows = [];
    let markers = [];
    let thumbnailURI;
    let mapClickHandler;
    let addLocationToggle;

    // Fetch the current config
    fetch('/get_config')
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
            thumbnailURI = data.GOOGLE_CLOUD_URI;
        });

    // Update the config
    document.getElementById('updateButton').addEventListener('click', function(e) {
        e.preventDefault();
        const formData = {};
        const inputs = document.querySelectorAll('#configForm input');
        inputs.forEach(function(input) {
            formData[input.name] = input.value;
        });

        fetch('/update_config', {
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
        }
    };

    // Load POI Data
    function loadPOIData() {
        fetch('/get_poi')
            .then(response => response.json())
            .then(data => {
                // Clear any existing markers from the map
                markers.forEach(marker => marker.remove());
                markers = [];
    
                // Add POIs to the map as markers
                data.forEach(poi => {
                    // create thumbnail url
                    const formattedPlaceName = poi.name.toLowerCase().replace(/\s+/g, '-');
                    const thumbnailUrl = `${thumbnailURI}${formattedPlaceName}.jpg`;
                    poi.thumbnail = thumbnailUrl || '/static/icons/default.png';
                    // Create a marker for each POI
                    const popup = new mapboxgl.Popup()
                        .setHTML(
                            `<strong>${poi.name}</strong><br>
                            <img src="${poi.thumbnail}" alt="${poi.name} thumbnail" style="width:100px;height:100px;"><br>
                            ${poi.description}<br>
                            Category: ${poi.category}<br>
                            Audience: ${poi.for}<br>
                            Hours: ${poi.operating_hours || "NA"} `
                        );

                    const marker = new mapboxgl.Marker()
                        .setLngLat([poi.longitude, poi.latitude]) // Longitude and Latitude of the POI
                        .setPopup(popup) // Add a popup with POI details and thumbnail
                        .addTo(map);
                    marker.getElement().addEventListener('click', () => {
                        populateForm(poi); // Call function to populate the form
                        document.getElementById("deletePOIButton").style.display = 'inline-block';
                    });
                    popup.on('close', () => {
                        clearForm(); // Call function to clear the form
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
    document.getElementById('savePOIButton').addEventListener('click', function(e) {
        e.preventDefault();
        showLoading();
        if (addLocationToggle){ //add new POI
            const form = document.getElementById('location-form'); // Get the form element
            const formData = new FormData(form);
            const poiData = {};
            formData.forEach((value, key) => poiData[key] = value);

            fetch('/add_poi', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(poiData)
            })
            .then(response => response.json())
            .then(response => {
                alert(response.message);
                form.reset();
                if (marker) {
                    marker.remove();
                    marker = null;
                }
            })
            .catch(error => {
                console.error('Error adding POI:', error);
                alert('Error adding POI');
            })
            .finally(() => {
                loadPOIData();
                hideLoading();
            });
        } else { // edit existing POI
            const form = document.getElementById('location-form'); // Get the form element
            const formData = new FormData(form);
            const poiData = {};
            formData.forEach((value, key) => poiData[key] = value);
            
            fetch('/edit_poi', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(poiData)
            })
            .then(response => response.json())
            .then(response => {
                alert(response.message);
                form.reset();
                if (marker) {
                    marker.remove();
                    marker = null;
                }
            })
            .catch(error => {
                console.error('Error editing POI:', error);
                alert('Error editing POI');
            })
            .finally(() => {
                loadPOIData();
                hideLoading();
            });
        }
        addLocationToggle = false;
        // Clear the form fields
        clearForm();
        if (marker) {
            marker.remove();
        }       
        // Remove the map click listener for adding new locations
        if (mapClickHandler) {
            map.off('click', mapClickHandler);
            mapClickHandler = null; // Clear the reference
        }
        // Hide the cancel button and restore the "add location" button
        document.getElementById('cancelLocationButton').style.display = 'none';
        // reload POI data or restore normal map behavior
        loadPOIData();
    });
    
    // Delete POI Button
    document.getElementById('deletePOIButton').addEventListener('click', function() {
        showLoading();
        // fetch delete endpoint to remove POI.
        const form = document.getElementById('location-form'); // Get the form element
        const poi_id = document.getElementById('poi-id').value;
        console.log(poi_id);
        fetch('/delete_poi', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({"id": poi_id})
        })
        .then(response => response.json())
        .then(response => {
            alert(response.message);
            form.reset();
            if (marker) {
                marker.remove();
                marker = null;
            }
        })
        .catch(error => {
            console.error('Error deleting POI:', error);
            alert('Error adding POI');
        })
        .finally(() => {
            loadPOIData();
            hideLoading();
        });
        document.getElementById('deletePOIButton').style.display = 'none';
    });
    // Handle CSV file upload
    document.getElementById('uploadCSVButton').addEventListener('click', function() {
        const fileInput = document.getElementById('uploadCSV');
        const file = fileInput.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const csvData = e.target.result;
                fetch('/upload_csv', {
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
    });
    // Add New Location button event listener
    document.getElementById('addLocationButton').addEventListener("click", function() {
        // Display cancel button
        document.getElementById('cancelLocationButton').style.display = 'inline-block';
        // Hide all existing markers
        markers.forEach(marker => marker.remove());

        // Enable 'Add Location' mode
        addLocationToggle = true;
        // Clear form data
        clearForm();

        // Define the click event handler function
        mapClickHandler = function(e) {
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
        };

        // Add the click event listener to the map
        map.on('click', mapClickHandler);
    });

    // Cancel Location button event listener
    document.getElementById('cancelLocationButton').addEventListener("click", function() {
        addLocationToggle = false;
        // Clear the form fields
        clearForm();
        if (marker) {
            marker.remove();
        }        // Remove the map click listener for adding new locations
        if (mapClickHandler) {
            map.off('click', mapClickHandler);
            mapClickHandler = null; // Clear the reference
        }

        // Hide the cancel button and restore the "add location" button
        document.getElementById('cancelLocationButton').style.display = 'none';

        // Reload POI data or restore normal map behavior
        loadPOIData();
    });
});

// Helper functions:
function populateForm(poi) {
    document.getElementById('poi-id').value = poi.id;
    document.getElementById('name').value = poi.name || '';
    document.getElementById('longitude').value = poi.longitude || '';
    document.getElementById('latitude').value = poi.latitude || '';
    document.getElementById('description').value = poi.description || 'NA';
    document.getElementById('category').value = poi.category || 'NA';
    document.getElementById('target_audience').value = poi.for || 'NA';
    document.getElementById('operating_hours').value = poi.operating_hours || 'NA';
    document.getElementById('thumbnail').value = poi.thumbnail || '';
}
// Function to clear the form fields
function clearForm() {
    document.getElementById('name').value = '';
    document.getElementById('longitude').value = '';
    document.getElementById('latitude').value = '';
    document.getElementById('description').value = '';
    document.getElementById('category').value = '';
    document.getElementById('target_audience').value = '';
    document.getElementById('operating_hours').value = '';
    document.getElementById('thumbnail').value = '';
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