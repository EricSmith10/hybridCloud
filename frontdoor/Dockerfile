FROM python:3.12-slim
WORKDIR /app
COPY app.py .
ENV PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
# OpenShift runs containers as a random non-root user; this app needs no write access.
USER 1001
CMD ["python", "app.py"]
