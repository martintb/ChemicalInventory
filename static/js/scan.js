// Configure AG Grid for the scanned data.
let gridOptions = {
  columnDefs: [
    { headerName: "Barcode", field: "barcode" },
    { headerName: "Timestamp", field: "timestamp" },
    { headerName: "Building", field: "building" },
    { headerName: "Room", field: "room" },
    { headerName: "Location", field: "location" },
    { headerName: "Category", field: "category" }
  ],
  rowData: []
};

// Configure AG Grid for the inventory data from the reference database.
let inventoryGridOptions = {
  columnDefs: [
    { headerName: "Barcode", field: "Barcode ID - Container", filter: true },
    { headerName: "Status", field: "Status - Container", filter: true },
    { headerName: "Time Sensitive", field: "Time Sensitive - Container", filter: true },
    { headerName: "Location", field: "Location - Container", filter: true },
    { headerName: "Owner Name", field: "Owner Name - Container", filter: true },
    { headerName: "Product Identifier", field: "Product Identifier - Product", filter: true },
    { headerName: "Current Quantity", field: "Current Quantity - Container", filter: true },
    { headerName: "Unit", field: "Unit - Container", filter: true },
    { headerName: "NFPA 704 Health Hazard", field: "NFPA 704 Health Hazard - Product", filter: true },
    { headerName: "NFPA 704 Flammability Hazard", field: "NFPA 704 Flammability Hazard - Product", filter: true }
  ],
  rowData: []
};

document.addEventListener('DOMContentLoaded', function () {
  // Initialize scanned data grid.
  let gridDiv = document.querySelector('#scan-table');
  new agGrid.Grid(gridDiv, gridOptions);
  fetchScannedData();

  // Initialize inventory data grid.
  let inventoryGridDiv = document.querySelector('#inventory-table');
  new agGrid.Grid(inventoryGridDiv, inventoryGridOptions);

  let barcodeInput = document.getElementById('barcode_input');
  barcodeInput.addEventListener('keydown', function (event) {
    if (event.key === "Enter" || event.keyCode === 13) {
      event.preventDefault();
      processBarcode();
    }
  });

  function processBarcode() {
    let barcode = barcodeInput.value.trim();
    if (barcode !== "") {
      processScan(barcode);
      barcodeInput.value = "";
    }
  }
});

function processScan(barcode) {
  fetch("/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ barcode: barcode })
  })
  .then(response => response.json())
  .then(data => {
    let msgElem = document.getElementById("scan-message");
    if (!data.success) {
      msgElem.innerText = data.message;
      return;
    }
    // Update dashboard counts.
    document.getElementById("total").innerText = data.stats.total;
    document.getElementById("found").innerText = data.stats.found;
    document.getElementById("not_found").innerText = data.stats.not_found;
    document.getElementById("archived").innerText = data.stats.archived;
    playSound(data.category);
    msgElem.innerText = data.duplicate
      ? "Duplicate scan: " + data.barcode
      : "Scanned: " + data.barcode + " (" + data.category + ")";
    fetchScannedData();

    // If the response includes inventory data, update the inventory grid.
    if (data.inventory_data && data.inventory_data.length > 0) {
      data.inventory_data.forEach(function(newRow) {
        // Check if this barcode already exists in the inventory grid.
        let exists = inventoryGridOptions.rowData.some(function(row) {
          return row["Barcode ID - Container"] == newRow["Barcode ID - Container"];
        });
        if (!exists) {
          inventoryGridOptions.rowData.push(newRow);
        }
      });
      inventoryGridOptions.api.setRowData(inventoryGridOptions.rowData);
    }
  })
  .catch(error => console.error("Error processing scan:", error));
}

function fetchScannedData() {
  fetch("/api/scanned_data")
    .then(response => response.json())
    .then(data => gridOptions.api.setRowData(data))
    .catch(error => console.error("Error fetching scanned data:", error));
}

function playSound(category) {
  let soundId = "";
  if (category === "found") {
    soundId = "sound_found";
  } else if (category === "not_found") {
    soundId = "sound_not_found";
  } else if (category === "archived") {
    soundId = "sound_archived";
  } else if (category === "duplicate") {
    soundId = "sound_duplicate";
  }
  if (soundId) {
    let sound = document.getElementById(soundId);
    if (sound) sound.play();
  }
}