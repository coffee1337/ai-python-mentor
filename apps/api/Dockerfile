FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN chmod +x entrypoint.sh && groupadd --gid 10001 api && useradd --uid 10001 --gid api --no-create-home api
USER api
EXPOSE 8000
CMD ["./entrypoint.sh"]
