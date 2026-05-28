# HK Math Student Portal — Render Deployment

香港中一至中四數學 AI 智能練習平台

## 一鍵部署到 Render.com

### Step 1: Fork/Push to GitHub (已完成 ✅)
```
https://github.com/lui62233/hk-math-student-portal
```

### Step 2: Render.com 設定

1. 打開 [dashboard.render.com](https://dashboard.render.com)
2. 點 **New** → **Web Service**
3. 連接 `lui62233/hk-math-student-portal`
4. Render 會自動偵測 `render.yaml`，包含：
   - **Web Service**: Python + Gunicorn
   - **PostgreSQL**: 免費層級 (question_bank)
   - **Migration**: 自動建表 + 導入 1,409 題

### Step 3: 環境變數 (自動設定)

| 變數 | 來源 | 說明 |
|------|------|------|
| `DATABASE_URL` | Render DB 自動 | PostgreSQL 連接 |
| `FRELLMAPI_URL` | 手動 | frellmapi 端點 |
| `FRELLMAPI_KEY` | 手動 | API 金鑰 |

### Step 4: frellmapi 設定

選項 A: 保留本機 frellmapi (需固定 IP)
```
FRELLMAPI_URL=http://your-public-ip:3001/v1
```

選項 B: 部署 frellmapi 到 Render (另開 Web Service)
```
# 使用 frellmapi Docker 映像或原始碼部署
```

選項 C: 使用 OpenAI/其他 API (修改 app.py)
```
FRELLMAPI_URL=https://api.openai.com/v1
FRELLMAPI_KEY=sk-...
```

### ⚠️ 注意事項

- 題庫 JSON 為 2.8MB，Render 免費層級有 512MB 限制 (足夠)
- PostgreSQL 免費層級 1GB (1,409 題約 5MB)
- frellmapi 需可從 Render 訪問 (本機 localhost:3001 無法直接訪問)
- 首次部署約 5-8 分鐘 (含 migration)

### 本機測試

```bash
pip install -r requirements.txt
python launch.py --port 5100
# 開啟 http://localhost:5100
```

### API 端點

| 方法 | 路徑 | 功能 |
|------|------|------|
| GET | `/` | 落地頁面 |
| GET | `/resources` | 學習資源 |
| GET | `/api/adaptive/<name>` | 自適應選題 |
| POST | `/api/smart` | 全 AI 管線 |
| POST | `/api/tutor/hint` | 漸進提示 |
| POST | `/api/mark` | 答案評分 |
| GET | `/api/diagnose/<name>` | 弱點診斷 |
| POST | `/api/submit` | 提交+進度 |

### 技術棧

- **Backend**: Python 3.11 + Flask + Gunicorn
- **Database**: PostgreSQL (Render managed)
- **AI**: frellmapi (99 models, $0) + DeepSeek
- **Frontend**: HTML/CSS (landing page)
- **Modules**: adaptive, tutor, mark, misconception, gamification, orchestrator, variant, feedback, quality scorer
