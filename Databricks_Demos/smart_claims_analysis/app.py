from flask import Flask, render_template, request, jsonify, request, send_file, abort
from genie_embedding import get_genie_response
from dotenv import load_dotenv
import os
import logging
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
from databricks.sdk.config import Config
from datetime import datetime
import copy
import json
from io import BytesIO
import random
import time

# Initialize Flask app
app = Flask(__name__, static_url_path='/static', static_folder='static')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure static directory exists
os.makedirs('static/images', exist_ok=True)

# Pull Environment Variables
load_dotenv()
databricks_host = "https://e2-demo-west.cloud.databricks.com"

# Get the environment variables
ENVIRONMENT = os.getenv("ENV", "prod")  # Default to 'prod' if ENV is not set
DATABRICKS_CLI_PROFILE = os.getenv("DATABRICKS_CLI_PROFILE", "DEFAULT")

# Initialize WorkspaceClient appropriately for the environment
config: Config = None
workspace_client: WorkspaceClient = None
current_user = None
if ENVIRONMENT == "dev":
    config = Config(profile=DATABRICKS_CLI_PROFILE)
    workspace_client = WorkspaceClient(config=config)
    current_user = workspace_client.current_user.me().as_dict()
    logger.info(f"Using Databricks host: {config.host}")
    logger.info(f"Using Databricks profile: {config.profile}")
else:
    workspace_client = WorkspaceClient()

# Rename 'w' to 'workspace_client' for consistency
w = workspace_client

def extract_email(email):
    if not email:
        return "Unknown User"
    try:
        local_part = email.split('@')[0]
        first_name, last_name = local_part.split('.')
        return f"{first_name.capitalize()} {last_name.capitalize()}"
    except Exception:
        return local_part

def extract_first_name(email):
    if not email:
        return "Unknown"
    try:
        local_part = email.split('@')[0]
        first_name, last_name = local_part.split('.')
        return f"{first_name.capitalize()}"
    except Exception:
        return local_part

# Function to call the model endpoint
def call_model_endpoint(endpoint_name, messages, max_tokens=300, timeout_minutes=3):
    chat_messages = [
        ChatMessage(
            content=message["content"],
            role=ChatMessageRole[message["role"].upper()]
        ) if isinstance(message, dict) else ChatMessage(content=message, role=ChatMessageRole.USER)
        for message in messages
    ]
    response = w.serving_endpoints.query(
        name=endpoint_name,
        messages=chat_messages,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

# Function to run the chain
def run_chain(question, answer, **kwargs):
    clean_content = f"Your job is to use this answer: ({answer}). Use it to respond to this question:({question}). If the answer is too long or too much JSON, just read through it and give me a summary of the responses to the best of your ability. For example, just give one row in reasonable English and then stop."
    messages = [
        {"role": "system", "content": clean_content},
        {"role": "user", "content": clean_content}
    ]
    response = call_model_endpoint("databricks-meta-llama-3-1-405b-instruct", messages)
    return response

@app.route('/genie')
def home():
    forwarded_email = request.headers.get('X-Forwarded-Email')
    name = extract_email(forwarded_email)
    first_name = extract_first_name(forwarded_email)
    app = request.args.get('app', 'va')
    if app == 'va':
        title_name = 'Claims Investigation'
    else:
        title_name = 'Long Term Care Incidence'
    return render_template('genie.html', user=name, first_name=first_name, app=app, title_name=title_name)

@app.route('/analytics')
@app.route('/')
def analytics():
    """
    Render the Analytics page with an embedded Databricks dashboard.
    """
    app = request.args.get('app', 'va')
    dashboard_name = 'Claims Dashboard 📊' if app == 'va' else 'Long Term Care Incidence'
    forwarded_user = request.headers.get('X-Forwarded-Preferred-Username')
    
    return render_template('analytics.html', 
                         user=extract_email(forwarded_user),
                         first_name=extract_first_name(forwarded_user),
                         dashboard_name=dashboard_name)

@app.route('/metrics')
def metrics():
    forwarded_user = request.headers.get('X-Forwarded-Preferred-Username')
    full_name = extract_email(forwarded_user)
    dashboard_name = "📊 Metrics and KPIs Dashboard"
    return render_template('metrics.html', user=full_name, user_name=full_name, dashboard_name=dashboard_name)

@app.route('/api/openai/chat', methods=['POST'])
def openai_chat():
    """
    Handle chat requests using OpenAI's Chat Completion API.
    """
    data = request.json  # Get JSON payload from frontend
    user_message = data.get('question', '')  # User's input message

    if not user_message:
        return jsonify({"error": "No message provided"}), 400
    try:
        ai_message = run_chain(user_message)
        return jsonify({"content": ai_message})  # Send AI response back to frontend
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/genie/start_conversation', methods=['POST'])
def genie_start_conversation():
    """
    Start a new conversation with Genie.
    """
    try:
        data = request.json
        question = data.get('question', '')
        app = data.get('app', 'va')  # Default to 'va' if not specified

        if not question:
            logger.error("No question provided in request")
            return jsonify({"error": "No question provided"}), 400

        # Log the incoming request
        logger.info(f"Starting new conversation for app {app}")
        logger.info(f"Question: {question}")

        # Get response from Genie
        response = get_genie_response(question, app=app)
        
        if response.get("status") == "ERROR":
            logger.error(f"Genie API error: {response.get('error')}")
            return jsonify({"error": response.get("error")}), 500
            
        # If no content in response, return error
        if not response.get("content"):
            logger.error("No content in Genie response")
            return jsonify({"error": "Failed to get response from Genie"}), 500
            
        # Return the response with conversation ID
        return jsonify({
            "content": response.get("content"),
            "conversation_id": response.get("conversation_id"),
            "query_result": response.get("query_result"),
            "description": response.get("description")
        })

    except Exception as e:
        logger.exception("Unexpected error in start_conversation")
        return jsonify({"error": str(e)}), 500

@app.route('/api/genie/continue_conversation', methods=['POST'])
def genie_continue_conversation():
    """
    Continue an existing conversation with Genie.
    """
    try:
        data = request.json
        question = data.get('question', '')
        conversation_id = data.get('conversation_id')
        app = data.get('app', 'va')  # Default to 'va' if not specified

        if not question:
            logger.error("No question provided in request")
            return jsonify({"error": "No question provided"}), 400
            
        if not conversation_id:
            logger.error("No conversation_id provided in request")
            return jsonify({"error": "No conversation_id provided"}), 400

        # Log the incoming request
        logger.info(f"Continuing conversation {conversation_id} for app {app}")
        logger.info(f"Question: {question}")

        # Get response from Genie
        response = get_genie_response(question, conversation_id=conversation_id, app=app)
        
        if response.get("status") == "ERROR":
            logger.error(f"Genie API error: {response.get('error')}")
            return jsonify({"error": response.get("error")}), 500
            
        # If no content in response, return error
        if not response.get("content"):
            logger.error("No content in Genie response")
            return jsonify({"error": "Failed to get response from Genie"}), 500
            
        # Return the response with conversation ID
        return jsonify({
            "content": response.get("content"),
            "conversation_id": response.get("conversation_id"),
            "query_result": response.get("query_result"),
            "description": response.get("description")
        })

    except Exception as e:
        logger.exception("Unexpected error in continue_conversation")
        return jsonify({"error": str(e)}), 500

@app.route('/images/<filename>')
def serve_image(filename):
    try:
        # Ensure we have a valid workspace client
        global w
        if w is None:
            w = WorkspaceClient()
        
        volume_path = f"/Volumes/demos_genie/dbdemos_fsi_smart_claims/volume_claims/Accidents/images/{filename}"
        response = w.files.download(volume_path)
        image_bytes = response.contents.read()
        
        # Create response with the image
        response = send_file(
            BytesIO(image_bytes),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=filename
        )
        
        # Add caching headers
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error serving image {filename}: {e}")
        # Try to reconnect workspace client on error
        try:
            w = WorkspaceClient()
        except:
            pass
        abort(404)

@app.route('/static/images/<filename>')
def serve_static_image(filename):
    try:
        response = send_file(f'static/images/{filename}', mimetype='image/jpeg')
        # Add cache control headers
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        app.logger.error(f"Error serving static image {filename}: {e}")
        abort(404)

model_payoff = [
    {
        "claim_number": "6e593b17-a3c4-47e6-a153-a1efb05e9511",
        "image_url": "/images/1_Low.jpg",
        "image_description": "Red vehicle with minor damage to rear bumper corner. Paint damage and small crack visible along panel seam.",
        "witness_report": "Recent damage to rear bumper from parking lot incident. Small crack where panels meet with some paint scratching.",
        "incident_data": {
            "date": "2025-03-15 09:30:00",
            "location": "Chicago, IL",
            "weather_data": {
                "conditions": "Clear",
                "visibility": "Excellent",
                "road_conditions": "Dry"
            }
        }
    },
    {
        "claim_number": "8f47b14c-826f-4d59-9935-b54e9ec7d2fa",
        "image_url": "/images/2_Medium.jpg",
        "image_description": "White vehicle with front bumper and headlight assembly damage. Multiple impact points visible with both fresh damage and weathered areas.",
        "witness_report": "Single incident caused crack near headlight during parking. No previous damage to report.",
        "incident_data": {
            "date": "2025-03-20 18:45:00",
            "location": "Boston, MA",
            "weather_data": {
                "conditions": "Heavy Rain",
                "visibility": "Poor",
                "road_conditions": "Wet"
            }
        }
    },
    {
        "claim_number": "c2e94b24-d19a-4cb9-90c2-7b89e8d38c43",
        "image_url": "/images/3_High.jpg",
        "image_description": "White vehicle with extensive side impact damage. Severe deformation of door panel and possible structural frame damage.",
        "witness_report": "Minor collision while parking. Just scraped against a pole.",
        "incident_data": {
            "date": "2025-03-25 22:15:00",
            "location": "Denver, CO",
            "weather_data": {
                "conditions": "Light Snow",
                "visibility": "Limited",
                "road_conditions": "Icy"
            }
        }
    }
]

review_log = []
comparison_review_log = []

def compute_json_diff(data):
    discrepancies = []
    for item in data:
        weather_data = item["incident_data"]["weather_data"]
        weather_context = f"AccuWeather historical data for the incident time shows {weather_data['conditions'].lower()} conditions, {weather_data['visibility'].lower()} visibility, and {weather_data['road_conditions'].lower()} road conditions."
        
        # Case 1: Pre-existing damage scenario
        if "minor" in item["image_description"].lower() and "paint damage" in item["image_description"].lower():
            if "recent" in item["witness_report"].lower():
                discrepancy = f"<strong>ASSESSMENT NOTE:</strong> The reported damage appears consistent with a minor parking incident. {weather_context} Recommend standard documentation of current damage to establish baseline for future claims."
                severity = "LOW"
            else:
                discrepancy = f"<strong>POTENTIAL DISCREPANCY:</strong> While damage appears minor, timeline of incident requires verification. {weather_context} Detailed photos of all damage areas recommended to document current condition."
                severity = "LOW"
                
        # Case 2: Multiple incidents scenario
        elif "multiple impact points" in item["image_description"].lower():
            if "single incident" in item["witness_report"].lower():
                discrepancy = f"<strong>SIGNIFICANT DISCREPANCY IDENTIFIED:</strong> Photographic evidence shows multiple impact points with varying degrees of wear, suggesting damage from separate incidents. {weather_context} The claim of a single recent incident requires further investigation."
                severity = "HIGH"
            else:
                discrepancy = f"<strong>ASSESSMENT NOTE:</strong> Multiple damage points identified. {weather_context} Detailed documentation needed to separate recent damage from any pre-existing conditions."
                severity = "MEDIUM"
                
        # Case 3: Under-reporting scenario
        elif "extensive" in item["image_description"].lower() or "severe" in item["image_description"].lower():
            if "minor" in item["witness_report"].lower():
                discrepancy = f"<strong>SIGNIFICANT DISCREPANCY IDENTIFIED:</strong> The documented damage indicates a substantial impact inconsistent with a minor collision. {weather_context} While adverse weather conditions were present, the damage pattern suggests an impact speed and force beyond what was reported."
                severity = "HIGH"
            else:
                discrepancy = f"<strong>ASSESSMENT NOTE:</strong> Severe damage documented with consistent reporting. {weather_context} Damage pattern aligns with reported circumstances."
                severity = "MEDIUM"
        
        discrepancies.append(f"{discrepancy.strip()}\n<strong>Severity:</strong> {severity.strip()}")
    
    return "".join(discrepancies).strip()

@app.route('/approval')
def approval():
    forwarded_user = request.headers.get('X-Forwarded-Preferred-Username')
    full_name = extract_email(forwarded_user)
    
    image_filter = request.args.get("image_filter", "6e593b17-a3c4-47e6-a153-a1efb05e9511")
    
    # Filter data based on claim number
    filtered_data = [item for item in model_payoff if item["claim_number"] == image_filter]
    if not filtered_data:
        filtered_data = [model_payoff[0]]  # Default to first claim if not found
        
    json_diff = compute_json_diff(filtered_data)

    return render_template(
        'approval.html',
        data=filtered_data,
        review_log=review_log,
        user=full_name,
        user_name=full_name,
        json_diff=json_diff,
        selected_filter=image_filter,
        all_claims=model_payoff  # Pass all claims for the dropdown
    )

# First, define all initial data at the top of the file after imports
initial_review_log = [
    {
        'date': '2025-03-28 15:23:17',
        'user_name': 'Stephen Hsu',
        'claim_number': '7d482e31-b4a5-4c8e-9f2b-8e4d2c1a9b3f',
        'action': 'Model results submitted',
        'comments': ''
    },
    {
        'date': '2025-04-10 09:24:30',
        'user_name': 'Suman Misra',
        'claim_number': '9a3f5d12-e8b7-4f2d-ae6c-1b5c8d4e7a9f',
        'action': 'Rejected',
        'comments': 'Review negative payoffs in DBRU'
    },
    {
        'date': '2025-04-11 11:03:43',
        'user_name': 'Shirly Wang',
        'claim_number': '5b2e8f4a-c9d6-4e7b-91a3-2f8c5d6e9b4a',
        'action': 'Model results submitted',
        'comments': ''
    }
]

initial_comparison_review_log = [
    {
        'date': '2025-04-22 09:18:43',
        'user_name': 'Michael Rodriguez',
        'case_number': 'CA-2024-123456',
        'policy_number': '102129232',
        'vin': '1HGCM82633A123456',
        'car_model': 'accord',
        'action': 'Further Investigation',
        'comments': 'Timeline discrepancy between images (summer vs winter). Request policyholder to confirm exact date of incident and provide repair shop estimate.'
    },
    {
        'date': '2025-04-20 10:37:28',
        'user_name': 'Alex Tsourmas',
        'case_number': 'CA-2024-123789',
        'policy_number': '102129544',
        'vin': '1FATP8UH3K5159877',
        'car_model': 'mustang',
        'action': 'Further Investigation',
        'comments': 'Damage severity exceeds described incident. Requesting police report and witness statements to verify circumstances of collision.'
    },
    {
        'date': '2025-04-23 14:52:16',
        'user_name': 'Jennifer Chang',
        'case_number': 'CA-2024-123789',
        'policy_number': '102129544',
        'vin': '1FATP8UH3K5159877',
        'car_model': 'mustang',
        'action': 'Rejected',
        'comments': 'Damage pattern inconsistent with reported low-speed incident. Police report confirms high-speed collision. Claim denied due to misrepresentation.'
    },
    {
        'date': '2025-04-21 11:05:37',
        'user_name': 'David Wilson',
        'case_number': 'CA-2024-124012',
        'policy_number': '102129788',
        'vin': '5TDKK3DC2CS289155',
        'car_model': 'sienna',
        'action': 'Approved',
        'comments': 'Damage consistent with reported incident. All documentation verified. Approved for repairs with preferred network shop.'
    }
]

# Initialize global variables
review_log = []
comparison_review_log = []

# File paths for storing review logs
APPROVAL_LOG_FILE = 'data/approval_review_log.json'
COMPARISON_LOG_FILE = 'data/comparison_review_log.json'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

def load_review_logs():
    """Load review logs from JSON files"""
    global review_log, comparison_review_log
    
    # Load approval review log
    try:
        with open(APPROVAL_LOG_FILE, 'r') as f:
            review_log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        review_log = []
    
    # Load comparison review log
    try:
        with open(COMPARISON_LOG_FILE, 'r') as f:
            comparison_review_log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        comparison_review_log = []
    
    # Always ensure initial entries are present at the bottom
    # For approval review log
    existing_dates = {entry['date'] for entry in review_log}
    for entry in initial_review_log:
        if entry['date'] not in existing_dates:
            review_log.append(entry)
    
    # For comparison review log
    existing_dates = {entry['date'] for entry in comparison_review_log}
    for entry in initial_comparison_review_log:
        if entry['date'] not in existing_dates:
            comparison_review_log.append(entry)
    
    # Save both logs to ensure files exist
    save_review_logs()

def save_review_logs():
    """Save review logs to JSON files"""
    # Save approval review log
    with open(APPROVAL_LOG_FILE, 'w') as f:
        json.dump(review_log, f, indent=2)
    
    # Save comparison review log
    with open(COMPARISON_LOG_FILE, 'w') as f:
        json.dump(comparison_review_log, f, indent=2)

# Load logs when app starts
load_review_logs()

@app.route('/submit_approval', methods=['POST'])
def submit_approval():
    global review_log
    try:
        # Get form data
        comments = request.form.get('comments', '')
        action = request.form.get('action', '')
        user_name = request.form.get('user_name', 'Unknown User')
        claim_number = request.form.get('claim_number', '')
        
        # Create new entry
        new_entry = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_name': user_name,
            'claim_number': claim_number,
            'action': action,
            'comments': comments
        }
        
        # Add to review log
        review_log.insert(0, new_entry)
        save_review_logs()
        
        return jsonify({
            'success': True,
            'entry': new_entry
        })
        
    except Exception as e:
        print(f"Error in submit_approval: {str(e)}")  # Debug log
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Add car comparison data
car_comparison = [
    {
        "model": "accord",
        "name": "Honda Accord",
        "case_number": "CA-2024-123456",
        "policy_number": "102129232",
        "vin": "1HGCM82633A123456",
        "image_url1": "/static/images/accord_1.png",
        "image_url2": "/static/images/accord_2.png",
        "analysis": "AI ANALYSIS: The second image of the red Honda Accord shows moderate front-end cosmetic damage localized to the lower passenger side of the front bumper, including scuffing, paint transfer, and abrasion near the fog light housing, likely from a parking collision or low-speed impact; there is no structural deformation to the grille, headlight, hood, or fender, and the alignment of panels appears intact, suggesting no underlying frame or sensor damage—repairs would likely involve bumper cover refinishing or replacement, repainting, and labor, with estimated costs ranging between $900–$1,500 depending on shop rates and whether OEM parts are used."
    },
    {
        "model": "mustang",
        "name": "Ford Mustang",
        "case_number": "CA-2024-123789",
        "policy_number": "102129544",
        "vin": "1FATP8UH3K5159877",
        "image_url1": "/static/images/mustang_1.png",
        "image_url2": "/static/images/mustang_2.png",
        "analysis": "AI ANALYSIS: The second image of the white Ford Mustang reveals significant front-end damage compared to the pristine condition in the first: the hood has large, visible creases and dents concentrated at the center, suggesting a substantial downward impact likely from a falling object or front-end collision; the front passenger-side fender and bumper also show scraping and deformation around the headlight and fog light area, and the windshield is visibly cracked, which may implicate damage to ADAS components if equipped—estimated repair costs could range from $3,500–$6,000 depending on whether the hood and windshield require replacement, and whether recalibration of sensors or structural alignment is needed."
    },
    {
        "model": "sienna",
        "name": "Toyota Sienna",
        "case_number": "CA-2024-124012",
        "policy_number": "102129788",
        "vin": "5TDKK3DC2CS289155",
        "image_url1": "/static/images/sienna_1.png",
        "image_url2": "/static/images/sienna_2.png",
        "analysis": "AI ANALYSIS: The second image of the light blue Toyota Sienna reveals two key changes from the undamaged baseline in the first: the front driver-side wheel has been replaced with a temporary black steel spare tire, and the driver-side sliding door shows significant denting and crumpling in the lower half, indicating a side impact or scraping incident—no apparent frame misalignment or glass damage is visible, so structural compromise is unlikely; estimated repair costs range from $1,800–$3,200 depending on whether the door skin can be repaired or must be replaced and repainted, while the wheel may cost $150–$300 if replaced with a full OEM match."
    }
]

# Add route for comparison page
@app.route('/comparison')
def comparison():
    forwarded_user = request.headers.get('X-Forwarded-Preferred-Username')
    full_name = extract_email(forwarded_user)
    
    # Get car model from query params, default to 'accord'
    car_model = request.args.get('car_model', 'accord')
    
    # Show analysis if requested
    show_analysis = request.args.get('show_analysis', 'false') == 'true'
    
    # Filter data for selected car model
    filtered_data = [item for item in car_comparison if item["model"] == car_model]
    
    return render_template(
        'comparison.html',
        data=filtered_data,
        comparison_review_log=comparison_review_log,
        user=full_name,
        user_name=full_name,
        show_analysis=show_analysis,
        selected_model=car_model,
        all_claims=car_comparison  # Pass all claims for the dropdown
    )

@app.route('/submit_comparison', methods=['POST'])
def submit_comparison():
    global comparison_review_log
    try:
        # Get form data
        car_model = request.form.get('car_model', '')
        comments = request.form.get('comments', '')
        action = request.form.get('action', '')
        user_name = request.form.get('user_name', 'Unknown User')
        
        # Find the matching car data to get policy number and VIN
        car_data = next((item for item in car_comparison if item["model"] == car_model), None)
        if not car_data:
            raise ValueError(f"No car data found for model: {car_model}")
        
        # Create new entry
        new_entry = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_name': user_name,
            'case_number': car_data['case_number'],
            'policy_number': car_data['policy_number'],
            'vin': car_data['vin'],
            'car_model': car_model,
            'action': action,
            'comments': comments
        }
        
        # Add to review log
        comparison_review_log.insert(0, new_entry)
        save_review_logs()
        
        return jsonify({
            'success': True,
            'entry': new_entry
        })
        
    except Exception as e:
        print(f"Error in submit_comparison: {str(e)}")  # Debug log
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/generate_comparison_analysis', methods=['POST'])
def generate_comparison_analysis():
    try:
        car_model = request.form.get('car_model')
        
        # Add a small delay to simulate processing
        time.sleep(0.5)
        
        # Mock analysis results (in real app, this would use AI/ML)
        analyses = {
            'accord': "Analysis complete: The Honda Accord shows significant changes between the previous and current conditions. The front bumper has sustained moderate damage with visible scratches and dents. The hood shows signs of impact damage that wasn't present in the previous condition. Paint damage is evident around the front quarter panel. Estimated repair costs would be substantial given the extent of visible damage.",
            'mustang': "Analysis complete: The Ford Mustang comparison reveals extensive modifications from its previous state. There is notable damage to the driver's side door and rear quarter panel. The side mirror shows signs of impact, and there are deep scratches along the vehicle's side. The current condition suggests a significant collision event.",
            'sienna': "Analysis complete: The Toyota Sienna exhibits clear differences between previous and current states. The rear bumper shows substantial damage with deep scratches and denting. The sliding door has visible impact marks, and the wheel well trim is partially detached. These changes indicate a significant incident requiring professional repair assessment."
        }
        
        analysis = analyses.get(car_model, "Analysis complete: Comparison reveals significant changes between previous and current conditions. Professional assessment recommended.")
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        print(f"Error in generate_comparison_analysis: {str(e)}")  # Debug log
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/delete_review_entry', methods=['POST'])
def delete_review_entry():
    try:
        data = request.get_json()
        log_type = data.get('log_type')
        entry_date = data.get('date')
        
        if log_type == 'approval':
            # Don't allow deletion of initial entries
            if any(entry['date'] == entry_date for entry in initial_review_log):
                return jsonify({
                    'success': False,
                    'error': 'Cannot delete initial entries'
                }), 400
            
            global review_log
            review_log = [entry for entry in review_log if entry['date'] != entry_date]
            save_review_logs()
        elif log_type == 'comparison':
            # Don't allow deletion of initial entries
            if any(entry['date'] == entry_date for entry in initial_comparison_review_log):
                return jsonify({
                    'success': False,
                    'error': 'Cannot delete initial entries'
                }), 400
            
            global comparison_review_log
            comparison_review_log = [entry for entry in comparison_review_log if entry['date'] != entry_date]
            save_review_logs()
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid log type'
            }), 400
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error in delete_review_entry: {str(e)}")  # Debug log
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)