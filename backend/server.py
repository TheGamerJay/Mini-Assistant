from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import json
import asyncio
from ollama import Client
from faster_whisper import WhisperModel
from gtts import gTTS
from duckduckgo_search import DDGS
import tempfile
import subprocess

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Initialize Ollama client (will connect to localhost:11434)
try:
    ollama_client = Client(host='http://localhost:11434')
except:
    ollama_client = None

# Initialize Whisper model for STT (lazy loading)
whisper_model = None

# Models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "llama3.2"
    stream: bool = False

class ChatResponse(BaseModel):
    response: str
    model: str

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5

class WebSearchResult(BaseModel):
    title: str
    url: str
    body: str

class FileListRequest(BaseModel):
    path: str = "/app"

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class CommandRequest(BaseModel):
    command: str
    allowlist: List[str] = ["ls", "pwd", "cat", "echo", "grep", "find", "wc", "head", "tail"]

class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    path: str
    description: Optional[str] = None
    commands: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProjectProfileCreate(BaseModel):
    name: str
    path: str
    description: Optional[str] = None
    commands: List[str] = []

class STTRequest(BaseModel):
    audio_data: str

class TTSRequest(BaseModel):
    text: str
    lang: str = "en"

class ImageGenRequest(BaseModel):
    prompt: str
    model: str = "stable-diffusion"

class FixLoopRequest(BaseModel):
    command: str
    error_output: str

class CodeSearchRequest(BaseModel):
    query: str
    path: str = "/app"
    max_results: int = 5

# Chat endpoint
@api_router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available. Please ensure Ollama is running on localhost:11434")
    
    try:
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        if request.stream:
            # For streaming, we'll aggregate chunks for simplicity
            response_text = ""
            stream = ollama_client.chat(model=request.model, messages=messages, stream=True)
            for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    response_text += chunk['message']['content']
        else:
            response = ollama_client.chat(model=request.model, messages=messages)
            response_text = response['message']['content']
        
        return ChatResponse(response=response_text, model=request.model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

# Voice endpoints
@api_router.post("/voice/stt")
async def speech_to_text(file: UploadFile = File(...)):
    global whisper_model
    try:
        if whisper_model is None:
            whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        segments, info = whisper_model.transcribe(tmp_path, language="en")
        transcription = " ".join([segment.text for segment in segments])
        
        os.unlink(tmp_path)
        return {"transcription": transcription, "language": info.language}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {str(e)}")

@api_router.post("/voice/tts")
async def text_to_speech(request: TTSRequest):
    try:
        tts = gTTS(text=request.text, lang=request.lang, slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tts.save(tmp.name)
            tmp_path = tmp.name
        
        def iter_file():
            with open(tmp_path, "rb") as f:
                yield from f
            os.unlink(tmp_path)
        
        return StreamingResponse(iter_file(), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")

# Web search endpoint
@api_router.post("/search/web", response_model=List[WebSearchResult])
async def web_search(request: WebSearchRequest):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(request.query, max_results=request.max_results))
        
        return [WebSearchResult(
            title=r.get('title', ''),
            url=r.get('href', ''),
            body=r.get('body', '')
        ) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

# File operations
@api_router.post("/files/list")
async def list_files(request: FileListRequest):
    try:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        
        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0
            })
        
        return {"items": sorted(items, key=lambda x: (not x['is_dir'], x['name']))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List error: {str(e)}")

@api_router.post("/files/read")
async def read_file(request: FileReadRequest):
    try:
        path = Path(request.path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        content = path.read_text()
        return {"content": content, "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read error: {str(e)}")

@api_router.post("/files/write")
async def write_file(request: FileWriteRequest):
    try:
        path = Path(request.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.content)
        return {"success": True, "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write error: {str(e)}")

# Command execution
@api_router.post("/commands/execute")
async def execute_command(request: CommandRequest):
    cmd_parts = request.command.strip().split()
    if not cmd_parts:
        raise HTTPException(status_code=400, detail="Empty command")
    
    base_cmd = cmd_parts[0]
    if base_cmd not in request.allowlist:
        raise HTTPException(status_code=403, detail=f"Command '{base_cmd}' not in allowlist")
    
    try:
        result = subprocess.run(
            request.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/app"
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Command timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

# Project Profiles
@api_router.get("/profiles", response_model=List[ProjectProfile])
async def get_profiles():
    profiles = await db.profiles.find({}, {"_id": 0}).to_list(1000)
    for profile in profiles:
        if isinstance(profile.get('created_at'), str):
            profile['created_at'] = datetime.fromisoformat(profile['created_at'])
    return profiles

@api_router.post("/profiles", response_model=ProjectProfile)
async def create_profile(input: ProjectProfileCreate):
    profile_dict = input.model_dump()
    profile_obj = ProjectProfile(**profile_dict)
    
    doc = profile_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.profiles.insert_one(doc)
    return profile_obj

@api_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    result = await db.profiles.delete_one({"id": profile_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True}

# Image generation placeholder
@api_router.post("/images/generate")
async def generate_image(request: ImageGenRequest):
    return {
        "success": False,
        "message": "Image generation requires local Stable Diffusion setup. Please install and configure ComfyUI or Automatic1111.",
        "prompt": request.prompt
    }

# FixLoop - Error analysis
@api_router.post("/fixloop/analyze")
async def analyze_error(request: FixLoopRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        prompt = f"""Analyze this command error and suggest a fix:

Command: {request.command}
Error Output: {request.error_output}

Provide:
1. Root cause analysis
2. Suggested fix (exact command or code change)
3. Explanation"""
        
        response = ollama_client.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )
        
        return {
            "analysis": response['message']['content'],
            "command": request.command
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

# App Builder
class AppBuilderRequest(BaseModel):
    description: str
    framework: str = "react"

@api_router.post("/app-builder/generate")
async def generate_app(request: AppBuilderRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        prompt = f"""Generate a complete {request.framework} application based on this description:

{request.description}

Provide:
1. Project structure (folders and files)
2. Complete code for each file
3. Installation instructions
4. Key features implemented

Format the response as JSON with this structure:
{{
  "name": "app-name",
  "description": "...",
  "files": [
    {{"path": "...", "content": "..."}},
    ...
  ],
  "install_commands": ["..."],
  "features": ["..."]
}}"""
        
        response = ollama_client.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Try to parse JSON from response
        content = response['message']['content']
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            
            app_data = json.loads(content)
        except:
            # If JSON parsing fails, return raw content
            app_data = {
                "name": "generated-app",
                "description": request.description,
                "raw_output": content,
                "files": []
            }
        
        return app_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")

# Code Review
class CodeReviewRequest(BaseModel):
    code: str
    language: str = "javascript"

@api_router.post("/code-review/analyze")
async def review_code(request: CodeReviewRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        prompt = f"""Review this {request.language} code and provide:

1. Issues found (errors, warnings, best practices)
2. Security vulnerabilities
3. Performance improvements
4. Fixed/improved version of the code

Code:
```{request.language}
{request.code}
```

Format response as JSON:
{{
  "issues": [
    {{"severity": "error|warning|info", "title": "...", "description": "...", "line": 0, "suggestion": "..."}},
    ...
  ],
  "summary": "Overall assessment...",
  "fixed_code": "Fixed version of the code..."
}}"""
        
        response = ollama_client.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response['message']['content']
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            
            analysis = json.loads(content)
        except:
            # If JSON parsing fails, create structured response from text
            analysis = {
                "issues": [{
                    "severity": "info",
                    "title": "Analysis Complete",
                    "description": content[:500],
                    "suggestion": "Review the full analysis"
                }],
                "summary": content,
                "fixed_code": ""
            }
        
        return {"analysis": analysis, "fixed_code": analysis.get("fixed_code", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review error: {str(e)}")

# Codebase search
@api_router.post("/search/codebase")
async def search_codebase(request: CodeSearchRequest):
    try:
        result = subprocess.run(
            f"grep -r -n '{request.query}' {request.path} --include='*.py' --include='*.js' --include='*.jsx' --include='*.ts' --include='*.tsx' | head -n {request.max_results}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        results = []
        for line in result.stdout.split('\n'):
            if line.strip():
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    results.append({
                        "file": parts[0],
                        "line": parts[1],
                        "content": parts[2]
                    })
        
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

# Health check
@api_router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_client else "disconnected",
        "whisper": "loaded" if whisper_model else "not_loaded"
    }

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()