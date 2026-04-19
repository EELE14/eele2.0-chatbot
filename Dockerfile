FROM python:3.13-slim

WORKDIR /app

COPY requirements-bot.txt .
RUN pip install --no-cache-dir -r requirements-bot.txt

# Copy source
COPY main.py bot.py config.py llm.py history.py search.py ./
COPY system_prompt*.txt ./

CMD ["python3", "main.py"]
