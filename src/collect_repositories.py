#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Coleta e Classificação de Repositórios GitHub

Este script busca repositórios no GitHub, aplica filtros e classifica em:
- RAPID: Releases com intervalo de 5-35 dias
- SLOW: Releases com intervalo > 60 dias
- NOT_ELIGIBLE: Não atende aos critérios

SAÍDA:
- all_repositories.csv: Todos os repositórios analisados com classificação
- rapid_release_repos.csv: Apenas repositórios RAPID
- slow_release_repos.csv: Apenas repositórios SLOW
"""

import os
import sys
import time
import csv
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple

import requests
from dotenv import load_dotenv

# Configurar encoding UTF-8 para evitar problemas com emojis no Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Força flush automático em todos os prints
import functools
print = functools.partial(print, flush=True)

# Carrega variáveis de ambiente do diretório pai
from pathlib import Path
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

# Configurações
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_GRAPHQL_URL = 'https://api.github.com/graphql'
GITHUB_REST_URL = 'https://api.github.com'

# Pasta de resultados
RESULTS_DIR = project_root / 'results'
RESULTS_DIR.mkdir(exist_ok=True)

# Critérios de filtragem
MIN_STARS = 50    
MIN_FORKS = 50    
MIN_RELEASES = 19
MIN_CONTRIBUTORS = 19
RAPID_MIN_DAYS = 5
RAPID_MAX_DAYS = 35
SLOW_MIN_DAYS = 60
TARGET_REPOS_PER_TYPE = 100  # Meta: 100 de cada tipo (RAPID e SLOW)
TOTAL_REPOS_TO_SEARCH = 1000  # Buscar até 1000 repos para encontrar 100 de cada tipo 


class GitHubAPI:
    """Cliente para interagir com a API do GitHub (GraphQL e REST)"""
    
    def __init__(self, token: str):
        self.token = token
        self.graphql_url = GITHUB_GRAPHQL_URL
        self.rest_url = GITHUB_REST_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
    
    def _run_query(self, query: str, variables: dict) -> dict:
        """Executa uma query GraphQL"""
        payload = {'query': query, 'variables': variables}
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                response = self.session.post(self.graphql_url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'errors' in result:
                        print(f"❌ Erro na query GraphQL: {result['errors']}")
                        return None
                    return result
                elif response.status_code == 403:
                    print(f"⚠️ Rate limit atingido, aguardando 60s...")
                    time.sleep(60)
                elif response.status_code in [502, 503, 504]:
                    wait_time = (attempt + 1) * 10
                    print(f"⚠️ Erro temporário {response.status_code}, aguardando {wait_time}s (tentativa {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ Erro HTTP {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                    
            except requests.Timeout:
                print(f"⚠️ Timeout na requisição (tentativa {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(10)
            except Exception as e:
                print(f"❌ Erro de requisição (tentativa {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        
        print(f"❌ Falha após {max_retries} tentativas")
        return None
    
    def search_repositories(self, query: str, max_results: int = 100) -> List[Dict]:
        """Busca repositórios usando a API GraphQL de forma otimizada"""
        search_query = """
        query($queryString: String!, $cursor: String) {
          search(query: $queryString, type: REPOSITORY, first: 50, after: $cursor) {
            repositoryCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              ... on Repository {
                nameWithOwner
                owner {
                  login
                }
                name
                stargazerCount
                forkCount
                primaryLanguage {
                  name
                }
              }
            }
          }
        }
        """
        
        repositories = []
        cursor = None
        page = 1
        
        print(f"Buscando até {max_results} repositórios mais populares...")
        
        while len(repositories) < max_results:
            print(f"📄 Página {page} - Coletados: {len(repositories)}/{max_results}", end='\r')
            variables = {'queryString': query, 'cursor': cursor}
            result = self._run_query(search_query, variables)
            
            if not result or 'data' not in result:
                print(f"\n⚠️ Falha na requisição, parando na página {page}")
                break
            
            nodes = result['data']['search']['nodes']
            repositories.extend(nodes)
            
            page_info = result['data']['search']['pageInfo']
            if not page_info['hasNextPage'] or len(repositories) >= max_results:
                break
            
            cursor = page_info['endCursor']
            page += 1
            time.sleep(2)  # Delay maior entre páginas
        
        print(f"\n✅ Total coletado: {len(repositories)} repositórios")
        return repositories[:max_results]
    
    def get_repo_details(self, owner: str, name: str) -> Optional[Dict]:
        """Obtém detalhes essenciais de um repositório (otimizado)"""
        query = """
        query($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) {
            nameWithOwner
            owner {
              login
            }
            name
            stargazerCount
            forkCount
            primaryLanguage {
              name
            }
            releases {
              totalCount
            }
          }
        }
        """
        
        variables = {'owner': owner, 'name': name}
        result = self._run_query(query, variables)
        
        if result and 'data' in result and result['data']['repository']:
            return result['data']['repository']
        return None
    
    def get_all_releases(self, owner: str, name: str) -> List[Dict]:
        """Obtém todas as releases de um repositório com paginação"""
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            releases(first: 100, orderBy: {field: CREATED_AT, direction: DESC}, after: $cursor) {
              totalCount
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                tagName
                name
                createdAt
                publishedAt
              }
            }
          }
        }
        """
        
        all_releases = []
        cursor = None
        
        while True:
            variables = {'owner': owner, 'name': name, 'cursor': cursor}
            result = self._run_query(query, variables)
            
            if not result or 'data' not in result or not result['data']['repository']:
                break
            
            releases_data = result['data']['repository']['releases']
            releases = releases_data['nodes']
            all_releases.extend(releases)
            
            print(f"Buscadas {len(releases)} releases (total acumulado: {len(all_releases)})")
            
            if not releases_data['pageInfo']['hasNextPage']:
                break
            
            cursor = releases_data['pageInfo']['endCursor']
            time.sleep(0.5)
        
        return all_releases
    
    def get_contributor_count(self, owner: str, name: str) -> int:
        """Obtém o número de contribuidores usando a API REST"""
        url = f"{self.rest_url}/repos/{owner}/{name}/contributors"
        params = {'per_page': 1, 'anon': 'true'}
        
        try:
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                link_header = response.headers.get('Link', '')
                if 'rel="last"' in link_header:
                    last_page = link_header.split('page=')[-1].split('>')[0].split('&')[0]
                    return int(last_page) * 100
                return len(response.json()) * 100
            return 0
        except Exception as e:
            print(f"Erro ao obter contribuidores: {e}")
            return 0


def calculate_release_interval(releases: List[Dict]) -> Tuple[float, str]:
    """
    Calcula o intervalo médio entre releases
    Retorna: (intervalo_medio_dias, tipo_release)
    """
    if len(releases) < 2:
        return 0, "NOT_ELIGIBLE"
    
    # Ordena releases por data
    sorted_releases = sorted(releases, key=lambda x: x['createdAt'])
    
    # Calcula intervalos
    intervals = []
    for i in range(len(sorted_releases) - 1):
        date1 = datetime.fromisoformat(sorted_releases[i]['createdAt'].replace('Z', '+00:00'))
        date2 = datetime.fromisoformat(sorted_releases[i + 1]['createdAt'].replace('Z', '+00:00'))
        interval_days = (date2 - date1).days
        if interval_days > 0:
            intervals.append(interval_days)
    
    if not intervals:
        return 0, "NOT_ELIGIBLE"
    
    avg_interval = sum(intervals) / len(intervals)
    
    # Classifica o tipo de release
    if RAPID_MIN_DAYS <= avg_interval <= RAPID_MAX_DAYS:
        release_type = "RAPID"
    elif avg_interval > SLOW_MIN_DAYS:
        release_type = "SLOW"
    else:
        release_type = "NOT_ELIGIBLE"
    
    return round(avg_interval, 1), release_type


def analyze_repository(github_api: GitHubAPI, owner: str, name: str) -> Optional[Dict]:
    """
    Analisa um repositório e retorna seus dados classificados
    """
    print(f"\n=== Processando repositório {owner}/{name} ===")
    
    # Obter detalhes
    repo_details = github_api.get_repo_details(owner, name)
    if not repo_details:
        print(f"❌ Falha ao obter detalhes do repositório")
        return None
    
    stars = repo_details['stargazerCount']
    forks = repo_details['forkCount']
    language = repo_details['primaryLanguage']['name'] if repo_details['primaryLanguage'] else 'Unknown'
    
    # Filtro 1: Stars
    print(f"✅ Repositório {owner}/{name} passou filtro de stars ({stars} stars)")
    
    # Filtro 2: Releases
    release_count = repo_details['releases']['totalCount']
    if release_count <= MIN_RELEASES:
        print(f"❌ Repositório {owner}/{name} não atende critério de releases (tem {release_count}, precisa > {MIN_RELEASES})")
        return {
            'owner': owner,
            'name': name,
            'stars': stars,
            'forks': forks,
            'language': language,
            'release_count': release_count,
            'contributors': 0,
            'avg_release_interval': 0,
            'release_type': 'NOT_ELIGIBLE',
            'reason': f'Poucas releases ({release_count})'
        }
    
    print(f"✅ Repositório {owner}/{name} passou filtro de releases ({release_count} releases)")
    
    # Filtro 3: Contribuidores
    print(f"Obtendo número de contribuidores...")
    contributor_count = github_api.get_contributor_count(owner, name)
    print(f"Contribuidores: {contributor_count}")
    
    if contributor_count <= MIN_CONTRIBUTORS:
        print(f"❌ Repositório {owner}/{name} não atende critério de contribuidores (tem {contributor_count}, precisa > {MIN_CONTRIBUTORS})")
        return {
            'owner': owner,
            'name': name,
            'stars': stars,
            'forks': forks,
            'language': language,
            'release_count': release_count,
            'contributors': contributor_count,
            'avg_release_interval': 0,
            'release_type': 'NOT_ELIGIBLE',
            'reason': f'Poucos contribuidores ({contributor_count})'
        }
    
    print(f"✅ Repositório {owner}/{name} passou filtro de contribuidores ({contributor_count} contribuidores)")
    
    # Obter todas as releases para análise
    all_releases = github_api.get_all_releases(owner, name)
    
    # Filtro 4: Intervalo de releases
    avg_interval, release_type = calculate_release_interval(all_releases)
    
    if release_type == "NOT_ELIGIBLE":
        print(f"❌ Repositório {owner}/{name} não atende critério de intervalo de releases")
        print(f"   Intervalo médio: {avg_interval} dias (precisa ser {RAPID_MIN_DAYS}-{RAPID_MAX_DAYS} para Rapid OU >{SLOW_MIN_DAYS} para Slow)")
        return {
            'owner': owner,
            'name': name,
            'stars': stars,
            'forks': forks,
            'language': language,
            'release_count': release_count,
            'contributors': contributor_count,
            'avg_release_interval': avg_interval,
            'release_type': 'NOT_ELIGIBLE',
            'reason': f'Intervalo inadequado ({avg_interval} dias)'
        }
    
    print(f"✅ Repositório {owner}/{name} classificado como '{release_type}' (intervalo: {avg_interval} dias)")
    
    return {
        'owner': owner,
        'name': name,
        'stars': stars,
        'forks': forks,
        'language': language,
        'release_count': release_count,
        'contributors': contributor_count,
        'avg_release_interval': avg_interval,
        'release_type': release_type,
        'reason': f'{avg_interval} dias entre releases'
    }


def save_to_csv(repositories: List[Dict], filename: str):
    """Salva lista de repositórios em CSV na pasta results/"""
    if not repositories:
        print(f"⚠️ Nenhum repositório para salvar em {filename}")
        return
    
    # Salvar na pasta results
    filepath = RESULTS_DIR / filename
    
    fieldnames = ['owner', 'name', 'stars', 'forks', 'language', 'release_count', 
                  'contributors', 'avg_release_interval', 'release_type', 'reason']
    
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(repositories)
    
    print(f"✅ Salvo {len(repositories)} repositórios em results/{filename}")


def main():
    print("=" * 80)
    print("SCRIPT DE COLETA E CLASSIFICAÇÃO DE REPOSITÓRIOS")
    print("=" * 80)
    print()
    
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN não configurado no arquivo .env")
        return
    
    print("Inicializando GitHub API...")
    github_api = GitHubAPI(GITHUB_TOKEN)
    
    print()
    print("=" * 80)
    print("CRITÉRIOS DE FILTRAGEM:")
    print(f"  • Stars: > {MIN_STARS} (ordenado dos MAIS POPULARES para os menos)")
    print(f"  • Forks: > {MIN_FORKS}")
    print(f"  • Releases: > {MIN_RELEASES}")
    print(f"  • Contribuidores: > {MIN_CONTRIBUTORS}")
    print(f"  • Intervalo RAPID: {RAPID_MIN_DAYS}-{RAPID_MAX_DAYS} dias")
    print(f"  • Intervalo SLOW: > {SLOW_MIN_DAYS} dias")
    print(f"  • Meta: {TARGET_REPOS_PER_TYPE} repositórios de CADA tipo (RAPID e SLOW)")
    print(f"  • Buscar até: {TOTAL_REPOS_TO_SEARCH} repositórios para atingir a meta")
    print("=" * 80)
    print()
    
    # Buscar repositórios ordenados por popularidade (stars)
    query = f"stars:>{MIN_STARS} forks:>{MIN_FORKS} sort:stars-desc"
    print(f"🔍 Query GitHub: {query}")
    print(f"📊 Estratégia: Buscar até {TOTAL_REPOS_TO_SEARCH} repositórios MAIS POPULARES")
    print(f"🎯 Objetivo: Encontrar {TARGET_REPOS_PER_TYPE} RAPID + {TARGET_REPOS_PER_TYPE} SLOW")
    print()
    repositories = github_api.search_repositories(query, TOTAL_REPOS_TO_SEARCH)
    print(f"Total de repositórios coletados: {len(repositories)}")
    print()
    
    # Analisar cada repositório
    all_results = []
    rapid_repos = []
    slow_repos = []
    
    for i, repo in enumerate(repositories, 1):
        # Verificar se já atingimos a meta
        if len(rapid_repos) >= TARGET_REPOS_PER_TYPE and len(slow_repos) >= TARGET_REPOS_PER_TYPE:
            print(f"\n🎉 META ATINGIDA! {TARGET_REPOS_PER_TYPE} RAPID + {TARGET_REPOS_PER_TYPE} SLOW")
            print(f"Parando busca no repositório {i}/{len(repositories)}")
            break
        
        print(f"\n[{i}/{len(repositories)}] Processando: {repo['nameWithOwner']}")
        print(f"   Status: RAPID={len(rapid_repos)}/{TARGET_REPOS_PER_TYPE}, SLOW={len(slow_repos)}/{TARGET_REPOS_PER_TYPE}")
        
        owner = repo['owner']['login']
        name = repo['name']
        
        result = analyze_repository(github_api, owner, name)
        
        if result:
            all_results.append(result)
            
            if result['release_type'] == 'RAPID' and len(rapid_repos) < TARGET_REPOS_PER_TYPE:
                rapid_repos.append(result)
                print(f"   ✅ RAPID adicionado! Total: {len(rapid_repos)}/{TARGET_REPOS_PER_TYPE}")
            elif result['release_type'] == 'SLOW' and len(slow_repos) < TARGET_REPOS_PER_TYPE:
                slow_repos.append(result)
                print(f"   ✅ SLOW adicionado! Total: {len(slow_repos)}/{TARGET_REPOS_PER_TYPE}")
        
        # Progresso a cada 10 repos
        if (i % 10 == 0):
            print(f"\n*** PROGRESSO: {i} repositórios processados ***")
            print(f"    RAPID: {len(rapid_repos)} | SLOW: {len(slow_repos)} | Total analisados: {len(all_results)}")
        
        time.sleep(1)  # Rate limiting
    
    # Salvar resultados em CSVs
    print()
    print("=" * 80)
    print("SALVANDO RESULTADOS")
    print("=" * 80)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    save_to_csv(all_results, f"all_repositories_{timestamp}.csv")
    save_to_csv(rapid_repos, f"rapid_release_repos_{timestamp}.csv")
    save_to_csv(slow_repos, f"slow_release_repos_{timestamp}.csv")
    
    # Resumo final
    print()
    print("=" * 80)
    print("RESUMO FINAL")
    print("=" * 80)
    print(f"Total de repositórios analisados: {len(all_results)}")
    print(f"Repositórios RAPID: {len(rapid_repos)}")
    print(f"Repositórios SLOW: {len(slow_repos)}")
    print(f"Repositórios não elegíveis: {len(all_results) - len(rapid_repos) - len(slow_repos)}")
    print()
    print("🎉 Coleta finalizada com sucesso!")


if __name__ == "__main__":
    main()
