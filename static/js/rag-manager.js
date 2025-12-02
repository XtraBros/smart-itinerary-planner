let sheetTable = null;
let activeUnitId = null;
let activeColumns = [];
let activeUnitName = "";
let tabulatorLoader = null;
const TABULATOR_SRC = "/static/js/tabulator.min.js";

function enterSheetOnlyMode() {
    if (document && document.body) {
        document.body.classList.add("sheet-only");
    }
}

function exitSheetOnlyMode() {
    if (document && document.body) {
        document.body.classList.remove("sheet-only");
    }
}

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
    try {
        const response = await fetch("/admin/get_units");
        const data = await response.json();
        console.log("Fetched units:", data);
        const container = document.getElementById("unit-container");
        container.innerHTML = "";

        data.units.forEach((unit) => {
            const unitBox = document.createElement("div");
            unitBox.className = "unit-box";
            unitBox.style.backgroundColor = "#dce775";

            const title = unit.name ? unit.name.toUpperCase() : "UNNAMED";
            const description = unit.description || "No description provided.";
            const source = (unit.source_type || "csv").toUpperCase();

            unitBox.innerHTML = `
                <h3>${title}</h3>
                <p>Source: ${source}</p>
                <p>Description: ${description}</p>
                <div class="unit-actions">
                    <button class="primary" onclick="openSheet('${unit.id}')">📄 Manage Data</button>
                    <button class="danger" onclick="confirmDeleteUnit('${unit.id}')">🗑 Delete</button>
                </div>
            `;

            container.appendChild(unitBox);
        });
    } catch (error) {
        console.error("Failed to fetch units", error);
        alert("Unable to fetch RAG units.");
    }
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

async function ensureTabulatorLoaded() {
    if (window.Tabulator) return;
    if (!tabulatorLoader) {
        tabulatorLoader = new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = TABULATOR_SRC;
            script.async = true;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Failed to load the Tabulator bundle. Ensure /static/js/tabulator.min.js is accessible."));
            document.head.appendChild(script);
        });
    }
    await tabulatorLoader;
}

async function openSheet(unitId) {
    try {
        showLoadingModal("Loading CSV...");
        const res = await fetch(`/admin/rag_unit/${unitId}/data`);
        const payload = await res.json();
        hideLoadingModal();
        if (!res.ok) {
            return alert(payload.error || "Failed to load POI data.");
        }
        await ensureTabulatorLoaded();
        activeUnitId = unitId;
        activeColumns = payload.columns || [];
        activeUnitName = payload.unit?.name || "POI Sheet";
        enterSheetOnlyMode();
        renderSheet(payload);
    } catch (error) {
        hideLoadingModal();
        console.error("Failed to load sheet", error);
        alert("Unable to load POI sheet.");
    }
}
window.openSheet = openSheet;

function getColumnDefinition(field) {
    return {
        title: field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        field,
        editor: "input",
        minWidth: 150,
        headerSort: false,
        resizable: true,
    };
}

function renderSheet(payload) {
    const panel = document.getElementById("sheetPanel");
    const title = document.getElementById("sheetTitle");
    const meta = document.getElementById("sheetMeta");
    const container = document.getElementById("sheetContainer");

    if (!panel || !title || !meta || !container) return;
    panel.classList.add("visible");
    title.textContent = payload.unit?.name || "POI Sheet";
    const description = payload.unit?.description || "No description";
    const sourcePath = payload.unit?.source_path || "";
    meta.textContent = `${description} ${sourcePath ? `• CSV: ${sourcePath}` : ""}`;

    container.innerHTML = "";
    const columns = (payload.columns || []).map((col) => getColumnDefinition(col));

    sheetTable = new Tabulator(container, {
        data: payload.rows || [],
        columns,
        layout: "fitDataStretch",
        height: 520,
        movableColumns: true,
        resizableRows: true,
        resizableColumns: true,
        clipboard: true,
        placeholder: "No rows in this CSV yet.",
        selectableRangeMode: "cell",
        selectableRollingSelection: true,
        pagination: false,
        clipboardPasteAction: "replace",
        rowHeight: 36,
        reactiveData: false,
    });
}

function addSheetRow() {
    if (!sheetTable || !activeColumns.length) {
        return alert("Open a POI sheet before adding rows.");
    }
    const blankRow = {};
    activeColumns.forEach((col) => {
        blankRow[col] = "";
    });
    sheetTable.addRow(blankRow);
}
window.addSheetRow = addSheetRow;

function addSheetColumn() {
    if (!sheetTable) {
        return alert("Open a POI sheet before modifying columns.");
    }

    const columnName = prompt("New column name:");
    if (columnName === null) return; // User cancelled
    const trimmed = columnName.trim();
    if (!trimmed) {
        return alert("Column name cannot be empty.");
    }
    if (!Array.isArray(activeColumns)) {
        activeColumns = [];
    }
    if (activeColumns.includes(trimmed)) {
        return alert("That column already exists in this sheet.");
    }

    activeColumns = [...activeColumns, trimmed];
    const newColumnDef = getColumnDefinition(trimmed);
    sheetTable.addColumn(newColumnDef, true, "end").then(() => {
        const patch = { [trimmed]: "" };
        sheetTable.getRows().forEach((row) => row.update(patch));
    });
}
window.addSheetColumn = addSheetColumn;

async function saveSheetEdits() {
    if (!sheetTable || !activeUnitId) {
        return alert("Open a POI sheet before saving.");
    }
    const rows = sheetTable.getData();
    try {
        showLoadingModal("Saving CSV...");
        const res = await fetch(`/admin/rag_unit/${activeUnitId}/data`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ rows, columns: activeColumns }),
        });
        hideLoadingModal();
        if (res.ok) {
            alert("CSV updated successfully.");
            await fetchUnits();
            await openSheet(activeUnitId);
        } else {
            const err = await res.json();
            alert(err.error || "Failed to save CSV.");
        }
    } catch (error) {
        hideLoadingModal();
        console.error("Failed to save POIs", error);
        alert("Unable to save POI data.");
    }
}
window.saveSheetEdits = saveSheetEdits;

function closeSheetPanel() {
    const panel = document.getElementById("sheetPanel");
    const meta = document.getElementById("sheetMeta");
    const container = document.getElementById("sheetContainer");
    if (sheetTable) {
        sheetTable.destroy();
        sheetTable = null;
    }
    if (container) {
        container.innerHTML = "";
    }
    activeUnitId = null;
    activeColumns = [];
    activeUnitName = "";
    if (panel) {
        panel.classList.remove("visible");
    }
    if (meta) {
        meta.textContent = "Select a unit to begin editing.";
    }
    exitSheetOnlyMode();
}
window.closeSheetPanel = closeSheetPanel;

window.onload = async function () {
    hideLoadingModal(); // Hide any old modals
    await fetchUnits(); // Fetch units, but don't show the modal unless inside submit
};
