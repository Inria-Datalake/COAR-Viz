import os
import json
import requests
from flask import request, jsonify
from xml.sax.saxutils import unescape
from xml.dom import minidom
from app.app import app, db
from utils.db import insert_json_db, update_nb_notification, update_nb_document_failed, bump_cache_version
from app.routes.blacklist_route import get_list_blacklist
import re


# --------------------------------------------------------------------
# UTILITY HELPERS
# --------------------------------------------------------------------

def ensure_folder(path):
    """Ensure that the directory exists."""
    os.makedirs(path, exist_ok=True)
    return path


def save_xml(hal_id, xml_content, folder="./app/static/data/xml"):
    """
    Save XML content to disk, attempt pretty formatting,
    and return a dict indicating success/failure.
    """
    ensure_folder(folder)
    xml_path = os.path.join(folder, f"{hal_id}.xml")

    decoded_xml = unescape(xml_content)
    safe_xml = re.sub(r'&(?!#?\w+;)', '&amp;', decoded_xml)

    # Try pretty formatting, fallback to raw XML
    try:
        xml_parsed = minidom.parseString(safe_xml)
        pretty_xml = xml_parsed.toprettyxml(indent="  ", encoding="utf-8")
    except Exception:
        pretty_xml = safe_xml.encode("utf-8")

    try:
        with open(xml_path, "wb") as f:
            f.write(pretty_xml)

        saved = os.path.exists(xml_path) and os.path.getsize(xml_path) > 0

        return {
            "saved": saved,
            "path": xml_path,
            "error": None if saved else "File written but is empty"
        }

    except Exception as e:
        return {
            "saved": False,
            "path": xml_path,
            "error": str(e)
        }


def save_json(file, folder="./app/static/data/json"):
    """
    Save JSON content either from a Flask-uploaded file or directly from a dict.
    Return a dict describing the result.
    """
    ensure_folder(folder)

    try:
        # If Flask file upload
        if hasattr(file, "read"):
            file.seek(0)
            try:
                data_json = json.load(file)
            except Exception as e:
                return {
                    "saved": False,
                    "path": None,
                    "error": f"Invalid JSON file: {str(e)}"
                }
            file_name = getattr(file, "filename", "unnamed")
            if file_name.endswith(".software.json"):
                file_name = file_name.replace(".software", "")
        json_path = os.path.join(folder, file_name)

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data_json, f, ensure_ascii=False, indent=4)

            saved = os.path.exists(json_path) and os.path.getsize(json_path) > 0

            return {
                "saved": saved,
                "path": json_path,
                "error": None if saved else "File written but is empty"
            }

        except Exception as e:
            return {
                "saved": False,
                "path": json_path,
                "error": f"Error writing JSON file: {str(e)}"
            }

    except Exception as e:
        return {
            "saved": False,
            "path": None,
            "error": f"Unexpected error: {str(e)}"
        }


# --------------------------------------------------------------------
# MAIN ROUTE
# --------------------------------------------------------------------

@app.route('/insert_json', methods=['POST'])
def insert_json():

    blacklist = get_list_blacklist()

    final_log = {
        "step": "",
        "status": "error",
        "hal_id": "",
        "xml": "",
        "json": "",
        "db_status": "",
        "paths": {},
        "errors": []
    }

    # ------------------ 1. FILE CHECK ------------------
    final_log["step"] = "File checker"

    if "file" not in request.files:
        final_log["errors"].append("No file found in request")
        update_nb_document_failed(final_log, db)
        print("🟥", json.dumps(final_log, indent=4, ensure_ascii=False), "\n")
        return jsonify(final_log), 400

    file = request.files["file"]
    hal_id = request.form.get("document_id")
    if hal_id.endswith(".software"):
        hal_id = hal_id.replace(".software", "")
    final_log["hal_id"] = hal_id

    # ------------------ 2. XML DOWNLOAD ------------------
    final_log["step"] = "XML download from HAL"

    url = "https://api.archives-ouvertes.fr/search/"
    hal_clean = hal_id[:-2] if hal_id[-2]=="v" else hal_id

    params = {"q": f"halId_id:{hal_clean}", "fl": "label_xml", "wt": "xml-tei"}

    try:
        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            final_log["errors"].append(f"Failed to download XML for {hal_id}")
            update_nb_document_failed(final_log, db)
            print("🟥", json.dumps(final_log, indent=4, ensure_ascii=False), "\n")
            return jsonify(final_log), 500

        data = response.text
        decoded_xml = unescape(data)

        xml_result = save_xml(hal_id, decoded_xml)

        if xml_result["saved"]:
            final_log["xml"] = "saved"
            final_log["paths"]["xml"] = xml_result["path"]
            xml_path = xml_result["path"]
        else:
            final_log["xml"] = "failed"
            final_log["errors"].append(xml_result["error"])
            final_log["paths"]["xml"] = xml_result["path"]
            xml_path = None
            raise Exception(xml_result["path"])


    except Exception as e:
        final_log["errors"].append(f"Exception while downloading XML: {str(e)}")
        update_nb_document_failed(final_log, db)
        print("🟥", json.dumps(final_log, indent=4, ensure_ascii=False), "\n")
        return jsonify(final_log), 500

    # ------------------ 3. JSON SAVE ------------------
    final_log["step"] = "Saving JSON file"

    try:
        json_result = save_json(file)

        if json_result["saved"]:
            final_log["json"] = "saved"
            final_log["paths"]["json"] = json_result["path"]
            json_path = json_result["path"]
        else:
            final_log["json"] = "failed"
            final_log["errors"].append(json_result["error"])
            final_log["paths"]["json"] = json_result["path"]
            json_path = None
            raise Exception(json_result["path"])


    except Exception as e:
        final_log["errors"].append(f"Exception while saving JSON: {str(e)}")
        update_nb_document_failed(final_log, db)
        print("🟥", json.dumps(final_log, indent=4, ensure_ascii=False), "\n")
        return jsonify(final_log), 500

    # ------------------ 4. DATABASE INSERTION ------------------
    final_log["step"] = "Database insertion"

    if json_path is None and xml_path is None:
        print("🟥", json.dumps(final_log, indent=4, ensure_ascii=False), "\n")
        update_nb_document_failed(final_log, db)
        return jsonify(final_log), 500

    result = insert_json_db(json_path, xml_path, db, blacklist)

    if result[0] == "success":

        try:
            if os.path.exists(xml_path):
                os.remove(xml_path)
            if os.path.exists(json_path):
                os.remove(json_path)
        except Exception as e:
            final_log['errors'].append(f"Document {hal_id} wasn't removed.")

        update_nb_notification(db, hal_id)
        bump_cache_version(db)  # invalidate cached dashboard aggregations across all workers
        final_log["status"] = "success"
        final_log["errors"].append(result[1])
        final_log["db_status"] = "inserted"
        final_log["step"] = "Completed"
        print("🟩",json.dumps(final_log, indent=4, ensure_ascii=False),"\n")
        return jsonify(final_log), 201

    else:
        final_log["status"] = "error"
        final_log["errors"].append(result[1])
        final_log["step"] = result[0]
        print("🟥",json.dumps(final_log, indent=4, ensure_ascii=False),"\n")
        update_nb_document_failed(final_log, db)
        return jsonify(final_log), 409

