import os
import json
import time
import asyncio
import base64
import logging
from dotenv import load_dotenv
import websockets
import google.generativeai as genai
from quart import Quart, websocket, Response, request

# Import custom modules
from realtime_tools import search_product_database
from tools import send_simple_whatsapp, generate_inquiry_invoice, send_templated_message
from google_calender import get_available_slots_handler, is_slot_available, book_slot_handler
from tools_two import upload_text_to_pdf_and_get_short_url
from db import does_number_exist, get_user_details, add_phone_with_role

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize environment variables
PORT = int(os.getenv('PORT', 5000))
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GENAI_API_KEY = os.getenv("GOOGLE_API_KEY")

# Verify required environment variables
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

# Configure Gemini API
genai.configure(api_key=GENAI_API_KEY)

# Define system prompts
SYSTEM_MESSAGE = """
You are a helpful assistant for Tec Nvirons who can handle three types of requests:
1. General chat - respond conversationally to general inquiries.
2. Product database queries - search the product database when users ask about specific products.
3. Appointment booking - help users schedule appointments using the calendar functions.
When users want to book an appointment, either directly verify if their requested time is available,
or check available slots if they haven't specified a time.
Book the appointment once a time is confirmed. Always be helpful, friendly, and conversational.
"""

NEW_USER_SYSTEM_MESSAGE = """
You are a helpful assistant for Tec Nvirons. I see you're a new caller.
Before we proceed, I need to know if you're a contractor or a customer.
Please let me know which one you are, and then I can assist you with
product information, appointment scheduling, or any other questions you have.
"""

# Initialize Quart app
app = Quart(__name__)

# Store call data separately for each call UUID
call_data = {}

@app.route("/webhook", methods=["GET", "POST"])
async def home():
    """Handle incoming calls and route to the WebSocket media stream"""
    try:
        # Get request values
        values = await request.values    
        caller_number = values.get('From', 'unknown')
        called_number = values.get('To', 'unknown')
        call_uuid = values.get('CallUUID', 'unknown')
            
        # Log the incoming call
        logger.info(f"Incoming call from {caller_number} to {called_number} (UUID: {call_uuid})")
        
        # Check if the caller's number exists in the database
        user_exists = does_number_exist(caller_number)
        user_details = None
        
        # Set appropriate greeting and system message based on user status
        if user_exists:
            # Fetch user details from the database
            user_details = get_user_details(caller_number)
            if user_details["status"] == "success":
                user_name = user_details["data"]["name"]
                greeting_message = f"Hey {user_name}! Welcome back to Technvi AI. How can I help you today?"
                logger.info(f"Existing user: {user_name} with email: {user_details['data'].get('email')}")
                system_message_to_use = SYSTEM_MESSAGE
            else:
                greeting_message = "Welcome to Technvi AI! How can I help you today?"
                system_message_to_use = SYSTEM_MESSAGE
        else:
            # For new users, prompt them to specify their role
            greeting_message = "Welcome to Technvi AI! I see you're a new caller. Are you a contractor or a customer?"
            system_message_to_use = NEW_USER_SYSTEM_MESSAGE
            logger.info(f"New user calling from: {caller_number}")
        
        # Initialize data structures for this call
        call_data[call_uuid] = {
            'caller_number': caller_number,
            'called_number': called_number,
            'timestamp': time.time(),
            'transcriptions': {},
            'function_calls': [],
            'assistant_responses': [],
            'appointments': [],
            'user_exists': user_exists,
            'user_details': user_details,
            'user_role_set': False,  # Flag to track if new user has set their role
            'system_message': system_message_to_use
        }
        
        # Generate Plivo XML response
        xml_data = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Speak voice="Polly.Amy">{greeting_message}</Speak>
            <Stream streamTimeout="86400" keepCallAlive="true" bidirectional="true" contentType="audio/x-mulaw;rate=8000" audioTrack="inbound" >
                ws://{request.host}/media-stream/{call_uuid}
            </Stream>
        </Response>
        '''
        return Response(xml_data, mimetype='application/xml')
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        # Return a simple response in case of error
        xml_data = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Speak>Sorry, there was a technical issue. Please try calling again later.</Speak>
            <Hangup/>
        </Response>
        '''
        return Response(xml_data, mimetype='application/xml')

@app.websocket('/media-stream/<call_uuid>')
async def handle_message(call_uuid):
    """Handle the WebSocket connection for streaming audio data"""
    logger.info(f'Client connected for call UUID: {call_uuid}')
    plivo_ws = websocket 
    
    # Ensure we have data for this call
    if call_uuid not in call_data:
        logger.warning(f"Warning: No call data found for UUID {call_uuid}, creating empty data")
        call_data[call_uuid] = {
            'caller_number': 'unknown',
            'called_number': 'unknown',
            'timestamp': time.time(),
            'transcriptions': {},
            'function_calls': [],
            'assistant_responses': [],
            'appointments': [],
            'user_exists': False,
            'user_details': None,
            'user_role_set': False,
            'system_message': NEW_USER_SYSTEM_MESSAGE
        }
    
    caller_number = call_data[call_uuid]['caller_number']
    logger.info(f"Processing call from: {caller_number} with UUID: {call_uuid}")
    
    # Pass call info to the WebSocket session
    plivo_ws.caller_number = caller_number
    plivo_ws.call_uuid = call_uuid

    # Connect to OpenAI Realtime API
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }

    try: 
        async with websockets.connect(url, extra_headers=headers) as openai_ws:
            logger.info(f'Connected to the OpenAI Realtime API for call {call_uuid}')

            # Send initial session configuration
            await send_session_update(openai_ws, call_uuid)
            
            # Create task for receiving from Plivo
            receive_task = asyncio.create_task(receive_from_plivo(plivo_ws, openai_ws, call_uuid))
            
            # Process messages from OpenAI
            async for message in openai_ws:
                await receive_from_openai(message, plivo_ws, openai_ws, call_uuid)
            
            # Wait for receive task to complete
            await receive_task
    
    except asyncio.CancelledError:
        logger.info(f'Client disconnected for call {call_uuid}')
        await after_call_hangup(call_uuid)
    except websockets.ConnectionClosed:
        logger.info(f"Connection closed by OpenAI server for call {call_uuid}")
        await after_call_hangup(call_uuid)
    except Exception as e:
        logger.error(f"Error during OpenAI's websocket communication for call {call_uuid}: {e}")
        await after_call_hangup(call_uuid)
        
async def receive_from_plivo(plivo_ws, openai_ws, call_uuid):
    """Receive audio data from Plivo and forward to OpenAI"""
    try:
        while True:
            message = await plivo_ws.receive()
            data = json.loads(message)
            
            if data['event'] == 'media' and openai_ws.open:
                # Forward audio data to OpenAI
                audio_append = {
                    "type": "input_audio_buffer.append",
                    "audio": data['media']['payload']
                }
                await openai_ws.send(json.dumps(audio_append))
                
            elif data['event'] == "start":
                logger.info(f'Plivo Audio stream has started for call {call_uuid}')
                plivo_ws.stream_id = data['start']['streamId']
                
            elif data['event'] == "hangup":
                logger.info(f'Call has ended for call {call_uuid}')
                await after_call_hangup(call_uuid)
                if openai_ws.open:
                    await openai_ws.close()
                break

    except websockets.ConnectionClosed:
        logger.info(f'Connection closed for the plivo audio streaming servers for call {call_uuid}')
        await after_call_hangup(call_uuid)
        if openai_ws.open:
            await openai_ws.close()
    except Exception as e:
        logger.error(f"Error during Plivo's websocket communication for call {call_uuid}: {e}")
        await after_call_hangup(call_uuid)

async def receive_from_openai(message, plivo_ws, openai_ws, call_uuid):
    """Process messages received from OpenAI"""
    try:
        response = json.loads(message)
        response_type = response.get("type", "unknown")
        
        if response_type == 'session.updated':
            logger.info(f'Session updated successfully for call {call_uuid}')
            
        elif response_type == 'error':
            logger.error(f'Error from OpenAI for call {call_uuid}: {response}')
            
        elif response_type == 'response.text.delta':
            # Store assistant text responses
            if call_uuid in call_data:
                text_delta = response.get('delta', '')
                item_id = response.get('item_id', 'unknown')
                
                # Create or update the response entry
                if item_id not in [r.get('item_id') for r in call_data[call_uuid]['assistant_responses']]:
                    call_data[call_uuid]['assistant_responses'].append({
                        'item_id': item_id,
                        'text': text_delta,
                        'timestamp': time.time()
                    })
                else:
                    # Find and update existing response
                    for r in call_data[call_uuid]['assistant_responses']:
                        if r.get('item_id') == item_id:
                            r['text'] += text_delta
                            break
                            
        elif response_type == 'response.audio.delta':
            # Forward audio response to Plivo
            audio_delta = {
                "event": "playAudio",
                "media": {
                    "contentType": 'audio/x-mulaw',
                    "sampleRate": 8000,
                    "payload": base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                }
            }
            await plivo_ws.send(json.dumps(audio_delta))
            
        elif response_type == 'response.function_call_arguments.done':
            # Process function call from OpenAI
            function_name = response.get('name', '')
            args = json.loads(response['arguments'])
            item_id = response.get('item_id', '')
            call_id = response.get('call_id', '')
            
            logger.info(f'Function call: {function_name} for call {call_uuid}')
            
            # Handle different function calls
            result = None
            instructions = ''
            
            if function_name == 'search_product_database':
                # Call the RAG function with the query
                query = args['query']
                result = await search_product_database(query)
                instructions = 'Share the product information from the database search with the user in a helpful way.'
                
            elif function_name == 'get_available_slots':
                # This function is kept but will rarely be used
                result = get_available_slots_handler()
                instructions = 'Share the available appointment slots with the user. Format the times in a clear, easy-to-understand way.'
                
            elif function_name == 'check_slot_availability':
                # Check if a specific slot is available
                proposed_time = args['proposed_time']
                availability = is_slot_available(proposed_time)
                
                # Record the function call
                if call_uuid in call_data:
                    call_data[call_uuid]['function_calls'].append({
                        'type': 'check_availability',
                        'timestamp': time.time(),
                        'args': args,
                        'result': {"is_available": availability, "proposed_time": proposed_time},
                        'item_id': item_id
                    })
                
                # If slot is available, automatically book it
                if availability:
                    email = 'customer@example.com'
                    
                    # Use email from database if available
                    if call_uuid in call_data and call_data[call_uuid]['user_exists'] and call_data[call_uuid]['user_details']:
                        if call_data[call_uuid]['user_details']['status'] == 'success' and call_data[call_uuid]['user_details']['data'].get('email'):
                            email = call_data[call_uuid]['user_details']['data']['email']
                    
                    # Book the appointment
                    booking_result = book_slot_handler(proposed_time, email)
                    
                    # Record the appointment booking
                    if call_uuid in call_data:
                        call_data[call_uuid]['appointments'].append({
                            'timestamp': time.time(),
                            'proposed_time': proposed_time,
                            'email': email,
                            'result': booking_result,
                            'item_id': item_id
                        })
                    
                    # Prepare result and instructions
                    result = {
                        "is_available": True,
                        "proposed_time": proposed_time,
                        "booking_result": booking_result
                    }
                    
                    if 'error' in booking_result:
                        instructions = f"Tell the user that the time ({proposed_time}) is available, but there was an error booking: {booking_result.get('error')}. Suggest trying again or choosing another time."
                    else:
                        instructions = f"Tell the user that the time ({proposed_time}) was available and has been successfully booked. Confirm the appointment details."
                else:
                    # Slot is not available
                    result = {"is_available": False, "proposed_time": proposed_time}
                    instructions = f"Inform the user that the requested time ({proposed_time}) is not available. Suggest they ask for another time."
                
            elif function_name == 'book_appointment':
                # This function is kept for compatibility, but will be rarely called directly now
                proposed_time = args['proposed_time']
                email = args.get('email', 'customer@example.com')
                
                # Use email from database if available
                if call_uuid in call_data and call_data[call_uuid]['user_exists'] and call_data[call_uuid]['user_details']:
                    if call_data[call_uuid]['user_details']['status'] == 'success' and call_data[call_uuid]['user_details']['data'].get('email'):
                        email = call_data[call_uuid]['user_details']['data']['email']
                
                result = book_slot_handler(proposed_time, email)
                instructions = f"Inform the user about the appointment booking result for {proposed_time}."
                if 'error' in result:
                    instructions += " Apologize and suggest trying another time slot."
                else:
                    instructions += " Confirm the appointment was successfully booked."
                
                # Record the appointment booking
                if call_uuid in call_data:
                    call_data[call_uuid]['appointments'].append({
                        'timestamp': time.time(),
                        'proposed_time': proposed_time,
                        'email': email,
                        'result': result,
                        'item_id': item_id
                    })
            
            # Send the function output back to OpenAI
            if result:
                output = function_call_output(result, item_id, call_id)
                await openai_ws.send(json.dumps(output))
                
                # Generate a response using the function result
                generate_response = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text", "audio"],
                        "temperature": 0.8,
                        "instructions": instructions
                    }
                }
                await openai_ws.send(json.dumps(generate_response))
                
        elif response_type == 'conversation.item.input_audio_transcription.delta':
            item_id = response.get('item_id')
            delta = response.get('delta', '')
            
            if call_uuid in call_data:
                if item_id not in call_data[call_uuid]['transcriptions']:
                    call_data[call_uuid]['transcriptions'][item_id] = {'text': delta, 'complete': False}
                else:
                    call_data[call_uuid]['transcriptions'][item_id]['text'] += delta
            
        elif response_type == 'conversation.item.input_audio_transcription.completed':
            item_id = response.get('item_id')
            full_transcript = response.get('transcript', '')
            
            if call_uuid in call_data:
                call_data[call_uuid]['transcriptions'][item_id] = {'text': full_transcript, 'complete': True}
                
                # For new users, check if they've specified their role
                if not call_data[call_uuid]['user_exists'] and not call_data[call_uuid]['user_role_set']:
                    lower_transcript = full_transcript.lower()
                    
                    # Check for role specification in the transcript
                    if 'contractor' in lower_transcript or 'customer' in lower_transcript:
                        role = 'contractor' if 'contractor' in lower_transcript else 'customer'
                        caller_number = call_data[call_uuid]['caller_number']
                        
                        # Add phone number with role to the database
                        result = add_phone_with_role(caller_number, role)
                        
                        if result['status'] == 'created' or result['status'] == 'exists':
                            call_data[call_uuid]['user_role_set'] = True
                            call_data[call_uuid]['system_message'] = SYSTEM_MESSAGE
                            
                            # Update session with new system message
                            update_message = {
                                "type": "session.update",
                                "session": {
                                    "instructions": SYSTEM_MESSAGE
                                }
                            }
                            await openai_ws.send(json.dumps(update_message))
                            
                            logger.info(f"Added new user with role: {role}, phone: {caller_number}")
                            
                            # Generate a response confirming role registration
                            generate_response = {
                                "type": "response.create",
                                "response": {
                                    "modalities": ["text", "audio"],
                                    "temperature": 0.8,
                                    "instructions": f"Thank the user for specifying they are a {role}. Now continue with normal conversation, offering to help with product information or appointment scheduling."
                                }
                            }
                            await openai_ws.send(generate_response)
                
        elif response_type == 'input_audio_buffer.speech_started':
            # Clear audio when user starts speaking
            clear_audio_data = {
                "event": "clearAudio",
                "stream_id": plivo_ws.stream_id
            }
            await plivo_ws.send(json.dumps(clear_audio_data))
            
            # Cancel any in-progress response
            cancel_response = {
                "type": "response.cancel"
            }
            await openai_ws.send(cancel_response)
            
    except Exception as e:
        logger.error(f"Error processing OpenAI message for call {call_uuid}: {str(e)}")
    
async def send_session_update(openai_ws, call_uuid):
    """Send initial session configuration to OpenAI"""
    # Get the current system message for this call
    current_system_message = SYSTEM_MESSAGE
    if call_uuid in call_data:
        current_system_message = call_data[call_uuid]['system_message']
    
    # Update system message to clarify the simplified appointment booking process
    current_system_message += """
    When a user wants to book an appointment, ask them directly for their preferred date and time. 
    Check if that specific time is available. If available, book it immediately.
    If not available, inform them and ask for a different time.
    """
    
    # Create session update with tools definitions
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "tools": [
                {
                    "type": "function",
                    "name": "search_product_database",
                    "description": "Search for product information in the database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": { 
                                "type": "string", 
                                "description": "The search query about a product or part"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "type": "function",
                    "name": "check_slot_availability",
                    "description": "Check if a specific time slot is available for booking and book it if available",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "proposed_time": {
                                "type": "string",
                                "description": "The proposed appointment time in ISO format (e.g., '2024-05-15T14:30:00')"
                            }
                        },
                        "required": ["proposed_time"]
                    }
                },
                # Keep these functions for backward compatibility
                {
                    "type": "function",
                    "name": "get_available_slots",
                    "description": "Get available appointment slots from the calendar (only use if the user specifically asks for available time slots)",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                },
                {
                    "type": "function",
                    "name": "book_appointment",
                    "description": "Book an appointment at the specified time (only use if check_slot_availability has already confirmed availability)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "proposed_time": {
                                "type": "string",
                                "description": "The appointment time in ISO format (e.g., '2024-05-15T14:30:00')"
                            },
                            "email": {
                                "type": "string",
                                "description": "Email address for the appointment (optional)"
                            }
                        },
                        "required": ["proposed_time"]
                    }
                }
            ],
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": "alloy",
            "instructions": current_system_message,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
            "input_audio_transcription": {
                "model": "gpt-4o-transcribe",
                "language": "en"
            },
            "include": ["item.input_audio_transcription.logprobs"]
        }
    }
    await openai_ws.send(json.dumps(session_update))

def function_call_output(result, item_id, call_id):
    """Format function output for OpenAI"""
    conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "id": item_id,
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps({"result": result})
        }
    }
    return conversation_item

async def after_call_hangup(call_uuid):
    """Process transcriptions, generate invoice, and send via WhatsApp for a specific call"""
    # Check if we have data for this call
    if call_uuid not in call_data:
        logger.warning(f"No call data found for UUID {call_uuid}")
        return
        
    logger.info(f"Processing after-call actions for {call_uuid}")
    call_info = call_data[call_uuid]
    
    try:
        transcriptions = call_info['transcriptions']
        function_calls = call_info['function_calls']
        assistant_responses = call_info.get('assistant_responses', [])
        appointments = call_info.get('appointments', [])
        
        if not transcriptions and not function_calls and not assistant_responses:
            logger.warning(f"No conversation data recorded for call {call_uuid}")
            if call_uuid in call_data:
                del call_data[call_uuid]
            return
            
        # Prepare complete conversation events with timestamps
        conversation_events = []
        
        # Add user transcriptions
        for item_id, data in transcriptions.items():
            conversation_events.append({
                'type': 'user_message',
                'timestamp': time.time(),  # We don't have actual timestamp in transcriptions
                'item_id': item_id,
                'text': data['text']
            })
        
        # Add assistant responses
        for response in assistant_responses:
            conversation_events.append({
                'type': 'assistant_message',
                'timestamp': response.get('timestamp', time.time()),
                'item_id': response.get('item_id', 'unknown'),
                'text': response.get('text', '')
            })
        
        # Add function calls with their actual timestamps
        for call in function_calls:
            conversation_events.append({
                'type': 'function_call',
                'timestamp': call.get('timestamp', time.time()),
                'item_id': call.get('item_id', 'unknown'),
                'call_type': call.get('type', 'unknown'),
                'data': call
            })
        
        # Add appointments
        for appt in appointments:
            conversation_events.append({
                'type': 'appointment',
                'timestamp': appt.get('timestamp', time.time()),
                'item_id': appt.get('item_id', 'unknown'),
                'proposed_time': appt.get('proposed_time', ''),
                'result': appt.get('result', {})
            })
        
        # Sort all events by timestamp
        conversation_events.sort(key=lambda x: x['timestamp'])
        
        # Format transcript data as string
        transcript_text = "CALL TRANSCRIPT & CONVERSATION\n"
        transcript_text += "============================\n\n"
        
        # Track if any appointments were booked
        booked_appointments = []
        
        # Display and format the conversation
        for event in conversation_events:
            if event['type'] == 'user_message':
                transcript_text += f"User: {event['text']}\n\n"
            elif event['type'] == 'assistant_message':
                transcript_text += f"Assistant: {event['text']}\n\n"
            elif event['type'] == 'function_call':
                if event['call_type'] == 'search_product_database':
                    transcript_text += f"\nDATABASE QUERY: {event['data'].get('args', {}).get('query', '')}\n"
                    transcript_text += f"RESULT: {event['data'].get('result', '')}\n\n"
                elif event['call_type'] in ['get_available_slots', 'check_slot_availability']:
                    transcript_text += f"\nCALENDAR QUERY: {event['call_type']}\n"
                    if event['call_type'] == 'check_slot_availability':
                        transcript_text += f"PROPOSED TIME: {event['data'].get('args', {}).get('proposed_time', '')}\n"
                        transcript_text += f"AVAILABLE: {event['data'].get('result', {}).get('is_available', False)}\n\n"
            elif event['type'] == 'appointment':
                transcript_text += f"\n===== APPOINTMENT BOOKING =====\n"
                transcript_text += f"Time: {event['proposed_time']}\n"
                
                if isinstance(event['result'], dict) and 'error' in event['result']:
                    transcript_text += f"Status: Failed - {event['result'].get('error', '')}\n\n"
                else:
                    transcript_text += f"Status: Successfully booked\n"
                    transcript_text += f"Calendar Link: {event['result'].get('htmlLink', '')}\n\n"
                    # Track successful bookings
                    booked_appointments.append({
                        'time': event['proposed_time'],
                        'link': event['result'].get('htmlLink', '')
                    })
        
        # Add a special summary section for appointments at the end
        if booked_appointments:
            transcript_text += "\n===== APPOINTMENT SUMMARY =====\n"
            for idx, appt in enumerate(booked_appointments, 1):
                transcript_text += f"Appointment #{idx}: {appt['time']}\n"
                transcript_text += f"Link: {appt.get('link', '')}\n"
            transcript_text += "==============================\n\n"
        
        # Get the caller number from call data
        caller_number = call_info.get('caller_number', 'unknown')
        logger.info(f"Sending summary to caller number: {caller_number}")
        
        # Generate invoice from transcript data
        invoice = generate_inquiry_invoice(transcript_text)
        
        # Send WhatsApp message with the invoice as PDF
        if caller_number and caller_number != 'unknown':
            try:
                # Create and upload PDF, get shortened URL
                short_url = upload_text_to_pdf_and_get_short_url(invoice)
                if short_url:
                    # Send WhatsApp message with PDF link
                    send_templated_message(caller_number, short_url, caller_number)
                    logger.info(f"WhatsApp Template invoice sent successfully to {caller_number} for call {call_uuid}")
                else:
                    # Fallback to plain text if PDF creation fails
                    send_simple_whatsapp(caller_number, invoice)
                    logger.warning(f"Sent plain text invoice to {caller_number} (PDF creation failed)")
            except Exception as e:
                logger.error(f"Failed to send WhatsApp message for call {call_uuid}: {e}")
        else:
            logger.warning(f"No valid caller number to send WhatsApp message for call {call_uuid}")
    
    except Exception as e:
        logger.error(f"Error in after-call processing for call {call_uuid}: {str(e)}")
    finally:
        # Clean up call data
        if call_uuid in call_data:
            logger.info(f"Cleaning up data for call {call_uuid}")
            del call_data[call_uuid]


if __name__ == "__main__":
    logger.info('Starting Technvi VoiceBot server')
    app.run(host='0.0.0.0', port=PORT)
