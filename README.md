# HK Math Student Portal

香港中一數學 AI 智能練習平台

## Quick Deploy (Render)
1. Push to GitHub
2. Connect render.com → this repo
3. Set DATABASE_URL env var
4. Deploy

## Local
```bash
pip install -r requirements.txt
python launch.py --port 5100
```

## APIs
- GET / — landing page
- GET /api/adaptive/<student> — smart questions
- POST /api/smart — full AI pipeline
- POST /api/tutor/hint — progressive hints
- POST /api/mark — answer scoring
- GET /api/diagnose/<student> — weakness detection
