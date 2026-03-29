FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend /app

ENV PYTHONPATH=/app
ENV DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/lms

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
