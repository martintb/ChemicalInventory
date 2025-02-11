import os
import datetime
import logging
import json
import re
import pandas as pd
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash

# --- Application and Logging Configuration ---
app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Change this for production

# Record the app start time for uptime calculation
app_start_time = datetime.datetime.now()

# Configure logging: All messages will be written to app.log
logging.basicConfig(
    level=logging.INFO,
    filename='app.log',
    format='%(asctime)s %(levelname)s: %(message)s'
)

# --- Global Variables & Directories ---
inventory_dataframe = pd.DataFrame()  # Combined reference inventory DataFrame
# scanned_dataframe holds the active campaign's scan log.
scanned_dataframe = pd.DataFrame(columns=[
    "barcode", "timestamp", "building", "room", "location", "category"
])

BASE_DIRECTORY = os.getcwd()
DATA_DIRECTORY = os.path.join(BASE_DIRECTORY, "data")
CAMPAIGNS_DIRECTORY = os.path.join(BASE_DIRECTORY, "campaigns")
UPLOADS_DIRECTORY = os.path.join(BASE_DIRECTORY, "uploads")
CONFIGURATION_FILE = os.path.join(BASE_DIRECTORY, "config.json")  # Configuration file

# Ensure required folders exist
for folder in [DATA_DIRECTORY, CAMPAIGNS_DIRECTORY, UPLOADS_DIRECTORY]:
    os.makedirs(folder, exist_ok=True)

# --- Configuration Handling ---
CONFIGURATION = {}

def load_configuration():
    global CONFIGURATION
    if not os.path.exists(CONFIGURATION_FILE):
        default_configuration = {"barcode_regex": "^[A-Za-z]?\\d{4,6}$"}
        with open(CONFIGURATION_FILE, "w") as file:
            json.dump(default_configuration, file)
        CONFIGURATION = default_configuration
        logging.info("Created default config file.")
    else:
        with open(CONFIGURATION_FILE, "r") as file:
            CONFIGURATION = json.load(file)
        logging.info("Loaded config file.")

def save_configuration():
    with open(CONFIGURATION_FILE, "w") as file:
        json.dump(CONFIGURATION, file)
    logging.info("Saved updated config file.")

# Load configuration on startup.
load_configuration()

# --- Utility Functions ---

def load_inventory():
    """Load all CSV reference inventory files from DATA_DIRECTORY into a single DataFrame."""
    global inventory_dataframe
    try:
        csv_files = [
            os.path.join(DATA_DIRECTORY, file)
            for file in os.listdir(DATA_DIRECTORY) if file.endswith('.csv')
        ]
        dataframe_list = []
        for file in csv_files:
            try:
                dataframe = pd.read_csv(file)
                dataframe_list.append(dataframe)
            except Exception as exception:
                logging.error(f"Error reading {file}: {exception}")
        if dataframe_list:
            inventory_dataframe = pd.concat(dataframe_list, ignore_index=True)
            logging.info(f"Loaded inventory with {len(inventory_dataframe)} rows from {len(csv_files)} files.")
        else:
            inventory_dataframe = pd.DataFrame()
    except Exception as exception:
        logging.exception("Failed to load inventory.")
        inventory_dataframe = pd.DataFrame()

# Load inventory on startup.
load_inventory()

def save_scanned_data():
    """Save the current campaign's scanned data to a CSV file in CAMPAIGNS_DIRECTORY."""
    try:
        campaign_id = session.get('campaign_id')
        if campaign_id:
            file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
            scanned_dataframe.to_csv(file_path, index=False)
            logging.info(f"Campaign {campaign_id} saved with {len(scanned_dataframe)} scans.")
    except Exception as exception:
        logging.exception("Error saving scanned campaign data.")

def archive_campaign():
    """Archive (save) the current campaign."""
    save_scanned_data()

def update_campaign_statistics():
    """Update campaign statistics in the session."""
    global scanned_dataframe
    session['total_scanned'] = len(scanned_dataframe)
    session['not_found'] = len(scanned_dataframe[scanned_dataframe['category'] == 'not_found'])
    session['active'] = len(scanned_dataframe[scanned_dataframe['category'] == 'active'])

def get_campaign_statistics():
    """Get current campaign statistics."""
    return {
        'total_scanned': session.get('total_scanned', 0),
        'not_found': session.get('not_found', 0),
        'active': session.get('active', 0)
    }

# --- Global Error Handler ---
@app.errorhandler(Exception)
def handle_exception(exception):
    logging.exception("Unhandled Exception: %s", exception)
    return render_template("error.html", error=str(exception)), 500

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Home page:
      - Displays total unique chemicals from the reference inventory.
      - Lets the user start a new scan campaign.
      - Provides forms to upload reference inventory CSVs and archived campaign CSVs.
      - (When a CSV is uploaded, the inventory summary is updated on reload.)
    """
    try:
        unique_count = 0
        if not inventory_dataframe.empty and "Barcode ID - Container" in inventory_dataframe.columns:
            unique_count = inventory_dataframe["Barcode ID - Container"].nunique()

        if request.method == 'POST':
            if 'start_campaign' in request.form:
                building = request.form.get('building')
                room = request.form.get('room')
                location = request.form.get('location', '')
                if not (building and room):
                    flash("Building and Room are required to start a campaign.", "danger")
                    return render_template("index.html", unique_count=unique_count)
                # Generate a unique campaign id: building_room_YYMMDD-HHMMSS
                campaign_id = f"{building}_{room}_{datetime.datetime.now().strftime('%y%m%d-%H%M%S')}"
                session['building'] = building
                session['room'] = room
                session['location'] = location
                session['campaign_id'] = campaign_id
                global scanned_dataframe
                scanned_dataframe = pd.DataFrame(columns=[
                    "barcode", "timestamp", "building", "room", "location", "category"
                ])
                archive_campaign()  # Save the new (empty) campaign file.
                return redirect(url_for('campaign'))
            elif 'upload_inventory' in request.form:
                file = request.files.get('inventory_file')
                if file and file.filename.endswith('.csv'):
                    filepath = os.path.join(DATA_DIRECTORY, file.filename)
                    file.save(filepath)
                    flash("Inventory CSV uploaded successfully.", "success")
                    load_inventory()  # Reload reference database.
                    if not inventory_dataframe.empty and "Barcode ID - Container" in inventory_dataframe.columns:
                        unique_count = inventory_dataframe["Barcode ID - Container"].nunique()
                else:
                    flash("Invalid file or no file selected for inventory.", "danger")
            elif 'upload_campaign' in request.form:
                file = request.files.get('campaign_file')
                if file and file.filename.endswith('.csv'):
                    filepath = os.path.join(CAMPAIGNS_DIRECTORY, file.filename)
                    file.save(filepath)
                    flash("Campaign CSV uploaded successfully.", "success")
                else:
                    flash("Invalid file or no file selected for campaign.", "danger")
        return render_template("index.html", unique_count=unique_count)
    except Exception as exception:
        logging.exception("Error in index route.")
        flash("An error occurred in the index route.", "danger")
        return render_template("index.html", unique_count=unique_count)

@app.route('/campaign')
@app.route('/campaign/<campaign_id>')
def campaign(campaign_id=None):
    if campaign_id:
        session['campaign_id'] = campaign_id
        global scanned_dataframe
        file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            scanned_dataframe = pd.read_csv(file_path)
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('index'))
    else:
        campaign_id = session.get('campaign_id')
        if not campaign_id:
            flash("No active campaign. Please start a new campaign.", "warning")
            return redirect(url_for('index'))
    campaign_info = {
        "building": session.get('building', ''),
        "room": session.get('room', ''),
        "location": session.get('location', ''),
        "campaign_id": campaign_id
    }
    return render_template("campaign.html", campaign=campaign_info)

@app.route('/scan', methods=['POST'])
def scan():
    try:
        data = request.get_json()
        barcode = data.get("barcode", "").strip().upper()
        if not barcode:
            return jsonify({"success": False, "message": "No barcode provided."}), 400

        global scanned_dataframe, inventory_dataframe

        # Check for duplicate scan by looking at the 'barcode' column in scanned_dataframe.
        if not scanned_dataframe.empty and barcode in scanned_dataframe["barcode"].values:
            return jsonify({
                "success": True,
                "duplicate": True,
                "message": "Barcode already scanned."
            })

        # Retrieve campaign metadata from the session.
        building = session.get("building", "")
        room = session.get("room", "")
        location = session.get("location", "")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Look up the barcode in the reference inventory.
        matched = pd.DataFrame()
        if not inventory_dataframe.empty and "Barcode ID - Container" in inventory_dataframe.columns:
            matched = inventory_dataframe[inventory_dataframe["Barcode ID - Container"].astype(str) == barcode]

        # Determine the category.
        if not matched.empty:
            statuses = matched["Status - Container"].astype(str).str.lower()
            if any(statuses == "archived"):
                category = "archived"
            else:
                category = "active"
        else:
            category = "not_found"

        # Build the new scan row.
        # Use "scan_building", "scan_room", and "scan_location" for the scan metadata.
        new_entry = {
            "barcode": barcode,
            "timestamp": timestamp,
            "scan_building": building,
            "scan_room": room,
            "scan_location": location,
            "category": category,
            "Status - Container": "",
            "Time Sensitive - Container": "",
            "Location - Container": "",
            "Owner Name - Container": "",
            "Product Identifier - Product": "",
            "Current Quantity - Container": "",
            "Unit - Container": "",
            "NFPA 704 Health Hazard - Product": "",
            "NFPA 704 Flammability Hazard - Product": ""
        }

        # If reference data is found, merge the first matching row into new_entry.
        if not matched.empty:
            reference_data = matched.iloc[0].to_dict()
            # Remove any redundant keys from the reference data.
            for redundant_key in ["building", "room", "location"]:
                if redundant_key in reference_data:
                    del reference_data[redundant_key]
            new_entry.update(reference_data)

        # Append the new row to scanned_dataframe using pd.concat (compatible with pandas 2.0).
        new_dataframe = pd.DataFrame([new_entry])
        scanned_dataframe = pd.concat([scanned_dataframe, new_dataframe], ignore_index=True)

        # Ensure that only the desired columns are kept.
        desired_columns = [
            "barcode", "timestamp", "scan_building", "scan_room", "scan_location", "category",
            "Status - Container", "Time Sensitive - Container", "Location - Container",
            "Owner Name - Container", "Product Identifier - Product", "Current Quantity - Container",
            "Unit - Container", "NFPA 704 Health Hazard - Product", "NFPA 704 Flammability Hazard - Product"
        ]
        scanned_dataframe = scanned_dataframe[[column for column in desired_columns if column in scanned_dataframe.columns]]

        # Save the updated campaign data to CSV.
        campaign_id = session.get("campaign_id")
        if campaign_id:
            file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
            scanned_dataframe.to_csv(file_path, index=False)

        # Recalculate campaign statistics.
        total_scanned = len(scanned_dataframe)
        active_count = len(scanned_dataframe[scanned_dataframe["category"] == "active"])
        not_found_count = len(scanned_dataframe[scanned_dataframe["category"] == "not_found"])
        archived_count = len(scanned_dataframe[scanned_dataframe["category"] == "archived"])
        campaign_statistics = {
            "total_scanned": total_scanned,
            "active": active_count,
            "not_found": not_found_count,
            "archived": archived_count
        }

        # Build the JSON response.
        response = {
            "success": True,
            "barcode": barcode,
            "timestamp": timestamp,
            "scan_building": building,
            "scan_room": room,
            "scan_location": location,
            "category": category,
            "inventory_data": []  # Will hold reference data if available.
        }
        if not matched.empty:
            response["inventory_data"] = [matched.iloc[0].to_dict()]
        response["campaign_statistics"] = campaign_statistics

        return jsonify(response)
    except Exception as exception:
        app.logger.exception("Error processing scan.")
        return jsonify({"success": False, "message": "Internal server error during scan."}), 500

@app.route('/api/scanned_data')
def api_scanned_data():
    """Return the current campaign's scanned data as JSON (for AG Grid)."""
    try:
        data = scanned_dataframe.to_dict(orient='records')
        return jsonify({
            'data': data,
            'campaign_statistics': get_campaign_statistics()
        })
    except Exception as exception:
        logging.exception("Error fetching scanned data.")
        return jsonify([])

@app.route('/download')
def download():
    """Download the active campaign CSV."""
    try:
        campaign_id = session.get('campaign_id')
        if campaign_id:
            file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)
            else:
                flash("Campaign file not found.", "danger")
        return redirect(url_for('campaign'))
    except Exception as exception:
        logging.exception("Error during download.")
        flash("Error during download.", "danger")
        return redirect(url_for('campaign'))

@app.route('/download_campaign/<campaign_id>')
def download_campaign(campaign_id):
    """Download an archived campaign CSV (by campaign_id)."""
    try:
        file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as exception:
        logging.exception("Error downloading campaign %s", campaign_id)
        flash("Error during download.", "danger")
        return redirect(url_for('campaign_history'))

@app.route('/campaign_history')
def campaign_history():
    try:
        campaigns_list = []
        # Iterate over all CSV files in the campaigns folder.
        for file in os.listdir(CAMPAIGNS_DIRECTORY):
            if file.endswith('.csv'):
                campaign_id = file[:-4]  # remove the '.csv' extension
                file_path = os.path.join(CAMPAIGNS_DIRECTORY, file)
                try:
                    dataframe = pd.read_csv(file_path)
                except Exception as exception:
                    app.logger.exception("Error reading campaign file %s", file)
                    continue  # Skip files that cannot be read

                total_scanned = len(dataframe)
                not_found_count = len(dataframe[dataframe["category"] == "not_found"])
                archived_count = len(dataframe[dataframe["category"] == "archived"])

                campaigns_list.append({
                    "campaign_id": campaign_id,
                    "total_scanned": total_scanned,
                    "not_found": not_found_count,
                    "archived": archived_count
                })
        # Sort campaigns in descending order (adjust sort key if needed)
        campaigns_list.sort(key=lambda campaign: campaign["campaign_id"], reverse=True)
        return render_template("campaign_history.html", campaigns=campaigns_list)
    except Exception as exception:
        app.logger.exception("Error loading campaign history.")
        flash("Error loading campaign history.", "danger")
        return redirect('/')

@app.route('/view_campaign/<campaign_id>')
def view_campaign(campaign_id):
    """Display an archived campaign in a table along with a restart option."""
    try:
        file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            campaign_data = pd.read_csv(file_path)
            data = campaign_data.to_dict(orient='records')
            statistics = {'total_scanned': len(data), 'not_found': sum(1 for item in data if item['category'] == 'not_found'),
                     'active': sum(1 for item in data if item['category'] == 'active')}
            return render_template("view_campaign.html", campaign_id=campaign_id, data=data, statistics=statistics)
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as exception:
        logging.exception("Error viewing campaign %s", campaign_id)
        flash("Error viewing campaign.", "danger")
        return redirect(url_for('campaign_history'))

@app.route('/restart_campaign/<campaign_id>')
def restart_campaign(campaign_id):
    """
    Restart an archived campaign as the active campaign.
    The campaign_id is assumed to be in the format: building_room_YYMMDD-HHMMSS.
    """
    try:
        file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            campaign_data = pd.read_csv(file_path)
            # Parse building and room from campaign_id.
            parts = campaign_id.split('_')
            if len(parts) >= 2:
                session['building'] = parts[0]
                session['room'] = parts[1]
            else:
                session['building'] = "Unknown"
                session['room'] = "Unknown"
            session['campaign_id'] = campaign_id
            global scanned_dataframe
            scanned_dataframe = campaign_data  # Set the active campaign data.
            flash("Campaign restarted successfully.", "success")
            return redirect(url_for('campaign'))
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as exception:
        logging.exception("Error restarting campaign %s", campaign_id)
        flash("Error restarting campaign.", "danger")
        return redirect(url_for('campaign_history'))

@app.route('/copy_campaign/<campaign_id>')
def copy_campaign(campaign_id):
    """
    Create a new campaign as a copy of an existing one, with a new timestamp.
    """
    try:
        file_path = os.path.join(CAMPAIGNS_DIRECTORY, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            # Load the existing campaign data
            campaign_data = pd.read_csv(file_path)
            
            # Parse building and room from campaign_id
            parts = campaign_id.split('_')
            if len(parts) >= 2:
                building = parts[0]
                room = parts[1]
            else:
                building = "Unknown"
                room = "Unknown"
            
            # Generate new campaign ID with current timestamp
            new_campaign_id = f"{building}_{room}_{datetime.datetime.now().strftime('%y%m%d-%H%M%S')}"
            
            # Set up the new campaign in the session
            session['building'] = building
            session['room'] = room
            session['campaign_id'] = new_campaign_id
            
            # Set up the global scanned_dataframe with the copied data
            global scanned_dataframe
            scanned_dataframe = campaign_data
            
            # Save the new campaign file
            save_scanned_data()
            flash("Campaign copied successfully.", "success")
            return redirect(url_for('campaign'))
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as exception:
        logging.exception("Error copying campaign %s", campaign_id)
        flash("Error copying campaign.", "danger")
        return redirect(url_for('campaign_history'))

@app.route('/upload_inventory', methods=['GET', 'POST'])
def upload_inventory():
    """Route for uploading reference inventory CSV files."""
    try:
        if request.method == 'POST':
            file = request.files.get('inventory_file')
            if file and file.filename.endswith('.csv'):
                filepath = os.path.join(DATA_DIRECTORY, file.filename)
                file.save(filepath)
                flash("Inventory CSV uploaded successfully.", "success")
                load_inventory()
            else:
                flash("Invalid file uploaded.", "danger")
        return render_template("upload_inventory.html")
    except Exception as exception:
        logging.exception("Error uploading inventory CSV.")
        flash("Error uploading inventory CSV.", "danger")
        return redirect(url_for('index'))

@app.route('/upload_campaign', methods=['GET', 'POST'])
def upload_campaign():
    """Route for uploading archived campaign CSV files."""
    try:
        if request.method == 'POST':
            file = request.files.get('campaign_file')
            if file and file.filename.endswith('.csv'):
                filepath = os.path.join(CAMPAIGNS_DIRECTORY, file.filename)
                file.save(filepath)
                flash("Campaign CSV uploaded successfully.", "success")
            else:
                flash("Invalid file uploaded.", "danger")
        return render_template("upload_campaign.html")
    except Exception as exception:
        logging.exception("Error uploading campaign CSV.")
        flash("Error uploading campaign CSV.", "danger")
        return redirect(url_for('index'))

# Configuration route for editing the barcode regular expression.
@app.route('/config', methods=['GET', 'POST'])
def config():
    """Display and allow updating of the barcode regular expression."""
    try:
        if request.method == 'POST':
            new_regex = request.form.get("barcode_regex", "").strip()
            if not new_regex:
                flash("Barcode regex cannot be empty.", "danger")
            else:
                CONFIGURATION["barcode_regex"] = new_regex
                save_configuration()
                flash("Barcode regex updated successfully.", "success")
            return redirect(url_for('config'))
        return render_template("config.html", barcode_regex=CONFIGURATION.get("barcode_regex", ""))
    except Exception as exception:
        logging.exception("Error updating config.")
        flash("Error updating configuration.", "danger")
        return redirect(url_for('index'))

# Server status route to display uptime and log output.
@app.route('/status')
def status():
    """Display the server status and log output."""
    try:
        try:
            with open("app.log", "r") as file:
                logs = file.read()
        except Exception as exception:
            logs = "Error reading logs: " + str(exception)
        uptime = datetime.datetime.now() - app_start_time
        return render_template("status.html", logs=logs, uptime=uptime)
    except Exception as exception:
        logging.exception("Error displaying server status.")
        flash("Error displaying server status.", "danger")
        return redirect(url_for('index'))

# New: Database browser route.
@app.route('/database')
def view_database():
    """
    View and filter the currently loaded reference inventory database using AG Grid.
    """
    try:
        if inventory_dataframe.empty:
            data = []
        else:
            data = inventory_dataframe.to_dict(orient='records')
        return render_template("database.html", data=data)
    except Exception as exception:
        logging.exception("Error viewing database.")
        flash("Error viewing database.", "danger")
        return redirect(url_for('index'))

@app.route('/generate_barcodes/<campaign_id>')
def generate_barcodes(campaign_id):
    """Generate a PDF of barcodes for selected items."""
    try:
        barcodes = request.args.get('barcodes', '').split(',')
        if not barcodes:
            flash("No barcodes selected.", "warning")
            return redirect(url_for('view_campaign', campaign_id=campaign_id))

        # Create a temporary directory for barcode images
        temporary_directory = os.path.join(app.root_path, 'temp')
        os.makedirs(temporary_directory, exist_ok=True)

        # Generate PDF with barcodes
        pdf_path = os.path.join(temporary_directory, f'barcodes_{campaign_id}.pdf')
        canvas_object = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter

        # Calculate layout
        margin = 50
        barcode_width = 200
        barcode_height = 100
        columns = 2
        rows = 5
        x_spacing = (width - 2 * margin) / columns
        y_spacing = (height - 2 * margin) / rows

        for index, barcode_value in enumerate(barcodes):
            # Generate barcode image
            barcode = Code128(barcode_value, writer=ImageWriter())
            barcode_path = os.path.join(temporary_directory, f'barcode_{index}')
            barcode.save(barcode_path)

            # Calculate position
            page = index // (columns * rows)
            if index % (columns * rows) == 0 and index > 0:
                canvas_object.showPage()
            
            position = index % (columns * rows)
            x = margin + (position % columns) * x_spacing
            y = height - margin - ((position // columns) + 1) * y_spacing

            # Draw barcode and text
            canvas_object.drawImage(barcode_path+'.png', x, y, barcode_width, barcode_height)
            canvas_object.drawString(x + 10, y - 20, barcode_value)

        canvas_object.save()
        return send_file(pdf_path, as_attachment=True, download_name=f'barcodes_{campaign_id}.pdf')
    except Exception as exception:
        logging.exception("Error generating barcodes")
        flash("Error generating barcodes.", "danger")
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

if __name__ == '__main__':
    app.run(debug=True)
