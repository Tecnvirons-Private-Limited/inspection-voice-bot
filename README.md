# Technvi AI Voice Bot

An advanced voice assistant system that handles customer inquiries, product searches, and appointment scheduling through natural language conversations.

## Overview

The Technvi AI Voice Bot is an intelligent telephony solution that uses state-of-the-art AI technologies to provide a seamless voice interface for customers and contractors interacting with Tec Nvirons. The system handles incoming calls, processes natural language, searches product databases, manages appointments, and delivers conversation summaries via WhatsApp.

## Features

- **Natural Voice Conversations**: Leverages OpenAI's realtime API for fluid, natural conversations
- **User Recognition**: Identifies new and returning users
- **Role-Based Interactions**: Customizes responses based on user role (contractor or customer)
- **Product Database Search**: Real-time vector search for product information
- **Appointment Scheduling**: Automated calendar management with Google Calendar
- **WhatsApp Integration**: Sends conversation summaries as PDF attachments via WhatsApp
- **PDF Report Generation**: Creates formatted invoices and inquiry summaries
- **Cloud Storage**: Stores generated documents in Supabase storage

## System Architecture

The system comprises several integrated components:

1. **Voice Call Handling**: Using Plivo for telephony integration
2. **Conversational AI**: OpenAI's GPT-4o for real-time voice conversations
3. **Vector Database**: Pinecone for product information retrieval
4. **Text Generation**: Google's Gemini AI for generating formatted summaries
5. **Database**: Supabase for user management and data storage
6. **Messaging**: WhatsApp Business API through Plivo for communication
7. **Calendar Integration**: Google Calendar API for appointment scheduling

## Prerequisites

- Python 3.8+
- Plivo account
- OpenAI API access with GPT-4o realtime
- Google Generative AI API key
- Supabase account and project
- Pinecone account and index
- Google Cloud project with Calendar API enabled

## Environment Variables

The system requires the following environment variables:

```
# API Keys
OPENAI_API_KEY=your-openai-api-key
GOOGLE_API_KEY=your-google-api-key
PINECONE_API_KEY=your-pinecone-api-key

# Supabase Configuration
SUPABASE_URLL=your-supabase-url
SUPABASE_KEYY=your-supabase-key
SUPABASE_SERVICE_ROLE_KEYY=your-supabase-service-role-key

# Plivo Configuration
PLIVO_AUTH_ID=your-plivo-auth-id
PLIVO_AUTH_TOKEN=your-plivo-auth-token

# Pinecone Configuration
PINECONE_INDEX_NAME=your-pinecone-index-name
DEFAULT_NAMESPACE=your-default-namespace

# Google Calendar Configuration
GOOGLE_CREDENTIALS_JSON={"web":{"client_id":"...","project_id":"...","auth_uri":"...","token_uri":"...","auth_provider_x509_cert_url":"...","client_secret":"..."}}
GOOGLE_TOKEN_JSON={"token":"...","refresh_token":"...","token_uri":"...","client_id":"...","client_secret":"...","scopes":["..."]}

# Server Configuration
PORT=5000
```

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/technvi-ai/inspection-voice-bot.git
   cd inspection-voice-bot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. Run the application:
   ```
   python mainn.py
   ```

## Usage

### Call Flow

1. The system answers incoming calls to the configured Plivo number
2. For new users, the system asks if they are a contractor or customer
3. Users can ask about products, request information, or schedule appointments
4. The system searches the product database or checks calendar availability as needed
5. After the call ends, a summary is generated and sent to the user via WhatsApp

### API Endpoints

- **GET/POST /webhook**: Handles incoming calls and initiates the voice assistant
- **WebSocket /media-stream/<call_uuid>**: Manages bi-directional audio streaming

## Core Components

### Main Application (mainn.py)

The central component handling:
- Call webhook processing
- WebSocket connections for audio streaming
- Integration with OpenAI's real-time API
- Conversation flow management
- Function calling for database queries and appointments
- Post-call processing and summary generation

### Tools Modules

- **tools.py**: WhatsApp messaging and invoice generation
- **tools_two.py**: PDF creation and Supabase storage
- **realtime_tools.py**: Vector search for product database
- **google_calender.py**: Calendar integration for scheduling
- **db.py**: Database operations for user management
- **number.py**: Phone number validation and WhatsApp verification

## File Structure

```
inspection-voice-bot/
├── mainn.py             # Main application with call handling logic
├── tools.py             # WhatsApp messaging and invoice generation
├── tools_two.py         # PDF creation and storage functions
├── db.py                # Database operations
├── google_calender.py   # Calendar integration for appointments
├── realtime_tools.py    # Vector search functionality
├── number.py            # Phone number utilities
└── README.md            # This file
```

## Deployment

The system is designed to be deployed as a web service that can receive webhook calls from Plivo. It can be hosted on platforms like:

- Railway
- AWS
- Google Cloud
- Heroku
- Digital Ocean

## Contributing

For internal contributions, please follow the company's development guidelines and code review process.

## License and Copyright

© 2024 Technvi AI / Tec Nvirons. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, transfer, or reproduction of the contents of this software, via any medium, is strictly prohibited.

---

Developed by Technvi AI