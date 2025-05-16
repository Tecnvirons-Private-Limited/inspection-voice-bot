import phonenumbers
from phonenumbers import PhoneNumberType, NumberParseException
import requests
import time
import re

def extract_mobile_numbers(raw, country):
    """Extract valid mobile numbers for a specific country."""
    # Pre-filter text with regex to find potential phone number patterns
    # This helps reduce the number of parsing attempts
    potential_numbers = re.findall(r'(?:\+\d{1,3})?[\s-]?\(?(?:\d{1,4})\)?[\s.-]?\d{3}[\s.-]?\d{4}', raw)
    
    valid_mobiles = []
    for potential in potential_numbers:
        try:
            number = phonenumbers.parse(potential, country)
            if (
                phonenumbers.is_valid_number(number) and
                phonenumbers.region_code_for_number(number) == country and
                phonenumbers.number_type(number) == PhoneNumberType.MOBILE
            ):
                # Format as E.164 (e.g., +9179XXXXXXXX)
                formatted = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
                if formatted not in valid_mobiles:  # Avoid duplicates
                    valid_mobiles.append(formatted)
        except NumberParseException:
            continue
    
    print(f"Valid mobile numbers found: {valid_mobiles}")
    return valid_mobiles

def extract_indian_whatsapp_numbers(raw):
    """Extract valid Indian mobile numbers and check WhatsApp status"""
    country = "IN"  # India specific
    valid_mobiles = extract_mobile_numbers(raw, country)
    
    whatsapp_numbers = []
    print("Checking WhatsApp status for each number...")
    
    for number in valid_mobiles:
        # Add delay to avoid rate limiting
        time.sleep(1)
        if check_whatsapp_existence(number):
            whatsapp_numbers.append(number)
    
    return whatsapp_numbers

def check_whatsapp_existence(phone_number):
    """
    Check if a phone number exists on WhatsApp
    Note: This is not 100% reliable as WhatsApp doesn't provide an official API for this
    """
    # Remove '+' from the number
    clean_number = phone_number.replace('+', '')
    
    # WhatsApp's click-to-chat API
    url = f"https://wa.me/{clean_number}"
    
    try:
        # Use a realistic user agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Set a shorter timeout to improve response time
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=5)
        
        # The best indicator available is that WhatsApp doesn't reject the number
        if response.status_code == 200:
            print(f"✓ {phone_number} appears to be on WhatsApp")
            return True
        else:
            print(f"✗ {phone_number} does not appear to be on WhatsApp (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"Error checking {phone_number}: {e}")
        # Default to True in case of error to enable sending message attempts
        return True
    
# Example usage
if __name__ == "__main__":
    raw_text = "Call me at +919869730965 or +91-9869730965. My number is 9869730965."
    whatsapp_numbers = extract_indian_whatsapp_numbers(raw_text)
    print("Indian numbers on WhatsApp:", whatsapp_numbers)