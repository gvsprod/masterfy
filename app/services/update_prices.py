import sqlite3
import os
from datetime import date

# --- HACK PARA O PYTHON ACHAR A PASTA 'app' ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, '..', '..')))

from app.services.price_engine import buscar_preco_acao

# --- CONFIGURAÇÃO DO CAMINHO DA BASE DE DADOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Sobe duas pastas (services -> app -> raiz) e entra na pasta data
DB_PATH = os.path.join(BASE_DIR, '..', '..', 'data', 'masterfy.db')

def atualizar_precos_b3():
    """Busca o preço atual de todos os ativos e atualiza a base de dados."""
    print("Iniciando a atualização diária de preços da B3...")
    
    conexao = sqlite3.connect(DB_PATH)
    cursor = conexao.cursor()
    
    # 1. Puxa todos os ativos registados (apenas o ID e o Ticker)
    cursor.execute("SELECT id, ticker FROM ativos")
    ativos = cursor.fetchall()
    
    # 2. Faz o loop para buscar e atualizar o preço de cada um
    for ativo in ativos:
        ativo_id = ativo[0]
        ticker = ativo[1]
        
        try:
            preco_hoje = buscar_preco_acao(ticker)
            
            if preco_hoje and preco_hoje > 0:
                # 3. Guarda o preço na nova coluna "preco_atual"
                cursor.execute(
                    "UPDATE ativos SET preco_atual = ? WHERE id = ?",
                    (preco_hoje, ativo_id)
                )
                print(f"✅ {ticker} atualizado com sucesso: R$ {preco_hoje:.2f}")
            else:
                print(f"⚠️ Aviso: Não foi possível obter o preço para {ticker}.")
                
        except Exception as e:
            print(f"❌ Erro ao processar {ticker}: {e}")
            
    # 4. Grava as alterações e fecha a ligação
    conexao.commit()
    conexao.close()
    print("Atualização concluída com sucesso!")

# Permite rodar o script manualmente para testes
if __name__ == "__main__":
    atualizar_precos_b3()
