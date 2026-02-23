import sqlite3
import os

# Define o caminho do arquivo do banco de dados (vai ficar na pasta 'data/')
# Isso garante que funcione independente da pasta onde você rodar o script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'masterfy.db')

def iniciar_banco():
    # 1. Garante que a pasta 'data' existe (cria se não existir)
    os.makedirs(DATA_DIR, exist_ok=True)

    # 2. Conecta ao SQLite (se o arquivo masterfy.db não existir, ele é criado aqui)
    conexao = sqlite3.connect(DB_PATH)
    cursor = conexao.cursor()

    # 3. Cria a tabela de Ativos
    # O comando "IF NOT EXISTS" é a mágica que impede erros se rodar o script duas vezes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ativos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            indexador TEXT
        )
    ''')

    # 4. Cria a tabela de Transações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ativo_id INTEGER NOT NULL,
            data DATE NOT NULL,
            tipo_transacao TEXT NOT NULL,
            quantidade REAL NOT NULL,
            preco_unitario REAL NOT NULL,
            taxas REAL DEFAULT 0.0,
            FOREIGN KEY (ativo_id) REFERENCES ativos (id)
        )
    ''')

    # 5. Cria a tabela de Histórico de Preços
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_precos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ativo_id INTEGER NOT NULL,
            data DATE NOT NULL,
            preco REAL NOT NULL,
            UNIQUE(ativo_id, data),
            FOREIGN KEY (ativo_id) REFERENCES ativos (id)
        )
    ''')

    # 6. Salva as alterações e fecha a conexão
    conexao.commit()
    conexao.close()
    print(f"✅ Banco de dados configurado com sucesso em: {DB_PATH}")

# Isso faz com que a função só rode se executarmos este arquivo diretamente
if __name__ == '__main__':
    iniciar_banco()