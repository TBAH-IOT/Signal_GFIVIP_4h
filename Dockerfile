FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY mom_basis ./mom_basis
COPY web ./web
COPY data ./data
ENV GFI_STATE_DIR=/state
EXPOSE 8765
CMD ["python", "-m", "mom_basis", "serve", "--mode", "live", "--host", "0.0.0.0", "--port", "8765", "--state-dir", "/state"]
