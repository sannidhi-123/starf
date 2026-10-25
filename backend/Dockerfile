FROM python:3.12-slim

WORKDIR /app

# Copy the stark source so it is importable by uvicorn
COPY ../src /app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

EXPOSE 8000

# PYTHONPATH includes /app/src so `from stark...` works at runtime
ENV PYTHONPATH=/app/src

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
