from flask import Flask, request, jsonify
import vonage
import openai
import os
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize Vonage client
vonage_client = vonage.Client(
    key=os.getenv('VONAGE_API_KEY'),
    secret=os.getenv('VONAGE_API_SECRET')
)

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Simple conversation memory (in production, use a database)
conversations = {}


@app.route("/", methods=["GET"])
def health_check():
    return "Voice bot is running!"


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
            "text": "Hello Yuvi, I think we are working.",
            "voiceName": "Amy",
            "bargeIn": True
        },
        {
            "action": "input",
            "eventUrl": [f"{get_base_url()}/webhooks/speech"],
            "speech": {
                "uuid": [call_uuid],
                "endOnSilence": 2,
                "language": "en-US",
                "context": ["customer_service", "general_inquiry"]
            }
        }
    ]

    return jsonify(ncco)


@app.route("/webhooks/speech", methods=["POST"])
def handle_speech():
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
                "speech": {
                    "uuid": [call_uuid],
                    "endOnSilence": 2,
                    "language": "en-US"
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
                "speech": {
                    "uuid": [call_uuid],
                    "endOnSilence": 2,
                    "language": "en-US"
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
        If you don't know something, be honest about it. Add in "uhh" and "umm" on ocasaion, make the conversaiton human"""

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
    print("2. Run ngrok to expose this server")
    print("3. Configure webhooks in Vonage dashboard")

    app.run(debug=True, port=5000)