import os
from dotenv import load_dotenv
from plivo import RestClient
from plivo.utils.template import Template
import google.generativeai as genai
from datetime import datetime
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize API clients
auth_id = os.getenv('PLIVO_AUTH_ID')
auth_token = os.getenv('PLIVO_AUTH_TOKEN')
GENAI_API_KEY = os.getenv("GOOGLE_API_KEY")

# Configure the Gemini API
genai.configure(api_key=GENAI_API_KEY)

# Initialize Plivo client
client = RestClient(auth_id, auth_token)

def send_templated_message(recipient_number, url, number):
    """
    Sends a WhatsApp message using a predefined template with PDF URL.
    
    Args:
        recipient_number (str): Recipient's WhatsApp number with country code
        url (str): URL of the PDF document to send
        number (str): Phone number for the web link parameter
    """
    try:
        # Generate the full web URL with the phone number parameter
        full_url = f"https://web-production-b5ae9.up.railway.app/?phonenumber={number}"
        
        # Shorten the URL using cleanuri.com API
        shorten_response = requests.post(
            "https://cleanuri.com/api/v1/shorten",
            data={"url": full_url},
        )
        
        # Get the shortened URL or use the original if shortening fails
        if shorten_response.status_code == 200:
            short_web_url = shorten_response.json().get("result_url")
        else:
            logger.error(f"Error shortening URL: {shorten_response.text}")
            short_web_url = full_url
        
        # Remove https:// from URLs as per template requirements
        short_web_url = short_web_url.replace("https://", "")
        url = url.replace("https://", "")
        
        # Define the template structure
        template = Template(**{
            "name": "pdf_regi_template",  # Template name
            "language": "en",
            "components": [{
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": url
                    },
                    {
                        "type": "text",
                        "text": short_web_url
                    }
                ]
            }]
        })
        
        # Send the WhatsApp message with the template
        response = client.messages.create(
            src="+15557282843",  # Your Plivo WhatsApp-enabled number
            dst=recipient_number,  # Recipient's WhatsApp number
            type_="whatsapp",
            template=template,
        )
        logger.info(f"Message sent successfully. UUID: {response}")
        return response
    except Exception as e:
        logger.error(f"Error sending templated message: {str(e)}")
        raise

def send_simple_whatsapp(recipient_number, message_text):
    """
    Sends a simple WhatsApp text message.
    
    Args:
        recipient_number (str): Recipient's WhatsApp number with country code
        message_text (str): The message text to send
    """
    try:
        response = client.messages.create(
            src="+15557282843",
            dst=recipient_number,
            text=message_text,
            type_="whatsapp"
        )
        logger.info(f"Simple message sent successfully. UUID: {response.message_uuid}")
        return response
    except Exception as e:
        logger.error(f"Error sending simple WhatsApp message: {str(e)}")
        raise

def generate_inquiry_invoice(transcript_and_queries: str):
    """
    Generates an invoice-like summary of product inquiries from a conversation transcript.
    
    Args:
        transcript_and_queries (str): The transcript text containing conversation and queries
        
    Returns:
        str: A formatted invoice-like summary
    """
    try:
        today = datetime.now().strftime("%d %B %Y")
        
        prompt = f"""
                You are a helpful assistant.

                Based on the following CALL TRANSCRIPT & DATABASE QUERIES, summarize the user's **inquired products** into a WhatsApp-style **readable invoice-like format**.

                **IMPORTANT NOTES:**
                - The customer has only *inquired* about the items, not purchased them.
                - Format output like a clean product invoice, with quantity, unit price, total price per item (if available).
                - If quantity or price is not available, don't show the item in the invoice.
                - At the end, add a line with the **Total Payable Amount** summing only the items with valid total prices.
                - ALWAYS include a separate and prominent section clearly showing APPOINTMENT details if present.
                - Look for information under "APPOINTMENT BOOKING", "APPOINTMENT SUMMARY", or "CALENDAR QUERY" sections.
                - If appointments are found, format them clearly with date, time, and status.
                - Keep the tone polite and informative.
                - Keep message with proper line breaks and spaces as this response will be converted into pdf format.
                - Include today's date as `{today}`.
                - If no transcript is available, just say "Thank you for the call"
                - Do not include symbols like ₹ or $ in the invoice. Just use INR.
                Here is the input:

                {transcript_and_queries}

                Generate output in this format:

                Product Inquiry Summary  
                Date: [Date]

                Requested Items: [List of general items, e.g., Bearings, Impellers]

                S.No   Product Name               Quantity    Unit Price    Total Price  
                1      [Product Name]             [Qty]       [INR]           [INR]  
                2      [Product Name]             [Qty]       [INR]           [INR]  
                ...  

                💵 Total Estimated Cost: INR [total]

                APPOINTMENT DETAILS (if any):
                Date: [Date]
                Time: [Time]
                Status: [Confirmed/Pending]
                
                No need to provide the calendar link.
                Note: This is only a summary of product inquiries. Let us know if you'd like to proceed or have any other questions.
                Thank you for your inquiry!
        """

        # Use Gemini for AI text generation
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        
        return response.text
    except Exception as e:
        logger.error(f"Error generating invoice: {str(e)}")
        return f"Thank you for your call. (Error generating summary: {str(e)})"