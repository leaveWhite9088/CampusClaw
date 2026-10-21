FROM python:3.13-slim

WORKDIR /app
COPY server.py .

ENV PORT=8090
EXPOSE 8090

CMD ["python", "server.py", "8090"]
