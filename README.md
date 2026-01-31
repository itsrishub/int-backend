# InterviewAI Backend Services

Backend services for the InterviewAI application.

## Services

### AI Avatar Service
Generates AI-powered talking avatar videos for interview sessions.

**Features:**
- 🎬 **Video Avatar**: D-ID Clips API with professional Amber presenter
- 🔊 **Text-to-Speech**: Microsoft neural voices (en-US-JennyNeural)
- 🔄 **Idle Video**: Pre-made idle loop for smooth transitions
- 📝 **Lip-Sync Timing**: Word-level timing for client-side animation
- 🔁 **Fallback Mode**: Audio-only with static image when D-ID unavailable
- 💬 **Real-time Sessions**: WebSocket-based interview flow
- 📋 **Mock Questions**: 10 mixed interview questions for testing

## Quick Start

### Prerequisites
- Python 3.10+
- Conda (recommended) or pip

### Installation

```bash
# Create conda environment
conda create -n interviewai python=3.11 -y
conda activate interviewai

# Install dependencies
cd int-backend
pip install -e .
```

### D-ID Setup (for Video Avatar)

1. Sign up at [D-ID Studio](https://studio.d-id.com/) (free trial: 5 minutes of video)
2. Get your API key from Account Settings
3. Create a `.env` file:

```bash
cp .env.example .env
# Edit .env and add your D-ID API key
```

Without D-ID API key, the service falls back to **audio-only mode** with static avatar image.

### Running the Service

```bash
# Activate environment
conda activate interviewai

# Run the server
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Avatar Status**: http://localhost:8000/api/v1/avatar/status
- **Postman Collection**: See `docs/postman_collection.json`

---

## 🚀 Deployment

### Option 1: Render (Recommended - Free Tier)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. **Create a Render account** at [render.com](https://render.com)

2. **Connect your GitHub repository**

3. **Create a new Web Service:**
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Set Environment Variables:**
   ```
   DID_API_KEY=your_did_api_key_here
   AVATAR_MODE=video
   ```

5. **Deploy!**

Your service will be available at: `https://your-app-name.onrender.com`

> ⚠️ **Note**: Free tier sleeps after 15 minutes of inactivity. First request may take 30-60 seconds to wake up.

### Option 2: Railway

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   railway login
   ```

2. **Deploy:**
   ```bash
   cd int-backend
   railway init
   railway up
   ```

3. **Set Environment Variables:**
   ```bash
   railway variables set DID_API_KEY=your_key
   ```

### Option 3: Fly.io

1. **Install Fly CLI:**
   ```bash
   curl -L https://fly.io/install.sh | sh
   fly auth login
   ```

2. **Deploy:**
   ```bash
   cd int-backend
   fly launch
   fly secrets set DID_API_KEY=your_key
   ```

### Deployment URLs

Once deployed, update your Android client to use:
- **HTTP API**: `https://your-app.onrender.com/api/v1/...`
- **WebSocket**: `wss://your-app.onrender.com/api/v1/interview/session`

---

## Avatar Modes

### 1. Video Mode (D-ID Clips)
When `DID_API_KEY` is configured, generates full avatar videos with realistic lip-sync.

**Presenter:** Amber (professional female)
**Voice:** en-US-JennyNeural (Microsoft TTS)

**Response includes:**
- `video_url`: URL to the generated MP4 video
- `idle_video_url`: Pre-made idle loop for transitions
- `avatar_mode`: "video"
- `latency_ms`: Generation time in milliseconds

### 2. Audio-Only Mode (Fallback)
When D-ID is not configured or fails, provides audio with lip-sync timing data.

**Response includes:**
- `audio_base64`: Base64 encoded MP3 audio
- `word_timings`: Timing data for client-side lip-sync animation
- `avatar_image_url`: Static avatar image URL
- `avatar_mode`: "audio_only"

---

## API Reference

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/avatar/status` | GET | D-ID status and credits |
| `/api/v1/interview/info` | GET | Interview configuration |
| `/api/v1/voices` | GET | Available TTS voices |
| `/docs` | GET | Swagger UI |
| `/openapi.json` | GET | OpenAPI spec |

### WebSocket Endpoint

```
ws://localhost:8000/api/v1/interview/session
wss://your-app.onrender.com/api/v1/interview/session  (production)
```

### Message Flow

1. **Connect** → Server sends `session_info` (includes `avatar_mode`)
2. **Send** `{"type": "start"}` → Server sends first `question`
3. **Send** `{"type": "answer", "data": {"question_id": 1, "answer_text": "..."}}` → Server sends next `question`
4. Repeat until server sends `complete`

### Client → Server Messages

```json
{"type": "start"}
{"type": "answer", "data": {"question_id": 1, "answer_text": "My answer..."}}
{"type": "ping", "data": {"timestamp": 1234567890}}
{"type": "end"}
```

### Server → Client: Session Info

```json
{
  "type": "session_info",
  "data": {
    "session_id": "session_abc123",
    "state": "created",
    "total_questions": 10,
    "avatar_mode": "video",
    "avatar_image_url": "https://clips-presenters.d-id.com/..."
  }
}
```

### Server → Client: Question (Video Mode)

```json
{
  "type": "question",
  "data": {
    "question_id": 1,
    "question_text": "Tell me about yourself...",
    "question_type": "introduction",
    "avatar_mode": "video",
    "video_url": "https://d-id-clips-prod.s3.us-west-2.amazonaws.com/...",
    "idle_video_url": "https://clips-presenters.d-id.com/.../idle.mp4",
    "audio_base64": "//uQxAAA...",
    "audio_duration": 10.5,
    "current_question": 1,
    "total_questions": 10,
    "latency_ms": 45000
  }
}
```

### Server → Client: Question (Audio-Only Mode)

```json
{
  "type": "question",
  "data": {
    "question_id": 1,
    "question_text": "Tell me about yourself...",
    "question_type": "introduction",
    "avatar_mode": "audio_only",
    "video_url": null,
    "idle_video_url": "https://clips-presenters.d-id.com/.../idle.mp4",
    "audio_base64": "//uQxAAA...",
    "audio_duration": 10.5,
    "word_timings": [
      {"word": "Tell", "start": 0.0, "end": 0.3},
      {"word": "me", "start": 0.3, "end": 0.5}
    ],
    "avatar_image_url": "https://clips-presenters.d-id.com/.../image.png",
    "current_question": 1,
    "total_questions": 10
  }
}
```

### Server → Client: Complete

```json
{
  "type": "complete",
  "data": {
    "message": "Congratulations! You have completed the interview.",
    "questions_answered": 10,
    "session_summary": {...}
  }
}
```

---

## Project Structure

```
int-backend/
├── main.py                     # Main entry point
├── pyproject.toml              # Dependencies
├── requirements.txt            # Pip requirements (for deployment)
├── render.yaml                 # Render deployment config
├── Procfile                    # Heroku/Railway config
├── .env.example                # Environment template
├── README.md
│
├── docs/
│   └── postman_collection.json # Postman API collection
│
├── services/
│   └── ai_avatar/              # AI Avatar Service
│       ├── main.py             # FastAPI app
│       ├── config.py           # Configuration (D-ID, TTS, etc.)
│       ├── api/
│       │   ├── routes.py       # WebSocket & HTTP endpoints
│       │   └── schemas.py      # Pydantic models
│       ├── core/
│       │   ├── tts_service.py  # Edge-TTS integration
│       │   ├── avatar_service.py  # D-ID Clips API
│       │   └── session_manager.py
│       └── mock/
│           └── question_service.py  # 10 mock questions
│
└── shared/
    └── utils.py
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DID_API_KEY` | D-ID API key for video avatars | "" (audio-only mode) |
| `AVATAR_MODE` | Force mode: "video" or "audio_only" | Auto-detect |
| `PORT` | Server port | 8000 |
| `DEBUG` | Enable debug mode | false |

### Config File

Edit `services/ai_avatar/config.py` to change:
- TTS voice (default: `en-US-JennyNeural`)
- Speaking rate, volume, pitch
- Avatar generation timeout
- Session timeout
- D-ID presenter ID

---

## Testing

### Test with Postman

1. Import `docs/postman_collection.json` into Postman
2. Set the `base_url` variable to your deployment URL
3. Run the requests!

### Test with WebSocket Client

```bash
# Install websocat
# Ubuntu: sudo apt install websocat
# macOS: brew install websocat

# Connect
websocat ws://localhost:8000/api/v1/interview/session
```

Then send:
```json
{"type": "start"}
```

### Test Avatar Status

```bash
curl http://localhost:8000/api/v1/avatar/status
```

### Test Health Check

```bash
curl https://your-app.onrender.com/api/v1/health
```

---

## Android Client Integration

The Android client should:

1. **Connect** to WebSocket endpoint (`wss://` for production)
2. **Handle `session_info`** to know the `avatar_mode` and get `idle_video_url`
3. **For `video` mode:**
   - Download and cache `idle_video_url` for transitions
   - Fetch and play video from `video_url` when question arrives
4. **For `audio_only` mode:**
   - Play `audio_base64` (decode from base64)
   - Display `avatar_image_url`
   - Use `word_timings` for mouth animation
5. **Send answers** as `{"type": "answer", ...}`
6. **Repeat** until `complete` message

### Example Kotlin WebSocket Connection

```kotlin
val client = OkHttpClient()
val request = Request.Builder()
    .url("wss://your-app.onrender.com/api/v1/interview/session")
    .build()

val webSocket = client.newWebSocket(request, object : WebSocketListener() {
    override fun onMessage(webSocket: WebSocket, text: String) {
        val message = JSONObject(text)
        when (message.getString("type")) {
            "session_info" -> handleSessionInfo(message)
            "question" -> handleQuestion(message)
            "complete" -> handleComplete(message)
        }
    }
})

// Start interview
webSocket.send("""{"type": "start"}""")
```

---

## License

MIT
