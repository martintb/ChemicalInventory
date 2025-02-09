document.addEventListener("DOMContentLoaded", function(){
    // Initialize campaign stats
    var campaignStats = {total_scanned: 0, not_found: 0, found: 0};
    updateCampaignStats(campaignStats);

    // Initialize the combined table using Tabulator.
    var combinedTable = new Tabulator("#combined-table", {
        layout:"fitColumns",
        placeholder:"No scanned items yet",
        // Use a custom ajaxRequestFunc so we can fix any NaN values.
        ajaxURL:"/api/scanned_data",
        ajaxRequestFunc: function(url, config, params) {
            return fetch(url, config)
                .then(response => response.text())
                .then(text => {
                    // Replace bare NaN tokens with null so JSON parses.
                    let fixedText = text.replace(/\bNaN\b/g, "null");
                    return JSON.parse(fixedText);
                });
        },
        // Use ajaxResponse to extract campaign stats and return only the data array.
        ajaxResponse: function(url, params, response) {
            updateCampaignStats(response.campaign_stats);
            return response.data;
        },
        pagination:"local",
        paginationSize:10,
        columns:[
            {title:"Barcode", field:"barcode"},
            {title:"Timestamp", field:"timestamp", sorter:"datetime"},
            {title:"Status", field:"Status - Container"},
            {title:"Time Sensitive", field:"Time Sensitive - Container"},
            {title:"Location", field:"Location - Container"},
            {title:"Owner Name", field:"Owner Name - Container"},
            {title:"Product Identifier", field:"Product Identifier - Product"},
            {title:"Current Quantity", field:"Current Quantity - Container"},
            {title:"Unit", field:"Unit - Container"},
            {title:"NFPA 704 Health Hazard", field:"NFPA 704 Health Hazard - Product"},
            {title:"NFPA 704 Flammability Hazard", field:"NFPA 704 Flammability Hazard - Product"}
        ],
        initialSort:[{column:"timestamp", dir:"desc"}]
    });

    // Listen for the Return/Enter key on the barcode input.
    document.getElementById("barcode_input").addEventListener("keydown", function(e){
        if(e.key === "Enter" || e.keyCode === 13){
            e.preventDefault();
            processBarcode();
        }
    });

    function processBarcode(){
         var barcodeInput = document.getElementById("barcode_input");
         var barcode = barcodeInput.value.trim();
         if(barcode !== ""){
             // Check if this barcode already exists in the table.
             var existingRows = combinedTable.getData().filter(function(row){
                 return row.barcode === barcode;
             });
             if(existingRows.length > 0){
                 showAlert("Barcode already scanned.");
                 // Clear and re‑focus the input.
                 barcodeInput.value = "";
                 barcodeInput.focus();
                 barcodeInput.select();
                 return;
             }
             // Otherwise, process the scan.
             processScan(barcode);
             // Clear and refocus the input.
             barcodeInput.value = "";
             barcodeInput.focus();
             barcodeInput.select();
         }
    }

    function processScan(barcode){
         fetch("/scan", {
             method:"POST",
             headers:{"Content-Type": "application/json"},
             body: JSON.stringify({barcode: barcode})
         })
         .then(res => res.text())
         .then(text => {
             // Replace any bare NaN tokens with null.
             let fixedText = text.replace(/\bNaN\b/g, "null");
             return JSON.parse(fixedText);
         })
         .then(data => {
              if(!data.success){
                  // Show an alert if the barcode is invalid (e.g. regex failure).
                  showAlert(data.message || "Invalid barcode.");
                  return;
              }
              // (Server-side duplicate checking could occur here too,
              // but our client-side check should catch duplicates.)
              if(data.duplicate){
                  showAlert(data.message || "Barcode already scanned.");
                  return;
              }

              // Prepare the new row data.
              let newRow = {
                  barcode: data.barcode,
                  timestamp: data.timestamp,
                  "Status - Container": "",
                  "Time Sensitive - Container": "",
                  "Location - Container": "",
                  "Owner Name - Container": "",
                  "Product Identifier - Product": "",
                  "Current Quantity - Container": "",
                  "Unit - Container": "",
                  "NFPA 704 Health Hazard - Product": "",
                  "NFPA 704 Flammability Hazard - Product": ""
              };

              // If inventory data is returned, update the row with that data.
              if (data.inventory_data && Array.isArray(data.inventory_data) && data.inventory_data.length > 0) {
                  for (let key in data.inventory_data[0]) {
                      // If the value is "NaN" (as string), set it to empty.
                      if (String(data.inventory_data[0][key]).toLowerCase() === "nan") {
                          data.inventory_data[0][key] = '';
                      }
                  }
                  Object.assign(newRow, data.inventory_data[0]);
              }

              // Add the new row to the table.
              combinedTable.addRow(newRow, true);

              // Update campaign statistics.
              updateCampaignStats(data.campaign_stats);

              // Play a sound based on the scan result.
              playSound(data.category);
         })
         .catch(err => console.error("Error processing scan:", err));
    }

    function playSound(category){
         var soundId = "";
         if(category === "found"){
             soundId = "sound_found";
         } else if(category === "not_found"){
             soundId = "sound_not_found";
         } else if(category === "archived"){
             soundId = "sound_archived";
         } else if(category === "duplicate"){
             soundId = "sound_duplicate";
         }
         if(soundId){
             var sound = document.getElementById(soundId);
             if(sound) sound.play();
         }
    }

    function updateCampaignStats(stats) {
        document.getElementById('total-scanned').textContent = stats.total_scanned;
        document.getElementById('not-found').textContent = stats.not_found;
        document.getElementById('found').textContent = stats.found;
    }

    function showAlert(message) {
         var alertElem = document.getElementById("scan-alert");
         if(alertElem) {
             alertElem.textContent = message;
             alertElem.style.display = "block";
             // Hide the alert after 3 seconds.
             setTimeout(function(){
                  alertElem.style.display = "none";
             }, 3000);
         }
    }

    // Initial fetch of campaign stats.
    fetch('/api/scanned_data')
      .then(res => res.text())
      .then(text => {
          let fixedText = text.replace(/\bNaN\b/g, "null");
          return JSON.parse(fixedText);
      })
      .then(data => updateCampaignStats(data.campaign_stats))
      .catch(err => console.error("Error fetching initial campaign stats:", err));
});