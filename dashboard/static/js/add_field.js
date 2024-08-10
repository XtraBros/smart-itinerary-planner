document.getElementById('addFieldBtn').addEventListener('click', function() {
    const configFields = document.getElementById('configFields');
    
    const newFieldDiv = document.createElement('div');
    const newFieldName = document.createElement('input');
    newFieldName.setAttribute('type', 'text');
    newFieldName.setAttribute('placeholder', 'Variable Name');
    newFieldName.classList.add('newFieldName');
    
    const newFieldValue = document.createElement('input');
    newFieldValue.setAttribute('type', 'text');
    newFieldValue.setAttribute('placeholder', 'Variable Value');
    newFieldValue.classList.add('newFieldValue');
    
    newFieldDiv.appendChild(newFieldName);
    newFieldDiv.appendChild(newFieldValue);
    configFields.appendChild(newFieldDiv);
});

document.getElementById('configForm').addEventListener('submit', function(e) {
    e.preventDefault();

    const settings = {};
    settings['setting1'] = document.getElementById('setting1').value;

    document.querySelectorAll('.newFieldName').forEach((nameField, index) => {
        const valueField = document.querySelectorAll('.newFieldValue')[index];
        if (nameField.value && valueField.value) {
            settings[nameField.value] = valueField.value;
        }
    });

    fetch('/update_config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Configuration updated successfully!');
        } else {
            alert('Failed to update configuration.');
        }
    });
});
