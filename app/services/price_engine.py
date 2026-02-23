import yfinance as yf

def buscar_preco_acao(ticker: str) -> float:
    """
    Busca o preço de fechamento mais recente de uma ação na B3.
    O ticker deve ser o padrão da B3 (ex: PETR4, VALE3, KNCR11).
    """
    # O Yahoo Finance exige o sufixo '.SA' para ações brasileiras
    ticker_yf = f"{ticker.upper()}.SA"
    
    try:
        # Cria o objeto do ticker
        ativo = yf.Ticker(ticker_yf)
        
        # Busca o histórico do último dia de negociação ('1d')
        dados = ativo.history(period="1d")
        
        # Verifica se retornou vazio (ticker inválido ou erro na API)
        if dados.empty:
            print(f"⚠️ Aviso: Nenhum dado encontrado para o ticker '{ticker}'. Verifique se ele existe.")
            return None
            
        # Pega o preço da coluna 'Close' (Fechamento) da primeira linha retornada
        preco_atual = dados['Close'].iloc[0]
        
        # Retorna arredondado para 2 casas decimais
        return round(preco_atual, 2)
        
    except Exception as e:
        print(f"❌ Erro ao buscar preço para '{ticker}': {e}")
        return None

# Bloco de teste: só roda se você executar este arquivo diretamente
if __name__ == '__main__':
    print("Iniciando motor de preços...\n")
    
    # Vamos testar com uma Ação e um FII
    ativos_para_testar = ["PETR4", "KNCR11", "TICKER_FALSO"]
    
    for ativo in ativos_para_testar:
        preco = buscar_preco_acao(ativo)
        if preco is not None:
            print(f"✅ {ativo}: R$ {preco}")
        else:
            print(f"❌ {ativo}: Falha na busca.")
