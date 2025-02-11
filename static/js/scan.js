document.addEventListener("DOMContentLoaded", function(){
    // Initialize campaign stats
    var campaignStats = {total_scanned: 0, not_found: 0, active: 0};
    var barcodeRegex = null;
    
    // Fetch the barcode regex from the server
    fetch('/config')
        .then(response => response.text())
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const regexInput = doc.getElementById('barcode_regex');
            if (regexInput) {
                try {
                    barcodeRegex = new RegExp(regexInput.value);
                } catch (e) {
                    console.error("Invalid regex pattern:", e);
                    barcodeRegex = null;
                }
            }
        });

    // Initialize the combined table using Tabulator.
    // This table loads its data via an ajax URL. When a campaign is restarted,
    // the /api/scanned_data route will return the updated data.
    var combinedTable = new Tabulator("#combined-table", {
        layout:"fitColumns",
        placeholder:"No scanned items yet",
        ajaxURL:"/api/scanned_data",
        // Custom ajaxRequestFunc to fix any NaN values in the JSON text.
        ajaxRequestFunc: function(url, config, params) {
            return fetch(url, config)
                .then(response => response.text())
                .then(text => {
                    let fixedText = text.replace(/\bNaN\b/g, "null");
                    return JSON.parse(fixedText);
                });
        },
        // Extract campaign_stats from the response and return the data array.
        ajaxResponse: function(url, params, response) {
            updateCampaignStats(response.campaign_statistics);
            return response.data;
        },
        pagination:"local",
        paginationSize:10,
        columns:[
            {title:"Barcode", field:"barcode", headerFilter:"input"},
            {title:"Scan Time", field:"timestamp", sorter:"datetime", headerFilter:"input"},
            {title:"Scan Building", field:"scan_building", headerFilter:"input"},
            {title:"Scan Room", field:"scan_room", headerFilter:"input"},
            {title:"Scan Location", field:"scan_location", headerFilter:"input"},
            {title:"Category", field:"category", headerFilter:"input"},
            // Reference columns:
            {title:"Status", field:"Status - Container", headerFilter:"input"},
            {title:"Time Sensitive", field:"Time Sensitive - Container", headerFilter:"input"},
            {title:"Owner Name", field:"Owner Name - Container", headerFilter:"input"},
            {title:"Product Identifier", field:"Product Identifier - Product", headerFilter:"input"},
            {title:"Current Quantity", field:"Current Quantity - Container", headerFilter:"input"},
            {title:"Unit", field:"Unit - Container", headerFilter:"input"},
            {title:"NFPA 704 Health Hazard", field:"NFPA 704 Health Hazard - Product", headerFilter:"input"},
            {title:"NFPA 704 Flammability Hazard", field:"NFPA 704 Flammability Hazard - Product", headerFilter:"input"}
        ],
        initialSort:[{column:"timestamp", dir:"desc"}]
    });

    // When the page loads, force the table to load data.
    combinedTable.on("tableBuilt", function(){
        combinedTable.replaceData();
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
         
         // Validate barcode against regex if available
         if (barcodeRegex && !barcodeRegex.test(barcode)) {
             ChemUtils.showAlert("Invalid barcode format");
             barcodeInput.value = "";
             barcodeInput.focus();
             barcodeInput.select();
             return;
         }
         
         if(barcode !== ""){
             // Client-side duplicate check: ensure barcode is not already in the table.
             var existing = combinedTable.getData().filter(function(row){
                 return row.barcode === barcode;
             });

             if(existing.length > 0){
                 ChemUtils.showAlert("Barcode already scanned.");
                 barcodeInput.value = "";
                 barcodeInput.focus();
                 barcodeInput.select();
                 return;
             }
             processScan(barcode);
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
             let fixedText = text.replace(/\bNaN\b/g, "null");
             return JSON.parse(fixedText);
         })
         .then(data => {
              if(!data.success){
                  ChemUtils.showAlert(data.message || "Invalid barcode.");
                  return;
              }
              if(data.duplicate){
                  ChemUtils.showAlert(data.message || "Barcode already scanned.");
                  return;
              }

              // Build the new row.
              // The row includes both the scan info and any reference data.
              let newRow = {
                  barcode: data.barcode,
                  timestamp: data.timestamp,
                  scan_building: data.scan_building,  // from campaign info
                  scan_room: data.scan_room,
                  scan_location: data.scan_location,
                  category: data.category,
                  "Status - Container": "",
                  "Time Sensitive - Container": "",
                  "Owner Name - Container": "",
                  "Product Identifier - Product": "",
                  "Current Quantity - Container": "",
                  "Unit - Container": "",
                  "NFPA 704 Health Hazard - Product": "",
                  "NFPA 704 Flammability Hazard - Product": ""
              };

              // If reference (inventory) data is returned, merge it into the row.
              if(data.inventory_data && Array.isArray(data.inventory_data) && data.inventory_data.length > 0){
                  // Replace any 'NaN' strings with empty strings.
                  for (let key in data.inventory_data[0]) {
                      if(String(data.inventory_data[0][key]).toLowerCase() === "nan"){
                          data.inventory_data[0][key] = "";
                      }
                  }
                  Object.assign(newRow, data.inventory_data[0]);
              }

              // Add the new row to the table.
              combinedTable.addRow(newRow, true);

              // Update campaign stats.
              updateCampaignStats(data.campaign_statistics);

              // Play a sound.
              playSound(data.category);
         })
         .catch(err => console.error("Error processing scan:", err));
    }

    function playSound(category){
         var soundId = "";
         if(category === "active"){
             soundId = "sound_active";
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
        document.getElementById('active').textContent = stats.active;
        document.getElementById('archived').textContent = stats.archived;

    }

    // Initial fetch of campaign stats.
    fetch('/api/scanned_data')
      .then(res => res.text())
      .then(text => {
          let fixedText = text.replace(/\bNaN\b/g, "null");
          return JSON.parse(fixedText);
      })
      .then(data => updateCampaignStats(data.campaign_statistics))
      .catch(err => console.error("Error fetching initial campaign stats:", err));
});
