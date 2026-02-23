from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import sqlite3
import os

# --- CONFIGURAÇÕES DO BANCO DE DADOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'data', 'masterfy.db')

def get_db():
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row 
    try:
        yield conexao
    finally:
        conexao.close()

# --- MODELOS DE DADOS (PYDANTIC) ---
class AtivoCreate(BaseModel):
    ticker: str
    nome: str
    tipo: str
    indexador: Optional[str] = None

class AtivoResponse(AtivoCreate):
    id: int

# Novos modelos para as Transações
class TransacaoCreate(BaseModel):
    ativo_id: int
    data: date
    tipo_transacao: str # 'COMPRA' ou 'VENDA'
    quantidade: float
    preco_unitario: float
    taxas: float = 0.0

class TransacaoResponse(TransacaoCreate):
    id: int

# --- INICIALIZANDO A API ---
app = FastAPI(title="Masterfy API", description="API para rastreamento de investimentos", version="0.1")

# --- ROTAS DE ATIVOS ---
@app.post("/ativos/", response_model=AtivoResponse)
def criar_ativo(ativo: AtivoCreate, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO ativos (ticker, nome, tipo, indexador) VALUES (?, ?, ?, ?)",
            (ativo.ticker.upper(), ativo.nome, ativo.tipo.upper(), ativo.indexador)
        )
        db.commit()
        return {**ativo.model_dump(), "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Este ticker já está cadastrado.")

@app.get("/ativos/", response_model=List[AtivoResponse])
def listar_ativos(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM ativos")
    return [dict(linha) for linha in cursor.fetchall()]

# --- ROTAS DE TRANSAÇÕES ---
@app.post("/transacoes/", response_model=TransacaoResponse)
def registrar_transacao(transacao: TransacaoCreate, db: sqlite3.Connection = Depends(get_db)):
    """Registra uma nova compra ou venda de um ativo."""
    cursor = db.cursor()
    
    # 1. Verifica se o ativo_id realmente existe no banco de dados
    cursor.execute("SELECT id FROM ativos WHERE id = ?", (transacao.ativo_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Ativo não encontrado. Cadastre o ativo primeiro.")

    # 2. Valida se o tipo de transação é válido
    tipo = transacao.tipo_transacao.upper()
    if tipo not in ["COMPRA", "VENDA"]:
        raise HTTPException(status_code=400, detail="O tipo de transação deve ser 'COMPRA' ou 'VENDA'.")

    # 3. Insere a transação no banco
    cursor.execute(
        """
        INSERT INTO transacoes (ativo_id, data, tipo_transacao, quantidade, preco_unitario, taxas)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (transacao.ativo_id, transacao.data, tipo, transacao.quantidade, transacao.preco_unitario, transacao.taxas)
    )
    db.commit()
    
    return {**transacao.model_dump(), "id": cursor.lastrowid}

@app.get("/transacoes/", response_model=List[TransacaoResponse])
def listar_transacoes(db: sqlite3.Connection = Depends(get_db)):
    """Lista todas as transações registradas."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM transacoes ORDER BY data DESC")
    return [dict(linha) for linha in cursor.fetchall()]