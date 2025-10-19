#!/usr/bin/env python3
"""
Script de Automação de Pesquisa de Repositórios GitHub com Análise SonarQube

DESCRIÇÃO:
Este script automatiza a pesquisa comparativa entre projetos de software open-source
com Rapid Release Cycles (RRCs) e Slow Releases. Coleta dados do GitHub via API GraphQL,
filtra repositórios, executa análises de qualidade de código com SonarQube e
persiste todas as métricas em um banco de dados PostgreSQL.

PRÉ-REQUISITOS:
- Docker e Docker Compose instalados e em execução
- Python 3.7+ com pacotes: requests, psycopg2-binary, python-dotenv
- Git instalado no sistema
- Imagem Docker do SonarScanner será baixada automaticamente (sonarsource/sonar-scanner-cli)

CONFIGURAÇÃO DE VARIÁVEIS DE AMBIENTE:
Configure o arquivo .env com as seguintes variáveis:
- GITHUB_TOKEN: Token de acesso pessoal do GitHub (OBRIGATÓRIO)
- SONAR_HOST: URL do servidor SonarQube (ex: http://localhost:9000) - OPCIONAL
- SONAR_TOKEN: Token de autenticação do SonarQube - OPCIONAL
- DB_HOST: Host do banco PostgreSQL (ex: localhost)
- DB_NAME: Nome do banco de dados (ex: sonar)
- DB_USER: Usuário do banco de dados
- DB_PASSWORD: Senha do banco de dados
- DB_PORT: Porta do banco de dados (padrão: 5432)

EXECUÇÃO:
1. Execute docker-compose up -d para iniciar SonarQube e PostgreSQL
2. Configure o SonarQube em http://localhost:9000 (admin/admin)
3. Execute: python3 research_automation_script.py

CONSIDERAÇÕES:
- O script respeita os limites de rate do GitHub (5000 requests/hora)
- A métrica de churn de PRs é um placeholder inicial
- Diretórios temporários são limpos automaticamente
- Análise completa pode levar várias horas dependendo do número de repositórios
"""

import os
import sys
import time
import json
import stat
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple, Any
from pathlib import Path

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()


class GitHubAPI:
    """Classe para interação com as APIs GraphQL e REST do GitHub"""
    
    def __init__(self, token: str):
        self.token = token
        self.graphql_url = "https://api.github.com/graphql"
        self.rest_base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Trata rate limiting das APIs do GitHub"""
        if response.status_code == 403:
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '0')
            if rate_limit_remaining == '0':
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                sleep_time = max(60, reset_time - int(time.time()) + 10)
                print(f"Rate limit atingido. Aguardando {sleep_time} segundos...")
                time.sleep(sleep_time)
                return
        
        if response.status_code != 200:
            response.raise_for_status()
    
    def _run_query(self, query: str, variables: dict = None) -> dict:
        """Executa requisições GraphQL"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.post(self.graphql_url, json=payload)
                self._handle_rate_limit(response)
                
                data = response.json()
                if "errors" in data:
                    print(f"Erro GraphQL: {data['errors']}")
                    if attempt == max_retries - 1:
                        raise Exception(f"GraphQL errors: {data['errors']}")
                    time.sleep(2 ** attempt)
                    continue
                
                return data
                
            except requests.exceptions.RequestException as e:
                print(f"Erro de requisição (tentativa {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        
        return {}
    
    def _run_rest_query(self, url: str, params: dict = None) -> dict:
        """Executa requisições REST"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params)
                self._handle_rate_limit(response)
                return response.json()
                
            except requests.exceptions.RequestException as e:
                print(f"Erro de requisição REST (tentativa {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        
        return {}
    
    def search_repositories(self, search_query: str, num_repos: int = 100) -> List[dict]:
        """Busca repositórios usando a API REST com paginação"""
        repositories = []
        per_page = min(100, num_repos)  # API GitHub limita a 100 por página
        pages_needed = (num_repos + per_page - 1) // per_page
        
        for page in range(1, pages_needed + 1):
            remaining_repos = num_repos - len(repositories)
            if remaining_repos <= 0:
                break
                
            current_per_page = min(per_page, remaining_repos)
            
            params = {
                "q": search_query,
                "sort": "stars",
                "order": "desc",
                "per_page": current_per_page,
                "page": page
            }
            
            print(f"Buscando repositórios - Página {page}/{pages_needed}")
            url = f"{self.rest_base_url}/search/repositories"
            
            try:
                data = self._run_rest_query(url, params)
                
                if "items" in data:
                    repositories.extend(data["items"])
                    print(f"Encontrados {len(data['items'])} repositórios nesta página")
                else:
                    print("Nenhum repositório encontrado nesta página")
                    break
                
                # Respeita rate limiting
                time.sleep(1)
                
            except Exception as e:
                print(f"Erro ao buscar página {page}: {e}")
                break
        
        print(f"Total de repositórios encontrados: {len(repositories)}")
        return repositories
    
    def get_repo_details(self, owner: str, name: str) -> dict:
        """Obtém detalhes específicos de um repositório via GraphQL"""
        query = """
        query GetRepoDetails($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) {
            name
            owner {
              login
            }
            stargazerCount
            forkCount
            primaryLanguage {
              name
            }
            releases(first: 100, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                createdAt
              }
              totalCount
            }
            pullRequests(first: 100, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                number
                merged
                createdAt
                mergedAt
                commits {
                  totalCount
                }
                comments {
                  totalCount
                }
              }
              totalCount
            }
            issues(first: 100, states: [OPEN, CLOSED], orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                number
                createdAt
                closedAt
                timelineItems(first: 100, itemTypes: [REOPENED_EVENT]) {
                  totalCount
                }
              }
              totalCount
            }
            issuesOpen: issues(states: [OPEN]) {
              totalCount
            }
            issuesClosed: issues(states: [CLOSED]) {
              totalCount
            }
          }
        }
        """
        
        variables = {"owner": owner, "name": name}
        
        try:
            result = self._run_query(query, variables)
            
            if "data" in result and result["data"]["repository"]:
                return result["data"]["repository"]
            else:
                print(f"Repositório {owner}/{name} não encontrado ou inacessível")
                return {}
                
        except Exception as e:
            print(f"Erro ao obter detalhes do repositório {owner}/{name}: {e}")
            return {}


class SonarQubeAPI:
    """Classe para interação com a API do SonarQube"""
    
    def __init__(self, host: str, token: str):
        self.host = host.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.auth = (token, '')
    
    def get_project_metrics(self, project_key: str) -> dict:
        """Extrai métricas de um projeto analisado no SonarQube"""
        metrics = [
            "bugs", "vulnerabilities", "code_smells", "sqale_index",
            "coverage", "duplicated_lines_density", "ncloc", "complexity",
            "cognitive_complexity", "reliability_rating", "security_rating",
            "sqale_rating", "alert_status"
        ]
        
        params = {
            "component": project_key,
            "metricKeys": ",".join(metrics)
        }
        
        url = f"{self.host}/api/measures/component"
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if "component" in data and "measures" in data["component"]:
                measures = {}
                for measure in data["component"]["measures"]:
                    metric_key = measure["metric"]
                    value = measure.get("value", "0")
                    
                    # Converte valores numéricos
                    if metric_key in ["bugs", "vulnerabilities", "code_smells", 
                                    "sqale_index", "ncloc", "complexity", "cognitive_complexity"]:
                        measures[metric_key] = int(value) if value.isdigit() else 0
                    elif metric_key in ["coverage", "duplicated_lines_density"]:
                        measures[metric_key] = float(value) if value.replace('.', '').isdigit() else 0.0
                    else:
                        measures[metric_key] = value
                
                return measures
            else:
                print(f"Nenhuma métrica encontrada para o projeto {project_key}")
                return {}
                
        except Exception as e:
            print(f"Erro ao obter métricas do SonarQube para {project_key}: {e}")
            return {}


class DatabaseManager:
    """Classe para gerenciamento do banco de dados PostgreSQL"""
    
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.connection = None
    
    def connect(self):
        """Estabelece conexão com o banco de dados"""
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.connection.autocommit = True
            print("Conexão com banco de dados estabelecida")
            return True
        except Exception as e:
            print(f"AVISO: Erro ao conectar com banco de dados: {e}")
            print("Continuando sem persistir dados no banco...")
            self.connection = None
            return False
    
    def disconnect(self):
        """Fecha conexão com o banco de dados"""
        if self.connection:
            self.connection.close()
            print("Conexão com banco de dados fechada")
    
    def create_tables(self):
        """Cria as tabelas necessárias no banco de dados"""
        if not self.connection:
            print("Sem conexão com banco de dados - pulando criação de tabelas")
            return
        
        tables_sql = [
            """
            CREATE TABLE IF NOT EXISTS repositories (
                id SERIAL PRIMARY KEY,
                owner VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                full_name VARCHAR(511) UNIQUE NOT NULL,
                stargazer_count INTEGER,
                fork_count INTEGER,
                language VARCHAR(100),
                total_releases INTEGER,
                avg_release_interval_days DECIMAL(10, 2),
                release_type VARCHAR(50),
                collaborator_count INTEGER,
                distinct_releases_count INTEGER,
                total_issues INTEGER,
                open_issues INTEGER,
                closed_issues INTEGER,
                issues_closed_to_open_ratio DECIMAL(5,2),
                total_pull_requests INTEGER,
                merged_pull_requests INTEGER,
                pull_request_merge_rate DECIMAL(5,2),
                issue_reopen_rate DECIMAL(5,2),
                avg_issue_close_time_hours DECIMAL(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pull_requests (
                id SERIAL PRIMARY KEY,
                repo_id INTEGER REFERENCES repositories(id),
                pr_number INTEGER,
                merged BOOLEAN,
                created_at TIMESTAMP,
                merged_at TIMESTAMP,
                commit_count INTEGER,
                comment_count INTEGER,
                churn INTEGER,
                merge_time_hours DECIMAL(10, 2),
                UNIQUE(repo_id, pr_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS issues (
                id SERIAL PRIMARY KEY,
                repo_id INTEGER REFERENCES repositories(id),
                issue_number INTEGER,
                created_at TIMESTAMP,
                closed_at TIMESTAMP,
                reopened_events INTEGER,
                time_to_close_hours DECIMAL(10, 2),
                UNIQUE(repo_id, issue_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sonarqube_metrics (
                id SERIAL PRIMARY KEY,
                repo_id INTEGER REFERENCES repositories(id),
                analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bugs INTEGER,
                vulnerabilities INTEGER,
                code_smells INTEGER,
                sqale_index INTEGER,
                coverage DECIMAL(5,2),
                duplicated_lines_density DECIMAL(5,2),
                ncloc INTEGER,
                complexity INTEGER,
                cognitive_complexity INTEGER,
                reliability_rating VARCHAR(10),
                security_rating VARCHAR(10),
                sqale_rating VARCHAR(10),
                alert_status VARCHAR(50),
                UNIQUE(repo_id, analysis_date)
            )
            """
        ]
        
        try:
            with self.connection.cursor() as cursor:
                for table_sql in tables_sql:
                    cursor.execute(table_sql)
            print("Tabelas criadas com sucesso")
        except Exception as e:
            print(f"Erro ao criar tabelas: {e}")
            raise
    
    def insert_repository(self, repo_data: dict) -> int:
        """Insere ou atualiza dados de um repositório"""
        if not self.connection:
            print(f"[SIMULAÇÃO] Inserindo repositório: {repo_data['full_name']}")
            return 1  # ID fictício
            
        sql = """
        INSERT INTO repositories (
            owner, name, full_name, stargazer_count, fork_count, language,
            total_releases, avg_release_interval_days, release_type,
            collaborator_count, distinct_releases_count, total_issues,
            open_issues, closed_issues, issues_closed_to_open_ratio,
            total_pull_requests, merged_pull_requests, pull_request_merge_rate,
            issue_reopen_rate, avg_issue_close_time_hours
        ) VALUES (
            %(owner)s, %(name)s, %(full_name)s, %(stargazer_count)s, %(fork_count)s, %(language)s,
            %(total_releases)s, %(avg_release_interval_days)s, %(release_type)s,
            %(collaborator_count)s, %(distinct_releases_count)s, %(total_issues)s,
            %(open_issues)s, %(closed_issues)s, %(issues_closed_to_open_ratio)s,
            %(total_pull_requests)s, %(merged_pull_requests)s, %(pull_request_merge_rate)s,
            %(issue_reopen_rate)s, %(avg_issue_close_time_hours)s
        )
        ON CONFLICT (full_name) DO UPDATE SET
            stargazer_count = EXCLUDED.stargazer_count,
            fork_count = EXCLUDED.fork_count,
            language = EXCLUDED.language,
            total_releases = EXCLUDED.total_releases,
            avg_release_interval_days = EXCLUDED.avg_release_interval_days,
            release_type = EXCLUDED.release_type,
            collaborator_count = EXCLUDED.collaborator_count,
            distinct_releases_count = EXCLUDED.distinct_releases_count,
            total_issues = EXCLUDED.total_issues,
            open_issues = EXCLUDED.open_issues,
            closed_issues = EXCLUDED.closed_issues,
            issues_closed_to_open_ratio = EXCLUDED.issues_closed_to_open_ratio,
            total_pull_requests = EXCLUDED.total_pull_requests,
            merged_pull_requests = EXCLUDED.merged_pull_requests,
            pull_request_merge_rate = EXCLUDED.pull_request_merge_rate,
            issue_reopen_rate = EXCLUDED.issue_reopen_rate,
            avg_issue_close_time_hours = EXCLUDED.avg_issue_close_time_hours
        RETURNING id
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, repo_data)
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"Erro ao inserir repositório: {e}")
            return None
    
    def insert_pull_request(self, repo_id: int, pr_data: dict):
        """Insere dados de uma pull request"""
        if not self.connection:
            print(f"[SIMULAÇÃO] Inserindo PR #{pr_data.get('pr_number', 'N/A')} do repo ID {repo_id}")
            return
            
        sql = """
        INSERT INTO pull_requests (
            repo_id, pr_number, merged, created_at, merged_at,
            commit_count, comment_count, churn, merge_time_hours
        ) VALUES (
            %(repo_id)s, %(pr_number)s, %(merged)s, %(created_at)s, %(merged_at)s,
            %(commit_count)s, %(comment_count)s, %(churn)s, %(merge_time_hours)s
        )
        ON CONFLICT (repo_id, pr_number) DO UPDATE SET
            merged = EXCLUDED.merged,
            merged_at = EXCLUDED.merged_at,
            commit_count = EXCLUDED.commit_count,
            comment_count = EXCLUDED.comment_count,
            churn = EXCLUDED.churn,
            merge_time_hours = EXCLUDED.merge_time_hours
        """
        
        pr_data['repo_id'] = repo_id
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, pr_data)
        except Exception as e:
            print(f"Erro ao inserir pull request: {e}")
    
    def insert_issue(self, repo_id: int, issue_data: dict):
        """Insere dados de uma issue"""
        if not self.connection:
            print(f"[SIMULAÇÃO] Inserindo Issue #{issue_data.get('issue_number', 'N/A')} do repo ID {repo_id}")
            return
            
        sql = """
        INSERT INTO issues (
            repo_id, issue_number, created_at, closed_at,
            reopened_events, time_to_close_hours
        ) VALUES (
            %(repo_id)s, %(issue_number)s, %(created_at)s, %(closed_at)s,
            %(reopened_events)s, %(time_to_close_hours)s
        )
        ON CONFLICT (repo_id, issue_number) DO UPDATE SET
            closed_at = EXCLUDED.closed_at,
            reopened_events = EXCLUDED.reopened_events,
            time_to_close_hours = EXCLUDED.time_to_close_hours
        """
        
        issue_data['repo_id'] = repo_id
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, issue_data)
        except Exception as e:
            print(f"Erro ao inserir issue: {e}")
    
    def insert_sonarqube_metrics(self, repo_id: int, metrics: dict):
        """Insere métricas do SonarQube"""
        if not self.connection:
            print(f"[SIMULAÇÃO] Inserindo métricas SonarQube para repo ID {repo_id}")
            return
            
        sql = """
        INSERT INTO sonarqube_metrics (
            repo_id, bugs, vulnerabilities, code_smells, sqale_index,
            coverage, duplicated_lines_density, ncloc, complexity,
            cognitive_complexity, reliability_rating, security_rating,
            sqale_rating, alert_status
        ) VALUES (
            %(repo_id)s, %(bugs)s, %(vulnerabilities)s, %(code_smells)s, %(sqale_index)s,
            %(coverage)s, %(duplicated_lines_density)s, %(ncloc)s, %(complexity)s,
            %(cognitive_complexity)s, %(reliability_rating)s, %(security_rating)s,
            %(sqale_rating)s, %(alert_status)s
        )
        ON CONFLICT (repo_id, analysis_date) DO UPDATE SET
            bugs = EXCLUDED.bugs,
            vulnerabilities = EXCLUDED.vulnerabilities,
            code_smells = EXCLUDED.code_smells,
            sqale_index = EXCLUDED.sqale_index,
            coverage = EXCLUDED.coverage,
            duplicated_lines_density = EXCLUDED.duplicated_lines_density,
            ncloc = EXCLUDED.ncloc,
            complexity = EXCLUDED.complexity,
            cognitive_complexity = EXCLUDED.cognitive_complexity,
            reliability_rating = EXCLUDED.reliability_rating,
            security_rating = EXCLUDED.security_rating,
            sqale_rating = EXCLUDED.sqale_rating,
            alert_status = EXCLUDED.alert_status
        """
        
        metrics['repo_id'] = repo_id
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, metrics)
        except Exception as e:
            print(f"Erro ao inserir métricas SonarQube: {e}")


class RepositoryProcessor:
    """Classe principal para processamento de repositórios"""
    
    def __init__(self, github_api: GitHubAPI, sonarqube_api: Optional[SonarQubeAPI], 
                 database_manager: DatabaseManager):
        self.github_api = github_api
        self.sonarqube_api = sonarqube_api
        self.db_manager = database_manager
        # Usa diretório temporário do sistema (funciona no Windows e Linux)
        self.temp_base_dir = os.path.join(tempfile.gettempdir(), "repos_analise")
        
        # Cria diretório temporário base apenas se SonarQube estiver habilitado
        if self.sonarqube_api:
            Path(self.temp_base_dir).mkdir(parents=True, exist_ok=True)
    
    def _calculate_avg_release_interval(self, releases_nodes: List[dict]) -> Optional[float]:
        """Calcula o intervalo médio entre releases em dias"""
        if len(releases_nodes) < 2:
            return None
        
        dates = []
        for release in releases_nodes:
            try:
                date = datetime.fromisoformat(release['createdAt'].replace('Z', '+00:00'))
                dates.append(date)
            except:
                continue
        
        if len(dates) < 2:
            return None
        
        dates.sort(reverse=True)  # Mais recente primeiro
        intervals = []
        
        for i in range(len(dates) - 1):
            interval = (dates[i] - dates[i + 1]).days
            if interval > 0:
                intervals.append(interval)
        
        return sum(intervals) / len(intervals) if intervals else None
    
    def _classify_release_type(self, avg_interval: Optional[float]) -> str:
        """Classifica o tipo de release baseado no intervalo médio"""
        if 5 <= avg_interval <= 35:
            return 'rapid'
        elif avg_interval >= 60:
            return 'slow'
        else:
            return 'unclassified'
    
    def _calculate_pr_metrics(self, pr_nodes: List[dict]) -> Tuple[int, int, float, float, int]:
        """Calcula métricas de pull requests"""
        total_prs = len(pr_nodes)
        merged_prs = 0
        merge_times = []
        total_churn = 0  # Placeholder
        
        for pr in pr_nodes:
            if pr.get('merged', False):
                merged_prs += 1
                
                # Calcula tempo de merge
                if pr.get('createdAt') and pr.get('mergedAt'):
                    try:
                        created = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
                        merged = datetime.fromisoformat(pr['mergedAt'].replace('Z', '+00:00'))
                        merge_time = (merged - created).total_seconds() / 3600  # horas
                        if merge_time > 0:
                            merge_times.append(merge_time)
                    except:
                        pass
            
            # Placeholder para churn - seria número de commits como proxy
            total_churn += pr.get('commits', {}).get('totalCount', 0)
        
        pr_merge_rate = (merged_prs / total_prs) if total_prs > 0 else 0
        avg_merge_time = sum(merge_times) / len(merge_times) if merge_times else 0
        
        return total_prs, merged_prs, pr_merge_rate, avg_merge_time, total_churn
    
    def _calculate_issue_metrics(self, issue_nodes: List[dict], open_issues: int, 
                                closed_issues: int) -> Tuple[int, float, float, float]:
        """Calcula métricas de issues"""
        total_issues = len(issue_nodes)
        total_reopened = 0
        close_times = []
        
        for issue in issue_nodes:
            # Conta eventos de reabertura
            reopened_events = issue.get('timelineItems', {}).get('totalCount', 0)
            total_reopened += reopened_events
            
            # Calcula tempo de fechamento
            if issue.get('createdAt') and issue.get('closedAt'):
                try:
                    created = datetime.fromisoformat(issue['createdAt'].replace('Z', '+00:00'))
                    closed = datetime.fromisoformat(issue['closedAt'].replace('Z', '+00:00'))
                    close_time = (closed - created).total_seconds() / 3600  # horas
                    if close_time > 0:
                        close_times.append(close_time)
                except:
                    pass
        
        issues_ratio = (closed_issues / open_issues) if open_issues > 0 else 0
        reopen_rate = (total_reopened / total_issues) if total_issues > 0 else 0
        avg_close_time = sum(close_times) / len(close_times) if close_times else 0
        
        return total_issues, issues_ratio, reopen_rate, avg_close_time
    
    def _clone_repository(self, owner: str, name: str) -> Optional[str]:
        """Clona um repositório para análise"""
        repo_url = f"https://github.com/{owner}/{name}.git"
        temp_dir = os.path.join(self.temp_base_dir, f"{owner}_{name}")
        
        # Remove diretório se já existir (com tratamento de permissões)
        if os.path.exists(temp_dir):
            print(f"Removendo diretório existente: {temp_dir}")
            self._cleanup_temp_dir(temp_dir)
        
        try:
            print(f"Clonando repositório {owner}/{name}...")
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', repo_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=300  # Timeout de 5 minutos
            )
            
            if result.returncode == 0:
                print(f"Repositório clonado com sucesso em {temp_dir}")
                return temp_dir
            else:
                print(f"Erro ao clonar repositório: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"Timeout ao clonar repositório {owner}/{name}")
            self._cleanup_temp_dir(temp_dir)
            return None
        except FileNotFoundError:
            print("ERRO: Git não está instalado ou não está no PATH")
            print("Instale o Git: https://git-scm.com/download/win")
            return None
        except Exception as e:
            print(f"Erro ao clonar repositório {owner}/{name}: {e}")
            self._cleanup_temp_dir(temp_dir)
            return None
    
    def _run_sonar_scanner(self, repo_dir: str, owner: str, name: str) -> bool:
        """Executa o SonarScanner via Docker em um repositório"""
        project_key = f"{owner}_{name}"
        
        # Obtém configurações do ambiente
        sonar_host = os.getenv("SONAR_HOST", "http://localhost:9000")
        sonar_token = os.getenv("SONAR_TOKEN")
        
        if not sonar_token:
            print("ERRO: SONAR_TOKEN não configurado")
            return False
        
        # Converte path do Windows para formato Docker (se necessário)
        # Ex: C:\Users\... -> /c/Users/...
        if os.name == 'nt':  # Windows
            # Normaliza o caminho
            repo_dir_normalized = os.path.abspath(repo_dir)
            # Converte para formato Docker volume (Windows)
            # Mantém o formato Windows para Docker Desktop
            docker_volume = f"{repo_dir_normalized}:/usr/src"
        else:
            docker_volume = f"{repo_dir}:/usr/src"
        
        # Comando Docker para executar SonarScanner
        docker_cmd = [
            'docker', 'run',
            '--rm',  # Remove container após execução
            '--network', 'host',  # Permite acesso ao localhost
            '-e', f'SONAR_HOST_URL={sonar_host}',
            '-e', f'SONAR_TOKEN={sonar_token}',
            '-v', docker_volume,
            'sonarsource/sonar-scanner-cli',
            '-Dsonar.projectKey=' + project_key,
            '-Dsonar.projectName=' + project_key,
            '-Dsonar.sources=.',
            '-Dsonar.python.version=3.13'
        ]
        
        try:
            print(f"Executando SonarScanner via Docker para {owner}/{name}...")
            print(f"Comando: {' '.join(docker_cmd)}")
            
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=900,  # Timeout de 15 minutos
                cwd=repo_dir  # Define working directory
            )
            
            # Exibe saída para debug
            if result.stdout:
                print("STDOUT:", result.stdout[-500:])  # Últimos 500 chars
            
            if result.returncode == 0:
                print(f"✅ SonarScanner executado com sucesso para {owner}/{name}")
                # Aguarda processamento no SonarQube
                print("Aguardando processamento no SonarQube...")
                time.sleep(30)
                return True
            else:
                print(f"❌ Erro no SonarScanner (exit code {result.returncode}):")
                if result.stderr:
                    print("STDERR:", result.stderr[-500:])
                return False
                
        except subprocess.TimeoutExpired:
            print(f"⏱️ Timeout ao executar SonarScanner para {owner}/{name}")
            return False
        except FileNotFoundError:
            print("❌ ERRO: Docker não está instalado ou não está no PATH")
            print("Instale o Docker Desktop: https://www.docker.com/products/docker-desktop")
            return False
        except Exception as e:
            print(f"❌ Erro ao executar SonarScanner via Docker para {owner}/{name}: {e}")
            return False
    
    def _cleanup_temp_dir(self, temp_dir: str):
        """Limpa diretório temporário com tratamento especial para Windows e repositórios Git"""
        try:
            if os.path.exists(temp_dir):
                # No Windows, arquivos Git podem ter atributo somente-leitura
                # Esta função remove esse atributo antes de deletar
                def handle_remove_readonly(func, path, exc):
                    """Trata erros de permissão ao remover arquivos no Windows"""
                    import stat
                    if not os.access(path, os.W_OK):
                        # Remove atributo somente-leitura
                        os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
                        func(path)
                    else:
                        raise
                
                # Remove com tratamento de erros de permissão
                shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
                print(f"Diretório temporário {temp_dir} removido")
        except PermissionError as e:
            print(f"AVISO: Erro de permissão ao remover {temp_dir}: {e}")
            print(f"Você pode precisar remover manualmente: {temp_dir}")
        except Exception as e:
            print(f"AVISO: Erro ao remover diretório temporário {temp_dir}: {e}")
    
    def process_repository(self, owner: str, name: str):
        """Processa um repositório completo"""
        full_name = f"{owner}/{name}"
        print(f"\n=== Processando repositório {full_name} ===")
        
        # 1. Obtém detalhes do repositório
        repo_details = self.github_api.get_repo_details(owner, name)
        if not repo_details:
            print(f"Falha ao obter detalhes do repositório {full_name}")
            return
        
        # 2. Aplica filtros iniciais (relaxados para funcionar sem permissões especiais)
        total_releases = repo_details.get('releases', {}).get('totalCount', 0)
        stargazer_count = repo_details.get('stargazerCount', 0)
        fork_count = repo_details.get('forkCount', 0)
        
        # Usa stars e forks como proxy para atividade do projeto
        if stargazer_count < 100:
            print(f"Repositório {full_name} não atende critério de popularidade (tem {stargazer_count} stars, precisa >= 100)")
            return
        
        if total_releases < 5:  # Reduzido para ser mais inclusivo
            print(f"Repositório {full_name} não atende critério de releases (tem {total_releases}, precisa >= 5)")
            return
        
        print(f"Repositório {full_name} passou nos filtros iniciais")
        
        # 3. Calcula métricas do GitHub
        releases_nodes = repo_details.get('releases', {}).get('nodes', [])
        avg_interval = self._calculate_avg_release_interval(releases_nodes)
        release_type = self._classify_release_type(avg_interval)
        
        pr_nodes = repo_details.get('pullRequests', {}).get('nodes', [])
        total_prs, merged_prs, pr_merge_rate, avg_merge_time, pr_churn = self._calculate_pr_metrics(pr_nodes)
        
        issue_nodes = repo_details.get('issues', {}).get('nodes', [])
        open_issues = repo_details.get('issuesOpen', {}).get('totalCount', 0)
        closed_issues = repo_details.get('issuesClosed', {}).get('totalCount', 0)
        total_issues, issues_ratio, reopen_rate, avg_close_time = self._calculate_issue_metrics(
            issue_nodes, open_issues, closed_issues
        )
        
        # 4. Prepara dados do repositório
        repo_data = {
            'owner': owner,
            'name': name,
            'full_name': full_name,
            'stargazer_count': repo_details.get('stargazerCount', 0),
            'fork_count': repo_details.get('forkCount', 0),
            'language': repo_details.get('primaryLanguage', {}).get('name') if repo_details.get('primaryLanguage') else None,
            'total_releases': total_releases,
            'avg_release_interval_days': avg_interval,
            'release_type': release_type,
            'collaborator_count': repo_details.get('collaborators', {}).get('totalCount', 0),
            'distinct_releases_count': total_releases,
            'total_issues': total_issues,
            'open_issues': open_issues,
            'closed_issues': closed_issues,
            'issues_closed_to_open_ratio': issues_ratio,
            'total_pull_requests': total_prs,
            'merged_pull_requests': merged_prs,
            'pull_request_merge_rate': pr_merge_rate,
            'issue_reopen_rate': reopen_rate,
            'avg_issue_close_time_hours': avg_close_time
        }
        
        # 5. Exibe/Persiste dados do repositório
        print(f"\n📊 MÉTRICAS CALCULADAS para {full_name}:")
        print(f"   ⭐ Stars: {repo_data['stargazer_count']}")
        print(f"   🍴 Forks: {repo_data['fork_count']}")
        print(f"   👥 Colaboradores: {repo_data['collaborator_count']}")
        print(f"   🏷️  Releases: {repo_data['total_releases']}")
        print(f"   📈 Tipo de Release: {repo_data['release_type']}")
        if repo_data['avg_release_interval_days']:
            print(f"   ⏱️  Intervalo médio: {repo_data['avg_release_interval_days']:.1f} dias")
        print(f"   🔀 Pull Requests: {repo_data['total_pull_requests']} (taxa merge: {repo_data['pull_request_merge_rate']:.2%})")
        print(f"   🐛 Issues: {repo_data['total_issues']} (abertas: {repo_data['open_issues']}, fechadas: {repo_data['closed_issues']})")
        
        repo_id = self.db_manager.insert_repository(repo_data)
        if not repo_id:
            print(f"❌ Falha ao inserir repositório {full_name} no banco de dados")
            return
        
        if self.db_manager.connection:
            print(f"✅ Repositório {full_name} inserido no banco com ID {repo_id}")
        else:
            repo_id = 1  # ID fictício para continuar o processamento
        
        # 6. Persiste pull requests
        for pr in pr_nodes:
            pr_data = {
                'pr_number': pr.get('number', 0),
                'merged': pr.get('merged', False),
                'created_at': pr.get('createdAt'),
                'merged_at': pr.get('mergedAt'),
                'commit_count': pr.get('commits', {}).get('totalCount', 0),
                'comment_count': pr.get('comments', {}).get('totalCount', 0),
                'churn': pr.get('commits', {}).get('totalCount', 0),  # Placeholder
                'merge_time_hours': None
            }
            
            # Calcula tempo de merge se disponível
            if pr.get('createdAt') and pr.get('mergedAt'):
                try:
                    created = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
                    merged = datetime.fromisoformat(pr['mergedAt'].replace('Z', '+00:00'))
                    pr_data['merge_time_hours'] = (merged - created).total_seconds() / 3600
                except:
                    pass
            
            self.db_manager.insert_pull_request(repo_id, pr_data)
        
        # 7. Persiste issues
        for issue in issue_nodes:
            issue_data = {
                'issue_number': issue.get('number', 0),
                'created_at': issue.get('createdAt'),
                'closed_at': issue.get('closedAt'),
                'reopened_events': issue.get('timelineItems', {}).get('totalCount', 0),
                'time_to_close_hours': None
            }
            
            # Calcula tempo de fechamento se disponível
            if issue.get('createdAt') and issue.get('closedAt'):
                try:
                    created = datetime.fromisoformat(issue['createdAt'].replace('Z', '+00:00'))
                    closed = datetime.fromisoformat(issue['closedAt'].replace('Z', '+00:00'))
                    issue_data['time_to_close_hours'] = (closed - created).total_seconds() / 3600
                except:
                    pass
            
            self.db_manager.insert_issue(repo_id, issue_data)
        
        # 8. Análise SonarQube (se token disponível)
        if self.sonarqube_api and os.getenv('SONAR_TOKEN'):
            temp_dir = None
            try:
                # Clona repositório
                temp_dir = self._clone_repository(owner, name)
                if temp_dir:
                    # Executa SonarScanner
                    if self._run_sonar_scanner(temp_dir, owner, name):
                        # Extrai métricas
                        project_key = f"{owner}_{name}"
                        metrics = self.sonarqube_api.get_project_metrics(project_key)
                        
                        if metrics:
                            self.db_manager.insert_sonarqube_metrics(repo_id, metrics)
                            print(f"Métricas SonarQube inseridas para {full_name}")
                        else:
                            print(f"Nenhuma métrica SonarQube encontrada para {full_name}")
            except Exception as e:
                print(f"ERRO durante análise SonarQube de {full_name}: {e}")
            finally:
                # Limpa diretório temporário
                if temp_dir:
                    self._cleanup_temp_dir(temp_dir)
        else:
            print("SonarQube não configurado, pulando análise de código")
        
        print(f"=== Processamento de {full_name} concluído ===\n")


def check_prerequisites() -> Tuple[bool, bool]:
    """Verifica pré-requisitos do sistema"""
    print("=== Verificando pré-requisitos ===")
    
    # Verifica Git
    git_available = False
    try:
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Git: {result.stdout.strip()}")
            git_available = True
        else:
            print("❌ Git: Não encontrado")
    except FileNotFoundError:
        print("❌ Git: Não instalado")
        print("   Instale: https://git-scm.com/download/win")
    
    # Verifica Docker
    docker_available = False
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker: {result.stdout.strip()}")
            docker_available = True
            
            # Verifica se Docker está rodando
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
            if result.returncode != 0:
                print("⚠️  Docker está instalado mas não está rodando")
                print("   Inicie o Docker Desktop")
                docker_available = False
        else:
            print("❌ Docker: Não encontrado")
    except FileNotFoundError:
        print("❌ Docker: Não instalado")
        print("   Instale: https://www.docker.com/products/docker-desktop")
    
    print()
    return git_available, docker_available


def main():
    """Função principal do script"""
    print("=== Script de Automação de Pesquisa GitHub ===")
    print("Versão com análise SonarQube via Docker\n")
    
    # Verifica pré-requisitos
    git_available, docker_available = check_prerequisites()
    
    if not git_available:
        print("ERRO: Git é obrigatório para clonar repositórios")
        sys.exit(1)
    
    # Verifica variáveis de ambiente obrigatórias
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("ERRO: GITHUB_TOKEN não configurado!")
        print("Configure no arquivo .env: GITHUB_TOKEN=seu_token_aqui")
        sys.exit(1)
    
    sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
    sonar_token = os.getenv('SONAR_TOKEN')
    
    # Aviso sobre SonarQube
    if not sonar_token:
        print("⚠️  AVISO: SONAR_TOKEN não configurado. Análise SonarQube será pulada.")
        print("   Para habilitar SonarQube, configure SONAR_TOKEN no .env\n")
    elif not docker_available:
        print("⚠️  AVISO: Docker não disponível. Análise SonarQube será pulada.")
        print("   Para habilitar SonarQube, instale e inicie o Docker Desktop\n")
        sonar_token = None  # Desabilita SonarQube se Docker não estiver disponível
    else:
        print(f"✅ SonarQube configurado: {sonar_host}\n")
    
    # Configuração do banco de dados
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'sonar'),
        'user': os.getenv('DB_USER', 'sonar'),
        'password': os.getenv('DB_PASSWORD', 'sonar'),
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    try:
        # Inicializa APIs
        print("Inicializando GitHub API...")
        github_api = GitHubAPI(github_token)
        
        sonarqube_api = None
        if sonar_token:
            print("Inicializando SonarQube API...")
            sonarqube_api = SonarQubeAPI(sonar_host, sonar_token)
        
        # Tenta conectar com banco de dados
        print("Tentando conectar com banco de dados...")
        db_manager = DatabaseManager(db_config)
        db_connected = db_manager.connect()
        
        if db_connected:
            db_manager.create_tables()
            print("Banco de dados configurado com sucesso!")
        else:
            print("Continuando sem banco de dados - dados serão apenas exibidos\n")
        
        processor = RepositoryProcessor(github_api, sonarqube_api, db_manager)
        
        # Queries de busca para diferentes tipos de repositório (critérios ajustados)
        search_queries = [
            "stars:>100 forks:>50 language:Python",
            "stars:>100 forks:>50 language:JavaScript", 
            "stars:>100 forks:>50 language:Java",
            "stars:>100 forks:>50 language:TypeScript",
            "stars:>100 forks:>50 language:Go",
            "stars:>200 forks:>100",  # Busca geral com critérios mais altos
        ]
        
        processed_repos = set()
        total_processed = 0
        target_repos_per_type = 1  # Ainda mais reduzido para teste inicial
        
        print(f"Iniciando busca de repositórios (máximo {target_repos_per_type} por linguagem)...")
        print("Para aumentar, modifique 'target_repos_per_type' no código\n")
        
        for query in search_queries:
            print(f"\n--- Buscando repositórios com query: {query} ---")
            
            try:
                repositories = github_api.search_repositories(query, target_repos_per_type)
                
                for repo in repositories:
                    owner = repo['owner']['login']
                    name = repo['name']
                    full_name = f"{owner}/{name}"
                    
                    # Evita processar o mesmo repositório múltiplas vezes
                    if full_name in processed_repos:
                        print(f"Pulando {full_name} (já processado)")
                        continue
                    
                    processed_repos.add(full_name)
                    
                    try:
                        print(f"\n[{total_processed + 1}] Processando: {full_name}")
                        processor.process_repository(owner, name)
                        total_processed += 1
                        
                        # Pausa para respeitar rate limiting
                        time.sleep(2)
                        
                        # Status report a cada 5 repositórios
                        if total_processed % 5 == 0:
                            print(f"\n*** PROGRESSO: {total_processed} repositórios processados ***\n")
                        
                    except Exception as e:
                        print(f"ERRO ao processar repositório {full_name}: {e}")
                        continue
                
                # Pausa entre queries
                print(f"Pausando 3 segundos antes da próxima query...")
                time.sleep(3)
                
            except Exception as e:
                print(f"ERRO na busca com query '{query}': {e}")
                continue
        
        print(f"\n=== PROCESSAMENTO CONCLUÍDO ===")
        print(f"Total de repositórios processados: {total_processed}")
        print(f"Total de repositórios únicos encontrados: {len(processed_repos)}")
        
    except Exception as e:
        print(f"Erro fatal no script: {e}")
        sys.exit(1)
        
    finally:
        # Limpa recursos
        if 'db_manager' in locals() and db_manager.connection:
            db_manager.disconnect()
        
        # Limpa diretório temporário base (apenas se foi criado para SonarQube)
        temp_base = os.path.join(tempfile.gettempdir(), "repos_analise")
        if os.path.exists(temp_base):
            try:
                def handle_remove_readonly(func, path, exc):
                    """Trata erros de permissão ao remover arquivos no Windows"""
                    import stat
                    if not os.access(path, os.W_OK):
                        os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
                        func(path)
                    else:
                        raise
                
                shutil.rmtree(temp_base, onerror=handle_remove_readonly)
                print(f"Diretório temporário base {temp_base} limpo")
            except Exception as e:
                print(f"AVISO: Não foi possível limpar {temp_base}: {e}")
                print(f"Você pode precisar remover manualmente o diretório")
        
        print("\n🎉 Execução finalizada!")


if __name__ == "__main__":
    main()