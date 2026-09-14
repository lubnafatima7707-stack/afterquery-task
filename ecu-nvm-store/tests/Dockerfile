FROM python:3.11-slim
RUN pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5 numpy==2.0.2
RUN id -u runner >/dev/null 2>&1 || useradd --create-home --uid 10001 runner
COPY . /tests/
RUN chmod -R go-rwx /tests && mkdir -p /app
