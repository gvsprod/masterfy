from fastapi import FastAPI, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import sqlite3
import os

# Importando os nossos motores (A mágica acontece aqui)
from app.database import iniciar_banco
from app.services.price_engine import buscar_preco_acao
from app.services.renda_fixa_engine import calcular_evolucao_cdb_pos

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

class TransacaoCreate(BaseModel):
    ativo_id: int
    data: date
    tipo_transacao: str 
    quantidade: float
    preco_unitario: float
    taxas: float = 0.0

class TransacaoResponse(TransacaoCreate):
    id: int

# Novos Modelos para o Portfólio
class PosicaoAtivo(BaseModel):
    ativo_id: int
    ticker: str
    nome: str
    tipo: str
    quantidade_total: float
    valor_investido: float
    valor_atual: float
    lucro_prejuizo: float

class PortfolioResponse(BaseModel):
    valor_total_investido: float
    valor_total_atual: float
    lucro_prejuizo_total: float
    posicoes: List[PosicaoAtivo]

# 2. Executa a criação do banco de dados antes da API subir
iniciar_banco()

# --- INICIALIZANDO A API ---
app = FastAPI(title="Masterfy API", description="API para rastreamento de investimentos", version="0.1")

# --- CONFIGURAÇÃO DO FRONTEND (JINJA2) ---
# Aponta para a pasta templates que criamos
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, '..', 'templates'))

# Cria um filtro para formatar dinheiro no padrão Brasil (1.000,00)
def format_br(valor: float):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Ensina o Jinja2 a usar esse filtro com o nome 'moeda'
templates.env.filters["moeda"] = format_br

# --- ROTAS DE ATIVOS E TRANSAÇÕES ---
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

@app.post("/transacoes/", response_model=TransacaoResponse)
def registrar_transacao(transacao: TransacaoCreate, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM ativos WHERE id = ?", (transacao.ativo_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Ativo não encontrado.")
    tipo = transacao.tipo_transacao.upper()
    if tipo not in ["COMPRA", "VENDA"]:
        raise HTTPException(status_code=400, detail="O tipo de transação deve ser 'COMPRA' ou 'VENDA'.")
    cursor.execute(
        "INSERT INTO transacoes (ativo_id, data, tipo_transacao, quantidade, preco_unitario, taxas) VALUES (?, ?, ?, ?, ?, ?)",
        (transacao.ativo_id, transacao.data, tipo, transacao.quantidade, transacao.preco_unitario, transacao.taxas)
    )
    db.commit()
    return {**transacao.model_dump(), "id": cursor.lastrowid}

@app.get("/transacoes/", response_model=List[TransacaoResponse])
def listar_transacoes(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM transacoes ORDER BY data DESC")
    return [dict(linha) for linha in cursor.fetchall()]

# --- ROTA DE PORTFÓLIO (A MÁGICA) ---
@app.get("/portfolio/", response_model=PortfolioResponse)
def obter_portfolio(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    
    # 1. Busca todas as transações cruzando com os dados do ativo
    cursor.execute("""
        SELECT a.id, a.ticker, a.nome, a.tipo, a.indexador,
               t.data, t.tipo_transacao, t.quantidade, t.preco_unitario
        FROM transacoes t
        JOIN ativos a ON t.ativo_id = a.id
    """)
    transacoes = cursor.fetchall()
    
    posicoes = {}
    
    # 2. Agrupa as transações por ativo
    for t in transacoes:
        ativo_id = t['id']
        if ativo_id not in posicoes:
            posicoes[ativo_id] = {
                "ativo_id": ativo_id, "ticker": t['ticker'], "nome": t['nome'], "tipo": t['tipo'],
                "quantidade_total": 0.0, "valor_investido": 0.0, "valor_atual": 0.0, "compras_rf": []
            }
        
        # Calcula o saldo e o valor investido
        if t['tipo_transacao'] == 'COMPRA':
            posicoes[ativo_id]["quantidade_total"] += t['quantidade']
            posicoes[ativo_id]["valor_investido"] += (t['quantidade'] * t['preco_unitario'])
            
            # Se for Renda Fixa, guardamos a compra isolada para calcular o juros desde aquela data específica
            if t['tipo'] == 'RENDA_FIXA_POS':
                posicoes[ativo_id]["compras_rf"].append(t)
                
        elif t['tipo_transacao'] == 'VENDA':
            posicoes[ativo_id]["quantidade_total"] -= t['quantidade']
            posicoes[ativo_id]["valor_investido"] -= (t['quantidade'] * t['preco_unitario'])

    # 3. Calcula o valor de mercado HOJE para cada ativo agrupado
    posicoes_finais = []
    total_investido = 0.0
    total_atual = 0.0
    
    for pos in posicoes.values():
        if pos["quantidade_total"] <= 0:
            continue # Ignora ativos que você já vendeu tudo
            
        if pos["tipo"] in ['ACAO', 'FII', 'ETF']:
            # Chama o motor da B3
            preco_hoje = buscar_preco_acao(pos['ticker'])
            if preco_hoje:
                pos["valor_atual"] = pos["quantidade_total"] * preco_hoje
            else:
                pos["valor_atual"] = pos["valor_investido"] # Fallback se falhar a internet
                
        elif pos["tipo"] == 'RENDA_FIXA_POS':
            # Chama o motor do CDI para CADA aporte feito naquele CDB
            valor_atual_rf = 0.0
            for compra in pos["compras_rf"]:
                valor_inicial = compra['quantidade'] * compra['preco_unitario']
                # Nota: Estamos assumindo 100% (1.0) do CDI como padrão. 
                # Futuramente podemos adicionar uma coluna 'taxa' no banco de dados.
                valor_atualizado = calcular_evolucao_cdb_pos(valor_inicial, 1.0, str(compra['data']))
                valor_atual_rf += valor_atualizado
            pos["valor_atual"] = valor_atual_rf
            
        else:
            pos["valor_atual"] = pos["valor_investido"]
            
        pos["lucro_prejuizo"] = round(pos["valor_atual"] - pos["valor_investido"], 2)
        pos["valor_atual"] = round(pos["valor_atual"], 2)
        pos["valor_investido"] = round(pos["valor_investido"], 2)
        
        # Soma para o totalzão da carteira
        total_investido += pos["valor_investido"]
        total_atual += pos["valor_atual"]
        posicoes_finais.append(PosicaoAtivo(**pos))
        
    return PortfolioResponse(
        valor_total_investido=round(total_investido, 2),
        valor_total_atual=round(total_atual, 2),
        lucro_prejuizo_total=round(total_atual - total_investido, 2),
        posicoes=posicoes_finais
    )
  
  # --- ROTA DA INTERFACE WEB (FRONTEND) ---
@app.get("/", response_class=HTMLResponse)
def dashboard_web(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Renderiza a página principal (index.html) com os dados reais do portfólio."""
    
    # Busca os dados do portfólio (que já tínhamos)
    dados_portfolio = obter_portfolio(db)
    
    # NOVO: Busca todos os ativos para popular o formulário de "Nova Transação"
    cursor = db.cursor()
    cursor.execute("SELECT id, ticker, nome FROM ativos ORDER BY ticker")
    lista_ativos = [dict(linha) for linha in cursor.fetchall()]
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "portfolio": dados_portfolio,
            "ativos": lista_ativos  # Enviamos a lista para o HTML
        }
    )
   
@app.post("/web/transacoes/")
def registrar_transacao_web(
    ativo_id: int = Form(...),
    data: str = Form(...),
    tipo_transacao: str = Form(...),
    quantidade: float = Form(...),
    preco_unitario: float = Form(...),
    db: sqlite3.Connection = Depends(get_db)
):
    """Recebe os dados do formulário HTML, salva a transação e recarrega a página."""
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO transacoes (ativo_id, data, tipo_transacao, quantidade, preco_unitario, taxas) VALUES (?, ?, ?, ?, ?, ?)",
        (ativo_id, data, tipo_transacao, quantidade, preco_unitario, 0.0)
    )
    db.commit()
    
    # O código 303 diz ao navegador: "Sucesso! Agora redirecione de volta para a página inicial (GET /)"
    return RedirectResponse(url="/", status_code=303)
  
@app.post("/web/ativos/")
def registrar_ativo_web(
    ticker: str = Form(...),
    nome: str = Form(...),
    tipo: str = Form(...),
    indexador: str = Form(""), # Opcional no HTML, vem como string vazia
    db: sqlite3.Connection = Depends(get_db)
):
    """Recebe os dados do formulário HTML, cadastra o ativo e recarrega a página."""
    cursor = db.cursor()
    
    # Se o indexador vier vazio (ex: Ações não têm indexador), transformamos em None (Nulo)
    idx = indexador if indexador else None
    
    try:
        cursor.execute(
            "INSERT INTO ativos (ticker, nome, tipo, indexador) VALUES (?, ?, ?, ?)",
            (ticker.upper(), nome, tipo.upper(), idx)
        )
        db.commit()
    except sqlite3.IntegrityError:
        # Se o ticker já existir, o banco de dados vai chiar. 
        # Como é uma interface simples, por enquanto apenas ignoramos e recarregamos a página.
        pass
        
    return RedirectResponse(url="/", status_code=303)