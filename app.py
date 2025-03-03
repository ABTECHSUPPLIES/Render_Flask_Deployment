import os
import openai
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
import logging
import threading
import time
from datetime import datetime
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")

# Load OpenAI API key
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY environment variable is missing.")
client = openai.OpenAI(api_key=openai_api_key)
logging.info("✅ OpenAI API key loaded successfully.")

# Sales tracking and user states
sales_data = {"completed": [], "pending": []}
user_states = {}
state_lock = threading.Lock()

# Query OpenAI
def query_openai(customer_message: str, context: list) -> str:
    try:
        messages = [
            {"role": "system", "content": """
            You are an AI assistant for ANB Tech Supplies, specializing in iPhone sales. Assist customers with iPhone models, pricing (apply a 40% discount), installment plans, and inquiries. Respond clearly, politely, and helpfully with short sentences and simple language. Maintain context from previous messages. Use only these banking details when asked: Account Number: 1773081371, Bank: Capitec, Name: Mr N Nkapele. For specific requests (e.g., "Pink iPhone 13, 128GB"), provide tailored details.
            """}
        ] + context + [{"role": "user", "content": customer_message}]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except openai.OpenAIError as e:
        logging.error(f"OpenAI query failed: {e}")
        return "Sorry, I couldn’t process your request. How can I assist otherwise?"

# Check for admin access
def is_admin(message_body: str) -> bool:
    return "admin access granted" in message_body.lower()

# Generate sales report
def generate_sales_report() -> str:
    completed_count = len(sales_data["completed"])
    pending_count = len(sales_data["pending"])
    report = f"📊 Sales Report\n\nCompleted: {completed_count}\n"
    for sale in sales_data["completed"]:
        report += f"- {sale['item']} (R{sale['amount']}) on {sale['date']}\n"
    report += f"\nPending: {pending_count}\n"
    for pend in sales_data["pending"]:
        report += f"- {pend['item']} (R{pend['amount']})\n"
    return report

# Parse reminder request
def parse_reminder(message: str) -> tuple[int, str, bool]:
    pattern = r"remind me in (\d+) (minute|minutes|hour|hours|day|days)"
    match = re.search(pattern, message.lower())
    if match:
        value, unit = int(match.group(1)), match.group(2)
        if unit.startswith("minute"):
            return value * 60, "minutes", True
        elif unit.startswith("hour"):
            return value * 3600, "hours", True
        elif unit.startswith("day"):
            return value * 24 * 3600, "days", True
    return 0, "", False

# Reminder thread
def reminder_thread():
    while True:
        with state_lock:
            current_time = time.time()
            for session_id, state in list(user_states.items()):
                reminder_time = state.get("reminder_time", 0)
                if reminder_time and current_time >= reminder_time:
                    state["reminder_response"] = f"⏰ Reminder: {state['reminder_text']}\nHow can I help now?"
                    state["reminder_time"] = 0
                    state["reminder_text"] = ""
                    user_states[session_id] = state
        time.sleep(60)

threading.Thread(target=reminder_thread, daemon=True).start()

@app.route('/')
def home():
    session["context"] = session.get("context", [])
    session["session_id"] = session.get("session_id", os.urandom(16).hex())
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        if not data or "message" not in data:
            return jsonify({"error": "No message provided"}), 400

        user_message = data["message"].strip().lower()
        session_id = session["session_id"]
        context = session["context"]

        # Update user state
        with state_lock:
            state = user_states.get(session_id, {"last_message_time": time.time()})
            state["last_message_time"] = time.time()
            user_states[session_id] = state

        # Process message
        response = ""
        if is_admin(user_message):
            response = generate_sales_report()
        elif user_message.startswith("paid"):
            parts = user_message.split(" ", 1)
            if len(parts) > 1:
                order_details = parts[1].strip()
                with state_lock:
                    pending = [p for p in sales_data["pending"] if p["session_id"] == session_id]
                    if pending:
                        sale = pending[0]
                        sales_data["pending"].remove(sale)
                        sale["date"] = datetime.now().strftime("%Y-%m-%d")
                        sales_data["completed"].append(sale)
                    else:
                        sales_data["completed"].append({
                            "session_id": session_id,
                            "item": order_details,
                            "amount": 9599,  # Default amount
                            "date": datetime.now().strftime("%Y-%m-%d")
                        })
                response = "✅ Payment received! How else can I assist?"
            else:
                response = "Please include order details after 'PAID' (e.g., 'PAID iPhone 12 Pro')."
        elif seconds := parse_reminder(user_message)[0]:
            seconds, unit, _ = parse_reminder(user_message)
            reminder_text = user_message.split("about", 1)[1].strip() if "about" in user_message else "Your request"
            response = f"⏰ Reminder set for {seconds // (60 if unit == 'minutes' else 3600 if unit == 'hours' else 24 * 3600)} {unit}"
            with state_lock:
                state["reminder_time"] = time.time() + seconds
                state["reminder_text"] = reminder_text
                user_states[session_id] = state
        else:
            response = query_openai(user_message, context)

        # Check for reminder response
        with state_lock:
            if session_id in user_states and "reminder_response" in user_states[session_id]:
                response = user_states[session_id]["reminder_response"] + "\n" + response
                del user_states[session_id]["reminder_response"]

        # Update context
        context.append({"role": "user", "content": user_message})
        context.append({"role": "assistant", "content": response})
        if len(context) > 20:
            context = context[-20:]
        session["context"] = context

        return jsonify({"response": response})

    except openai.OpenAIError as e:
        logging.error(f"OpenAI API Error: {e}")
        return jsonify({"error": "Failed to process request."}), 500
    except Exception as e:
        logging.error(f"General Error: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "False") == "True")
