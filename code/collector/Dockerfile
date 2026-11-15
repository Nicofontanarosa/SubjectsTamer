# Uses less memory and reduces the security attack surface.
FROM python:3.12.10-slim-bookworm
WORKDIR /app

# Gunicorn is a Python WSGI (Web Server Gateway Interface) HTTP server primarily used to run web applications in production.
# Flask's built-in development server is convenient for local testing, but it is not secure or scalable and is not designed
# to handle real internet traffic. Gunicorn fills this gap by sitting between the main web server (such as Nginx or Apache)
# and the Python application.
COPY collector/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
# This is a security best practice: instead of running everything with maximum privileges (as root),
# these steps isolate the application, protect the system, and follow the principle of least privilege.
# Creates the "appuser" account with UID 10001, creates the /data directory, and assigns ownership of /app and /data to "appuser".

# Contains modules shared by multiple microservices, such as game logic, monster classes, and catalog-loading functions.
COPY common /app/common
# The catalog and card images are shared project resources.
COPY shared/catalog.json /app/shared/catalog.json
COPY shared/assets /app/shared/assets

COPY collector/app.py /app/app.py
COPY collector/routes /app/routes

# Tells Docker to run subsequent commands and the container process as user ID 10001 and group ID 10001.
USER 10001:10001
EXPOSE 5005

# - Starts the Flask application (the "app" instance in app.py) on port 5005 inside the container.
# - The "--bind 0.0.0.0:5005" option allows the server to accept traffic from outside the Docker container.
# - The "--workers 2" option starts two parallel worker processes to handle user requests.
CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "2", "app:app"]

# If you used CMD ["flask", "--app", "app", "run", "--host=0.0.0.0", "--port=5005"],
# it would use a development server that is generally single-threaded or handles requests with limited concurrency.
# If two users submit resource-intensive requests at the same time, the second may have to wait for the first to finish.
# Gunicorn uses a pre-fork worker model. The --workers 2 option starts two separate, independent processes
# to handle requests in parallel, allowing it to serve multiple users concurrently.