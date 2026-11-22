FROM python:3.12.10-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir Flask==3.1.1
COPY app.py /app/app.py
EXPOSE 5005
CMD ["python", "app.py"]
