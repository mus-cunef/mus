# Imagen para publicar la web de Mus Arena en internet (Hugging Face Spaces, Render, Fly.io...).
#   docker build -t mus-arena .
#   docker run -p 7860:7860 mus-arena        ->  http://localhost:7860
# Las mesas viven en memoria: un solo proceso. MUS_PUBLICO=1 activa los límites para internet.
FROM python:3.12-slim

RUN useradd --create-home mus
WORKDIR /home/mus/app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[web]"

COPY bots ./bots
COPY docs/reglas.md docs/clasificacion.json ./docs/
RUN mkdir partidas && chown -R mus:mus /home/mus/app
USER mus

ENV MUS_PUBLICO=1 PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "mus-web --red --no-abrir --puerto ${PORT}"]
