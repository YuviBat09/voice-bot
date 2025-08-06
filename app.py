from flask import Flask, request, jsonify
import vonage
import openai
import os
from dotenv import load_dotenv
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize clients with error handling
try:
    vonage_client = vonage.Client(
        key=os.getenv('VONAGE_API_KEY'),
        secret=os.getenv('VONAGE_API_SECRET')
    )
    logger.info("Vonage client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Vonage client: {e}")
    vonage_client = None

# Initialize OpenAI
try:
    openai.api_key = os.getenv('OPENAI_API_KEY')
    logger.info("OpenAI API key set successfully")
except Exception as e:
    logger.error(f"Failed to set OpenAI API key: {e}")

# Simple conversation memory
conversations = {}

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint"""
    status = {
        "status": "running",
        "vonage_client": "initialized" if vonage_client else "failed",
        "openai_api": "set" if openai.api_key else "missing"
    }
    logger.info(f"Health check: {status}")
    return jsonify(status)

@app.route("/webhooks/answer", methods=["GET", "POST"])
def answer_call():
    """Handle incoming calls"""
    call_uuid = request.args.get('uuid', 'unknown')
    print(f"Incoming call: {call_uuid}")
    
    # Initialize conversation for this call
    conversations[call_uuid] = []
    
    ncco = [
        {
            "action": "talk",
            "text": "Hello! I'm your AI assistant. Press 1 to test me, or press 2 for help.",
            "voiceName": "Amy"
        },
        {
            "action": "input",
            "eventUrl": [f"{get_base_url()}/webhooks/dtmf"],
            "type": ["dtmf"],
            "dtmf": {
                "timeOut": 10,
                "maxDigits": 1
            }
        }
    ]
    
    return jsonify(ncco)

@app.route("/webhooks/dtmf", methods=["POST"])
def handle_dtmf():
    """Process keypad input and generate AI response"""
    data = request.get_json()
    call_uuid = data.get('uuid')
    dtmf_input = data.get('dtmf', '')
    
    print(f"User pressed: {dtmf_input}")
    
    # Convert keypad press to text
    if dtmf_input == '1':
        user_message = "Hello, test my AI capabilities"
    elif dtmf_input == '2':
        user_message = "What can you help me with?"
    else:
        user_message = "I pressed a key on my phone"
    
    # Get AI response
    ai_response = get_ai_response(call_uuid, user_message)
    
    ncco = [
        {
            "action": "talk",
            "text": ai_response + " Press 1 to continue testing, or hang up to end.",
            "voiceName": "Amy"
        },
        {
            "action": "input",
            "eventUrl": [f"{get_base_url()}/webhooks/dtmf"],
            "type": ["dtmf"],
            "dtmf": {
                "timeOut": 10,
                "maxDigits": 1
            }
        }
    ]
    
    return jsonify(ncco)
    """Process speech input and generate AI response"""
    data = request.get_json()
    call_uuid = data.get('uuid')
    speech_text = data.get('speech', {}).get('results', [{}])[0].get('text', '')
    
    print(f"User said: {speech_text}")
    
    if not speech_text:
        # No speech detected, ask again
        ncco = [
            {
                "action": "talk",
                "text": "I didn't catch that. Could you please repeat?",
                "voiceName": "Amy"
            },
            {
                "action": "input",
                "eventUrl": [f"{get_base_url()}/webhooks/speech"],
                "type": ["speech"],
                "speech": {
                    "endOnSilence": 3,
                    "language": "en-US",
                    "startTimeout": 10,
                    "maxDuration": 60
                }
            }
        ]
        return jsonify(ncco)
    
    # Get AI response
    ai_response = get_ai_response(call_uuid, speech_text)
    
    # Continue conversation or end call
    if "goodbye" in speech_text.lower() or "bye" in speech_text.lower():
        ncco = [
            {
                "action": "talk",
                "text": ai_response + " Goodbye!",
                "voiceName": "Amy"
            }
        ]
    else:
        ncco = [
            {
                "action": "talk",
                "text": ai_response,
                "voiceName": "Amy",
                "bargeIn": True
            },
            {
                "action": "input",
                "eventUrl": [f"{get_base_url()}/webhooks/speech"],
                "type": ["speech"],
                "speech": {
                    "endOnSilence": 3,
                    "language": "en-US",
                    "startTimeout": 10,
                    "maxDuration": 60
                }
            }
        ]
    
    return jsonify(ncco)

@app.route("/webhooks/events", methods=["POST"])
def handle_events():
    """Handle call events (started, completed, etc.)"""
    data = request.get_json()
    print(f"Event: {data}")
    
    # Clean up conversation when call ends
    if data.get('status') == 'completed':
        call_uuid = data.get('uuid')
        if call_uuid in conversations:
            del conversations[call_uuid]
            print(f"Cleaned up conversation for {call_uuid}")
    
    return "OK"

def get_ai_response(call_uuid, user_message):
    """Generate AI response using OpenAI"""
    try:
        # Add user message to conversation history
        if call_uuid not in conversations:
            conversations[call_uuid] = []
        
        conversations[call_uuid].append({"role": "user", "content": user_message})
        
        # System prompt for the voice bot
        system_prompt = """You are a helpful AI assistant answering phone calls. 
        Keep responses conversational, concise (under 50 words), and friendly. 
        You can help with general questions, provide information, and have casual conversations.
        If you don't know something, be honest about it."""
        
        messages = [{"role": "system", "content": system_prompt}] + conversations[call_uuid]
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=150,
            temperature=0.7
        )
        
        ai_message = response.choices[0].message.content
        
        # Add AI response to conversation history
        conversations[call_uuid].append({"role": "assistant", "content": ai_message})
        
        # Keep conversation history manageable (last 10 exchanges)
        if len(conversations[call_uuid]) > 20:
            conversations[call_uuid] = conversations[call_uuid][-20:]
        
        return ai_message
        
    except Exception as e:
        print(f"Error getting AI response: {e}")
        return "I'm sorry, I'm having trouble processing that right now. Could you try again?"

def get_base_url():
    """Get base URL for webhooks"""
    return request.url_root.rstrip('/')

if __name__ == "__main__":
    print("Starting voice bot server...")
    print("Make sure to:")
    print("1. Set up your .env file with API keys")
    print("2. Configure webhooks in Vonage dashboard")
    
    # Use Railway's PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
