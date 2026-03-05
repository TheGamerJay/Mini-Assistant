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

class GitRemoteRequest(BaseModel):
    name: str
    url: str

class GitCommitRequest(BaseModel):
    message: str

class GitPushRequest(BaseModel):
    remote: str = "origin"
    branch: str = "main"

class GitPullRequest(BaseModel):
    remote: str = "origin"
    branch: str = "main"

class GitBranchRequest(BaseModel):
    name: str

class CodeRunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 10

class APITestRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    body: Optional[str] = None

class PackageInstallRequest(BaseModel):
    package: str
    type: str = "npm"

class EnvVarRequest(BaseModel):
    type: str
    variables: List[Dict[str, str]] = []

class SnippetCreate(BaseModel):
    title: str
    code: str
    language: str = "javascript"
    tags: Optional[str] = None

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

# Git Integration
@api_router.get("/git/status")
async def git_status():
    try:
        result = subprocess.run(
            "cd /app && git status --porcelain -b",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Check if git repo exists
        if result.returncode != 0:
            return {
                "initialized": False,
                "branch": None,
                "modified": [],
                "staged": []
            }
        
        lines = result.stdout.strip().split('\n')
        branch = lines[0].split('/')[-1] if lines else 'main'
        
        modified = []
        staged = []
        for line in lines[1:]:
            if line:
                status = line[:2]
                filename = line[3:]
                if 'M' in status or '?' in status:
                    modified.append(filename)
                if status[0] in ['A', 'M', 'D']:
                    staged.append(filename)
        
        return {
            "initialized": True,
            "branch": branch,
            "modified": modified,
            "staged": staged,
            "branches": []
        }
    except Exception as e:
        return {
            "initialized": False,
            "branch": None,
            "modified": [],
            "staged": []
        }

@api_router.post("/git/init")
async def git_init():
    try:
        result = subprocess.run(
            "cd /app && git init",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Configure git user
            subprocess.run("cd /app && git config user.name 'Mini Assistant'", shell=True)
            subprocess.run("cd /app && git config user.email 'mini@assistant.ai'", shell=True)
            return {"success": True, "message": "Repository initialized"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Init error: {str(e)}")

@api_router.post("/git/add")
async def git_add(files: List[str] = ["."])  :
    try:
        file_list = " ".join(files)
        result = subprocess.run(
            f"cd /app && git add {file_list}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Files staged"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Add error: {str(e)}")

@api_router.post("/git/commit")
async def git_commit(request: GitCommitRequest):
    try:
        result = subprocess.run(
            f'cd /app && git commit -m "{request.message}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 or "nothing to commit" in result.stdout:
            return {"success": True, "message": "Changes committed"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or result.stdout)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commit error: {str(e)}")

@api_router.post("/git/push")
async def git_push(request: GitPushRequest):
    try:
        result = subprocess.run(
            f"cd /app && git push {request.remote} {request.branch}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Pushed successfully"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or "Push failed. Make sure remote is configured and you have permissions.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push error: {str(e)}")

@api_router.post("/git/pull")
async def git_pull(request: GitPullRequest):
    try:
        result = subprocess.run(
            f"cd /app && git pull {request.remote} {request.branch}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Pulled successfully"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or "Pull failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pull error: {str(e)}")

@api_router.post("/git/remote/add")
async def git_add_remote(request: GitRemoteRequest):
    try:
        result = subprocess.run(
            f"cd /app && git remote add {request.name} {request.url}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {"success": True, "message": f"Remote '{request.name}' added"}
        else:
            # Try removing and re-adding if already exists
            subprocess.run(f"cd /app && git remote remove {request.name}", shell=True, capture_output=True)
            result = subprocess.run(
                f"cd /app && git remote add {request.name} {request.url}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return {"success": True, "message": f"Remote '{request.name}' updated"}
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Remote add error: {str(e)}")

@api_router.post("/git/branch/create")
async def git_create_branch(request: GitBranchRequest):
    try:
        result = subprocess.run(
            f"cd /app && git checkout -b {request.name}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {"success": True, "message": f"Branch '{request.name}' created"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Branch create error: {str(e)}")

# Code Runner
@api_router.post("/code-runner/execute")
async def execute_code(request: CodeRunRequest):
    try:
        if request.language == "python":
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(request.code)
                temp_file = f.name
            
            result = subprocess.run(
                f"python3 {temp_file}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=request.timeout
            )
            os.unlink(temp_file)
            
        elif request.language in ["javascript", "nodejs"]:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(request.code)
                temp_file = f.name
            
            result = subprocess.run(
                f"node {temp_file}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=request.timeout
            )
            os.unlink(temp_file)
        else:
            raise HTTPException(status_code=400, detail="Unsupported language")
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Execution timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

# API Tester
@api_router.post("/api-tester/request")
async def test_api(request: APITestRequest):
    try:
        import requests as req_lib
        
        method = request.method.upper()
        headers = request.headers or {}
        
        if method == "GET":
            response = req_lib.get(request.url, headers=headers, timeout=10)
        elif method == "POST":
            body_data = json.loads(request.body) if request.body else None
            response = req_lib.post(request.url, json=body_data, headers=headers, timeout=10)
        elif method == "PUT":
            body_data = json.loads(request.body) if request.body else None
            response = req_lib.put(request.url, json=body_data, headers=headers, timeout=10)
        elif method == "PATCH":
            body_data = json.loads(request.body) if request.body else None
            response = req_lib.patch(request.url, json=body_data, headers=headers, timeout=10)
        elif method == "DELETE":
            response = req_lib.delete(request.url, headers=headers, timeout=10)
        else:
            raise HTTPException(status_code=400, detail="Unsupported method")
        
        try:
            response_data = response.json()
        except:
            response_data = response.text
        
        return {
            "status": response.status_code,
            "headers": dict(response.headers),
            "data": response_data
        }
    except req_lib.exceptions.Timeout:
        raise HTTPException(status_code=408, detail="Request timeout")
    except req_lib.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API test error: {str(e)}")

# Package Manager
@api_router.get("/packages/list")
async def list_packages(type: str = "npm"):
    try:
        if type == "npm":
            result = subprocess.run(
                "cd /app/frontend && npm list --depth=0 --json",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                packages = [{"name": k, "version": v.get("version")} for k, v in data.get("dependencies", {}).items()]
                return {"packages": packages}
        elif type == "pip":
            result = subprocess.run(
                "pip list --format=json",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return {"packages": packages}
        
        return {"packages": []}
    except Exception as e:
        return {"packages": []}

@api_router.post("/packages/install")
async def install_package(request: PackageInstallRequest):
    try:
        if request.type == "npm":
            result = subprocess.run(
                f"cd /app/frontend && yarn add {request.package}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
        elif request.type == "pip":
            result = subprocess.run(
                f"pip install {request.package} && pip freeze > /app/backend/requirements.txt",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid package type")
        
        if result.returncode == 0:
            return {"success": True, "message": f"{request.package} installed"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Install error: {str(e)}")

@api_router.post("/packages/uninstall")
async def uninstall_package(request: PackageInstallRequest):
    try:
        if request.type == "npm":
            result = subprocess.run(
                f"cd /app/frontend && yarn remove {request.package}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        elif request.type == "pip":
            result = subprocess.run(
                f"pip uninstall -y {request.package} && pip freeze > /app/backend/requirements.txt",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid package type")
        
        if result.returncode == 0:
            return {"success": True, "message": f"{request.package} uninstalled"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Uninstall error: {str(e)}")

# Environment Manager
@api_router.get("/env/read")
async def read_env(type: str = "frontend"):
    try:
        env_path = "/app/frontend/.env" if type == "frontend" else "/app/backend/.env"
        if not Path(env_path).exists():
            return {"variables": []}
        
        variables = []
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    variables.append({"id": len(variables), "key": key, "value": value})
        
        return {"variables": variables}
    except Exception as e:
        return {"variables": []}

@api_router.post("/env/write")
async def write_env(request: EnvVarRequest):
    try:
        env_path = "/app/frontend/.env" if request.type == "frontend" else "/app/backend/.env"
        
        with open(env_path, 'w') as f:
            for var in request.variables:
                if var.get('key'):
                    f.write(f"{var['key']}={var.get('value', '')}\\n")
        
        return {"success": True, "message": "Environment variables saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write error: {str(e)}")

# Snippet Library
@api_router.get("/snippets/list")
async def list_snippets():
    snippets = await db.snippets.find({}, {"_id": 0}).to_list(1000)
    return {"snippets": snippets}

@api_router.post("/snippets/create")
async def create_snippet(snippet: SnippetCreate):
    snippet_dict = snippet.model_dump()
    snippet_dict["id"] = str(uuid.uuid4())
    snippet_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.snippets.insert_one(snippet_dict)
    return {"success": True, "id": snippet_dict["id"]}

@api_router.delete("/snippets/delete/{snippet_id}")
async def delete_snippet(snippet_id: str):
    result = await db.snippets.delete_one({"id": snippet_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return {"success": True}

# Conversation Summarization
class SummarizeRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "llama3.2"

@api_router.post("/chat/summarize")
async def summarize_conversation(request: SummarizeRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        conversation_text = "\n".join([f"{msg.role}: {msg.content}" for msg in request.messages])
        
        summary_prompt = f"""Please provide a concise summary of this conversation. Include:
1. Key topics discussed
2. Important decisions or conclusions
3. Any action items mentioned

Conversation:
{conversation_text}

Summary:"""
        
        response = ollama_client.chat(
            model=request.model,
            messages=[{"role": "user", "content": summary_prompt}]
        )
        
        return {"summary": response['message']['content']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization error: {str(e)}")

# Security Scanner
class SecurityScanRequest(BaseModel):
    code: str

@api_router.post("/security/scan")
async def security_scan(request: SecurityScanRequest):
    vulnerabilities = []
    code = request.code
    
    # Check for common security issues
    security_patterns = [
        {"pattern": "eval(", "title": "Dangerous eval() usage", "severity": "critical", "description": "eval() can execute arbitrary code", "fix": "Use safer alternatives like JSON.parse()"},
        {"pattern": "exec(", "title": "Dangerous exec() usage", "severity": "critical", "description": "exec() can execute arbitrary system commands", "fix": "Use subprocess with proper input validation"},
        {"pattern": "dangerouslySetInnerHTML", "title": "XSS Risk", "severity": "high", "description": "May allow XSS attacks", "fix": "Sanitize HTML content before rendering"},
        {"pattern": "password", "title": "Hardcoded Password", "severity": "high", "description": "Password found in code", "fix": "Use environment variables for secrets"},
        {"pattern": "api_key", "title": "Exposed API Key", "severity": "high", "description": "API key found in code", "fix": "Use environment variables"},
        {"pattern": "secret", "title": "Potential Secret Exposure", "severity": "medium", "description": "Secret keyword found", "fix": "Review and secure sensitive data"},
        {"pattern": "http://", "title": "Insecure HTTP", "severity": "medium", "description": "Using HTTP instead of HTTPS", "fix": "Use HTTPS for secure communication"},
        {"pattern": "SELECT * FROM", "title": "SQL Injection Risk", "severity": "high", "description": "Raw SQL query detected", "fix": "Use parameterized queries"},
        {"pattern": "pickle.load", "title": "Unsafe Deserialization", "severity": "critical", "description": "Pickle can execute arbitrary code", "fix": "Use safer formats like JSON"},
        {"pattern": "shell=True", "title": "Shell Injection Risk", "severity": "high", "description": "subprocess with shell=True is risky", "fix": "Use shell=False with argument list"},
    ]
    
    for i, line in enumerate(code.split('\n'), 1):
        for pattern in security_patterns:
            if pattern["pattern"].lower() in line.lower():
                vulnerabilities.append({
                    "line": i,
                    "code": line.strip(),
                    **{k: v for k, v in pattern.items() if k != "pattern"}
                })
    
    return {"vulnerabilities": vulnerabilities, "scanned_lines": len(code.split('\n'))}

# Deployment
class DeployRequest(BaseModel):
    platform: str
    project_path: str = "/app"

@api_router.post("/deploy/start")
async def start_deployment(request: DeployRequest):
    # Mock deployment - in real scenario, this would integrate with Vercel/Netlify/Railway APIs
    return {
        "status": "initiated",
        "platform": request.platform,
        "message": f"Deployment to {request.platform} would be initiated here. Configure your {request.platform} API token to enable real deployments.",
        "url": f"https://your-app.{request.platform}.app"
    }

# Docker Management (Mock - requires Docker to be available)
@api_router.get("/docker/containers")
async def list_docker_containers():
    try:
        result = subprocess.run(
            "docker ps -a --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        containers = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 4:
                    containers.append({
                        "id": parts[0],
                        "name": parts[1],
                        "image": parts[2],
                        "status": "running" if "Up" in parts[3] else "stopped"
                    })
        
        return {"containers": containers}
    except Exception as e:
        return {"containers": [], "error": str(e)}

@api_router.post("/docker/start/{container_id}")
async def start_docker_container(container_id: str):
    try:
        result = subprocess.run(
            f"docker start {container_id}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {"success": result.returncode == 0, "output": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/docker/stop/{container_id}")
async def stop_docker_container(container_id: str):
    try:
        result = subprocess.run(
            f"docker stop {container_id}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {"success": result.returncode == 0, "output": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Performance Monitor
@api_router.get("/monitor/performance")
async def get_performance_metrics():
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        boot_time = psutil.boot_time()
        
        uptime_seconds = datetime.now().timestamp() - boot_time
        hours, remainder = divmod(int(uptime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
        
        return {
            "cpu": round(cpu_percent, 1),
            "memory": round(memory.percent, 1),
            "disk": round(disk.percent, 1),
            "uptime": uptime_str
        }
    except ImportError:
        return {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "uptime": "N/A",
            "error": "psutil not installed"
        }

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