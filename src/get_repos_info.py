import requests
import json
import time
from datetime import datetime

# --- CONFIGURAÇÕES E CREDENCIAIS ---
# ATENÇÃO: Use seu Personal Access Token
GITHUB_TOKEN = ""
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# Headers padrão (com Token)
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json",
}

# --- PARÂMETROS DA PESQUISA ---
TARGET_COUNT = 10000
MIN_STARS = 50
MIN_FORKS = 50
# Mantido em 20, valor que você estava usando para evitar 5xx
REPOS_PER_PAGE = 20 
INITIAL_QUERY_STRING = f"stars:>{MIN_STARS} forks:>{MIN_FORKS} sort:stars-desc"

# --- QUERY GRAPHQL ---
GRAPHQL_QUERY = """
query TopRepositories(
  $queryString: String!
  $first: Int!
  $after: String
) {
  rateLimit {
    limit
    cost
    remaining
    resetAt
  }
  search(query: $queryString, type: REPOSITORY, first: $first, after: $after) {
    repositoryCount
    pageInfo {
      endCursor
      hasNextPage
    }
    edges {
      node {
        ... on Repository {
          nameWithOwner
          stargazerCount
          forkCount
          url
          
          # Número total de releases
          releases {
            totalCount
          }
          
          # Detalhes das Releases (Últimas 10)
          releasesDetail: releases(first: 10, orderBy: {field: CREATED_AT, direction: DESC}) {
            nodes {
              name
              createdAt
              publishedAt
              tag {
                name
              }
            }
          }
        }
      }
    }
  }
}
"""

# --- FUNÇÃO DE CHAMADA DA API COM RETRY (Tolerância Máxima a Falhas) ---
def call_graphql_api(query, variables, max_retries=10):
    """
    Chama a API GraphQL com tratamento de Rate Limit (403), erros de Timeout/Servidor (5xx).
    Retorna None apenas se FALHAR APÓS max_retries tentativas, sinalizando para avançar.
    """
    for attempt in range(max_retries):
        try:
            response = requests.post(
                GITHUB_GRAPHQL_URL, 
                headers=HEADERS, 
                json={'query': query, 'variables': variables}
            )

            # 1. Tratar erros de Timeout/Servidor (5xx)
            if response.status_code in [502, 504, 503]:
                # Reduzido o tempo de espera, conforme ajuste anterior
                print(f"ERRO API (5xx - Servidor/Timeout): Tentativa {attempt + 1}. Tentando novamente em 5 segundos...")
                time.sleep(5)
                continue
            
            response.raise_for_status() 
            data = response.json()
            
            if 'errors' in data:
                error_messages = [err.get('message', 'Erro desconhecido') for err in data['errors']]
                
                # Trata RATE LIMIT
                if any('rate limit' in msg.lower() for msg in error_messages):
                     rate_limit = data['data']['rateLimit']
                     reset_timestamp = datetime.strptime(rate_limit['resetAt'], "%Y-%m-%dT%H:%M:%SZ").timestamp()
                     wait_time = reset_timestamp - time.time() + 5 
                     print(f"RATE LIMIT EXCEDIDO: Esperando {max(0, wait_time):.0f} segundos até o reset em {rate_limit['resetAt']}.")
                     time.sleep(max(0, wait_time))
                     continue

                # Outros erros GraphQL
                print(f"ERRO GRAPGHQL: {error_messages}")
                print(f"Erro inesperado, mas não fatal. Tentativa {attempt + 1}. Tentando novamente em 5 segundos...")
                time.sleep(5)
                continue
            
            return data

        except requests.exceptions.RequestException as e:
            print(f"ERRO DE CONEXÃO: {e}. Tentativa {attempt + 1}. Tentando novamente em 10 segundos...")
            time.sleep(10)
            continue
        except json.JSONDecodeError:
            print(f"ERRO DE JSON: Resposta inválida. Tentativa {attempt + 1}. Tentando novamente em 5s...")
            time.sleep(5)
            continue
            
    print(f"ERRO FATAL APÓS 10 TENTATIVAS: A requisição não pôde ser completada.")
    return None

# --- FUNÇÃO PRINCIPAL (Avanço Imediato na Falha) ---
def fetch_top_repositories():
    all_repositories = []
    current_count = 0
    current_cursor = None
    current_query_string = INITIAL_QUERY_STRING
    last_stars = 0
    stagnation_counter = 0
    consecutive_failures = 0 
    
    # Novo: Contador para monitorar o progresso dentro da faixa de 1000
    repos_collected_in_current_query = 0 

    print(f"Iniciando busca por {TARGET_COUNT} repositórios com '{current_query_string}'")

    while current_count < TARGET_COUNT:
        variables = {
            "queryString": current_query_string,
            "first": REPOS_PER_PAGE,
            "after": current_cursor
        }
        
        print(f"\n--- Busca Atual: Cursor={current_cursor}, Query='{current_query_string}' ---")

        data = call_graphql_api(GRAPHQL_QUERY, variables)

        if data is None or 'search' not in data['data']:
            consecutive_failures += 1
            
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"AVANÇO FORÇADO (Limite de {MAX_CONSECUTIVE_FAILURES} Falhas): Erro persistente. MUDANDO FAIXA.")
                
                # --- Lógica de AVANÇO DE QUEBRA DE LIMITE (FORÇADO) ---
                if last_stars > MIN_STARS:
                     current_query_string = f"stars:<{last_stars} forks:>{MIN_FORKS} sort:stars-desc"
                else:
                     # Se falhou sem coletar nada, recomeça com a query inicial
                     current_query_string = INITIAL_QUERY_STRING
                
                current_cursor = None 
                stagnation_counter = 0 
                consecutive_failures = 0
                repos_collected_in_current_query = 0 # Reinicia a contagem
            
            continue 
        
        # --- SE A REQUISIÇÃO FOR BEM-SUCEDIDA ---
        consecutive_failures = 0
        
        search_data = data['data']['search']
        page_info = search_data['pageInfo']
        new_cursor = page_info['endCursor']
        has_next_page = page_info['hasNextPage']
        
        repo_nodes = [edge['node'] for edge in search_data['edges'] if edge['node']]
        
        # Processamento e atualização das estrelas
        for repo in repo_nodes:
            if current_count >= TARGET_COUNT:
                break
            
            releases_data = repo.get('releasesDetail', {}).get('nodes', [])
            
            repo_data = {
                "nameWithOwner": repo.get('nameWithOwner'),
                "url": repo.get('url'),
                "stargazerCount": repo.get('stargazerCount'),
                "forkCount": repo.get('forkCount'),
                
                "releaseCount": repo.get('releases', {}).get('totalCount', 0),
                "releases": [
                    {
                        "name": r.get('name'),
                        "tag": r.get('tag', {}).get('name') if r.get('tag') else None, 
                        "createdAt": r.get('createdAt'),
                        "publishedAt": r.get('publishedAt')
                    }
                    for r in releases_data if r is not None 
                ]
            }
            all_repositories.append(repo_data)
            current_count += 1
            last_stars = repo_data['stargazerCount']
            repos_collected_in_current_query += 1 # Conta na faixa de 1000
            
        print(f"Página processada. Repositórios coletados: {len(repo_nodes)}. Total acumulado: {current_count}/{TARGET_COUNT}. Últimas estrelas: {last_stars}")

        if not has_next_page or current_count >= TARGET_COUNT:
            print("Fim da paginação ou meta atingida.")
            break

        # ********** LÓGICA DE QUEBRA DE LIMITE DE 1000 REFORÇADA **********
        
        # Se coletamos 1000 repositórios ou mais NA FAIXA ATUAL, ou se o GitHub
        # diz que não há mais páginas (mas o contador é baixo), forçamos a mudança.
        if repos_collected_in_current_query >= 900:
            print("LIMITE DE 1000 ATINGIDO. Forçando mudança de faixa de estrelas.")
            current_query_string = f"stars:<{last_stars} forks:>{MIN_FORKS} sort:stars-desc"
            current_cursor = None 
            repos_collected_in_current_query = 0
            stagnation_counter = 0
        else:
            # Paginação normal
            current_cursor = new_cursor
            stagnation_counter = 0

    # --- SALVAR RESULTADOS EM JSON ---
    filename = f"github_top_repos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    print(f"\nBusca finalizada. Salvando {len(all_repositories)} repositórios em '{filename}'...")
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_repositories, f, ensure_ascii=False, indent=4)
        
    print("Concluído!")

if __name__ == "__main__":
    fetch_top_repositories()