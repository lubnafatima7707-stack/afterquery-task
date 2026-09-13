FROM python:3.11-slim

RUN pip install --no-cache-dir numpy==2.0.2

# tools/harness.py runs the store under this account when it is started by root,
# which is how the graded run drives it too, so the development checker behaves
# the same way here as it does in grading
RUN useradd --create-home --uid 10001 runner

WORKDIR /app
COPY data/ /app/data/
COPY tools/ /app/tools/
