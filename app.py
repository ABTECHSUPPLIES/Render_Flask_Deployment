from flask import Flask, render_template, request, jsonify
import openai
import markdown
import os

app = Flask(__name__)

# Securely retrieve OpenAI API Key from environment variable
openai_api_key = os.getenv("OPENAI_API_KEY")

if not openai_api_key:
    print("⚠️ ERROR: OpenAI API key is missing! Set it in your environment variables.")
else:
    print("✅ OpenAI API key loaded successfully.")

openai.api_key = openai_api_key

# iPhone Models & Prices (Before Discount)
IPHONES = {
    "iPhone XS": 8999, "iPhone XS Max": 9999, "iPhone 11 Pro": 12999,
    "iPhone 11 Pro Max": 13999, "iPhone 12 Pro": 15999, "iPhone 12 Pro Max": 16999,
    "iPhone 13 Pro": 17999, "iPhone 13 Pro Max": 18999, "iPhone 14 Pro": 20999,
    "iPhone 14 Pro Max": 21999, "iPhone 15 Pro": 22999, "iPhone 15 Pro Max": 23999,
    "iPhone 16 Pro": 24999, "iPhone 16 Pro Max": 25999
}

# Apply 40% Discount
def get_discounted_prices():
    return {model: int(price * 0.6) for model, price in IPHONES.items()}

@app.route('/')
def home():
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message", "").strip().lower()

    # Custom chatbot logic for ANB Tech Supplies
    prices = get_discounted_prices()

    system_prompt = f"""
This GPT serves as a customer support assistant exclusively for ANB Tech Supplies. It helps customers with inquiries about iPhones and related products available from ANB Tech Supplies. It provides detailed product information, answers to queries about shipping, warranties, and store policies, and supports customers by highlighting available iPhone models (XS to 16 Pro Max, including all Pro versions), their features, pricing in South African Rand (ZAR), and discounts. The assistant also offers customization options such as engravings and accessory bundles.

### **Updated Pricing - 40% Discount Applied**
The assistant now automatically reduces iPhone prices by 40% when providing price details. Customers will see the discounted prices instead of the original ones.

**📍 Store Information:**
- **Address:** 609 Roger St, Lusikisiki, Eastern Cape, South Africa, 4828
- **Phone:** +27 82 888 2353

✅ **Order Submission:**  
- Selected iPhone model & color details will be sent to:  
  📩 **+27 68 830 8314**

✅ **Banking Details & Proof of Payment Submission:**  
- **Account Holder:** Jayden Allen  
- **Bank Name:** TymeBank (Business)  
- **Branch Code:** 678910  
- **Account Number:** 51059661139  
- Customers must send **proof of payment** to WhatsApp: 📩 **+27 68 830 8314**  
- **Orders will only be confirmed after proof of payment is received.**
"""

    try:
        if "picture" in user_message or "image" in user_message:
            response = """
            **📸 iPhone Images**  

            **🔗 View iPhone Pictures Here:**  
            👉 [Click to View iPhone Images](https://abtechsupplies.github.io/Pictures/)  

            **💬 Need Help?**  
            If you have any issues viewing the pictures, you can request them via WhatsApp at:  
            **📞 078 870 9557**  

            **🎨 Looking for a specific color?**  
            Let me know, and I can provide more details based on your preference!
            """
        else:
            gpt_response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
            )
            response = gpt_response["choices"][0]["message"]["content"]

        # Convert Markdown to formatted HTML
        formatted_response = markdown.markdown(response)

    except Exception as e:
        print(f"⚠️ ERROR: {str(e)}")  # Log error in console
        formatted_response = "⚠️ Sorry, there was an error processing your request. Please try again."

    return jsonify({"response": formatted_response})

if __name__ == '__main__':
    app.run()
