$(document).ready(function() {
    // Fetch the current config
    $.get('/get-config', function(data) {
        for (const key in data) {
            if (data.hasOwnProperty(key)) {
                $('#configForm').append(
                    `<label for="${key}">${key}:</label>
                    <input type="text" id="${key}" name="${key}" value="${data[key]}" required><br><br>`
                );
            }
        }
    });

    // Update the config
    $('#updateButton').on('click', function(e) {
        e.preventDefault();
        const formData = {};
        $('#configForm').find('input').each(function() {
            formData[$(this).attr('name')] = $(this).val();
        });

        $.ajax({
            url: '/update-config',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(formData),
            success: function(response) {
                alert(response.message);
            },
            error: function(error) {
                alert('Error updating config');
            }
        });
    });

    // Open tabs
    window.openTab = function(tabName) {
        $('.tab-content').removeClass('active');
        $('#' + tabName).addClass('active');
        if (tabName === 'poi') {
            loadPOIData();
        }
    };

    let hot; // Handsontable instance

    // Load POI Data
    function loadPOIData() {
        $.get('/get-poi', function(data) {
            const container = document.getElementById('poiTable');
            if (hot) {
                hot.destroy();
            }
    
            // Extract column headers and column configuration from the data
            const colHeaders = Object.keys(data[0]);
            const columns = colHeaders.map(header => ({
                data: header,
                readOnly: header === 'id'  // Assuming 'id' should be read-only
            }));
    
            hot = new Handsontable(container, {
                data: data,
                colHeaders: colHeaders,
                columns: columns,
                rowHeaders: true,
                contextMenu: true,
                minSpareRows: 1,
                licenseKey: 'non-commercial-and-evaluation' // For non-commercial use
            });
        }, 'json');
    }
    
    // Save POI Data
    $('#savePOIButton').on('click', function() {
        const data = hot.getData();
        $.ajax({
            url: '/save-poi',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(response) {
                alert(response.message);
            },
            error: function(error) {
                alert('Error saving POI data');
            }
        });
    });
    // Handle CSV file upload
    $('#uploadCSVButton').on('click', function() {
        const fileInput = document.getElementById('uploadCSV');
        const file = fileInput.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const csvData = e.target.result;
                $.ajax({
                    url: '/upload-csv',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ csv: csvData }),
                    success: function(response) {
                        alert(response.message);
                        loadPOIData(); // Reload the POI data
                    },
                    error: function(xhr) {
                        const errorMessage = xhr.responseJSON ? xhr.responseJSON.message : 'Error uploading CSV';
                        alert(errorMessage);
                    }
                });
            };
            reader.readAsText(file);
        } else {
            alert('Please select a CSV file to upload');
        }
    });
   // Hamburger menu functionality
   $('#hamburgerMenu').on('click', function() {
        $('.sidebar').addClass('show');
        document.getElementById("sidebar").style.width = "250px";
        document.getElementById("mainContent").classList.add('shift-right');
    });

    $('#closeSidebar').on('click', function() {
        $('.sidebar').removeClass('show');
        document.getElementById("mainContent").classList.remove('shift-right');
    });
});
