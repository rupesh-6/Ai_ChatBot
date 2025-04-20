from flask import Flask, request, jsonify, render_template, session as flask_session, redirect, url_for, flash
import requests
from datetime import datetime, timedelta
import re
import time
import json
import os
import uuid
import google.generativeai as genai
import markdown
import pymongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "medication-reminder-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/medassist")
client = pymongo.MongoClient(MONGODB_URI)
db = client.get_database()
users_collection = db.users
sessions_collection = db.sessions
medications_collection = db.medications
chat_history_collection = db.chat_history

# Configure Gemini API
try:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "your-api-key-here")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')  # Using gemini-2.0-flash
    GEMINI_ENABLED = True
    print(f"Gemini API configured successfully with model: gemini-2.0-flash")
except Exception as e:
    print(f"Warning: Gemini API configuration failed: {str(e)}")
    GEMINI_ENABLED = False

# Import fallback mechanisms
try:
    from api_fallbacks import FallbackAPI, get_backup_disease_info
    FALLBACKS_ENABLED = True
except ImportError:
    print("Warning: API fallbacks module not found. Some backup features will be disabled.")
    FALLBACKS_ENABLED = False

# Common diseases (not medications)
DISEASES = [
    "malaria", "dengue", "covid", "mononucleosis", "syphilis", "tuberculosis", 
    "hepatitis", "gonorrhea", "chlamydia", "hiv", "aids", "herpes", 
    "influenza", "measles", "mumps", "rubella", "chickenpox", "gastroenteritis",
    "diarrhea", "flu", "common cold", "pneumonia", "bronchitis", "diabetes", 
    "hypertension", "asthma", "arthritis", "cancer", "alzheimer", "parkinson"
]

# Common diseases and related medications
DISEASE_MEDICATIONS = {
    "dengue": [
        {"name": "Paracetamol", "purpose": "Reduce fever and relieve pain", 
         "dosage": "500-1000mg every 4-6 hours as needed, not exceeding 4000mg in 24 hours", 
         "warning": "Avoid NSAIDs like ibuprofen or aspirin as they may increase bleeding risk"},
        {"name": "Oral Rehydration Solution", "purpose": "Prevent dehydration", 
         "dosage": "Drink regularly throughout the day to maintain hydration", 
         "warning": "Watch for signs of severe dehydration requiring medical attention"},
        {"name": "Papaya Leaf Extract", "purpose": "May help increase platelet count", 
         "dosage": "As directed on the product or by healthcare provider", 
         "warning": "Considered complementary; consult doctor before use"}
    ],
    "malaria": [
        {"name": "Chloroquine", "purpose": "Treat specific types of malaria", 
         "dosage": "As prescribed by healthcare provider", 
         "warning": "Take exactly as directed; may cause stomach upset or headache"},
        {"name": "Artemisinin-based combination therapies (ACTs)", 
         "purpose": "First-line treatment for P. falciparum malaria", 
         "dosage": "Follow precise prescription from healthcare provider", 
         "warning": "Complete full course of medication even when feeling better"}
    ],
    "mononucleosis": [
        {"name": "Acetaminophen", "purpose": "Reduce fever and relieve pain", 
         "dosage": "As directed on package or by healthcare provider", 
         "warning": "Do not exceed recommended dosage; can cause liver damage"},
        {"name": "Ibuprofen", "purpose": "Reduce inflammation and pain", 
         "dosage": "As directed on package or by healthcare provider", 
         "warning": "Take with food; can cause stomach irritation"}
    ],
    "covid": [
        {"name": "Paracetamol", "purpose": "Reduce fever and relieve pain", 
         "dosage": "500-1000mg every 4-6 hours as needed, not exceeding 4000mg in 24 hours", 
         "warning": "Not a treatment for COVID-19, only for symptom relief"},
        {"name": "Vitamin C", "purpose": "Support immune function", 
         "dosage": "500-1000mg daily or as directed by healthcare provider", 
         "warning": "High doses may cause digestive issues in some people"},
        {"name": "Vitamin D", "purpose": "Support immune function", 
         "dosage": "1000-4000 IU daily or as directed by healthcare provider", 
         "warning": "Very high doses may lead to toxicity; follow recommendations"}
    ],
    "syphilis": [
        {"name": "Penicillin G", "purpose": "Primary antibiotic for treatment of syphilis", 
         "dosage": "As prescribed by healthcare provider, typically administered as injections", 
         "warning": "May cause allergic reactions; inform your doctor if you have penicillin allergy"},
        {"name": "Doxycycline", "purpose": "Alternative for patients allergic to penicillin", 
         "dosage": "100 mg twice daily for 14 days (for secondary syphilis)", 
         "warning": "Avoid sun exposure; do not take with dairy products; not suitable for pregnant women"}
    ]
}

# Use DISEASE_MEDICATIONS for consistency
CONDITION_MEDICATIONS = DISEASE_MEDICATIONS

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Function to fetch drug info from OpenFDA API with improved error handling
def fetch_drug_info(med_name):
    # First check if this medication is for a common condition we have predefined info for
    condition_info = get_condition_medication_info(med_name)
    if condition_info:
        return condition_info
    
    try:
        # Try generic name search first
        response = requests.get(
            "https://api.fda.gov/drug/label.json",
            params={"search": f"openfda.generic_name:({med_name})", "limit": 1}
        )
        data = response.json()
        
        # If no results, try brand name search
        if "results" not in data or len(data.get("results", [])) == 0:
            response = requests.get(
                "https://api.fda.gov/drug/label.json",
                params={"search": f"openfda.brand_name:({med_name})", "limit": 1}
            )
            data = response.json()
        
        # If still no results, try substance name search
        if "results" not in data or len(data.get("results", [])) == 0:
            response = requests.get(
                "https://api.fda.gov/drug/label.json",
                params={"search": f"openfda.substance_name:({med_name})", "limit": 1}
            )
            data = response.json()
            
        if "results" in data and len(data.get("results", [])) > 0:
            result = data["results"][0]
            # Get various information fields if available
            purpose = result.get("purpose", ["No purpose listed"])[0] if result.get("purpose") else "No purpose listed"
            usage = result.get("indications_and_usage", ["No usage info"])[0] if result.get("indications_and_usage") else "No usage information available"
            warnings = result.get("warnings", ["No warnings listed"])[0] if result.get("warnings") else "No warnings listed"
            dosage = result.get("dosage_and_administration", ["No dosage information"])[0] if result.get("dosage_and_administration") else "Consult your healthcare provider for dosage information"
            
            # Format with Markdown
            info = f"""### {med_name.title()} Information

#### Purpose
{purpose}

#### Usage
{usage[:300]}...

#### Recommended Dosage
{dosage[:200]}...

#### Important Warnings
{warnings[:200]}...
"""
            return info
        else:
            # If no data found in OpenFDA, use Gemini to fill in basic information
            return use_gemini_for_basic_info(med_name)
    except Exception as e:
        print(f"OpenFDA API error: {str(e)}")
        # Fallback to Gemini if OpenFDA fails
        return use_gemini_for_basic_info(med_name)

def get_condition_medication_info(med_name):
    """Check if the user is asking about a medication for a specific condition"""
    med_name_lower = med_name.lower()
    
    # Check if they mentioned a condition directly
    for condition, medications in CONDITION_MEDICATIONS.items():
        if condition in med_name_lower:
            # Generate info about all medications for this condition
            med_info = f"""### Medications for {condition.title()}

Here are the recommended medications for {condition}:

"""
            for med in medications:
                med_info += f"""#### {med['name']}
**Purpose**: {med['purpose']}
**Dosage**: {med['dosage']}
**Warning**: {med['warning']}

"""
            return med_info
        
        # Check if they mentioned a specific medication for a condition
        for med in medications:
            if med['name'].lower() in med_name_lower:
                med_info = f"""### {med['name']} (for {condition.title()})

#### Purpose
{med['purpose']}

#### Recommended Dosage
{med['dosage']}

#### Important Warnings
{med['warning']}
"""
                return med_info
    
    return None

def use_gemini_for_basic_info(med_name):
    """Use Gemini AI to provide basic information when OpenFDA doesn't have data"""
    if not GEMINI_ENABLED:
        return f"❌ **No information found for {med_name} in our database.**"
    
    try:
        prompt = f"""
        Please provide accurate, concise information about the medication '{med_name}' in this format:
        
        1. Purpose: What is this medication typically used for?
        2. Typical Usage: How is it typically used?
        3. Common Dosage: What is the typical dosage? (with disclaimer that actual dosage should come from doctor)
        4. Important Warnings: What are key warnings or side effects?
        
        If this is not a recognized medication, please respond with "This does not appear to be a standard medication."
        Format the response in clear Markdown with appropriate headers.
        """
        
        response = model.generate_content(prompt)
        
        if response and hasattr(response, 'text'):
            if "not appear to be a standard medication" in response.text:
                return f"❌ **No information found for {med_name} in our database.**"
            
            return f"""### {med_name.title()} Information

{response.text}

> *Note: This information is AI-generated as this medication wasn't found in our primary database. Always consult your healthcare provider.*
"""
        else:
            return f"❌ **No information found for {med_name} in our database.**"
    except Exception as e:
        print(f"Gemini API error for basic info: {str(e)}")
        return f"❌ **No information found for {med_name} in our database.**"

# Function to get information about a disease using multiple methods
def get_disease_info(disease_name):
    """Get information about a disease using multiple fallback methods"""
    if not GEMINI_ENABLED and not FALLBACKS_ENABLED:
        return f"I don't have information about {disease_name} in my database.", None
    
    # Check if we have predefined medications for this disease
    disease_meds = None
    canonical_disease = None
    
    for disease, medications in DISEASE_MEDICATIONS.items():
        if disease.lower() in disease_name.lower() or disease_name.lower() in disease.lower():
            disease_meds = medications
            canonical_disease = disease  # Use our canonical name
            break
    
    # Try using Gemini first if available
    if GEMINI_ENABLED:
        try:
            prompt = f"""
            Please provide accurate, concise information about the disease or condition '{disease_name}' in this format:
            
            1. What is {disease_name}?
            2. Common symptoms
            3. How is it transmitted/caused?
            4. Common treatments and medications
            5. Prevention measures
            
            Format the response in clear Markdown with appropriate headers.
            Make your answer concise but informative.
            If this is not a recognized medical condition, please say "This does not appear to be a standard medical condition."
            """
            
            response = model.generate_content(prompt)
            
            if response and hasattr(response, 'text'):
                if "not appear to be a standard medical condition" in response.text:
                    print(f"Gemini API: No information found for {disease_name}")
                else:
                    disease_info = f"""## Information About {disease_name.title()}

{response.text}
"""
                    # Add medication info if available
                    if disease_meds:
                        disease_info += "\n## Recommended Medications\n\n"
                        for med in disease_meds:
                            disease_info += f"### {med['name']}\n"
                            disease_info += f"**Purpose**: {med['purpose']}\n"
                            disease_info += f"**Dosage**: {med['dosage']}\n"
                            disease_info += f"**Warning**: {med['warning']}\n\n"
                        
                        disease_info += "*Would you like me to set a reminder for any of these medications? Please specify which medication.*"
                    else:
                        disease_info += "\n*Would you like to set a reminder for any medications related to this condition? Please specify which medication.*"
                    
                    return disease_info, canonical_disease or disease_name.lower()
        except Exception as e:
            print(f"Gemini API error: {str(e)}")
    
    # Try fallback methods
    if FALLBACKS_ENABLED:
        fallback_info, success = FallbackAPI.get_disease_info(disease_name)
        if success:
            return fallback_info, disease_name.lower()

    # If all methods fail, try searching the web
    try:
        web_info = search_web_for_disease_info(disease_name)
        if web_info:
            return web_info, disease_name.lower()
    except Exception as e:
        print(f"Web search error: {str(e)}")

    # If we reached here, all methods failed
    return f"I couldn't find specific information about {disease_name}. Please check the spelling or try a different condition.", None

def search_web_for_disease_info(disease_name):
    """Search the web for disease information as a last resort"""
    try:
        from googlesearch import search
        query = f"{disease_name} disease information site:wikipedia.org"
        results = list(search(query, num_results=1))
        if results:
            return f"## Information About {disease_name.title()}\n\nI couldn't find detailed information in my database, but you can learn more here: [Learn More]({results[0]})", None
    except Exception as e:
        print(f"Error during web search: {str(e)}")
    return None

# Function to check if a text refers to a disease rather than a medication
def is_likely_disease(text):
    """Check if the input text likely refers to a disease rather than a medication"""
    text_lower = text.lower()
    
    # Check against our known disease list
    for disease in DISEASES:
        if disease in text_lower:
            return True
    
    # Check for disease keywords
    disease_keywords = ["disease", "infection", "condition", "syndrome", "virus", "bacterial", "fungal",
                     "itis", "osis", "emia", "pathy", "fever", "disorder", "cancer"]
    
    # Check for keywords
    for keyword in disease_keywords:
        if keyword in text_lower:
            return True
    
    # Check for disease suffix patterns (like -itis for inflammation)
    disease_suffixes = ["itis", "osis", "emia", "pathy", "algia", "oma"]
    for suffix in disease_suffixes:
        if text_lower.endswith(suffix):
            return True
            
    # Check in our disease medications dictionary
    for disease in DISEASE_MEDICATIONS.keys():
        if disease in text_lower:
            return True
    
    return False

# Helper function to validate medication names
def is_valid_medication_name(name):
    """Checks if the provided string is likely a valid medication name."""
    if not name or not isinstance(name, str):
        return False
    
    name_lower = name.lower().strip()
    
    # Check length (arbitrary limits, adjust as needed)
    if len(name_lower) < 2 or len(name_lower) > 50:
        return False
        
    # Check for common problematic phrases or questions
    invalid_phrases = [
        "tell me about", "what is", "remind me", "set a reminder",
        "view all", "show me", "medicine", "medication", "pills",
        "at ", " for ", " on ", "?"
    ]
    if any(phrase in name_lower for phrase in invalid_phrases):
        # Allow "medicine" or "medication" if it's part of a longer name like "fever medicine"
        if name_lower not in ["medicine", "medication", "pills"]:
             # Check if it's just the invalid word or part of a longer name
             is_just_invalid_word = False
             for phrase in ["medicine", "medication", "pills"]:
                 if name_lower == phrase:
                     is_just_invalid_word = True
                     break
             if not is_just_invalid_word and any(phrase in name_lower for phrase in ["medicine", "medication", "pills"]):
                 pass # Allow names like "fever medicine"
             elif any(phrase in name_lower for phrase in invalid_phrases if phrase not in ["medicine", "medication", "pills"]):
                 return False # Contains other invalid phrases

    # Check if it looks like a time format
    if re.match(r'^\d{1,2}:?\d{2}?\s*(am|pm)?$', name_lower):
        return False
        
    # Add more checks if needed (e.g., check against a known list, disallow only numbers)
    
    return True

# Add the database helper functions that were omitted
def get_or_create_user(user_id, data=None):
    """Get or create a user in the database"""
    if data is None:
        data = {}
    
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "name": data.get("name", ""),
            "age": data.get("age", ""),
            "conditions": data.get("conditions", []),
            "custom_condition": data.get("custom_condition", ""),
            "preferred_reminder_time": data.get("preferred_reminder_time", "08:00")
        }
        users_collection.insert_one(user)
    return user

def get_user_by_email(email):
    """Get a user by email"""
    return users_collection.find_one({"email": email})

def get_user_by_id(user_id):
    """Get a user by ID"""
    return users_collection.find_one({"user_id": user_id})

def create_user(name, email, password):
    """Create a new user"""
    user_id = str(uuid.uuid4())
    
    user = {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "user_id": user_id,
        "created_at": datetime.now(),
        "conditions": [],
        "age": "",
        "custom_condition": "",
        "preferred_reminder_time": "08:00",
        "last_login": datetime.now()
    }
    
    users_collection.insert_one(user)
    return user

def update_user_profile(user_id, data):
    """Update a user's profile information"""
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": data}
    )

def get_user_medications(user_id):
    """Get all medications for a user"""
    return list(medications_collection.find({"user_id": user_id}))

def save_medication(user_id, medication):
    """Save a medication to the database"""
    medication["user_id"] = user_id
    
    # Check if medication already exists
    existing = medications_collection.find_one({
        "user_id": user_id,
        "name": medication["name"]
    })
    
    if existing:
        # Update existing medication
        medications_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": medication}
        )
        return existing["_id"]
    else:
        # Insert new medication
        medication["created_at"] = datetime.now()
        result = medications_collection.insert_one(medication)
        return result.inserted_id

def delete_medication(user_id, medication_id):
    """Delete a medication from the database"""
    result = medications_collection.delete_one({
        "user_id": user_id,
        "name": medication_id.replace("_", " ")
    })
    return result.deleted_count > 0

def save_chat_message(user_id, role, content):
    """Save a chat message to the database"""
    message = {
        "user_id": user_id,
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    }
    chat_history_collection.insert_one(message)

def get_chat_history(user_id, limit=50):
    """Get chat history for a user, converting timestamps to strings."""
    history_cursor = chat_history_collection.find(
        {"user_id": user_id}
    ).sort("timestamp", 1).limit(limit) # Sort ascending for chronological display

    history_list = []
    for msg in history_cursor:
        # Convert ObjectId and datetime to string for JSON serialization
        msg['_id'] = str(msg['_id'])
        if isinstance(msg.get('timestamp'), datetime):
            msg['timestamp'] = msg['timestamp'].isoformat()
        history_list.append(msg)
    return history_list

# Add route definitions for app
@app.route('/onboarding')
def onboarding():
    # If user is already logged in, redirect to index
    if 'user_id' in flask_session:
        return redirect(url_for('index'))
    return render_template('onboarding.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to index
    if 'user_id' in flask_session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = get_user_by_email(email)
        
        if user and check_password_hash(user['password_hash'], password):
            # Update last login time
            users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.now()}}
            )
            
            # Set session data
            flask_session.clear()
            flask_session['user_id'] = user['user_id']
            flask_session['name'] = user['name']
            flask_session['email'] = user['email']
            flask_session.permanent = True
            
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # If user is already logged in, redirect to index
    if 'user_id' in flask_session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate input
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')
        
        # Check if email already exists
        existing_user = get_user_by_email(email)
        if existing_user:
            flash('Email already registered. Please use a different email.', 'error')
            return render_template('register.html')
        
        # Create new user
        user = create_user(name, email, password)
        
        # Log the user in
        flask_session['user_id'] = user['user_id']
        flask_session['name'] = user['name']
        flask_session['email'] = user['email']
        flask_session.permanent = True
        
        flash('Registration successful!', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    flask_session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route("/")
def index():
    # Redirect to onboarding if not logged in
    if 'user_id' not in flask_session:
        return redirect(url_for('onboarding')) # Changed from login to onboarding
    
    # Use the user_id from session
    user_id = flask_session['user_id']
    
    # Create or get user record
    user = get_or_create_user(user_id)
    
    return render_template("index.html")

@app.route("/reminders")
@login_required
def reminders_page():
    return render_template("reminders.html")

@app.route("/update-profile", methods=["POST"])
@login_required
def update_profile():
    """API endpoint to update user profile"""
    user_id = flask_session.get('user_id')
    data = request.json
    
    if not data:
        return jsonify(success=False, message="No data provided")
    
    update_data = {}
    
    if "name" in data:
        update_data["name"] = data["name"]
        flask_session['name'] = data["name"]
    
    if "age" in data:
        update_data["age"] = data["age"]
    
    if "conditions" in data:
        update_data["conditions"] = data["conditions"]
    
    if "customCondition" in data:
        update_data["custom_condition"] = data["customCondition"]
    
    if "preferredReminderTime" in data:
        update_data["preferred_reminder_time"] = data["preferredReminderTime"]
    
    if update_data:
        update_user_profile(user_id, update_data)
        return jsonify(success=True, message="Profile updated successfully")
    else:
        return jsonify(success=False, message="No valid fields to update")

@app.route("/get-profile", methods=["GET"])
@login_required
def get_profile():
    """API endpoint to get user profile"""
    user_id = flask_session.get('user_id')
    
    user = get_user_by_id(user_id)
    
    if not user:
        return jsonify(success=False, message="User not found")
    
    profile = {
        "name": user.get("name", ""),
        "age": user.get("age", ""),
        "conditions": user.get("conditions", []),
        "customCondition": user.get("custom_condition", ""),
        "preferredReminderTime": user.get("preferred_reminder_time", "08:00"),
        "email": user.get("email", "")
    }
    
    return jsonify(success=True, profile=profile)

@app.route("/get-reminders", methods=["GET"])
@login_required
def get_reminders():
    """API endpoint to get all reminders for the current user"""
    user_id = flask_session.get('user_id')
    
    medications = get_user_medications(user_id)
    reminders = []
    
    for med in medications:
        if med.get("time"):
            reminder = {
                "id": med["name"].replace(" ", "_").lower(),
                "name": med["name"],
                "time": med["time"],
                "condition": med.get("condition", "general"),
                "info": med.get("info", "")
            }
            reminders.append(reminder)
    
    return jsonify(reminders=reminders)

@app.route("/get-chat-history", methods=["GET"])
@login_required
def get_chat_history_route():
    """API endpoint to get chat history for the current user"""
    user_id = flask_session.get('user_id')
    
    history = get_chat_history(user_id)
    return jsonify(history=history)

@app.route("/update-reminder", methods=["POST"])
@login_required
def update_reminder():
    """API endpoint to update a medication reminder"""
    user_id = flask_session.get('user_id')
    data = request.json
    
    if not data or "id" not in data:
        return jsonify(success=False, message="Invalid request")
    
    med_id = data["id"].lower()
    
    # Extract the medication name from the ID
    med_name = med_id.replace("_", " ")
    
    # Update fields if provided
    update_data = {}
    if "time" in data:
        update_data["time"] = data["time"]
    
    if "name" in data:
        update_data["name"] = data["name"]
    
    if update_data:
        medications_collection.update_one(
            {"user_id": user_id, "name": med_name},
            {"$set": update_data}
        )
    
    return jsonify(success=True, message="Reminder updated successfully")

@app.route("/delete-reminder", methods=["POST"])
@login_required
def delete_reminder():
    """API endpoint to delete a medication reminder"""
    user_id = flask_session.get('user_id')
    data = request.json
    
    if not data or "id" not in data:
        return jsonify(success=False, message="Invalid request")
    
    med_id = data["id"].lower()
    
    # Delete the medication
    if delete_medication(user_id, med_id):
        return jsonify(success=True, message="Reminder deleted successfully")
    else:
        return jsonify(success=False, message="Medication not found")

@app.route("/clear-chat-history", methods=["POST"])
@login_required
def clear_chat_history():
    """API endpoint to delete all chat history for the current user"""
    user_id = flask_session.get('user_id')
    try:
        result = chat_history_collection.delete_many({"user_id": user_id})
        print(f"Cleared {result.deleted_count} chat messages for user {user_id}")
        # Also reset the session context/step as the history is gone
        sessions_collection.update_one(
            {"user_id": user_id},
            {"$set": {"step": 1, "context": {}}},
            upsert=True
        )
        return jsonify(success=True, message="Chat history cleared successfully.")
    except Exception as e:
        print(f"Error clearing chat history for user {user_id}: {str(e)}")
        return jsonify(success=False, message="An error occurred while clearing history.")


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_msg = request.json.get("message")
    user_id = flask_session.get('user_id')
    user_name = flask_session.get('name', '')
    
    # Save user message to chat history
    save_chat_message(user_id, "user", user_msg)
    
    # Get the current session state
    session_data = sessions_collection.find_one({"user_id": user_id}) or {
        "user_id": user_id,
        "step": 1,
        "context": {}
    }
    
    step = session_data.get("step", 1)
    context = session_data.get("context", {})
    
    # Generate bot response based on user input
    bot_response = ""
    reset_session = False # Flag to reset session after a successful flow
    
    # Check for view all medications request
    if any(phrase in user_msg.lower() for phrase in ["view all", "all medication", "all reminder", "show reminder", "see my"]):
        bot_response = get_all_medications_summary(user_id)
        reset_session = True # Reset context after showing summary
    
    # Handle "yes" confirmation after asking about setting a reminder for a disease
    elif user_msg.lower() == "yes" and context.get("awaiting_reminder_confirmation"):
        bot_response = f"Okay! Which medication related to **{context.get('current_disease', 'the condition')}** would you like to set a reminder for?"
        context["awaiting_medication_name"] = True
        context.pop("awaiting_reminder_confirmation", None) # Remove the confirmation flag
        sessions_collection.update_one(
            {"user_id": user_id},
            {"$set": {"step": 2, "context": context}},
            upsert=True
        )
    
    # Handle setting a new medication reminder (covers multiple steps)
    elif "set a new medication reminder" in user_msg.lower() or "remind me" in user_msg.lower() or (step == 2 and context.get("awaiting_medication_name")) or (step == 3 and context.get("medication_name")):
        # Consolidate reminder setting logic
        # Refined regex to capture name until time indicators or end of string
        med_pattern = re.search(r'(?:remind\s+me\s+(?:to\s+take|about)\s+)(.*?)(?:\s+(?:at|for|on)\s+\d|\s*$)', user_msg, re.IGNORECASE)
        time_pattern = re.search(r'(?:at|for|on)\s+(\d{1,2}):?(\d{2})?\s*(am|pm|AM|PM)?', user_msg, re.IGNORECASE) # Use IGNORECASE for time pattern too
    
        if step == 1:
            if med_pattern:
                potential_med_name = med_pattern.group(1).strip()
                if is_valid_medication_name(potential_med_name):
                    context["medication_name"] = potential_med_name
                    if time_pattern:
                        # Medication and time provided in step 1
                        hour = time_pattern.group(1)
                        minute = time_pattern.group(2) or "00"
                        ampm = time_pattern.group(3) or "AM" # Default to AM if not specified
                        time_str = f"{hour}:{minute} {ampm.upper()}"
                        save_medication(user_id, {
                            "name": context["medication_name"],
                            "time": time_str,
                            "info": fetch_drug_info(context["medication_name"])
                        })
                        bot_response = f"""## ✅ Reminder Set Successfully!
    Your reminder for **{context['medication_name']}** has been set for **{time_str}** daily.
    Would you like to set another reminder or ask about a medication?"""
                        reset_session = True
                    else:
                        # Medication provided, ask for time
                        bot_response = f"Got it! What time should I remind you to take **{context['medication_name']}**? (e.g., 8:00 AM)"
                        sessions_collection.update_one(
                            {"user_id": user_id},
                            {"$set": {"step": 3, "context": context}}, # Go to step 3 (awaiting time)
                            upsert=True
                        )
                else:
                    # Invalid medication name extracted in step 1
                    bot_response = f"Sorry, '{potential_med_name}' doesn't seem like a valid medication name. Could you please specify the medication you want a reminder for?"
                    context["awaiting_medication_name"] = True
                    sessions_collection.update_one(
                        {"user_id": user_id},
                        {"$set": {"step": 2, "context": context}}, # Go to step 2 (awaiting name)
                        upsert=True
                    )
            else:
                # No medication provided, ask for it
                bot_response = "Sure! What medication would you like to set a reminder for?"
                context["awaiting_medication_name"] = True
                sessions_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"step": 2, "context": context}}, # Go to step 2 (awaiting name)
                    upsert=True
                )
        elif step == 2 and context.get("awaiting_medication_name"):
            # User provided medication name (potentially with time) after being asked
            med_name_in_msg = user_msg.strip()
            potential_time_str = ""
            if time_pattern:
                # Extract time if present
                hour = time_pattern.group(1)
                minute = time_pattern.group(2) or "00"
                ampm = time_pattern.group(3) or "AM"
                potential_time_str = f"{hour}:{minute} {ampm.upper()}"
                # Remove the time part from the message to get the medication name
                med_name_in_msg = re.sub(r'(?:at|for|on)\s+\d{1,2}:?\d{2}?\s*(am|pm|AM|PM)?', '', med_name_in_msg, flags=re.IGNORECASE).strip()
    
            # Validate the extracted/provided name before proceeding
            if is_valid_medication_name(med_name_in_msg):
                context["medication_name"] = med_name_in_msg
                context.pop("awaiting_medication_name", None)
    
                if potential_time_str:
                     # Medication and time provided in step 2
                    save_medication(user_id, {
                        "name": context["medication_name"],
                        "time": potential_time_str,
                        "info": fetch_drug_info(context["medication_name"])
                    })
                    bot_response = f"""## ✅ Reminder Set Successfully!
    Your reminder for **{context['medication_name']}** has been set for **{potential_time_str}** daily.
    Would you like to set another reminder or ask about a medication?"""
                    reset_session = True
                else:
                    # Only medication name provided, ask for time
                    bot_response = f"Got it! What time should I remind you to take **{context['medication_name']}**? (e.g., 8:00 AM)"
                    sessions_collection.update_one(
                        {"user_id": user_id},
                        {"$set": {"step": 3, "context": context}}, # Go to step 3 (awaiting time)
                        upsert=True
                    )
            else:
                # Invalid name provided in step 2
                bot_response = f"Sorry, '{med_name_in_msg}' doesn't seem like a valid medication name. Please provide the correct medication name."
                # Stay in step 2, keep awaiting_medication_name flag
                context["awaiting_medication_name"] = True
                context.pop("medication_name", None) # Clear any potentially bad name from context
                sessions_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"step": 2, "context": context}},
                    upsert=True
                )
    
        elif step == 3 and context.get("medication_name"):
            # User provided time after being asked
            # Ensure medication_name in context is valid before proceeding (should be, due to step 2 check, but double-check)
            if not is_valid_medication_name(context.get("medication_name")):
                 bot_response = "Something went wrong. Let's start over. What medication do you want to set a reminder for?"
                 reset_session = True
            else:
                time_pattern_step3 = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm|AM|PM)?', user_msg, re.IGNORECASE) # Re-check time pattern here
                if time_pattern_step3:
                    hour = time_pattern_step3.group(1)
                    minute = time_pattern_step3.group(2) or "00"
                    ampm = time_pattern_step3.group(3) or "AM"
                    time_str = f"{hour}:{minute} {ampm.upper()}"
                    save_medication(user_id, {
                        "name": context["medication_name"],
                        "time": time_str,
                        "info": fetch_drug_info(context["medication_name"])
                    })
                    bot_response = f"""## ✅ Reminder Set Successfully!
    Your reminder for **{context['medication_name']}** has been set for **{time_str}** daily.
    Would you like to set another reminder or ask about a medication?"""
                    reset_session = True
                else:
                    bot_response = "I couldn't understand the time. Please specify a time in the format like '8:00 AM' or '14:30'."
                    # Keep the session state as is (step 3, awaiting time)
    
    # Check if this is asking about a disease or medication (only if no other intent matched)
    elif not bot_response and (user_msg.lower().startswith("tell me about ") or user_msg.lower().startswith("what is ")):
        potential_topic = user_msg.lower().replace("tell me about ", "").replace("what is ", "").strip()
    
        if is_likely_disease(potential_topic):
            disease_info, canonical_disease = get_disease_info(potential_topic)
            if canonical_disease:
                context["current_disease"] = canonical_disease
                # Set flag to check for 'yes' in the next turn
                context["awaiting_reminder_confirmation"] = True
            else:
                # If disease not found or no canonical name, clear confirmation flag
                context.pop("awaiting_reminder_confirmation", None)
    
            sessions_collection.update_one(
                {"user_id": user_id},
                {"$set": {"context": context}},
                upsert=True
            )
            bot_response = disease_info
        else:
            # Treat as a medication query
            med_info = fetch_drug_info(potential_topic)
            context["current_medication"] = potential_topic
            # Clear disease context if asking about medication
            context.pop("current_disease", None)
            context.pop("awaiting_reminder_confirmation", None)
            sessions_collection.update_one(
                {"user_id": user_id},
                {"$set": {"context": context}},
                upsert=True
            )
            bot_response = med_info
    
    # Handle no matching intent or reset session
    if not bot_response:
        # If we are in a multi-step flow, don't show the generic welcome
        if step > 1 and context:
             bot_response = "Sorry, I didn't quite understand that. Could you please clarify?"
             # Optionally, guide the user based on the current step/context
             if context.get("awaiting_medication_name"):
                 bot_response += " I was expecting a medication name."
             elif context.get("medication_name") and step == 3:
                 bot_response += " I was expecting a time for the reminder (e.g., 8:00 AM)."
             # Reset if stuck in an invalid state
             else:
                 reset_session = True
                 bot_response = "Let's start over. How can I help you?"
    
        else:
            # Default welcome/help message
            bot_response = f"""## Welcome to MedAssist! 👋
    
    I'm your medication assistant! What medication would you like me to remind you about?
    
    You can:
    - Ask about specific medications (e.g., "Tell me about Ibuprofen")
    - Ask about conditions (e.g., "Tell me about diabetes")
    - Set medication reminders (e.g., "Remind me to take Metformin at 8:00 AM")
    - View all your medication reminders (e.g., "Show all my reminders")
    """
            # Don't reset session here automatically, only if no other intent matched *and* not in a flow
            if step == 1 and not context:
                 reset_session = True # Reset context if showing welcome message outside a flow
    
    # Reset session state if flagged
    if reset_session:
        sessions_collection.update_one(
            {"user_id": user_id},
            {"$set": {"step": 1, "context": {}}},
            upsert=True
        )
    
    # Save bot message to chat history
    save_chat_message(user_id, "bot", bot_response)
    
    return jsonify(reply=bot_response)

def get_all_medications_summary(user_id):
    """Generate a summary of all medications for a user"""
    medications = get_user_medications(user_id)
    
    if not medications:
        return """### You don't have any medication reminders set up yet.

Would you like to set up a reminder for a medication now? Just tell me the name of the medication.

You can also visit the [Reminders Dashboard](/reminders) to manage your reminders visually."""
    
    # Group medications by condition
    conditions = {}
    individual_meds = []
    
    for med in medications:
        # Ensure med name is a string and handle potential None values
        med_name = med.get("name", "Unnamed Medication")
        med_time = med.get("time") # Keep time as is, might be None

        if "condition" in med and med["condition"]:
            condition = med["condition"]
            if condition not in conditions:
                conditions[condition] = []
            conditions[condition].append({"name": med_name, "time": med_time})
        else:
            individual_meds.append({"name": med_name, "time": med_time})
    
    # Build response
    response = """## Your Medication Reminders

You can visit the [Reminders Dashboard](/reminders) to see countdowns and manage your reminders.

"""
    
    # Add conditions
    if conditions:
        for condition, condition_meds in conditions.items():
            response += f"### For {condition.title()}\n"
            for i, med in enumerate(condition_meds, 1):
                time_display = med.get("time") or "No time set" # Display 'No time set' if time is None
                response += f"{i}. **{med['name']}** - Daily at **{time_display}**\n"
            response += "\n"
    
    # Add individual medications
    if individual_meds:
        if conditions:
            response += "### Other Medications\n"
        for i, med in enumerate(individual_meds, 1):
            time_display = med.get("time") or "No time set" # Display 'No time set' if time is None
            response += f"{i}. **{med['name']}** - Daily at **{time_display}**\n"
    
    response += "\n*You can ask for details about any specific medication by name.*"
    return response

# Enhance with Gemini function to ensure it's correctly updated
def enhance_with_gemini(med_name, basic_info):
    if not GEMINI_ENABLED:
        return basic_info
    
    try:
        prompt = f"""
        I need comprehensive, accurate information about the medication {med_name}. 
        Please provide the following details in a well-structured markdown format:
        
        1. Brief overview of what {med_name} is
        2. Common uses and conditions it treats
        3. Important side effects to be aware of
        4. Special precautions and considerations for patients
        5. Typical dosing information (though mention that exact dosing should come from a doctor)
        
        Make the information concise but comprehensive, and format it nicely with markdown headers.
        """
        
        response = model.generate_content(prompt)
        
        if response and hasattr(response, 'text'):
            # Combine OpenFDA and Gemini information
            combined_info = f"""## Medication Information: {med_name.title()}

### Database Information:
{basic_info}

### Additional Information:
{response.text}

> *Always consult your healthcare provider for personalized medical advice.*
"""
            return combined_info
        else:
            return basic_info
    except Exception as e:
        print(f"Gemini API error: {str(e)}")
        return basic_info

# Add a fallback function for when FALLBACKS_ENABLED is True but the module is not imported
def get_backup_disease_info(disease_name):
    """Function to get backup disease info when the fallback module is not available"""
    common_descriptions = {
        "gastroenteritis": """## Information About Gastroenteritis

### What is Gastroenteritis?
Gastroenteritis is an inflammation of the lining of the intestines caused by a virus, bacteria, or parasites. It's commonly known as the stomach flu.

### Common Symptoms
- Watery diarrhea
- Abdominal cramps and pain
- Nausea, vomiting
- Occasional fever
- Headache and muscle aches

### How is it Transmitted/Caused?
- Viral infection (most common)
- Bacterial infection from contaminated food or water
- Parasites
- Medication side effects
- Food allergies

### Common Treatments
- Rest and hydration
- Oral rehydration solutions
- Anti-diarrheal medications (in some cases)
- Antibiotics (only for certain bacterial infections)
- Probiotics may help recovery

### Prevention Measures
- Frequent handwashing
- Safe food handling and preparation
- Avoiding close contact with infected individuals
- Drinking clean, safe water
- Getting rotavirus vaccine (for infants)

*Would you like to set a reminder for any medications related to this condition? Please specify which medication.*""",
        "diarrhea": """## Information About Diarrhea

### What is Diarrhea?
Diarrhea is loose, watery stools that occur more frequently than usual. It's typically a symptom of an underlying condition rather than a disease itself.

### Common Symptoms
- Loose, watery stools
- Abdominal cramps or pain
- Urgency to use the bathroom
- Nausea
- Possible fever or blood in stool (in severe cases)

### How is it Transmitted/Caused?
- Viral infections
- Bacterial infections
- Parasitic infections
- Food intolerances or allergies
- Medications (especially antibiotics)
- Digestive disorders (IBS, IBD, etc.)

### Common Treatments
- Hydration (most important)
- Oral rehydration solutions
- Anti-diarrheal medications (loperamide, bismuth subsalicylate)
- Probiotics
- Bland diet (BRAT - bananas, rice, applesauce, toast)
- Treating underlying cause

### Prevention Measures
- Handwashing
- Safe food handling
- Clean drinking water
- Avoiding food triggers
- Proper hygiene when traveling

*Would you like to set a reminder for any medications related to this condition? Please specify which medication.*"""
    }
            
    if disease_name.lower() in common_descriptions:
        return common_descriptions[disease_name.lower()], disease_name.lower()
            
    return None

if __name__ == "__main__":
    app.run(debug=True)
