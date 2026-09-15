FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/plc_server.py .

# CHAL_FLAG is injected at deploy time — never bake the real flag into the image layer history.
ENV CHAL_HOST=0.0.0.0
ENV CHAL_PORT=502

EXPOSE 502

CMD ["python3", "plc_server.py"]
