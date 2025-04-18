from flask import Flask, request, render_template, jsonify, send_from_directory, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import os
import json
import re
import uuid
import logging
import base64
import requests

# Load environment variables
load_dotenv()

# Flask app configuration
application = Flask(__name__)  # ✅ Required for Elastic Beanstalk
CORS(application)
application.config['UPLOAD_FOLDER'] = 'temp_uploads'
application.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # ✅ 20MB upload limit
os.makedirs(application.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(application.config['UPLOAD_FOLDER'], 'chunks'), exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI client
client = OpenAI()

# ---------------- ROUTES ---------------- #

@application.route("/")
def home():
    search_term = request.args.get("search", "")
    return render_template("index.html", initial_search=search_term)

@application.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)

@application.route("/api/chunked_upload", methods=["POST"])
def chunked_upload():
    """Endpoint for handling chunked uploads to bypass Nginx limits"""
    logger.info("Chunked upload API call received")
    
    # Get the chunk data
    chunk_data = request.get_data()
    
    # Get metadata from headers
    filename = request.headers.get('X-Filename', 'unknown')
    chunk_index = int(request.headers.get('X-Chunk-Index', '0'))
    total_chunks = int(request.headers.get('X-Total-Chunks', '1'))
    
    logger.info(f"Received chunk {chunk_index+1}/{total_chunks} for file {filename}")
    
    # Create temp directory if it doesn't exist
    temp_dir = os.path.join(application.config['UPLOAD_FOLDER'], 'chunks')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Save the chunk
    chunk_path = os.path.join(temp_dir, f"{filename}.part{chunk_index}")
    with open(chunk_path, 'wb') as f:
        f.write(chunk_data)
    
    # Just return success - processing will happen in process_chunked_upload
    return jsonify({
        "success": True, 
        "chunk_received": chunk_index,
        "remaining_chunks": total_chunks - chunk_index - 1
    })

@application.route("/api/process_chunked_upload", methods=["POST"])
def process_chunked_upload():
    """Process a completed chunked upload"""
    logger.info("Processing chunked upload")
    
    data = request.json
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename is required"}), 400
        
    filename = data['filename']
    final_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
    
    # Check if we need to combine chunks
    temp_dir = os.path.join(application.config['UPLOAD_FOLDER'], 'chunks')
    chunk_files = [f for f in os.listdir(temp_dir) if f.startswith(filename + '.part')]
    
    if not chunk_files:
        return jsonify({"error": "No chunks found for this file"}), 404
        
    # Sort chunk files by index
    chunk_files.sort(key=lambda x: int(x.split('.part')[1]))
    
    logger.info(f"Combining {len(chunk_files)} chunks for {filename}")
    
    # Combine chunks
    with open(final_path, 'wb') as outfile:
        for chunk_file in chunk_files:
            chunk_path = os.path.join(temp_dir, chunk_file)
            with open(chunk_path, 'rb') as infile:
                outfile.write(infile.read())
            os.remove(chunk_path)
    
    try:
        # Process the file
        logger.info(f"Processing combined file: {final_path}")
        base64_image = encode_image_to_base64(final_path)
        extracted_text = query_openai_vision(base64_image)
        cleaned_text = extracted_text.strip().upper()
        logger.info(f"Extracted text: {cleaned_text}")

        match = re.match(r"^([A-Z]+)(\d+)$", cleaned_text)
        if match:
            cleaned_text = f"{match.group(1)}-{match.group(2)}"

        if cleaned_text == "UNKNOWN" or not cleaned_text:
            return jsonify({"error": "Unable to read medication name or code from image"}), 404

        # Now use the existing function to get medication info
        summary, similar_meds = get_gpt_summary(cleaned_text)
        
        return jsonify({
            "code": cleaned_text,
            "name": cleaned_text,
            "summary": summary,
            "similar_meds": similar_meds
        })
        
    except Exception as e:
        logger.error(f"Image processing error: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up the file
        if os.path.exists(final_path):
            os.remove(final_path)

@application.route("/api/explain", methods=["POST"])
def explain_api():
    data = request.json
    raw_code = data.get("code", "").upper()
    clean = re.sub(r"[^A-Z0-9]", "", raw_code)
    match = re.match(r"^([A-Z]+)(\d+)$", clean)
    code = f"{match.group(1)}-{match.group(2)}" if match else clean

    if not code:
        return jsonify({"error": "No code provided"}), 400

    summary, similar_meds = get_gpt_summary(code)

    logger.info(f"Medication explained via GPT: {code}")

    return jsonify({
        "code": code,
        "name": code,
        "summary": summary,
        "category": "See summary",
        "uses": [],
        "similar_meds": similar_meds
    })

@application.route("/api/voice_search", methods=["POST"])
def voice_search():
    if "audio" not in request.files:
        return jsonify({"error": "No audio provided"}), 400

    audio_file = request.files["audio"]
    filename = f"voice_{uuid.uuid4().hex}.webm"
    path = os.path.join(application.config["UPLOAD_FOLDER"], filename)
    audio_file.save(path)

    try:
        with open(path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text"
            )
        return jsonify({"transcript": transcript.strip()})
    except Exception as e:
        logger.error(f"Voice transcription failed: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(path):
            os.remove(path)

@application.route("/api/identify_pill", methods=["POST"])
def identify_pill():
    logger.info("API call received: /api/identify_pill")
    
    if 'image' not in request.files:
        logger.error("No image file in request")
        return jsonify({"error": "No image provided"}), 400

    image_file = request.files['image']
    logger.info(f"Received file: {image_file.filename}")
    
    # Get file size
    image_file.seek(0, os.SEEK_END)
    file_size = image_file.tell()
    image_file.seek(0)
    logger.info(f"File size: {file_size} bytes")
    
    filename = f"{uuid.uuid4().hex}{os.path.splitext(image_file.filename)[1]}"
    image_path = os.path.join(application.config['UPLOAD_FOLDER'], secure_filename(filename))
    logger.info(f"Saving to: {image_path}")
    
    try:
        image_file.save(image_path)
        logger.info("File saved successfully")
        
        base64_image = encode_image_to_base64(image_path)
        extracted_text = query_openai_vision(base64_image)
        cleaned_text = extracted_text.strip().upper()
        logger.info(f"Extracted text: {cleaned_text}")

        match = re.match(r"^([A-Z]+)(\d+)$", cleaned_text)
        if match:
            cleaned_text = f"{match.group(1)}-{match.group(2)}"

        if cleaned_text == "UNKNOWN" or not cleaned_text:
            return jsonify({"error": "Unable to read medication name or code from image"}), 404

        summary, similar_meds = get_gpt_summary(cleaned_text)
        
        return jsonify({
            "code": cleaned_text,
            "name": cleaned_text,
            "summary": summary,
            "similar_meds": similar_meds
        })
        
    except Exception as e:
        logger.error(f"Image processing error: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)

# ---------------- UTILITIES ---------------- #

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def query_openai_vision(base64_image):
    prompt = """
You are a clinical assistant. Analyze this medication image and extract the most **prominent medication name or code** you can see.

✔️ If you see a **medication code** (e.g., AMLO-10, IBU-200), return that.
✔️ If no code is present but a **medication name** is visible (e.g., Amlodipine, Ibuprofen, ), return the name.
❌ Do not return dosage, descriptions, or manufacturer names unless they are part of the name/code.
🎯 Return only the name or code as a single clean string.
If nothing is clearly visible or readable, respond with: UNKNOWN
"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        }],
        max_tokens=50
    )
    return response.choices[0].message.content.strip()

def get_gpt_summary(code):
    logger.info(f"📦 Generating summary for code: {code}")
    
    prompt = f""" You are a clinical pharmacist assistant.  A user has entered or scanned the medication code: '{code}'.  Your task is to: 
1. Generate a detailed explanation of this medication based **only on the code or name** and its most likely real-world match. If it's unknown or rare, provide your best educated estimate. 
2. Include the manufacturer/pharmaceutical company that produces this medication.
3. In the **Composition** section, you MUST wrap EVERY active compound name in a clickable HTML hyperlink with this exact format:
   <a href="https://molescope.efraprojects.com/viewer?compound=COMPOUNDNAME" target="_blank">Compound Name</a>
   For example: <a href="https://molescope.efraprojects.com/viewer?compound=CAFFEINE" target="_blank">Caffeine</a>
   The compound name in the URL must be ALL CAPS with no spaces.
4. Then suggest **6 truly relevant** medications that are:
   - in the same drug class,
   - have similar clinical use,
   - or represent a brand/generic/alternative.

### RESPONSE FORMAT
Use these tags exactly to separate your sections:

[SUMMARY_START]
<h4>Purpose</h4>
<p>...</p>
<h4>Manufacturer</h4>
<p>...</p>
<h4>Dosage Information</h4>
<p>...</p>
<h4>Composition</h4>
<ul><li>...</li></ul>
<h4>Common Side Effects</h4>
<ul><li>...</li></ul>
<h4>Important Drug Interactions</h4>
<ul><li>...</li></ul>
<h4>Storage Recommendations</h4>
<p>...</p>
<h4>Cost and Alternatives</h4>
<p>...</p>
<h4>Important Notes</h4>
<p>...</p>
[SUMMARY_END]

[SIMILARS_START]
[
  {{
    "code": "SAMPLE-1",
    "name": "SampleDrug 10mg",
    "category": "NSAID",
    "relation": "Alternative"
  }},
  {{
    "code": "SAMPLE-2",
    "name": "SampleGeneric 500mg",
    "category": "Analgesic",
    "relation": "Generic"
  }},
  {{
    "code": "SAMPLE-3",
    "name": "SampleBrand",
    "category": "Analgesic",
    "relation": "Brand name"
  }}
]
[SIMILARS_END]
"""
    
    try:
        logger.info("⏳ Sending request to OpenAI...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        logger.info("✅ Received response from OpenAI")
        
        content = response.choices[0].message.content
        
        summary = ""
        similars = []
        
        if "[SUMMARY_START]" in content and "[SUMMARY_END]" in content:
            summary = content.split("[SUMMARY_START]")[1].split("[SUMMARY_END]")[0].strip()
            logger.info("📄 Extracted summary section")
            
            # Additional processing to ensure all compounds are hyperlinked
            # This is a fallback in case OpenAI misses some compounds
            common_compounds = ["Acetaminophen", "Ibuprofen", "Aspirin", "Metoprolol", "Lisinopril", 
                              "Atorvastatin", "Metformin", "Omeprazole", "Simvastatin", "Losartan",
                              "Albuterol", "Amlodipine", "Levothyroxine", "Gabapentin", "Hydrochlorothiazide",
                              "Osimertinib"] # Added Osimertinib for Tagrisso example
            
            # Check if we have a composition section to process
            if "<h4>Composition</h4>" in summary:
                composition_section = summary.split("<h4>Composition</h4>")[1].split("<h4>")[0]
                
                # Process each common compound
                for compound in common_compounds:
                    # Check if compound exists in composition but isn't already linked
                    if compound in composition_section and f"compound={compound.upper()}" not in composition_section:
                        # Create the hyperlink
                        hyperlink = f'<a href="https://molescope.efraprojects.com/viewer?compound={compound.upper()}" target="_blank">{compound}</a>'
                        # Replace the compound name with the hyperlink
                        composition_section = composition_section.replace(compound, hyperlink)
                        logger.info(f"🔗 Injected hyperlink for {compound}")
                
                # Update the summary with the modified composition section
                summary = summary.split("<h4>Composition</h4>")[0] + "<h4>Composition</h4>" + composition_section + "<h4>" + summary.split("<h4>Composition</h4>")[1].split("<h4>", 1)[1]
        
        if "[SIMILARS_START]" in content and "[SIMILARS_END]" in content:
            raw_json = content.split("[SIMILARS_START]")[1].split("[SIMILARS_END]")[0].strip()
            try:
                similars = json.loads(raw_json)
                logger.info(f"🧬 Parsed {len(similars)} similar medications")
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse similar meds JSON: {e}")
        
        return summary, similars
    
    except Exception as e:
        logger.error(f"🔥 OpenAI GPT error for {code}: {e}")
        return "<p>Error generating medication summary. Try again later.</p>", []


# ---------------- ERROR HANDLING ---------------- #

@application.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "Uploaded file is too large. Max size is 20MB."}), 413

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    application.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))