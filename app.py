import os
import uuid
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

import config
import auth
import database
import functions.run_python_file
import functions.write_files

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Session storage for conversation history
sessions: dict[str, list] = {}

# API request counter for monitoring
api_request_counter = 0

# Function mappings
functions_map = {
    "run_python_file": functions.run_python_file.run_python_file,
    "write_files": functions.write_files.write_files
}

available_functions = types.Tool(
    function_declarations=[
        functions.run_python_file.schema_run_python_file,
        functions.write_files.schema_write_files
    ]
)


def call_function(function_call_part):
    """Execute a function call and return the result as Content."""
    working_dir = os.path.abspath("./sandbox")
    
    if function_call_part.name in functions_map:
        try:
            result = functions_map[function_call_part.name](
                working_dir=working_dir,
                **function_call_part.args
            )
            
            # Clear sandbox.py after running it
            if function_call_part.name == "run_python_file":
                sandbox_path = os.path.join(working_dir, "sandbox.py")
                if os.path.exists(sandbox_path):
                    with open(sandbox_path, "w") as f:
                        f.write("")  # Clear the file
                        
        except Exception as e:
            return types.Content(
                role="tool",
                parts=[
                    types.Part.from_function_response(
                        name=function_call_part.name,
                        response={"error": str(e)},
                    )
                ]
            ), {"name": function_call_part.name, "args": dict(function_call_part.args), "error": str(e)}
        
        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_call_part.name,
                    response={"result": result},
                )
            ],
        ), {"name": function_call_part.name, "args": dict(function_call_part.args), "success": True}
    else:
        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_call_part.name,
                    response={"error": f"Unknown function: {function_call_part.name}"},
                )
            ]
        ), {"name": function_call_part.name, "error": "Unknown function"}


def process_chat(message: str, session_id: str) -> tuple[str, list[dict]]:
    """Process a chat message and return the response with function calls info."""
    
    # Initialize session if new
    if session_id not in sessions:
        sessions[session_id] = []
    
    messages = sessions[session_id].copy()
    messages.append(
        types.Content(
            role="user",
            parts=[types.Part(text=message)]
        )
    )
    
    function_calls_made = []
    count = 1
    
    while count <= 15:
        global api_request_counter
        api_request_counter += 1
        
        # Get current model based on daily limits
        current_model, model_display = database.get_current_model()
        print(f"[API Request #{api_request_counter}] Using model: {model_display} (loop iteration {count})")
        
        # Increment the request count for this model
        database.increment_request_count(current_model)
        
        try:
            response = client.models.generate_content(
                model=current_model,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=config.system_prompt,
                    tools=[available_functions]
                )
            )
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            return f"Error: {str(e)}", function_calls_made
        
        has_function_calls = response.function_calls is not None and len(response.function_calls) > 0
        has_text_response = response.text is not None and response.text.strip()
        
        if not has_function_calls and has_text_response:
            # Store in session - user message and assistant response
            sessions[session_id].append(
                types.Content(role="user", parts=[types.Part(text=message)])
            )
            sessions[session_id].append(
                types.Content(role="model", parts=[types.Part(text=response.text)])
            )
            return response.text, function_calls_made
        
        # If there are function calls, we need to process them
        if has_function_calls:
            # Append the model's response (which contains the function calls)
            messages.append(response.candidates[0].content)
            
            function_responses = []
            for each in response.function_calls:
                try:
                    result, call_info = call_function(each)
                    function_calls_made.append(call_info)
                except Exception as e:
                    print(f"Error executing function {each.name}: {e}")
                    continue
                
                if not result.parts or not result.parts[0].function_response:
                    continue
                
                function_responses.append(result.parts[0])
            
            if function_responses:
                messages.append(
                    types.Content(role="user", parts=function_responses)
                )
        
        count += 1
    
    return "I apologize, but I wasn't able to complete the request.", function_calls_made


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    function_calls: list[dict]
    session_id: str
    conversation_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield

app = FastAPI(title="Singularity AI Chat", lifespan=lifespan)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/api/chat")
async def chat_options():
    """Handle CORS preflight requests."""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: Optional[str] = Header(None)):
    """Handle chat messages and return AI response."""
    # Get user from token
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user_id = auth.validate_token(token)
    
    # Check rate limit
    is_allowed, wait_seconds = database.check_user_rate_limit(user_id)
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. Please wait {wait_seconds} seconds."
        )
    
    # Record this request for rate limiting
    database.record_user_request(user_id)
    
    session_id = request.session_id or str(uuid.uuid4())
    conversation_id = request.conversation_id
    
    # Create new conversation if needed
    if user_id and not conversation_id:
        # Create a new conversation with first message as title
        title = request.message[:50] + "..." if len(request.message) > 50 else request.message
        conversation = auth.create_conversation(user_id, title)
        conversation_id = conversation.id
    
    response_text, function_calls = process_chat(request.message, session_id)
    
    # Save messages to conversation file
    if user_id and conversation_id:
        from datetime import datetime
        conversation = auth.load_conversation(user_id, conversation_id)
        if conversation:
            conversation.messages.append({
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat()
            })
            conversation.messages.append({
                "role": "assistant", 
                "content": response_text,
                "function_calls": function_calls,
                "timestamp": datetime.now().isoformat()
            })
            conversation.updated_at = datetime.now().isoformat()
            auth.save_conversation(conversation)
    
    return ChatResponse(
        response=response_text,
        function_calls=function_calls,
        session_id=session_id,
        conversation_id=conversation_id or ""
    )


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/model-status")
async def model_status():
    """Get current model status (lite/main) and usage counts."""
    return database.get_model_status()


# ==================== Auth Request/Response Models ====================

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    error: Optional[str] = None


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


# ==================== Auth Endpoints ====================

@app.options("/api/register")
@app.options("/api/login")
@app.options("/api/logout")
@app.options("/api/conversations")
@app.options("/api/conversations/{conversation_id}")
async def auth_options():
    """Handle CORS preflight for auth endpoints."""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.post("/api/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user."""
    if len(request.username) < 3:
        return AuthResponse(success=False, error="Username must be at least 3 characters")
    if len(request.password) < 6:
        return AuthResponse(success=False, error="Password must be at least 6 characters")
    
    user, error = auth.create_user(request.username, request.password)
    if error:
        return AuthResponse(success=False, error=error)
    
    token = auth.create_auth_token(user.id)
    return AuthResponse(
        success=True,
        token=token.token,
        user_id=user.id,
        username=user.username
    )


@app.post("/api/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login and get auth token."""
    user, error = auth.authenticate_user(request.username, request.password)
    if error:
        return AuthResponse(success=False, error=error)
    
    token = auth.create_auth_token(user.id)
    return AuthResponse(
        success=True,
        token=token.token,
        user_id=user.id,
        username=user.username
    )


@app.post("/api/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout and invalidate token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        auth.invalidate_token(token)
    return {"success": True}


@app.get("/api/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user info from token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization[7:]
    user_id = auth.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user = auth.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {"user_id": user.id, "username": user.username}


# ==================== Conversation Endpoints ====================

@app.get("/api/conversations")
async def list_conversations(authorization: Optional[str] = Header(None)):
    """List all conversations for the current user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization[7:]
    user_id = auth.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    conversations = auth.list_user_conversations(user_id)
    return {"conversations": conversations}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, authorization: Optional[str] = Header(None)):
    """Get a specific conversation."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization[7:]
    user_id = auth.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    conversation = auth.load_conversation(user_id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversation.model_dump()


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, authorization: Optional[str] = Header(None)):
    """Delete a conversation."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization[7:]
    user_id = auth.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    success = auth.delete_conversation(user_id, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"success": True}


@app.post("/api/conversations")
async def create_new_conversation(authorization: Optional[str] = Header(None)):
    """Create a new conversation."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization[7:]
    user_id = auth.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    conversation = auth.create_conversation(user_id)
    return conversation.model_dump()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

