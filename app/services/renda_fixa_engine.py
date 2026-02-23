import requests
from datetime import datetime

def obter_historico_cdi(data_inicio: datetime, data_fim: datetime):
    """
    Busca o histórico da taxa CDI diária na API do Banco Central (SGS).
    Série 12: Taxa de juros - CDI (diária).
    """
    inicio_str = data_inicio.strftime('%d/%m/%Y')
    fim_str = data_fim.strftime('%d/%m/%Y')
    
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={inicio_str}&dataFinal={fim_str}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Erro na API do BCB: Código {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Erro de conexão com o BCB: {e}")
        return []

def calcular_evolucao_cdb_pos(valor_inicial: float, percentual_cdi: float, data_compra: str):
    """
    Calcula o valor atualizado de um investimento pós-fixado atrelado ao CDI.
    Ex: percentual_cdi = 1.10 (para 110% do CDI).
    """
    data_inicio = datetime.strptime(data_compra, '%Y-%m-%d')
    data_hoje = datetime.now()
    
    dados_cdi = obter_historico_cdi(data_inicio, data_hoje)
    valor_atual = valor_inicial
    
    for dia in dados_cdi:
        # A Série 12 já retorna a taxa em % ao dia. Ex: "0.040168"
        taxa_diaria_percentual = float(dia['valor'])
        
        # 1. Converte de porcentagem para decimal
        taxa_diaria_decimal = taxa_diaria_percentual / 100
        
        # 2. Aplica o multiplicador do seu CDB (ex: 110% = 1.10)
        rendimento_diario = taxa_diaria_decimal * percentual_cdi
        
        # 3. Acumula no saldo
        valor_atual *= (1 + rendimento_diario)
        
    return round(valor_atual, 2)

# --- BLOCO DE TESTE ---
if __name__ == '__main__':
    print("Iniciando Motor de Renda Fixa...\n")
    
    valor_investido = 1000.00
    taxa_contratada = 1.10 
    data_aplicacao = '2023-01-01'
    
    print(f"💰 Simulando CDB de {taxa_contratada * 100}% do CDI")
    print(f"Data da aplicação: {data_aplicacao} | Valor inicial: R$ {valor_investido:.2f}")
    
    valor_hoje = calcular_evolucao_cdb_pos(valor_investido, taxa_contratada, data_aplicacao)
    
    if valor_hoje:
        lucro = valor_hoje - valor_investido
        print(f"\n✅ Valor Atualizado: R$ {valor_hoje:.2f}")
        print(f"📈 Lucro no período: R$ {lucro:.2f}")
