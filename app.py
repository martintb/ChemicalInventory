import os
import datetime
import logging
import json
import re
import pandas as pd
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
inventory_df = pd.DataFrame()  # Combined reference inventory DataFrame
# scanned_df holds the active campaign's scan log.
scanned_df = pd.DataFrame(columns=[
    "barcode", "timestamp", "building", "room", "location", "category"
])

BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
CAMPAIGNS_DIR = os.path.join(BASE_DIR, "campaigns")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")  # Configuration file

# Ensure required folders exist
for folder in [DATA_DIR, CAMPAIGNS_DIR, UPLOADS_DIR]:
    os.makedirs(folder, exist_ok=True)

# --- Configuration Handling ---
CONFIG = {}

def load_config():
    global CONFIG
    if not os.path.exists(CONFIG_FILE):
        default_config = {"barcode_regex": "^[A-Za-z]?\\d{4,6}$"}
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f)
        CONFIG = default_config
        logging.info("Created default config file.")
    else:
        with open(CONFIG_FILE, "r") as f:
            CONFIG = json.load(f)
        logging.info("Loaded config file.")

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(CONFIG, f)
    logging.info("Saved updated config file.")

# Load configuration on startup.
load_config()

# --- Utility Functions ---

def load_inventory():
    """Load all CSV reference inventory files from DATA_DIR into a single DataFrame."""
    global inventory_df
    try:
        csv_files = [
            os.path.join(DATA_DIR, f)
            for f in os.listdir(DATA_DIR) if f.endswith('.csv')
        ]
        df_list = []
        for file in csv_files:
            try:
                df = pd.read_csv(file)
                df_list.append(df)
            except Exception as e:
                logging.error(f"Error reading {file}: {e}")
        if df_list:
            inventory_df = pd.concat(df_list, ignore_index=True)
            logging.info(f"Loaded inventory with {len(inventory_df)} rows from {len(csv_files)} files.")
        else:
            inventory_df = pd.DataFrame()
    except Exception as e:
        logging.exception("Failed to load inventory.")
        inventory_df = pd.DataFrame()

# Load inventory on startup.
load_inventory()

def save_scanned_data():
    """Save the current campaign's scanned data to a CSV file in CAMPAIGNS_DIR."""
    try:
        campaign_id = session.get('campaign_id')
        if campaign_id:
            file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
            scanned_df.to_csv(file_path, index=False)
            logging.info(f"Campaign {campaign_id} saved with {len(scanned_df)} scans.")
    except Exception as e:
        logging.exception("Error saving scanned campaign data.")

def archive_campaign():
    """Archive (save) the current campaign."""
    save_scanned_data()

def update_campaign_stats():
    """Update campaign statistics in the session."""
    global scanned_df
    session['total_scanned'] = len(scanned_df)
    session['not_found'] = len(scanned_df[scanned_df['category'] == 'not_found'])
    session['found'] = len(scanned_df[scanned_df['category'] == 'found'])

def get_campaign_stats():
    """Get current campaign statistics."""
    return {
        'total_scanned': session.get('total_scanned', 0),
        'not_found': session.get('not_found', 0),
        'found': session.get('found', 0)
    }

# --- Global Error Handler ---
@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled Exception: %s", e)
    return render_template("error.html", error=str(e)), 500

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
        if not inventory_df.empty and "Barcode ID - Container" in inventory_df.columns:
            unique_count = inventory_df["Barcode ID - Container"].nunique()

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
                global scanned_df
                scanned_df = pd.DataFrame(columns=[
                    "barcode", "timestamp", "building", "room", "location", "category"
                ])
                archive_campaign()  # Save the new (empty) campaign file.
                return redirect(url_for('campaign'))
            elif 'upload_inventory' in request.form:
                file = request.files.get('inventory_file')
                if file and file.filename.endswith('.csv'):
                    filepath = os.path.join(DATA_DIR, file.filename)
                    file.save(filepath)
                    flash("Inventory CSV uploaded successfully.", "success")
                    load_inventory()  # Reload reference database.
                    if not inventory_df.empty and "Barcode ID - Container" in inventory_df.columns:
                        unique_count = inventory_df["Barcode ID - Container"].nunique()
                else:
                    flash("Invalid file or no file selected for inventory.", "danger")
            elif 'upload_campaign' in request.form:
                file = request.files.get('campaign_file')
                if file and file.filename.endswith('.csv'):
                    filepath = os.path.join(CAMPAIGNS_DIR, file.filename)
                    file.save(filepath)
                    flash("Campaign CSV uploaded successfully.", "success")
                else:
                    flash("Invalid file or no file selected for campaign.", "danger")
        return render_template("index.html", unique_count=unique_count)
    except Exception as e:
        logging.exception("Error in index route.")
        flash("An error occurred in the index route.", "danger")
        return render_template("index.html", unique_count=unique_count)

@app.route('/campaign')
@app.route('/campaign/<campaign_id>')
def campaign(campaign_id=None):
    if campaign_id:
        session['campaign_id'] = campaign_id
        global scanned_df
        file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            scanned_df = pd.read_csv(file_path)
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

import os
import datetime
import pandas as pd
from flask import request, jsonify, session

@app.route('/scan', methods=['POST'])
def scan():
    try:
        data = request.get_json()
        barcode = data.get("barcode", "").strip()
        if not barcode:
            return jsonify({"success": False, "message": "No barcode provided."}), 400

        global scanned_df, inventory_df

        # Check if this barcode has already been scanned.
        if not scanned_df.empty and barcode in scanned_df["barcode"].values:
            return jsonify({
                "success": True,
                "duplicate": True,
                "message": "Barcode already scanned."
            })

        # Get scan metadata from the session.
        building = session.get("building", "")
        room = session.get("room", "")
        location = session.get("location", "")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Look up the barcode in the reference inventory.
        matched = pd.DataFrame()
        if not inventory_df.empty and "Barcode ID - Container" in inventory_df.columns:
            matched = inventory_df[inventory_df["Barcode ID - Container"].astype(str) == barcode]

        # Determine the category based on the lookup.
        if not matched.empty:
            statuses = matched["Status - Container"].astype(str).str.lower()
            if any(statuses == "archived"):
                category = "archived"
            else:
                category = "found"
        else:
            category = "not_found"

        # Build the new scan row with both scan metadata and empty reference fields.
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

        # If a matching reference row was found, merge its data into new_entry.
        if not matched.empty:
            # For simplicity, take the first matching row.
            ref_row = matched.iloc[0].to_dict()
            for key in [
                "Status - Container", "Time Sensitive - Container", "Location - Container",
                "Owner Name - Container", "Product Identifier - Product", "Current Quantity - Container",
                "Unit - Container", "NFPA 704 Health Hazard - Product", "NFPA 704 Flammability Hazard - Product"
            ]:
                new_entry[key] = ref_row.get(key, "")

        # Append the new row to the campaign DataFrame using pd.concat.
        new_df = pd.DataFrame([new_entry])
        scanned_df = pd.concat([scanned_df, new_df], ignore_index=True)

        # Save the updated campaign data to CSV.
        campaign_id = session.get("campaign_id")
        if campaign_id:
            file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
            scanned_df.to_csv(file_path, index=False)

        # Recalculate campaign statistics.
        total_scanned = len(scanned_df)
        found_count = len(scanned_df[scanned_df["category"] == "found"])
        not_found_count = len(scanned_df[scanned_df["category"] == "not_found"])
        campaign_stats = {
            "total_scanned": total_scanned,
            "found": found_count,
            "not_found": not_found_count
        }

        # Build the response.
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
        response["campaign_stats"] = campaign_stats

        return jsonify(response)
    except Exception as e:
        app.logger.exception("Error processing scan.")
        return jsonify({"success": False, "message": "Internal server error during scan."}), 500


@app.route('/api/scanned_data')
def api_scanned_data():
    """Return the current campaign's scanned data as JSON (for AG Grid)."""
    try:
        data = scanned_df.to_dict(orient='records')
        return jsonify({
            'data': data,
            'campaign_stats': get_campaign_stats()
        })
    except Exception as e:
        logging.exception("Error fetching scanned data.")
        return jsonify([])

@app.route('/download')
def download():
    """Download the active campaign CSV."""
    try:
        campaign_id = session.get('campaign_id')
        if campaign_id:
            file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)
            else:
                flash("Campaign file not found.", "danger")
        return redirect(url_for('campaign'))
    except Exception as e:
        logging.exception("Error during download.")
        flash("Error during download.", "danger")
        return redirect(url_for('campaign'))

@app.route('/download_campaign/<campaign_id>')
def download_campaign(campaign_id):
    """Download an archived campaign CSV (by campaign_id)."""
    try:
        file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as e:
        logging.exception("Error downloading campaign %s", campaign_id)
        flash("Error during download.", "danger")
        return redirect(url_for('campaign_history'))

@app.route('/campaign_history')
def campaign_history():
    """Display a list of archived campaigns (CSV files in CAMPAIGNS_DIR)."""
    try:
        campaigns = []
        for file in os.listdir(CAMPAIGNS_DIR):
            if file.endswith('.csv'):
                campaigns.append(file)
        campaigns.sort(reverse=True)
        return render_template("campaign_history.html", campaigns=campaigns)
    except Exception as e:
        logging.exception("Error loading campaign history.")
        flash("Error loading campaign history.", "danger")
        return redirect(url_for('index'))

@app.route('/view_campaign/<campaign_id>')
def view_campaign(campaign_id):
    """Display an archived campaign in a table along with a restart option."""
    try:
        file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
        if os.path.exists(file_path):
            campaign_data = pd.read_csv(file_path)
            data = campaign_data.to_dict(orient='records')
            stats = {'total_scanned': len(data), 'not_found': sum(1 for item in data if item['category'] == 'not_found'),
                     'found': sum(1 for item in data if item['category'] == 'found')}
            return render_template("view_campaign.html", campaign_id=campaign_id, data=data, stats=stats)
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as e:
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
        file_path = os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.csv")
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
            global scanned_df
            scanned_df = campaign_data  # Set the active campaign data.
            flash("Campaign restarted successfully.", "success")
            return redirect(url_for('campaign'))
        else:
            flash("Campaign file not found.", "danger")
            return redirect(url_for('campaign_history'))
    except Exception as e:
        logging.exception("Error restarting campaign %s", campaign_id)
        flash("Error restarting campaign.", "danger")
        return redirect(url_for('campaign_history'))

@app.route('/upload_inventory', methods=['GET', 'POST'])
def upload_inventory():
    """Route for uploading reference inventory CSV files."""
    try:
        if request.method == 'POST':
            file = request.files.get('inventory_file')
            if file and file.filename.endswith('.csv'):
                filepath = os.path.join(DATA_DIR, file.filename)
                file.save(filepath)
                flash("Inventory CSV uploaded successfully.", "success")
                load_inventory()
            else:
                flash("Invalid file uploaded.", "danger")
        return render_template("upload_inventory.html")
    except Exception as e:
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
                filepath = os.path.join(CAMPAIGNS_DIR, file.filename)
                file.save(filepath)
                flash("Campaign CSV uploaded successfully.", "success")
            else:
                flash("Invalid file uploaded.", "danger")
        return render_template("upload_campaign.html")
    except Exception as e:
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
                CONFIG["barcode_regex"] = new_regex
                save_config()
                flash("Barcode regex updated successfully.", "success")
            return redirect(url_for('config'))
        return render_template("config.html", barcode_regex=CONFIG.get("barcode_regex", ""))
    except Exception as e:
        logging.exception("Error updating config.")
        flash("Error updating configuration.", "danger")
        return redirect(url_for('index'))

# Server status route to display uptime and log output.
@app.route('/status')
def status():
    """Display the server status and log output."""
    try:
        try:
            with open("app.log", "r") as f:
                logs = f.read()
        except Exception as e:
            logs = "Error reading logs: " + str(e)
        uptime = datetime.datetime.now() - app_start_time
        return render_template("status.html", logs=logs, uptime=uptime)
    except Exception as e:
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
        if inventory_df.empty:
            data = []
        else:
            data = inventory_df.to_dict(orient='records')
        return render_template("database.html", data=data)
    except Exception as e:
        logging.exception("Error viewing database.")
        flash("Error viewing database.", "danger")
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
