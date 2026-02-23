import sqlite3
import os
from datetime import date
from price_engine import buscar_preco_acao

# --- CONFIGURAÇÕES DO BANCO DE DADOS ---
# Como estamos dentro da pasta 'services', precisamos subir dois níveis ('..', '..') para chegar na raiz
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', '..', 'data', 'masterfy.db')

def atualizar_precos_b3():
    hoje = date.today()
    print(f"[{hoje}] Iniciando atualização de preços da B3...")
    
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()
    
    # Busca APENAS ativos de renda variável. 
    # Renda Fixa terá uma lógica matemática separada no futuro.
    cursor.execute("SELECT id, ticker FROM ativos WHERE tipo IN ('ACAO', 'FII', 'ETF')")
    ativos = cursor.fetchall()
    
    if not ativos:
        print("Nenhum ativo de renda variável cadastrado para atualizar.")
        conexao.close()
        return

    for ativo in ativos:
        ativo_id = ativo['id']
        ticker = ativo['ticker']
        
        print(f"Buscando cotação para {ticker}...")
        preco_atual = buscar_preco_acao(ticker)
        
        if preco_atual is not None:
            # O "ON CONFLICT" é a mágica do SQLite: 
            # Se já existir um preço salvo para este ativo na data de HOJE, 
            # ele apenas atualiza o valor, evitando dados duplicados.
            cursor.execute('''
                INSERT INTO historico_precos (ativo_id, data, preco)
                VALUES (?, ?, ?)
                ON CONFLICT(ativo_id, data) DO UPDATE SET preco=excluded.preco
            ''', (ativo_id, hoje, preco_atual))
            
            print(f"✅ {ticker} salvo: R$ {preco_atual}")
        else:
            print(f"❌ Falha ao buscar preço para {ticker}.")
            
    # Salva todas as inserções no banco
    conexao.commit()
    conexao.close()
    print("\n🏁 Atualização de preços concluída com sucesso!")

if __name__ == '__main__':
    atualizar_precos_b3()
