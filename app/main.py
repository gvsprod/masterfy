from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import os

# --- CONFIGURAÇÕES DO BANCO DE DADOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'data', 'masterfy.db')

def get_db():
    """Cria uma conexão com o banco de dados para cada requisição e fecha depois."""
    conexao = sqlite3.connect(DB_PATH)
    # Isso permite acessar as colunas pelo nome (ex: linha['ticker']) em vez de índice (linha[0])
    conexao.row_factory = sqlite3.Row 
    try:
        yield conexao
    finally:
        conexao.close()

# --- MODELOS DE DADOS (PYDANTIC) ---
# Estes modelos validam os dados que entram na API. 
# Se você esquecer de mandar o "nome" do ativo, o FastAPI bloqueia e avisa do erro.
class AtivoCreate(BaseModel):
    ticker: str
    nome: str
    tipo: str # ACAO, FII, RENDA_FIXA_POS, etc.
    indexador: Optional[str] = None # Pode ser nulo/vazio para ações

class AtivoResponse(AtivoCreate):
    id: int

# --- INICIALIZANDO A API ---
app = FastAPI(title="Masterfy API", description="API para rastreamento de investimentos", version="0.1")

# --- ROTAS (ENDPOINTS) ---

@app.post("/ativos/", response_model=AtivoResponse)
def criar_ativo(ativo: AtivoCreate, db: sqlite3.Connection = Depends(get_db)):
    """Cadastra um novo ativo no banco de dados."""
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO ativos (ticker, nome, tipo, indexador) VALUES (?, ?, ?, ?)",
            (ativo.ticker.upper(), ativo.nome, ativo.tipo.upper(), ativo.indexador)
        )
        db.commit()
        ativo_id = cursor.lastrowid
        
        # Retorna o ativo criado com seu novo ID
        return {**ativo.model_dump(), "id": ativo_id}
    except sqlite3.IntegrityError:
        # Captura o erro se tentarmos cadastrar um ticker que já existe (lembra do UNIQUE que colocamos?)
        raise HTTPException(status_code=400, detail="Este ticker já está cadastrado.")

@app.get("/ativos/", response_model=List[AtivoResponse])
def listar_ativos(db: sqlite3.Connection = Depends(get_db)):
    """Retorna todos os ativos cadastrados."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM ativos")
    linhas = cursor.fetchall()
    
    # Converte as linhas do SQLite para dicionários Python
    return [dict(linha) for linha in linhas]