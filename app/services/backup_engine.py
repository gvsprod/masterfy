import os
import sqlite3
from datetime import datetime
import glob

# Define os caminhos das pastas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'masterfy.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

def realizar_backup_diario():
    """Cria uma cópia do banco de dados e mantém apenas os últimos 7 dias."""
    # Cria a pasta de backups se ela não existir
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    # Gera o nome do arquivo com a data e hora atual
    data_atual = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'masterfy_backup_{data_atual}.db')
    
    try:
        # Copia o arquivo usando a API nativa do SQLite
        source = sqlite3.connect(DB_PATH)
        dest = sqlite3.connect(backup_path)
        with source, dest:
            source.backup(dest)
        source.close()
        dest.close()
        print(f"✅ Backup realizado: {backup_path}")
        
        # Limpa backups antigos (mantém apenas os 7 mais recentes)
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, '*.db')))
        if len(backups) > 7:
            for b in backups[:-7]: # Pega todos exceto os 7 últimos
                os.remove(b)
                print(f"🗑️ Backup antigo removido: {b}")
                
    except Exception as e:
        print(f"❌ Erro ao realizar backup: {e}")
