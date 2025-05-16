from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pathlib

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class UserRegistration(BaseModel):
    name: str
    phone_number: str
    email: str
    location: str
    role: str = None

class UserUpdate(BaseModel):
    name: str
    email: str
    location: str

# Routes
@app.get("/api/check-registration/{phone_number}")
async def check_registration(phone_number: str):
    try:
        response = supabase.table("registration_form").select("*").eq("phone_number", phone_number).execute()
        
        if len(response.data) > 0:
            user_data = response.data[0]
            # Check if all required fields are filled
            is_complete = all(user_data.get(field) for field in ["name", "email", "location"])
            return {
                "exists": True, 
                "is_complete": is_complete,
                "user_data": user_data
            }
        else:
            # Check if we have role information for this number
            role_response = supabase.table("registration_form").select("role").eq("phone_number", phone_number).execute()
            role = role_response.data[0]["role"] if role_response.data else None
            
            return {"exists": False, "role": role}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/register")
async def register_user(user_data: UserRegistration):
    try:
        # Check if user exists
        response = supabase.table("registration_form").select("*").eq("phone_number", user_data.phone_number).execute()
        
        if len(response.data) > 0:
            # Update existing user
            update_data = {
                "name": user_data.name,
                "email": user_data.email,
                "location": user_data.location
            }
            update_response = supabase.table("registration_form").update(update_data).eq("phone_number", user_data.phone_number).execute()
            return {"success": True, "message": "User information updated", "data": update_response.data}
        else:
            # Create new user
            insert_response = supabase.table("registration_form").insert(user_data.dict()).execute()
            return {"success": True, "message": "User registered successfully", "data": insert_response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Serve the HTML page
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_registration_page(request: Request, phonenumber: str = None):
    return templates.TemplateResponse("index.html", {"request": request, "phonenumber": phonenumber})

# Create static directory if it doesn't exist
static_dir = pathlib.Path("static")
if not static_dir.exists():
    static_dir.mkdir(exist_ok=True)
    print(f"Created missing static directory: {static_dir.absolute()}")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
