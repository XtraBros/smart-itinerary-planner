function updateSourceFields() {
    const source = document.getElementById("sourceType").value;

    // Hide all dynamic input sections first
    document.getElementById("csv-fields").style.display = "none";
    document.getElementById("json-fields").style.display = "none";
    document.getElementById("index-fields").style.display = "none";
    document.getElementById("mongodb-fields").style.display = "none";
    document.getElementById("sql-fields").style.display = "none";

    // Show the appropriate section
    if (source === "csv") {
        document.getElementById("csv-fields").style.display = "block";
    } else if (source === "index") {
        document.getElementById("index-fields").style.display = "block";
    } else if (source === "mongodb") {
        document.getElementById("mongodb-fields").style.display = "block";
    } else if (source === "sql") {
        document.getElementById("sql-fields").style.display = "block";
    } else if (source === "json") {
        document.getElementById("json-fields").style.display = "block";
    }
}
window.updateSourceFields = updateSourceFields;
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
    const sourceEl = document.getElementById("sourceType");

    if (!nameEl || !descEl || !sourceEl) {
        return alert("Missing required fields in the form.");
    }

    const name = nameEl.value.trim();
    const description = descEl.value.trim();
    const source = sourceEl.value;

    if (!name) return alert("Please enter a unit name.");
    formData.append("unit_name", name);
    formData.append("description", description);
    formData.append("source", source);

    if (source === "csv") {
        const fileInput = document.getElementById("csvFile");
        if (!fileInput || !fileInput.files[0])
            return alert("Please select a CSV file.");
        formData.append("file", fileInput.files[0]);
    } else if (source === "mongodb") {
        const urlEl = document.getElementById("mongoUrl");
        const dbEl = document.getElementById("mongoDb");
        const collEl = document.getElementById("mongoCollection");

        if (!urlEl || !dbEl || !collEl)
            return alert("MongoDB input fields are missing.");
        if (!urlEl.value || !dbEl.value || !collEl.value)
            return alert("Please fill in all MongoDB connection details.");

        formData.append("mongo_url", urlEl.value);
        formData.append("mongo_db", dbEl.value);
        formData.append("mongo_collection", collEl.value);
    } else if (source === "sql") {
        const host = document.getElementById("host")?.value;
        const port = document.getElementById("port")?.value;
        const user = document.getElementById("user")?.value;
        const pass = document.getElementById("pw")?.value;
        const db = document.getElementById("database")?.value;
        const query = document.getElementById("query")?.value;

        if (!host || !db || !query)
            return alert("Please enter SQL host, database, and query.");

        formData.append("host", host);
        formData.append("port", port || "");
        formData.append("user", user || "");
        formData.append("pw", pass || "");
        formData.append("database", db);
        formData.append("query", query);
    }

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
    const response = await fetch("/admin/get_units");
    const data = await response.json();
    console.log("Fetched units:", data);
    const container = document.getElementById("unit-container");
    container.innerHTML = "";

    const colorMap = {
        csv: "#dce775",
        sql: "#81d4fa",
        mongodb: "#ffcc80",
        json: "#ce93d8",
        cms: "#a5d6a7",
        unknown: "#eeeeee",
    };

    data.units.forEach((unit) => {
        const unitBox = document.createElement("div");
        unitBox.className = "unit-box";
        unitBox.style.backgroundColor = colorMap[unit.source_type] || "#f0f0f0";

        unitBox.innerHTML = `
        <h3>${unit.name.toUpperCase()}</h3>
        <p>Source: ${unit.source_type}</p>
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
window,deleteUnit = deleteUnit;
window.onload = async function () {
    hideLoadingModal(); // Hide any old modals
    await fetchUnits(); // Fetch units, but don't show the modal unless inside submit
};