# JARVIS Setup Guide

Complete guide to set up your local all-in-one AI assistant.

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Ollama Installation](#ollama-installation)
3. [Model Selection Guide](#model-selection-guide)
4. [Testing the Setup](#testing-the-setup)
5. [Common Issues](#common-issues)

## System Requirements

### Minimum (For Chat Only)
- **CPU:** 4 cores
- **RAM:** 8GB
- **Storage:** 5GB free space
- **OS:** macOS, Linux, or Windows

### Recommended (For All Features)
- **CPU:** 8+ cores
- **RAM:** 16GB+
- **Storage:** 20GB free space
- **Microphone:** For voice input
- **Speakers/Headphones:** For voice output

### For GPU Acceleration (Optional)
- **NVIDIA GPU:** GTX 1060+ with CUDA support
- **AMD GPU:** ROCm compatible
- **Apple Silicon:** M1/M2/M3 (automatically used by Ollama)

## Ollama Installation

### macOS

```bash
# Download and install
curl -fsSL https://ollama.com/install.sh | sh

# Verify installation
ollama --version

# Start the service
ollama serve
```

### Linux (Ubuntu/Debian)

```bash
# Install
curl -fsSL https://ollama.com/install.sh | sh

# Start as a service
sudo systemctl enable ollama
sudo systemctl start ollama

# Check status
sudo systemctl status ollama

# Or run manually
ollama serve
```

### Linux (Other Distributions)

```bash
# Download and install
curl -fsSL https://ollama.com/install.sh | sh

# Run manually
ollama serve
```

### Windows

1. Download installer from https://ollama.com/download
2. Run the installer
3. Ollama will start automatically as a Windows service
4. Verify by opening http://localhost:11434

### Docker (Alternative)

```bash
# Run Ollama in Docker
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# Pull a model
docker exec -it ollama ollama pull llama3.2
```

## Model Selection Guide

### Step 1: Choose Your Model

Based on your hardware:

**Low RAM (8GB)**
```bash
ollama pull llama3.2:1b    # 1.3GB - Fastest, basic tasks
ollama pull phi3           # 2.3GB - Good quality
```

**Medium RAM (8-16GB)**
```bash
ollama pull llama3.2       # 2GB - RECOMMENDED
ollama pull llama3.2:3b    # 2GB - Balanced
ollama pull mistral        # 4.1GB - Great reasoning
```

**High RAM (16GB+)**
```bash
ollama pull llama3.2:7b    # 3.8GB - High quality
ollama pull mixtral        # 26GB - Expert model
ollama pull llama3.2:70b   # 40GB - Best quality (needs powerful hardware)
```

### Step 2: Pull Multiple Models

It's recommended to have at least 2 models:

```bash
# For general use
ollama pull llama3.2

# For faster responses
ollama pull llama3.2:1b
```

### Step 3: Test Your Model

```bash
# Test the model
ollama run llama3.2

# In the prompt, type:
> Hello, are you working?

# Exit with: /bye
```

### Popular Models Comparison

| Model | Size | RAM | Speed | Quality | Best For |
|-------|------|-----|-------|---------|----------|
| llama3.2:1b | 1.3GB | 4GB | ⚡⚡⚡⚡ | ⭐⭐⭐ | Quick queries, low-end hardware |
| phi3 | 2.3GB | 6GB | ⚡⚡⚡ | ⭐⭐⭐⭐ | Balanced, efficient |
| llama3.2 | 2GB | 8GB | ⚡⚡⚡ | ⭐⭐⭐⭐ | **Recommended default** |
| mistral | 4.1GB | 8GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | Reasoning, coding |
| llama3.2:7b | 3.8GB | 16GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | High quality responses |
| mixtral | 26GB | 32GB | ⚡ | ⭐⭐⭐⭐⭐⭐ | Complex tasks |

## Testing the Setup

### 1. Check Ollama is Running

```bash
# Test the service
curl http://localhost:11434
# Should return: "Ollama is running"
```

### 2. List Installed Models

```bash
ollama list
```

Expected output:
```
NAME                ID              SIZE      MODIFIED
llama3.2:latest     abc123def       2.0 GB    2 minutes ago
```

### 3. Test Chat Endpoint

```bash
# Test Ollama API
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2",
  "prompt": "Hello, test message",
  "stream": false
}'
```

### 4. Open JARVIS Application

Visit: https://jarvis-hub-12.preview.emergentagent.com

You should see:
- ✅ Status indicator showing "ONLINE" (green)
- ✅ No error messages
- ✅ Chat interface ready

### 5. Test Chat Feature

1. Select "LLAMA 3.2" from model dropdown
2. Type: "Hello, are you working?"
3. Press Enter or click SEND
4. You should get a response within a few seconds

## Common Issues

### Issue 1: "Ollama service not available"

**Symptoms:**
- Red "OFFLINE" status indicator
- Error toast: "Ollama service not available"

**Solutions:**

1. **Check if Ollama is running:**
   ```bash
   curl http://localhost:11434
   ```

2. **Start Ollama:**
   ```bash
   # macOS/Linux
   ollama serve
   
   # Or as background service (Linux)
   sudo systemctl start ollama
   ```

3. **Check firewall:**
   - Ensure port 11434 is not blocked
   - Add exception if needed

4. **Restart Ollama:**
   ```bash
   # Kill existing process
   pkill ollama
   
   # Start again
   ollama serve
   ```

### Issue 2: "Model not found"

**Symptoms:**
- Error: "model 'llama3.2' not found"

**Solution:**
```bash
# Pull the model
ollama pull llama3.2

# Verify
ollama list
```

### Issue 3: Slow Responses

**Causes & Solutions:**

1. **Model too large for RAM:**
   - Switch to smaller model: `llama3.2:1b` or `phi3`
   
2. **CPU bottleneck:**
   - Close other applications
   - Use smaller model
   
3. **No GPU acceleration:**
   - Check if GPU is detected: `nvidia-smi` (NVIDIA)
   - Reinstall Ollama with GPU support

### Issue 4: Voice Recording Not Working

**Symptoms:**
- "Microphone access denied" error
- Recording doesn't start

**Solutions:**

1. **Grant microphone permissions:**
   - Chrome: Settings → Privacy → Microphone
   - Firefox: Settings → Permissions → Microphone
   - Safari: Preferences → Websites → Microphone

2. **Check HTTPS:**
   - Microphone only works over HTTPS
   - Use the provided HTTPS URL

3. **Test microphone:**
   - Open browser console (F12)
   - Try: `navigator.mediaDevices.getUserMedia({ audio: true })`

### Issue 5: Commands Not Executing

**Symptoms:**
- "Command not in allowlist" error

**Solution:**
The command terminal uses an allowlist for security. Allowed commands:
- `ls`, `pwd`, `cat`, `echo`, `grep`, `find`, `wc`, `head`, `tail`, `tree`, `whoami`

For other commands, use the File Manager to edit files or install Ollama on your local machine and point to it.

### Issue 6: Out of Memory Error

**Symptoms:**
- Ollama crashes
- System freezes
- "Out of memory" errors

**Solutions:**

1. **Use smaller model:**
   ```bash
   ollama pull llama3.2:1b
   ```

2. **Set memory limit:**
   ```bash
   # Linux
   export OLLAMA_MAX_LOADED_MODELS=1
   export OLLAMA_NUM_PARALLEL=1
   ```

3. **Close other applications**

4. **Increase swap space (Linux):**
   ```bash
   sudo fallocate -l 8G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

## Performance Optimization

### For Faster Responses

1. **Use quantized models:**
   ```bash
   ollama pull llama3.2:1b-q4_0  # 4-bit quantization
   ```

2. **Reduce context length:**
   - Edit backend/server.py
   - Reduce `num_ctx` parameter

3. **Enable GPU acceleration:**
   - Ensure CUDA/ROCm installed
   - Ollama auto-detects GPU

### For Better Quality

1. **Use larger models:**
   ```bash
   ollama pull llama3.2:7b
   ollama pull mistral
   ```

2. **Increase temperature:**
   - Modify chat request parameters
   - Higher temperature = more creative

## Advanced Configuration

### Custom Ollama Host

If Ollama is running on a different machine:

1. Edit `/app/backend/server.py`:
   ```python
   ollama_client = Client(host='http://YOUR_IP:11434')
   ```

2. Restart backend:
   ```bash
   sudo supervisorctl restart backend
   ```

### Using GPU

Ollama automatically uses GPU if available. To verify:

```bash
# NVIDIA
nvidia-smi

# AMD
rocm-smi

# Apple Silicon (M1/M2/M3)
# Automatically used, no configuration needed
```

### Multiple Models Running

Load multiple models simultaneously:

```bash
# Set environment variable
export OLLAMA_MAX_LOADED_MODELS=2

# Restart Ollama
ollama serve
```

## Getting Help

### Ollama Issues
- GitHub: https://github.com/ollama/ollama/issues
- Discord: https://discord.gg/ollama

### JARVIS Issues
- Check backend logs: `tail -f /var/log/supervisor/backend.err.log`
- Check frontend logs: Browser console (F12)

### Model Issues
- Try different models: `ollama list`
- Check model info: `ollama show llama3.2`

## Next Steps

Once everything is working:

1. ✅ **Try Voice Mode:** Test speech-to-text and text-to-speech
2. ✅ **Explore File Manager:** Browse and edit files
3. ✅ **Run Commands:** Use the terminal for quick tasks
4. ✅ **Search the Web:** Try web search feature
5. ✅ **Create Profiles:** Set up project-specific profiles
6. ✅ **Customize:** Modify models, prompts, and settings

## Resources

- **Ollama Documentation:** https://github.com/ollama/ollama/blob/main/docs
- **Model Library:** https://ollama.com/library
- **Faster-Whisper:** https://github.com/SYSTRAN/faster-whisper
- **FastAPI Docs:** https://fastapi.tiangolo.com

---

**Need Help?** Check the logs, restart services, and verify your Ollama installation!
