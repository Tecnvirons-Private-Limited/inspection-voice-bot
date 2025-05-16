import os
from dotenv import load_dotenv
from supabase import create_client, ClientOptions
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URLL")
supabase_key = os.getenv("SUPABASE_KEYY")  # Using anon key is fine for read operations
supabase = create_client(supabase_url, supabase_key)



def does_number_exist(phone_number):
    """
    Checks if a phone number exists in the Registration_form table.
    
    Args:
        phone_number (str): The phone number to check
        
    Returns:
        bool: True if the number exists, False otherwise
    """
    try:
        # Query the database for the phone number
        response = supabase.table("registration_form").select("phone_number").eq("phone_number", phone_number).execute()
        
        # Return True if phone number exists, False otherwise
        return bool(response.data and len(response.data) > 0)
            
    except Exception as e:
        logger.error(f"Database error while checking if number exists: {str(e)}")
        return False  # Return False on error to be safe


def get_user_details(phone_number):
    """
    Retrieves all user details from the Registration_form table using their phone number.
    
    Args:
        phone_number (str): The phone number to look up
        
    Returns:
        dict: User details with status information
    """
    try:
        # Query the database for the phone number
        response = supabase.table("registration_form").select("*").eq("phone_number", phone_number).execute()
        
        # Check if the phone number exists in the database
        if not response.data or len(response.data) == 0:
            return {
                "status": "not_found",
                "message": "Number is not registered",
                "data": None
            }
        
        # Check if the phone number exists but email is missing or null
        user_data = response.data[0]
        if not user_data.get('email') or (isinstance(user_data.get('email'), str) and user_data['email'].startswith('pending_')):
            return {
                "status": "incomplete",
                "message": "Registration incomplete. Please fill up the registration form.",
                "data": user_data
            }
            
        # Return all details if registration is complete
        return {
            "status": "success",
            "message": "User found",
            "data": user_data
        }
            
    except Exception as e:
        logger.error(f"Database error while retrieving user details: {str(e)}")
        return {
            "status": "error",
            "message": f"Error retrieving user details: {str(e)}",
            "data": None
        }
    
# user_info = get_user_details("7884455")
# if user_info["status"] == "success":
#     email = user_info["data"]["email"]
#     name = user_info["data"]["name"]
#     print(f"User found: {name}, Email: {email}")
#     # Use other fields as needed
# else:
#     # Handle not found, incomplete, or error cases
#     message = user_info["message"]
#     print(f"Status: {user_info['status']}, Message: {message}")

def add_phone_with_role(phone_number, role):
    """
    Adds a phone number and role to the Registration_form table.
    Only creates a new record if the phone number doesn't exist.
    
    Args:
        phone_number (str): The phone number to add
        role (str): The user's role
        
    Returns:
        dict: Status of the operation with message
    """
    try:
        # Check if the phone number already exists
        check_response = supabase.table("registration_form").select("phone_number").eq("phone_number", phone_number).execute()
        
        if check_response.data and len(check_response.data) > 0:
            # Phone number already exists
            logger.info(f"Phone number {phone_number} already exists in the database")
            return {"status": "exists", "message": "Phone number already exists"}
        else:
            # Create a new entry with placeholder values for required fields
            # Note: This will fail if email is already taken or if constraints aren't met
            new_record = {
                "phone_number": phone_number,
                "email": None,  # Placeholder, can be updated later
                "name": None,  # Placeholder, can be updated later
                'location': None,  # Placeholder, can be updated later
                "role": role
            }
            
            insert_response = supabase.table("registration_form").insert(new_record).execute()
            return {"status": "created", "message": "New phone number entry created"}
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Database error while adding phone with role: {error_msg}")
        return {"status": "error", "message": f"Failed to process registration: {error_msg}"}


