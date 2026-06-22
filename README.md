PRO-2 backend is set up in Profy-Backend. The repo had only git initialized; the full FastAPI stack is in place and verified locally.

What was created
Structure

Profy-Backend/
├── app/
│   ├── main.py          # FastAPI, CORS, lifespan DB check
│   ├── config.py        # pydantic-settings (DATABASE_URL, REDIS_URL, SECRET_KEY, LLM_API_KEY)
│   ├── database.py      # SQLAlchemy 2.0 async engine + sessionmaker
│   ├── routers/         # empty api_router (ready for PRO-3)
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── prompts/
├── alembic/             # async env.py configured
├── docker-compose.yml   # api, db, redis, nginx
├── Dockerfile
├── nginx.conf           # proxy 80/443 → api:8000
├── requirements.txt
└── .env.example
Verified acceptance criteria (backend)

docker compose up -d — all 4 services healthy
GET http://localhost/docs — Swagger UI (HTTP 200, empty paths: [])
Startup log: INFO:app.main:Database connected
.env.example includes all required variables



How to run
cd Profy-Backend
cp .env.example .env
# SSL certs for nginx :443 (one-time)
mkdir -p nginx/ssl && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem -subj "/CN=localhost"
docker compose up -d --build
Swagger: http://localhost/docs