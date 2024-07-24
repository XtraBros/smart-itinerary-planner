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
    
            // Drop the 'id' column from data
            const filteredData = data.map(row => {
                const { id, ...rest } = row;
                return rest;
            });

            // Extract column headers and column configuration from the filtered data
            const colHeaders = Object.keys(filteredData[0]);
            const columns = colHeaders.map(header => ({
                data: header
            }));
    
            hot = new Handsontable(container, {
                data: filteredData,
                colHeaders: colHeaders,
                columns: columns,
                rowHeaders: true,
                contextMenu: true,
                minSpareRows: 1,
                licenseKey: 'non-commercial-and-evaluation' // For non-commercial use
            });

            // Add afterChange hook to edit POI
            hot.addHook('afterChange', function(changes, source) {
                if (source === 'loadData') {
                    return; // Don't send request when loading data
                }
                changes.forEach(function(change) {
                    const [row, prop, oldValue, newValue] = change;
                    if (oldValue !== newValue) {
                        const rowData = hot.getDataAtRow(row);
                        const poi = {
                            id: data[row].id,
                            ...rowData.reduce((obj, value, index) => {
                                obj[colHeaders[index]] = value;
                                return obj;
                            }, {})
                        };
                        $.ajax({
                            url: '/edit-poi',
                            method: 'POST',
                            contentType: 'application/json',
                            data: JSON.stringify(poi),
                            success: function(response) {
                                console.log(response.message);
                            },
                            error: function(error) {
                                console.error(error);
                            }
                        });
                    }
                });
            });

            // Add afterCreateRow hook to add POI
            hot.addHook('afterCreateRow', function(index, amount) {
                for (let i = 0; i < amount; i++) {
                    const rowData = hot.getDataAtRow(index + i);
                    const poi = {
                        name: rowData[1],
                        longitude: rowData[2],
                        latitude: rowData[3],
                        description: rowData[4]
                    };
                    $.ajax({
                        url: '/add-poi',
                        method: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify(poi),
                        success: function(response) {
                            console.log(response.message);
                            loadPOIData(); // Reload the POI data
                        },
                        error: function(error) {
                            console.error(error);
                        }
                    });
                }
            });

            // Add afterRemoveRow hook to delete POI
            hot.addHook('afterRemoveRow', function(index, amount) {
                for (let i = 0; i < amount; i++) {
                    const rowData = hot.getDataAtRow(index + i);
                    const poiId = data[index + i].id;
                    $.ajax({
                        url: '/delete-poi',
                        method: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify({id: poiId}),
                        success: function(response) {
                            console.log(response.message);
                        },
                        error: function(error) {
                            console.error(error);
                        }
                    });
                }
            });
        }, 'json');
    }

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
