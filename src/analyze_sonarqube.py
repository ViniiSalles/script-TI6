#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Análise SonarQube para Repositórios Filtrados

Este script lê os CSVs gerados pelo collect_repositories.py e executa
análise SonarQube em cada release dos repositórios filtrados.

ENTRADA:
- rapid_release_repos_*.csv: Lista de repositórios RAPID
- slow_release_repos_*.csv: Lista de repositórios SLOW

SAÍDA:
- Banco de dados PostgreSQL com métricas SonarQube por release
- Arquivos JSON/CSV com resumo das análises
"""

import os
import sys
import csv
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import requests
import psycopg2
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
SONAR_HOST = os.getenv('SONAR_HOST', 'http://localhost:9000')
SONAR_TOKEN = os.getenv('SONAR_TOKEN')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'sonar')
DB_USER = os.getenv('DB_USER', 'sonar')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'sonar')
DB_PORT = os.getenv('DB_PORT', '5432')

GITHUB_GRAPHQL_URL = 'https://api.github.com/graphql'
CLONE_DIR = project_root / 'cloned_repos'
RESULTS_DIR = project_root / 'results'


class GitHubAPI:
    """Cliente para interagir com a API do GitHub (GraphQL)"""
    
    def __init__(self, token: str):
        self.token = token
        self.graphql_url = GITHUB_GRAPHQL_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
    
    def _run_query(self, query: str, variables: dict) -> dict:
        """Executa uma query GraphQL"""
        payload = {'query': query, 'variables': variables}
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.session.post(self.graphql_url, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'errors' in result:
                        print(f"❌ Erro na query GraphQL: {result['errors']}")
                        return None
                    return result
                elif response.status_code == 403:
                    print(f"⚠️ Rate limit atingido, aguardando...")
                    time.sleep(60)
                else:
                    print(f"❌ Erro HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"Erro de requisição (tentativa {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        
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
            
            if not releases_data['pageInfo']['hasNextPage']:
                break
            
            cursor = releases_data['pageInfo']['endCursor']
            time.sleep(0.5)
        
        return all_releases


class DatabaseManager:
    """Gerencia conexão e operações com PostgreSQL"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Conecta ao banco de dados"""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
            self.cursor = self.conn.cursor()
            print("✅ Conexão com banco de dados estabelecida")
        except Exception as e:
            print(f"❌ Erro ao conectar ao banco de dados: {e}")
            sys.exit(1)
    
    def create_tables(self):
        """Cria as tabelas necessárias se não existirem"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS research_repositories (
                id SERIAL PRIMARY KEY,
                owner VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                stars INTEGER,
                forks INTEGER,
                language VARCHAR(100),
                release_type VARCHAR(20),
                contributors INTEGER,
                avg_release_interval FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner, name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS research_releases (
                id SERIAL PRIMARY KEY,
                repo_id INTEGER REFERENCES research_repositories(id) ON DELETE CASCADE,
                tag_name VARCHAR(255) NOT NULL,
                release_name VARCHAR(255),
                created_at TIMESTAMP,
                published_at TIMESTAMP,
                UNIQUE(repo_id, tag_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS research_sonarqube_metrics (
                id SERIAL PRIMARY KEY,
                repo_id INTEGER REFERENCES research_repositories(id) ON DELETE CASCADE,
                release_id INTEGER REFERENCES research_releases(id) ON DELETE CASCADE,
                sonar_project_key VARCHAR(255),
                lines_of_code INTEGER,
                complexity INTEGER,
                cognitive_complexity INTEGER,
                bugs INTEGER,
                vulnerabilities INTEGER,
                code_smells INTEGER,
                coverage FLOAT,
                duplicated_lines_density FLOAT,
                security_hotspots INTEGER,
                analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(release_id)
            )
            """
        ]
        
        try:
            for query in queries:
                self.cursor.execute(query)
            self.conn.commit()
            print("✅ Tabelas criadas/verificadas com sucesso")
        except Exception as e:
            print(f"❌ Erro ao criar tabelas: {e}")
            self.conn.rollback()
            sys.exit(1)
    
    def insert_repository(self, repo_data: Dict) -> int:
        """Insere ou atualiza repositório e retorna o ID"""
        query = """
            INSERT INTO research_repositories (owner, name, stars, forks, language, release_type, contributors, avg_release_interval)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner, name) DO UPDATE SET
                stars = EXCLUDED.stars,
                forks = EXCLUDED.forks,
                language = EXCLUDED.language,
                release_type = EXCLUDED.release_type,
                contributors = EXCLUDED.contributors,
                avg_release_interval = EXCLUDED.avg_release_interval
            RETURNING id
        """
        
        try:
            self.cursor.execute(query, (
                repo_data['owner'],
                repo_data['name'],
                repo_data['stars'],
                repo_data['forks'],
                repo_data['language'],
                repo_data['release_type'],
                repo_data['contributors'],
                repo_data['avg_release_interval']
            ))
            repo_id = self.cursor.fetchone()[0]
            self.conn.commit()
            return repo_id
        except Exception as e:
            print(f"❌ Erro ao inserir repositório: {e}")
            self.conn.rollback()
            return None
    
    def insert_release(self, repo_id: int, release_data: Dict) -> int:
        """Insere release e retorna o ID"""
        query = """
            INSERT INTO research_releases (repo_id, tag_name, release_name, created_at, published_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (repo_id, tag_name) DO UPDATE SET
                release_name = EXCLUDED.release_name,
                created_at = EXCLUDED.created_at,
                published_at = EXCLUDED.published_at
            RETURNING id
        """
        
        try:
            created_at = datetime.fromisoformat(release_data['createdAt'].replace('Z', '+00:00'))
            published_at = None
            if release_data.get('publishedAt'):
                published_at = datetime.fromisoformat(release_data['publishedAt'].replace('Z', '+00:00'))
            
            self.cursor.execute(query, (
                repo_id,
                release_data['tagName'],
                release_data.get('name'),
                created_at,
                published_at
            ))
            release_id = self.cursor.fetchone()[0]
            self.conn.commit()
            return release_id
        except Exception as e:
            print(f"❌ Erro ao inserir release: {e}")
            self.conn.rollback()
            return None
    
    def insert_sonar_metrics(self, repo_id: int, release_id: int, project_key: str, metrics: Dict):
        """Insere métricas do SonarQube"""
        query = """
            INSERT INTO research_sonarqube_metrics 
            (repo_id, release_id, sonar_project_key, lines_of_code, complexity, cognitive_complexity,
             bugs, vulnerabilities, code_smells, coverage, duplicated_lines_density, security_hotspots)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (release_id) DO UPDATE SET
                sonar_project_key = EXCLUDED.sonar_project_key,
                lines_of_code = EXCLUDED.lines_of_code,
                complexity = EXCLUDED.complexity,
                cognitive_complexity = EXCLUDED.cognitive_complexity,
                bugs = EXCLUDED.bugs,
                vulnerabilities = EXCLUDED.vulnerabilities,
                code_smells = EXCLUDED.code_smells,
                coverage = EXCLUDED.coverage,
                duplicated_lines_density = EXCLUDED.duplicated_lines_density,
                security_hotspots = EXCLUDED.security_hotspots,
                analysis_date = CURRENT_TIMESTAMP
        """
        
        try:
            self.cursor.execute(query, (
                repo_id,
                release_id,
                project_key,
                metrics.get('lines_of_code', 0),
                metrics.get('complexity', 0),
                metrics.get('cognitive_complexity', 0),
                metrics.get('bugs', 0),
                metrics.get('vulnerabilities', 0),
                metrics.get('code_smells', 0),
                metrics.get('coverage', 0.0),
                metrics.get('duplicated_lines_density', 0.0),
                metrics.get('security_hotspots', 0)
            ))
            self.conn.commit()
        except Exception as e:
            print(f"❌ Erro ao inserir métricas: {e}")
            self.conn.rollback()
    
    def close(self):
        """Fecha conexão com banco"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


class RepositoryProcessor:
    """Processa repositórios, clona e executa análise SonarQube"""
    
    def __init__(self, github_api: GitHubAPI, db: DatabaseManager):
        self.github_api = github_api
        self.db = db
        self.clone_base = CLONE_DIR
        self.clone_base.mkdir(exist_ok=True)
    
    def _clone_repository(self, owner: str, name: str) -> Optional[Path]:
        """Clona repositório"""
        repo_path = self.clone_base / f"{owner}_{name}"
        
        if repo_path.exists():
            print(f"Removendo clone anterior em {repo_path}")
            shutil.rmtree(repo_path)
        
        clone_url = f"https://{GITHUB_TOKEN}@github.com/{owner}/{name}.git"
        
        print(f"Clonando {owner}/{name}...")
        
        try:
            result = subprocess.run(
                ['git', 'clone', clone_url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=1800,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                print(f"✅ Repositório clonado com sucesso")
                
                # Configurações Git
                subprocess.run(['git', 'config', 'http.postBuffer', '524288000'], cwd=repo_path)
                subprocess.run(['git', 'config', 'http.timeout', '1800'], cwd=repo_path)
                
                return repo_path
            else:
                print(f"❌ Erro ao clonar: {result.stderr}")
                return None
                
        except Exception as e:
            print(f"❌ Exceção ao clonar: {e}")
            return None
    
    def _checkout_release(self, repo_path: Path, tag_name: str) -> bool:
        """Faz checkout de uma release específica"""
        try:
            result = subprocess.run(
                ['git', 'checkout', tag_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                return True
            else:
                print(f"⚠️ Erro ao fazer checkout da tag {tag_name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Exceção ao fazer checkout: {e}")
            return False
    
    def _run_sonar_scanner(self, repo_path: Path, project_key: str) -> bool:
        """Executa SonarQube Scanner"""
        try:
            print(f"Executando SonarQube Scanner para projeto {project_key}...")
            
            cmd = [
                'docker', 'run', '--rm',
                '--network', 'host',
                '-v', f'{repo_path.absolute()}:/usr/src',
                'sonarsource/sonar-scanner-cli',
                f'-Dsonar.projectKey={project_key}',
                f'-Dsonar.sources=.',
                f'-Dsonar.host.url={SONAR_HOST}',
                f'-Dsonar.token={SONAR_TOKEN}'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                print(f"✅ Análise SonarQube concluída")
                return True
            else:
                print(f"⚠️ Erro na análise SonarQube")
                print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
                return False
                
        except Exception as e:
            print(f"❌ Exceção ao executar SonarQube: {e}")
            return False
    
    def _get_sonar_metrics(self, project_key: str) -> Optional[Dict]:
        """Obtém métricas do SonarQube"""
        metrics_to_fetch = [
            'ncloc', 'complexity', 'cognitive_complexity', 'bugs', 'vulnerabilities',
            'code_smells', 'coverage', 'duplicated_lines_density', 'security_hotspots'
        ]
        
        url = f"{SONAR_HOST}/api/measures/component"
        params = {
            'component': project_key,
            'metricKeys': ','.join(metrics_to_fetch)
        }
        headers = {'Authorization': f'Bearer {SONAR_TOKEN}'}
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'component' not in data or 'measures' not in data['component']:
                        print(f"⚠️ Projeto ainda não analisado (tentativa {attempt + 1}/{max_retries})")
                        time.sleep(10)
                        continue
                    
                    measures = data['component']['measures']
                    metrics = {}
                    
                    for measure in measures:
                        metric_key = measure['metric']
                        value = measure.get('value', '0')
                        
                        if metric_key == 'ncloc':
                            metrics['lines_of_code'] = int(float(value))
                        elif metric_key == 'complexity':
                            metrics['complexity'] = int(float(value))
                        elif metric_key == 'cognitive_complexity':
                            metrics['cognitive_complexity'] = int(float(value))
                        elif metric_key == 'bugs':
                            metrics['bugs'] = int(float(value))
                        elif metric_key == 'vulnerabilities':
                            metrics['vulnerabilities'] = int(float(value))
                        elif metric_key == 'code_smells':
                            metrics['code_smells'] = int(float(value))
                        elif metric_key == 'coverage':
                            metrics['coverage'] = float(value)
                        elif metric_key == 'duplicated_lines_density':
                            metrics['duplicated_lines_density'] = float(value)
                        elif metric_key == 'security_hotspots':
                            metrics['security_hotspots'] = int(float(value))
                    
                    return metrics
                    
                elif response.status_code == 404:
                    print(f"⚠️ Projeto não encontrado (tentativa {attempt + 1}/{max_retries})")
                    time.sleep(10)
                else:
                    print(f"❌ Erro HTTP {response.status_code}")
                    return None
                    
            except Exception as e:
                print(f"❌ Erro ao obter métricas: {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
        
        return None
    
    def process_repository(self, repo_data: Dict):
        """Processa um repositório completo"""
        owner = repo_data['owner']
        name = repo_data['name']
        
        print()
        print("=" * 80)
        print(f"PROCESSANDO: {owner}/{name} ({repo_data['release_type']})")
        print("=" * 80)
        
        # Inserir repositório no banco
        repo_id = self.db.insert_repository(repo_data)
        if not repo_id:
            print(f"❌ Falha ao inserir repositório no banco")
            return
        
        # Obter releases
        print(f"Obtendo releases...")
        releases = self.github_api.get_all_releases(owner, name)
        print(f"Total de releases: {len(releases)}")
        
        if not releases:
            print(f"⚠️ Nenhuma release encontrada")
            return
        
        # Clonar repositório
        repo_path = self._clone_repository(owner, name)
        if not repo_path:
            return
        
        # Processar cada release
        successful = 0
        failed = 0
        
        for i, release in enumerate(releases, 1):
            tag_name = release['tagName']
            print(f"\n[{i}/{len(releases)}] Processando release {tag_name}")
            
            # Inserir release no banco
            release_id = self.db.insert_release(repo_id, release)
            if not release_id:
                failed += 1
                continue
            
            # Checkout da release
            if not self._checkout_release(repo_path, tag_name):
                failed += 1
                continue
            
            # Executar análise SonarQube
            project_key = f"{owner}_{name}_{tag_name}".replace('.', '_').replace('-', '_')
            
            if not self._run_sonar_scanner(repo_path, project_key):
                failed += 1
                continue
            
            # Aguardar processamento
            time.sleep(15)
            
            # Obter métricas
            metrics = self._get_sonar_metrics(project_key)
            if metrics:
                self.db.insert_sonar_metrics(repo_id, release_id, project_key, metrics)
                print(f"✅ Métricas salvas: {metrics.get('lines_of_code', 0)} LoC, {metrics.get('bugs', 0)} bugs")
                successful += 1
            else:
                print(f"⚠️ Falha ao obter métricas")
                failed += 1
        
        # Limpar clone
        print(f"\nLimpando clone...")
        shutil.rmtree(repo_path)
        
        print()
        print(f"✅ Processamento concluído: {successful} releases com sucesso, {failed} falhas")


def verify_prerequisites():
    """Verifica se as ferramentas necessárias estão disponíveis"""
    print("Verificando pré-requisitos...")
    
    # Git
    try:
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        print(f"✅ Git: {result.stdout.strip()}")
    except:
        print("❌ Git não encontrado")
        return False
    
    # Docker
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        print(f"✅ Docker: {result.stdout.strip()}")
    except:
        print("❌ Docker não encontrado")
        return False
    
    # SonarQube
    try:
        response = requests.get(f"{SONAR_HOST}/api/system/status", timeout=10)
        if response.status_code == 200:
            print(f"✅ SonarQube configurado: {SONAR_HOST}")
        else:
            print(f"⚠️ SonarQube não respondeu corretamente")
            return False
    except:
        print(f"❌ Não foi possível conectar ao SonarQube em {SONAR_HOST}")
        return False
    
    return True


def load_repositories_from_csv(csv_pattern: str) -> List[Dict]:
    """Carrega repositórios dos CSVs mais recentes na pasta results/"""
    import glob
    
    # Buscar na pasta results
    search_pattern = str(RESULTS_DIR / csv_pattern)
    csv_files = glob.glob(search_pattern)
    
    if not csv_files:
        print(f"❌ Nenhum arquivo CSV encontrado com padrão: results/{csv_pattern}")
        return []
    
    # Pegar o mais recente
    latest_csv = max(csv_files, key=os.path.getmtime)
    print(f"📂 Carregando: {Path(latest_csv).relative_to(project_root)}")
    
    repositories = []
    with open(latest_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            repositories.append({
                'owner': row['owner'],
                'name': row['name'],
                'stars': int(row['stars']),
                'forks': int(row['forks']),
                'language': row['language'],
                'release_type': row['release_type'],
                'contributors': int(row['contributors']),
                'avg_release_interval': float(row['avg_release_interval'])
            })
    
    print(f"✅ Carregados {len(repositories)} repositórios")
    return repositories


def main():
    print("=" * 80)
    print("SCRIPT DE ANÁLISE SONARQUBE")
    print("=" * 80)
    print()
    
    # Verificar pré-requisitos
    if not verify_prerequisites():
        print("❌ Pré-requisitos não atendidos")
        return
    
    print()
    
    # Inicializar clientes
    print("Inicializando GitHub API...")
    github_api = GitHubAPI(GITHUB_TOKEN)
    
    print("Conectando ao banco de dados...")
    db = DatabaseManager()
    db.connect()
    db.create_tables()
    
    print()
    
    # Carregar repositórios dos CSVs
    print("=" * 80)
    print("CARREGANDO REPOSITÓRIOS DOS CSVs")
    print("=" * 80)
    
    rapid_repos = load_repositories_from_csv("rapid_release_repos_*.csv")
    slow_repos = load_repositories_from_csv("slow_release_repos_*.csv")
    
    all_repos = rapid_repos + slow_repos
    
    if not all_repos:
        print("❌ Nenhum repositório para processar")
        return
    
    print(f"\nTotal de repositórios a processar: {len(all_repos)}")
    print(f"  • RAPID: {len(rapid_repos)}")
    print(f"  • SLOW: {len(slow_repos)}")
    print()
    
    # Processar repositórios
    processor = RepositoryProcessor(github_api, db)
    
    for i, repo in enumerate(all_repos, 1):
        print(f"\n{'='*80}")
        print(f"REPOSITÓRIO {i}/{len(all_repos)}")
        print(f"{'='*80}")
        
        try:
            processor.process_repository(repo)
        except KeyboardInterrupt:
            print("\n⚠️ Processo interrompido pelo usuário")
            break
        except Exception as e:
            print(f"❌ Erro ao processar {repo['owner']}/{repo['name']}: {e}")
            continue
    
    # Fechar conexões
    db.close()
    
    print()
    print("=" * 80)
    print("🎉 ANÁLISE FINALIZADA")
    print("=" * 80)


if __name__ == "__main__":
    main()
