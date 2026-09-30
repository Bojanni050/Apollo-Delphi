FROM python:3.12-slim

WORKDIR /app

# git: every werkmap is a git repository (see services/workspace_repo.py).
# safe.directory '*': the repositories live on bind mounts owned by another user.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
