import os
import sqlite3
from datetime import date
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

# Importando os nossos motores
from app.database import iniciar_banco
from app.services.backup_engine import realizar_backup_diario
from app.services.update_prices import atualizar_precos_b3

# --- CONFIGURAÇÕES DO BANCO DE DADOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'masterfy.db')

# Certifica-se de que a pasta data existe
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_db():
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row 
    # OTIMIZAÇÃO: Ativa o modo WAL (Write-Ahead Logging) para concorrência
    conexao.execute("PRAGMA journal_mode=WAL;")
    conexao.execute("PRAGMA synchronous=NORMAL;")
    try:
        yield conexao
    finally:
        conexao.close()

# --- INICIA E ATUALIZA O BANCO ---
iniciar_banco()

def aplicar_patch_banco():
    """Adiciona novas colunas caso o banco seja de uma versão anterior."""
    conexao = sqlite3.connect(DB_PATH)
    cursor = conexao.cursor()
    cursor.execute("PRAGMA table_info(ativos)")
    colunas = [col[1] for col in cursor.fetchall()]
    
    if 'setor' not in colunas:
        cursor.execute("ALTER TABLE ativos ADD COLUMN setor TEXT DEFAULT 'Outros'")
    # Nova coluna para armazenar o preço de fechamento
    if 'preco_atual' not in colunas:
        cursor.execute("ALTER TABLE ativos ADD COLUMN preco_atual REAL DEFAULT 0.0")
        
    # NOVO: Tabela de Proventos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS proventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ativo_id INTEGER,
            data TEXT,
            tipo TEXT,
            valor REAL,
            FOREIGN KEY(ativo_id) REFERENCES ativos(id)
        )
    """)
    conexao.commit()
    conexao.close()

aplicar_patch_banco()

# --- AUTOMAÇÃO (CRON) ---
agendador = BackgroundScheduler()
agendador.add_job(atualizar_precos_b3, trigger='cron', day_of_week='mon-fri', hour=18, minute=0)
agendador.add_job(realizar_backup_diario, trigger='cron', hour=2, minute=0)
agendador.start()

# --- INICIALIZANDO A API ---
app = FastAPI(title="masterfy API")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, '..', 'templates'))

# --- FILTROS DO JINJA2 ---
def format_moeda(valor):
    return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
templates.env.filters["moeda"] = format_moeda

# --- MODELOS (PYDANTIC) ---
class PosicaoAtivo(BaseModel):
    ativo_id: int
    ticker: str
    nome: str
    tipo: str
    setor: str 
    quantidade_total: float
    preco_medio: float 
    valor_investido: float
    valor_atual: float
    lucro_prejuizo: float
    percentual_carteira: float 

class PortfolioResponse(BaseModel):
    valor_total_investido: float
    valor_total_atual: float
    lucro_prejuizo_total: float
    posicoes: List[PosicaoAtivo]

# --- ROTAS DA API DE DADOS ---
@app.get("/portfolio/", response_model=PortfolioResponse)
def obter_portfolio(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    
    # Busca transações e o preco_atual salvo no banco
    cursor.execute("""
        SELECT a.id, a.ticker, a.nome, a.tipo, a.setor, a.preco_atual,
               t.data, t.tipo_transacao, t.quantidade, t.preco_unitario
        FROM transacoes t
        JOIN ativos a ON t.ativo_id = a.id
    """)
    transacoes = cursor.fetchall()
    
    posicoes = {}
    for t in transacoes:
        ativo_id = t['id']
        if ativo_id not in posicoes:
            posicoes[ativo_id] = {
                "ativo_id": ativo_id, "ticker": t['ticker'], "nome": t['nome'], 
                "tipo": t['tipo'], "setor": t['setor'], "preco_atual_banco": t['preco_atual'],
                "quantidade_total": 0.0, "valor_investido": 0.0, "valor_atual": 0.0
            }
        
        if t['tipo_transacao'] == 'COMPRA':
            posicoes[ativo_id]["quantidade_total"] += t['quantidade']
            posicoes[ativo_id]["valor_investido"] += (t['quantidade'] * t['preco_unitario'])
        elif t['tipo_transacao'] == 'VENDA':
            posicoes[ativo_id]["quantidade_total"] -= t['quantidade']
            posicoes[ativo_id]["valor_investido"] -= (t['quantidade'] * t['preco_unitario'])

    posicoes_intermediarias = []
    total_investido = 0.0
    total_atual = 0.0
    
    for pos in posicoes.values():
        if pos["quantidade_total"] <= 0:
            continue
            
        pos["preco_medio"] = pos["valor_investido"] / pos["quantidade_total"]
        
        # OTIMIZAÇÃO: Lê do banco ao invés de buscar na internet
        preco_hoje = pos["preco_atual_banco"]
        
        # Se for 0.0 (novo ativo), usa o valor investido provisoriamente para a tela não quebrar
        if preco_hoje and preco_hoje > 0:
            pos["valor_atual"] = pos["quantidade_total"] * preco_hoje
        else:
            pos["valor_atual"] = pos["valor_investido"]
            
        pos["lucro_prejuizo"] = pos["valor_atual"] - pos["valor_investido"]
        
        total_investido += pos["valor_investido"]
        total_atual += pos["valor_atual"]
        
        posicoes_intermediarias.append(pos)
        
    posicoes_finais = []
    for pos in posicoes_intermediarias:
        percentual = (pos["valor_atual"] / total_atual * 100) if total_atual > 0 else 0.0
        pos["percentual_carteira"] = round(percentual, 2)
        
        pos["preco_medio"] = round(pos["preco_medio"], 2)
        pos["valor_atual"] = round(pos["valor_atual"], 2)
        pos["valor_investido"] = round(pos["valor_investido"], 2)
        pos["lucro_prejuizo"] = round(pos["lucro_prejuizo"], 2)
        
        # Removemos a chave temporária para o Pydantic não reclamar
        del pos["preco_atual_banco"]
        
        posicoes_finais.append(PosicaoAtivo(**pos))
        
    return PortfolioResponse(
        valor_total_investido=round(total_investido, 2),
        valor_total_atual=round(total_atual, 2),
        lucro_prejuizo_total=round(total_atual - total_investido, 2),
        posicoes=posicoes_finais
    )

# --- ROTAS WEB (FRONTEND) ---
@app.get("/", response_class=HTMLResponse)
def dashboard_web(request: Request, db: sqlite3.Connection = Depends(get_db)):
    portfolio_data = obter_portfolio(db)
    
    cursor = db.cursor()
    cursor.execute("SELECT id, ticker FROM ativos ORDER BY ticker")
    ativos = [dict(row) for row in cursor.fetchall()]
    
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "portfolio": portfolio_data, "ativos": ativos}
    )

@app.post("/web/ativos/")
def registrar_ativo_web(
    ticker: str = Form(...),
    nome: str = Form(...),
    tipo: str = Form(...),
    setor: str = Form("Outros"),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO ativos (ticker, nome, tipo, setor, preco_atual) VALUES (?, ?, ?, ?, 0.0)",
            (ticker.upper(), nome, tipo.upper(), setor)
        )
        db.commit()
    except sqlite3.IntegrityError:
        pass
    return RedirectResponse(url="/", status_code=303)

@app.post("/web/transacoes/")
def registrar_transacao_web(
    ativo_id: int = Form(...),
    data: str = Form(...),
    tipo_transacao: str = Form(...),
    quantidade: float = Form(...),
    preco_unitario: float = Form(...),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO transacoes (ativo_id, data, tipo_transacao, quantidade, preco_unitario) VALUES (?, ?, ?, ?, ?)",
        (ativo_id, data, tipo_transacao.upper(), quantidade, preco_unitario)
    )
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@@app.get("/ativo/{ativo_id}", response_class=HTMLResponse)
def detalhes_ativo(request: Request, ativo_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM ativos WHERE id = ?", (ativo_id,))
    ativo = cursor.fetchone()
    if not ativo:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    
    cursor.execute("SELECT * FROM transacoes WHERE ativo_id = ? ORDER BY data DESC", (ativo_id,))
    transacoes = [dict(linha) for linha in cursor.fetchall()]
    
    # NOVO: Busca os proventos e soma o total
    cursor.execute("SELECT * FROM proventos WHERE ativo_id = ? ORDER BY data DESC", (ativo_id,))
    proventos = [dict(linha) for linha in cursor.fetchall()]
    total_proventos = sum(p['valor'] for p in proventos)
    
    return templates.TemplateResponse(
        "ativo.html", 
        {
            "request": request, "ativo": dict(ativo), 
            "transacoes": transacoes, "proventos": proventos, 
            "total_proventos": total_proventos
        }
    )

@app.post("/web/transacoes/{transacao_id}/deletar")
def deletar_transacao_web(
    transacao_id: int, 
    ativo_id: int = Form(...), 
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("DELETE FROM transacoes WHERE id = ?", (transacao_id,))
    db.commit()
    return RedirectResponse(url=f"/ativo/{ativo_id}", status_code=303)

@app.post("/web/transacoes/{transacao_id}/editar")
def editar_transacao_web(
    transacao_id: int,
    ativo_id: int = Form(...),
    data: str = Form(...),
    tipo_transacao: str = Form(...),
    quantidade: float = Form(...),
    preco_unitario: float = Form(...),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute(
        "UPDATE transacoes SET data = ?, tipo_transacao = ?, quantidade = ?, preco_unitario = ? WHERE id = ?",
        (data, tipo_transacao, quantidade, preco_unitario, transacao_id)
    )
    db.commit()
    return RedirectResponse(url=f"/ativo/{ativo_id}", status_code=303)
    
@app.post("/web/ativos/{ativo_id}/editar")
def editar_ativo_web(
    ativo_id: int,
    setor: str = Form(...),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("UPDATE ativos SET setor = ? WHERE id = ?", (setor, ativo_id))
    db.commit()
    return RedirectResponse(url=f"/ativo/{ativo_id}", status_code=303)

@app.get("/backup/download")
def baixar_backup_manual():
    data_hoje = date.today().strftime('%Y-%m-%d')
    nome_arquivo = f"masterfy_exportacao_{data_hoje}.db"
    if os.path.exists(DB_PATH):
        return FileResponse(path=DB_PATH, media_type='application/octet-stream', filename=nome_arquivo)
    raise HTTPException(status_code=404, detail="Banco de dados não encontrado.")
    
 @app.post("/web/proventos/")
def registrar_provento_web(
    ativo_id: int = Form(...),
    data: str = Form(...),
    tipo: str = Form(...),
    valor: float = Form(...),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO proventos (ativo_id, data, tipo, valor) VALUES (?, ?, ?, ?)",
        (ativo_id, data, tipo, valor)
    )
    db.commit()
    return RedirectResponse(url=f"/ativo/{ativo_id}", status_code=303)

@app.post("/web/proventos/{provento_id}/deletar")
def deletar_provento_web(
    provento_id: int, 
    ativo_id: int = Form(...), 
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("DELETE FROM proventos WHERE id = ?", (provento_id,))
    db.commit()
    return RedirectResponse(url=f"/ativo/{ativo_id}", status_code=303)