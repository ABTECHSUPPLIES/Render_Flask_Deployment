import os
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda: None
import openai
from flask import Flask, render_template, request, jsonify, session
import markdown
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

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")

# OpenAI setup
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logging.error("⚠️ ERROR: OpenAI API key is missing!")
    raise ValueError("OpenAI API key is missing.")
client = openai.OpenAI(api_key=openai_api_key)
logging.info("✅ OpenAI API key loaded successfully.")

# Sales tracking with promised category
sales_data = {"completed": [], "pending": [], "promised": []}
user_states = {}
state_lock = threading.Lock()

PRICE_LIST = """
📌 iPhone Price List – 40% Discount Applied  
Older Models:  
- iPhone X: ~~R7,999~~ Now R4,799 (Storage: 64GB, 128GB +R500, 256GB +R1,000; Colors: Space Gray, Silver)  
- iPhone XS: ~~R8,999~~ Now R5,399 (Storage: 64GB, 256GB +R600, 512GB +R1,200; Colors: Space Gray, Silver, Gold)  
- iPhone XS Max: ~~R9,999~~ Now R5,999 (Storage: 64GB, 256GB +R600, 512GB +R1,200; Colors: Space Gray, Silver, Gold)  
Mid-Range Models:  
- iPhone 11 Pro: ~~R12,999~~ Now R7,799 (Storage: 64GB, 256GB +R600, 512GB +R1,200; Colors: Space Gray, Silver, Gold, Midnight Green)  
- iPhone 11 Pro Max: ~~R13,999~~ Now R8,399 (Storage: 64GB, 256GB +R600, 512GB +R1,200; Colors: Space Gray, Silver, Gold, Midnight Green)  
- iPhone 12 Pro: ~~R15,999~~ Now R9,599 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Graphite, Silver, Gold, Pacific Blue)  
- iPhone 12 Pro Max: ~~R16,999~~ Now R10,199 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Graphite, Silver, Gold, Pacific Blue)  
- iPhone 13: ~~R12,582~~ Now R7,549 (Storage: 128GB, 256GB +R500, 512GB +R1,000; Colors: Pink, Blue, Midnight, Starlight, Red, Green)  
Newer Models:  
- iPhone 13 Pro: ~~R17,999~~ Now R10,799 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Graphite, Gold, Silver, Sierra Blue, Alpine Green)  
- iPhone 13 Pro Max: ~~R18,999~~ Now R11,399 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Graphite, Gold, Silver, Sierra Blue, Alpine Green)  
- iPhone 14 Pro: ~~R20,999~~ Now R12,599 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Space Black, Silver, Gold, Deep Purple)  
- iPhone 14 Pro Max: ~~R21,999~~ Now R13,199 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Space Black, Silver, Gold, Deep Purple)  
Latest Models:  
- iPhone 15 Pro: ~~R22,999~~ Now R13,799 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Black Titanium, White Titanium, Natural Titanium, Blue Titanium)  
- iPhone 15 Pro Max: ~~R23,999~~ Now R14,399 (Storage: 256GB, 512GB +R600, 1TB +R1,200; Colors: Black Titanium, White Titanium, Natural Titanium, Blue Titanium)  
- iPhone 16 Pro: ~~R24,999~~ Now R14,999 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Black Titanium, White Titanium, Natural Titanium, Blue Titanium)  
- iPhone 16 Pro Max: ~~R25,999~~ Now R15,599 (Storage: 128GB, 256GB +R600, 512GB +R1,200; Colors: Black Titanium, White Titanium, Natural Titanium, Blue Titanium)
"""

def query_openai(customer_message: str, context: list) -> str:
    try:
        messages = [
            {"role": "system", "content": """
            You are an AI assistant named "A N B Tech Supplies" specializing in iPhone sales for ANB Tech Supplies, a South African retailer. 
            Assist customers with iPhone models (X to 16 Pro Max), pricing, installment plans, and purchase inquiries. 
            Use pricing from the provided PRICE_LIST with 40% discount applied. 
            Banking details: Account Number: 1773081371, Bank: Capitec, Name: Mr N Nkapele. 
            Respond clearly, politely, with short sentences and simple language. 
            Maintain context from previous messages. 
            Do not include links unless specified in predefined responses. 
            Do not invent banking details.
            """}
        ] + context + [{"role": "user", "content": customer_message}]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except openai.OpenAIError as e:
        logging.error(f"OpenAI query failed: {e}")
        return "⚠️ Sorry, I couldn’t process your request. How can I assist otherwise?"

def is_admin(message_body: str) -> bool:
    return "admin access granted" in message_body.lower()

def generate_sales_report() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    completed_count = len(sales_data["completed"])
    pending_count = len(sales_data["pending"])
    promised_count = len([p for p in sales_data["promised"] if p["date"] == today])
    
    report = f"📊 Sales Report\nCompleted Sales: {completed_count}\n"
    for sale in sales_data["completed"]:
        report += f"- [Phone]: {sale['item']} (R{sale['amount']}) on {sale['date']}\n"
    report += f"Pending Sales: {pending_count}\n"
    for pend in sales_data["pending"]:
        report += f"- [Phone]: {pend['item']} (R{pend['amount']})\n"
    report += f"Promised Today ({today}): {promised_count}\n"
    for prom in [p for p in sales_data["promised"] if p["date"] == today]:
        report += f"- [Phone]: {prom['item']} (R{prom['amount']})\n"
    return report

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

def reminder_thread():
    while True:
        with state_lock:
            current_time = time.time()
            for session_id, state in list(user_states.items()):
                reminder_time = state.get("reminder_time", 0)
                if reminder_time and current_time >= reminder_time:
                    state["reminder_response"] = f"⏰ Your Reminder: {state['reminder_text']}\nHow can I assist you now?"
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

        user_message = data.get("message", "").strip().lower()
        session_id = session["session_id"]
        context = session["context"]

        with state_lock:
            state = user_states.get(session_id, {"last_message_time": time.time()})
            state["last_message_time"] = time.time()
            user_states[session_id] = state

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
                            "amount": 9599,  # Default, update based on actual price later
                            "date": datetime.now().strftime("%Y-%m-%d")
                        })
                response = "✅ Payment received! Thanks for your purchase. How else can I assist you?"
            else:
                response = "Please include order details after 'PAID' (e.g., 'PAID Pink iPhone 13 128GB')."
        elif user_message in ["price", "cost"]:
            response = PRICE_LIST
        elif user_message in ["recommend", "suggest"]:
            response = """
            📱 Top Picks for You  
            - iPhone 12 Pro + Wireless Charger: R10,899  
            - iPhone 14 Pro Max + Case: R14,299  
            Want more details or ready to buy? Just let me know!
            """
        elif user_message in ["installment", "monthly"]:
            response = """
            💳 Monthly Installment Plan  
            - Minimum Deposit: R750  
            - Flexible Repayment: Up to 24 months  
            Example for iPhone X (R4,799):  
            - 3 Months: R1,349/month  
            - 6 Months: R674/month  
            - 12 Months: R337/month  
            - 18 Months: R224/month  
            - 24 Months: R169/month  
            To apply, visit: https://applications-yzex.onrender.com/
            """
        elif any(word in user_message for word in ["picture", "pictures", "image", "images"]):
            response = """
            📸 See iPhones & Customize Your Order  
            Visit: https://iphone-customizer.onrender.com/
            """
        elif any(word in user_message for word in ["buy", "order", "purchase"]):
            response = """
            ✅ Ready to Buy? Here’s How  
            Prices:  
            - iPhone 12 Pro: R9,599  
            - iPhone 13 Pro Max: R11,399  
            Payment Options:  
            - 💳 Credit/Debit Card  
            - 💳 PayPal  
            - 🏦 Bank Transfer:  
              Account Number: 1773081371  
              Bank: Capitec  
              Name: Mr N Nkapele  
            - 📅 Installment Plan (up to 24 months)  
            For installments, ask me for the link!  
            Which option works for you?  
            Once paid, reply with "PAID" and your order details!
            """
        elif user_message == "promo":
            response = """
            🎉 Special Offer!  
            Get 5% off your next iPhone this week only.  
            Reply "PROMO" to claim it or ask for details!
            """
        elif "ad" in user_message:
            response = """
            👋 Thanks for replying!  
            We’re ANB Tech Supplies.  
            We sell the latest iPhones at great prices.  
            From the iPhone X to the iPhone 16 Pro Max, we have it all!  
            Flexible payment options too.  
            See our range and customize your order: https://iphone-customizer.onrender.com/  
            How can I assist you today?
            """
        elif seconds := parse_reminder(user_message)[0]:
            seconds, unit, _ = parse_reminder(user_message)
            reminder_text = user_message.split("about", 1)[1].strip() if "about" in user_message else "Your request"
            response = f"⏰ Reminder Set\nI’ll remind you in {seconds // (60 if unit == 'minutes' else 3600 if unit == 'hours' else 24 * 3600)} {unit}."
            with state_lock:
                state["reminder_time"] = time.time() + seconds
                state["reminder_text"] = reminder_text
                user_states[session_id] = state
        else:
            response = query_openai(user_message, context)

        with state_lock:
            if session_id in user_states and "reminder_response" in user_states[session_id]:
                response = user_states[session_id]["reminder_response"] + "\n" + response
                del user_states[session_id]["reminder_response"]

        context.append({"role": "user", "content": user_message})
        context.append({"role": "assistant", "content": response})
        if len(context) > 20:
            context = context[-20:]
        session["context"] = context

        formatted_response = markdown.markdown(response)
        return jsonify({"response": formatted_response})

    except openai.OpenAIError as e:
        logging.error(f"⚠️ OpenAI Error: {str(e)}")
        formatted_response = markdown.markdown("⚠️ Sorry, there was an error processing your request. Please try again.")
        return jsonify({"response": formatted_response}), 500
    except Exception as e:
        logging.error(f"⚠️ General Error: {str(e)}")
        formatted_response = markdown.markdown("⚠️ Sorry, an unexpected error occurred. Please try again.")
        return jsonify({"response": formatted_response}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
