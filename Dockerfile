FROM python:3.11-slim

WORKDIR /app

# Upgrade pip for optimal wheel processing
RUN pip install --no-cache-dir --upgrade pip

# FIXED: Added the correct repository endpoint for the CPU version
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install the remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
