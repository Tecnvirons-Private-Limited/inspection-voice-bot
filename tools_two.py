import os
import logging
import requests
import io
from datetime import datetime
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from supabase import create_client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Supabase client with service role key to bypass RLS
supabase_url = os.getenv("SUPABASE_URLL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEYY")  # Using service role key
supabase = create_client(supabase_url, supabase_key)

# Bucket name constant
BUCKET_NAME = "billings-data"

def ensure_bucket_exists(bucket_name):
    """Check if bucket exists, create if it doesn't, and ensure it's public"""
    try:
        # List all buckets to check if our bucket exists
        buckets = supabase.storage.list_buckets()
        bucket_exists = any(bucket.name == bucket_name for bucket in buckets)
        
        if not bucket_exists:
            logger.info(f"Bucket '{bucket_name}' not found. Creating it...")
            # Create the bucket with public access
            supabase.storage.create_bucket(bucket_name, {"public": True})
            logger.info(f"Bucket '{bucket_name}' created successfully.")
        else:
            logger.info(f"Bucket '{bucket_name}' already exists.")
            
            # Ensure the bucket is public
            supabase.storage.update_bucket(bucket_name, {"public": True})
            logger.info(f"Updated '{bucket_name}' bucket to be public.")
            
        return True
    except Exception as e:
        logger.error(f"Error managing bucket: {str(e)}")
        if hasattr(e, 'response'):
            logger.error(f"Response details: {e.response.text if hasattr(e.response, 'text') else e.response}")
        return False

def upload_text_to_pdf_and_get_short_url(text_content, filename_prefix="invoice"):
    """
    Convert text to PDF, upload to Supabase, and return shortened URL
    
    Args:
        text_content (str): The text content to include in the PDF
        filename_prefix (str, optional): Prefix for the generated filename.
        
    Returns:
        str: Shortened URL for the uploaded PDF, or None if an error occurs
    """
    try:
        # Ensure the bucket exists and is public
        if not ensure_bucket_exists(BUCKET_NAME):
            raise Exception(f"Failed to create or confirm bucket {BUCKET_NAME}")
            
        # Create PDF from provided text
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Create content elements
        elements = []
        for line in text_content.split('\n'):
            elements.append(Paragraph(line, styles['Normal']))
            elements.append(Spacer(1, 6))
        
        # Build the PDF
        doc.build(elements)
        buffer.seek(0)
        
        # Generate a unique filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{filename_prefix}_{timestamp}.pdf"
        
        # Upload the file to Supabase
        result = supabase.storage.from_(BUCKET_NAME).upload(
            path=filename,
            file=buffer.getvalue(),
            file_options={"content-type": "application/pdf"}
        )
        logger.info(f"Upload result: {result}")
        
        # Get public URL that doesn't expire
        pdf_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        logger.info(f"Generated URL: {pdf_url}")
        
        # Test the URL to make sure it's accessible
        test_response = requests.head(pdf_url)
        if test_response.status_code >= 400:
            logger.warning(f"The URL may not be accessible. Status code: {test_response.status_code}")
        
        # Shorten URL using CleanURI API
        shorten_response = requests.post(
            "https://cleanuri.com/api/v1/shorten",
            data={"url": pdf_url},
        )
        
        # Return the shortened URL or original if shortening fails
        if shorten_response.status_code == 200:
            short_url = shorten_response.json().get("result_url")
            logger.info(f"Shortened URL: {short_url}")
            return short_url
        else:
            logger.warning(f"Error shortening URL: {shorten_response.text}")
            return pdf_url
    
    except Exception as e:
        logger.error(f"Error creating/uploading PDF: {str(e)}")
        if hasattr(e, 'response'):
            logger.error(f"Response details: {e.response.text if hasattr(e.response, 'text') else e.response}")
        return None