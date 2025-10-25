import json
import os

def ler_arquivo_json(nome_arquivo):
    """
    Lê o conteúdo de um arquivo JSON e retorna o conteúdo como uma variável (geralmente um dicionário ou lista).
    # ... (a função de leitura está correta) ...
    """
    
    # 1. Verificar se o arquivo existe
    if not os.path.exists(nome_arquivo):
        print(f"ERRO: O arquivo '{nome_arquivo}' não foi encontrado.")
        return None
        
    try:
        # 2. Abrir o arquivo no modo de leitura ('r') com encoding UTF-8
        with open(nome_arquivo, 'r', encoding='utf-8') as arquivo:
            
            # 3. Usar json.load() para ler e desserializar o conteúdo
            dados = json.load(arquivo)
            
            print(f"SUCESSO: '{nome_arquivo}' lido com sucesso.")
            return dados
            
    except json.JSONDecodeError:
        print(f"ERRO: O arquivo '{nome_arquivo}' não está em um formato JSON válido.")
        return None
    except Exception as e:
        print(f"ERRO: Ocorreu um erro inesperado ao ler o arquivo: {e}")
        return None

# --- Exemplo de Uso ---

# 1. Defina o nome do arquivo JSON que você deseja ler.
NOME_DO_ARQUIVO = 'github_top_repos_20251025_175033.json' 
NOME_DO_ARQUIVO2 = 'jsonFiltrado.json'

# 2. Chamar a função para ler o arquivo e armazenar o resultado na variável.
conteudo_json = ler_arquivo_json(NOME_DO_ARQUIVO);
jsonFiltrado = []

if conteudo_json is None:
    print("Nenhum dado para iterar.")
else:
    # Preparação dos dados para iteração
    iterable = conteudo_json.get('items', conteudo_json) if isinstance(conteudo_json, dict) else conteudo_json
    
    # --- LOOP PARA FILTRAR OS DADOS ---
    for repo in iterable:
        # Simplificação do acesso aos releases (repositórios salvos no formato lista)
        if isinstance(repo, dict):
            releases_details = repo.get('releases', [])
        else:
            # Caso o objeto não seja um dict (improvável com a saída anterior, mas seguro)
            releases_details = getattr(repo, 'releases', []) 
            
        # Critério de filtragem: pelo menos 19 releases (detalhes)
        if len(releases_details) >= 5:
            jsonFiltrado.append(repo)

    # --- BLOCO DE ESCRITA DEVE SER EXECUTADO APENAS UMA VEZ, FORA DO LOOP! ---

    # Preparar o nome do arquivo de saída
    base, _ = os.path.splitext(NOME_DO_ARQUIVO2)
    output_file = f"{base}_filtered.json" # Ex: jsonFiltrado_filtered.json

    try:
        # Tenta salvar o JSON completo, agora que a filtragem terminou.
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(jsonFiltrado, f, ensure_ascii=False, indent=2)
            
        print(f"\n--- FILTRAGEM CONCLUÍDA ---")
        print(f"Total de Repositórios encontrados: {len(iterable)}")
        print(f"SUCESSO: {len(jsonFiltrado)} repositórios filtrados salvos em '{output_file}'.")
        
    except Exception as e:
        print(f"ERRO: Falha ao salvar arquivo: {e}")