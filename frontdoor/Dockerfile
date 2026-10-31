FROM python:3.12-slim
WORKDIR /app
COPY frontdoor.py .
ENV PORT=8095 PYTHONUNBUFFERED=1
EXPOSE 8095
USER 1001
CMD ["python", "frontdoor.py"]
