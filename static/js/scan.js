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

document.addEventListener('DOMContentLoaded', function () {
  let gridDiv = document.querySelector('#scan-table');
  new agGrid.Grid(gridDiv, gridOptions);
  fetchScannedData();

  let barcodeInput = document.getElementById('barcode_input');
  barcodeInput.addEventListener('keydown', function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      let barcode = barcodeInput.value.trim();
      if (barcode !== "") {
        processScan(barcode);
        barcodeInput.value = "";
      }
    }
  });
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