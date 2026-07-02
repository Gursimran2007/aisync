FROM python:3.11-slim

WORKDIR /app

# System deps: pdfplumber needs lib's for its pdfminer/pillow backend.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# headless server on the port Fly expects; address 0.0.0.0 so Fly can reach it.
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
