# Usa uma versão oficial e leve do Python
FROM python:3.11-slim

# Define a pasta de trabalho dentro do container
WORKDIR /masterfy

# Copia o arquivo de dependências primeiro (otimiza o tempo de build)
COPY requirements.txt .

# Instala as bibliotecas
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o resto do seu código (app, templates, etc) para o container
COPY . .

# Expõe a porta que o FastAPI usa
EXPOSE 8000

# O comando que o container vai rodar quando ligar
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]