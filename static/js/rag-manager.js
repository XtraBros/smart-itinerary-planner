function openAddModal() {
    document.getElementById("addModal").style.display = "flex";
    }

function closeAddModal() {
    document.getElementById("addModal").style.display = "none";
}

async function submitAddUnit() {
    const formData = new FormData();

    const nameEl = document.getElementById("unitName");
    const descEl = document.getElementById("unitDescription");
    const fileInput = document.getElementById("csvFile");

    if (!nameEl || !descEl || !fileInput) {
        return alert("Missing required fields in the form.");
    }

    const name = nameEl.value.trim();
    const description = descEl.value.trim();

    if (!name) return alert("Please enter a unit name.");
    if (!fileInput.files[0]) return alert("Please select a CSV file.");

    formData.append("unit_name", name);
    formData.append("description", description);
    formData.append("source", "csv"); // fixed to csv
    formData.append("file", fileInput.files[0]);

    // Show loading modal before request
    showLoadingModal("Adding RAG Unit...");

    try {
        const res = await fetch("/admin/add_unit", {
            method: "POST",
            body: formData,
        });

        if (res.ok) {
            hideLoadingModal();
            closeAddModal();
            alert("RAG Unit added successfully.");
            fetchUnits();
        } else {
            const err = await res.json();
            hideLoadingModal();
            alert(`Failed to add unit: ${err.error}`);
        }
    } catch (e) {
        hideLoadingModal();
        alert("Request failed: " + e.message);
    }
}
window.submitAddUnit = submitAddUnit;

function showLoadingModal(message = "Loading...") {
    const loadingModal = document.getElementById("loadingModal");
    const loadingText = document.getElementById("loadingText");
    if (loadingModal) loadingModal.style.display = "block";
    if (loadingText) loadingText.textContent = message;
}

function hideLoadingModal() {
    const loadingModal = document.getElementById("loadingModal");
    if (loadingModal) loadingModal.style.display = "none";
}

async function fetchUnits() {
    console.log("Fetching RAG units...");
    const response = await fetch("/admin/get\_units");
    const data = await response.json();
    console.log("Fetched units:", data);
    const container = document.getElementById("unit-container");
    container.innerHTML = "";

    data.units.forEach((unit) => {
        const unitBox = document.createElement("div");
        unitBox.className = "unit-box";
        unitBox.style.backgroundColor = "#dce775"; // fixed CSV color

        unitBox.innerHTML = `
        <h3>${unit.name.toUpperCase()}</h3>
        <p>Source: CSV</p>
        <p>Description: ${unit.description}</p>
        <button onclick="confirmDeleteUnit('${unit.id}')">🗑 Delete</button>
    `;

        container.appendChild(unitBox);
    });
}
window.fetchUnits = fetchUnits;

function confirmDeleteUnit(id) {
    if (confirm("Are you sure you want to delete this RAG Unit?")) {
    deleteUnit(id);
    }
}
window.confirmDeleteUnit = confirmDeleteUnit;

async function deleteUnit(id) {
    console.log("Deleting unit with ID:", id);
    const res = await fetch(`/admin/delete_unit`, {
    method: "POST",
    headers: {
    "Content-Type": "application/json",
    },
    body: JSON.stringify({ unit_id: id }),
    });

    if (res.ok) {
        alert("Unit deleted.");
        fetchUnits(); // Refresh list
    } else {
        alert("Failed to delete unit.");
    }
}
window.deleteUnit = deleteUnit;

window.onload = async function () {
    hideLoadingModal(); // Hide any old modals
    await fetchUnits(); // Fetch units, but don't show the modal unless inside submit
};