# Dockerfile
FROM python:3.14-slim

# Устанавливаем uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Копируем зависимости
COPY pyproject.toml uv.lock* ./

# Устанавливаем пакеты (очень быстро благодаря uv)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-install-project


# Копируем код
COPY . .

# Для dev — не нужно ENTRYPOINT, command в compose переопределит
EXPOSE 8000