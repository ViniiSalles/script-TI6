#!/usr/bin/env python3
"""
Script: Análise SonarQube de Repositórios a partir de CSV

OBJETIVO:
Processar repositórios de um arquivo CSV com análise de código SonarQube.
Suporta processamento paralelo com logging organizado.

PRÉ-REQUISITOS:
- Docker rodando
- SonarQube configurado (http://localhost:9000)
- Arquivo CSV com repositórios (formato: owner,name,stars,forks,language,...)

EXECUÇÃO:
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4

OPÇÕES:
--csv FILE      : Arquivo CSV com repositórios
--workers N     : Número de processos paralelos (padrão: 1)
--limit N       : Limitar número de análises
--skip-analyzed : Pular repositórios já analisados
--output FILE   : Arquivo de saída com análises (padrão: [input]_analyzed.csv)
"""

import os
import sys
import time
import argparse
import subprocess
import tempfile
import shutil
import stat
from pathlib import Path
from typing import Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from threading import Lock

from dotenv import load_dotenv
import psycopg2

from dataset_manager import DatasetManager
from utils import SonarQubeAPI

# Carrega variáveis de ambiente
load_dotenv()


class ProgressTracker:
    """Rastreia progresso da análise com saída organizada"""
    
    def __init__(self, total: int):
        self.total = total
        self.completed = 0
        self.successful = 0
        self.failed = 0
        self.lock = Lock()
        self.start_time = time.time()
    
    def update(self, repo_name: str, success: bool, message: str = ""):
        """Atualiza progresso de forma thread-safe"""
        with self.lock:
            self.completed += 1
            if success:
                self.successful += 1
                status = "✅"
            else:
                self.failed += 1
                status = "❌"
            
            elapsed = time.time() - self.start_time
            avg_time = elapsed / self.completed if self.completed > 0 else 0
            eta = avg_time * (self.total - self.completed)
            
            # Limpa linha e imprime progresso
            print(f"\r{' ' * 120}\r", end='', flush=True)
            progress = f"[{self.completed}/{self.total}] {status} {repo_name}"
            if message:
                progress += f" - {message}"
            print(progress, flush=True)
            
            # Barra de progresso
            percent = (self.completed / self.total) * 100
            bar_length = 50
            filled = int(bar_length * self.completed / self.total)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            stats = f"[{bar}] {percent:.1f}% | ✅ {self.successful} | ❌ {self.failed} | ETA: {eta/60:.1f}min"
            print(stats, flush=True)
            print()  # Linha em branco para separar


class SonarQubeAnalyzer:
    """Analisa repositórios com SonarQube"""
    
    def __init__(self, sonarqube_api: SonarQubeAPI, dataset_manager: DatasetManager, 
                 worker_id: int = 0, quiet: bool = False):
        self.sonarqube_api = sonarqube_api
        self.dataset = dataset_manager
        self.worker_id = worker_id
        self.quiet = quiet
        self.temp_base_dir = os.path.join(tempfile.gettempdir(), "repos_analise")
        Path(self.temp_base_dir).mkdir(parents=True, exist_ok=True)
    
    def _log(self, message: str):
        """Log interno (não imprime em modo paralelo)"""
        if not self.quiet:
            print(f"  [Worker {self.worker_id}] {message}")
    
    def _get_directory_size(self, directory: str) -> int:
        """Retorna o tamanho do diretório em bytes"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    # Pula links simbólicos
                    if not os.path.islink(filepath):
                        try:
                            total_size += os.path.getsize(filepath)
                        except (OSError, FileNotFoundError):
                            continue
        except Exception as e:
            pass
        return total_size
    
    def _clone_repository(self, owner: str, name: str) -> Optional[str]:
        """Clona um repositório para análise"""
        repo_url = f"https://github.com/{owner}/{name}.git"
        temp_dir = os.path.join(self.temp_base_dir, f"{owner}_{name}_{self.worker_id}")
        
        if os.path.exists(temp_dir):
            self._cleanup_temp_dir(temp_dir)
        
        try:
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', repo_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                # Verifica tamanho do repositório (limite: 2GB)
                repo_size = self._get_directory_size(temp_dir)
                size_gb = repo_size / (1024 ** 3)
                
                if repo_size > 2 * 1024 ** 3:  # 2GB em bytes
                    self._log(f"Repositório muito grande: {size_gb:.2f}GB (limite: 2GB)")
                    self._cleanup_temp_dir(temp_dir)
                    return None
                
                return temp_dir
            else:
                return None
                
        except subprocess.TimeoutExpired:
            self._cleanup_temp_dir(temp_dir)
            return None
        except FileNotFoundError:
            return None
        except Exception as e:
            self._cleanup_temp_dir(temp_dir)
            return None
    
    def _run_sonar_scanner(self, repo_dir: str, owner: str, name: str) -> bool:
        """Executa o SonarScanner via Docker em um repositório"""
        project_key = f"{owner}_{name}"
        
        sonar_host = os.getenv("SONAR_HOST", "http://localhost:9000")
        sonar_token = os.getenv("SONAR_TOKEN")
        
        if not sonar_token:
            return False
        
        # Normaliza caminho para compatibilidade Windows/Linux
        repo_dir_normalized = os.path.abspath(repo_dir)
        
        # Windows: mantém formato normal
        # Linux/macOS: também usa formato normal (Docker Desktop lida com isso)
        docker_volume = f"{repo_dir_normalized}:/usr/src"
        
        docker_cmd = [
            'docker', 'run',
            '--rm',
            '--network', 'host',
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
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=900,
                cwd=repo_dir
            )
            
            if result.returncode == 0:
                time.sleep(30)  # Aguarda processamento
                return True
            else:
                return False
                
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            return False
        except Exception as e:
            return False
    
    def _cleanup_temp_dir(self, temp_dir: str):
        """Limpa diretório temporário (compatível Windows/Linux)"""
        try:
            if os.path.exists(temp_dir):
                def handle_remove_readonly(func, path, exc):
                    """Trata permissões de arquivos (Windows e Linux)"""
                    try:
                        if not os.access(path, os.W_OK):
                            # Windows: remove atributo read-only
                            # Linux: adiciona permissão de escrita
                            os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                            func(path)
                        else:
                            raise
                    except Exception:
                        # Se ainda falhar, tenta forçar
                        try:
                            if os.path.isdir(path):
                                os.rmdir(path)
                            else:
                                os.remove(path)
                        except:
                            pass
                
                shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
        except Exception as e:
            pass
    
    def _save_metrics_to_db(self, repo_full_name: str, metrics: dict) -> bool:
        """Salva métricas no banco de dados"""
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'sonar'),
            'user': os.getenv('DB_USER', 'sonar'),
            'password': os.getenv('DB_PASSWORD', 'sonar'),
            'port': int(os.getenv('DB_PORT', 5432))
        }
        
        try:
            conn = psycopg2.connect(**db_config)
            conn.autocommit = True
            
            # Busca ID do repositório
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM research_repositories WHERE full_name = %s",
                    (repo_full_name,)
                )
                result = cursor.fetchone()
                
                if not result:
                    conn.close()
                    return False
                
                repo_id = result[0]
                
                # Insere métricas
                sql = """
                INSERT INTO research_sonarqube_metrics (
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
                    code_smells = EXCLUDED.code_smells
                """
                
                metrics['repo_id'] = repo_id
                cursor.execute(sql, metrics)
            
            conn.close()
            return True
            
        except Exception as e:
            return False
    
    def analyze_repository(self, repo_data: dict) -> tuple:
        """
        Analisa um repositório com SonarQube
        Retorna (full_name, success, message)
        """
        owner = repo_data['owner']
        name = repo_data['name']
        full_name = repo_data['full_name']
        
        temp_dir = None
        
        try:
            # 1. Clone
            temp_dir = self._clone_repository(owner, name)
            if not temp_dir:
                # Verifica se foi por tamanho ou erro de clone
                return (full_name, False, "Falha ao clonar ou >2GB")
            
            # 2. SonarScanner
            if not self._run_sonar_scanner(temp_dir, owner, name):
                return (full_name, False, "SonarScanner falhou")
            
            # 3. Extrai métricas
            project_key = f"{owner}_{name}"
            metrics = self.sonarqube_api.get_project_metrics(project_key)
            
            if not metrics:
                return (full_name, False, "Sem métricas")
            
            # 4. Salva no BD (opcional)
            self._save_metrics_to_db(full_name, metrics)
            
            # 5. Atualiza dataset
            dataset = self.dataset.load_dataset()
            for repo in dataset['repositories']:
                if repo['full_name'] == full_name:
                    repo['sonarqube_analyzed'] = True
                    repo['sonarqube_analyzed_at'] = datetime.now().isoformat()
                    repo['sonarqube_metrics'] = metrics
                    break
            self.dataset.save_dataset(dataset)
            
            return (full_name, True, "Concluído")
            
        except Exception as e:
            return (full_name, False, f"Erro: {str(e)[:50]}")
            
        finally:
            if temp_dir:
                self._cleanup_temp_dir(temp_dir)


def analyze_single_repo_worker(repo_data: dict, sonar_host: str, sonar_token: str, 
                                csv_file: str, worker_id: int) -> tuple:
    """Função auxiliar para análise paralela"""
    try:
        sonarqube_api = SonarQubeAPI(sonar_host, sonar_token)
        dataset_manager = DatasetManager(csv_file)
        analyzer = SonarQubeAnalyzer(sonarqube_api, dataset_manager, worker_id, quiet=True)
        
        full_name, success, message = analyzer.analyze_repository(repo_data)
        return (full_name, success, message)
        
    except Exception as e:
        return (repo_data.get('full_name', 'unknown'), False, f"Worker error: {str(e)[:50]}")


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description='Analisa repositórios de arquivo CSV com SonarQube'
    )
    parser.add_argument('--csv', type=str, required=True,
                       help='Arquivo CSV com repositórios')
    parser.add_argument('--workers', type=int, default=1,
                       help='Número de processos paralelos (padrão: 1)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limitar número de análises')
    parser.add_argument('--skip-analyzed', action='store_true',
                       help='Pular repositórios já analisados')
    parser.add_argument('--output', type=str, default=None,
                       help='Arquivo de saída (padrão: [input]_analyzed.csv)')
    
    args = parser.parse_args()
    
    # Verifica se arquivo CSV existe
    if not os.path.exists(args.csv):
        print(f"❌ ERRO: Arquivo CSV não encontrado: {args.csv}")
        sys.exit(1)
    
    print("="*80)
    print("🔬 ANÁLISE SONARQUBE A PARTIR DE CSV")
    print("="*80)
    
    # Verifica SonarQube
    sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
    sonar_token = os.getenv('SONAR_TOKEN')
    
    if not sonar_token:
        print("❌ ERRO: SONAR_TOKEN não configurado!")
        sys.exit(1)
    
    # Carrega dataset do CSV
    dataset_manager = DatasetManager(args.csv)
    dataset = dataset_manager.load_dataset()
    repositories = dataset['repositories']
    
    if args.skip_analyzed:
        repositories = [r for r in repositories if not r.get('sonarqube_analyzed', False)]
    
    if args.limit:
        repositories = repositories[:args.limit]
    
    print(f"\n📊 Configuração:")
    print(f"   • Arquivo CSV: {args.csv}")
    print(f"   • Repositórios total: {len(dataset['repositories'])}")
    print(f"   • Repositórios para analisar: {len(repositories)}")
    print(f"   • Workers: {args.workers}")
    print(f"   • Skip analyzed: {args.skip_analyzed}\n")
    
    if not repositories:
        print("⚠️  Nenhum repositório para analisar")
        sys.exit(0)
    
    # Cria tracker de progresso
    tracker = ProgressTracker(len(repositories))
    
    print("🚀 Iniciando análise...\n")
    
    # Análise sequencial ou paralela
    if args.workers == 1:
        # Sequencial com saída detalhada
        print("Modo: SEQUENCIAL (1 worker)\n")
        sonarqube_api = SonarQubeAPI(sonar_host, sonar_token)
        analyzer = SonarQubeAnalyzer(sonarqube_api, dataset_manager, quiet=False)
        
        for i, repo in enumerate(repositories, 1):
            print(f"\n{'─'*80}")
            print(f"[{i}/{len(repositories)}] 🔬 {repo['full_name']} ({repo['release_type'].upper()})")
            print(f"{'─'*80}")
            
            full_name, success, message = analyzer.analyze_repository(repo)
            tracker.update(full_name, success, message)
    
    else:
        # Paralelo com saída organizada
        print(f"Modo: PARALELO ({args.workers} workers)\n")
        
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            # Submete todas as tarefas
            futures = {}
            for i, repo in enumerate(repositories):
                future = executor.submit(
                    analyze_single_repo_worker, 
                    repo, sonar_host, sonar_token, args.csv, i % args.workers
                )
                futures[future] = repo
            
            # Processa resultados conforme completam
            for future in as_completed(futures):
                full_name, success, message = future.result()
                tracker.update(full_name, success, message)
    
    # Relatório final
    print(f"\n{'='*80}")
    print("📊 RELATÓRIO FINAL")
    print(f"{'='*80}")
    print(f"Total analisados: {tracker.completed}")
    print(f"✅ Bem-sucedidos: {tracker.successful}")
    print(f"❌ Falharam: {tracker.failed}")
    print(f"⏱️  Tempo total: {(time.time() - tracker.start_time) / 60:.1f} minutos")
    print(f"{'='*80}\n")
    
    # Define arquivo de saída
    output_file = args.output or args.csv.replace('.csv', '_analyzed.csv')
    print(f"📁 Resultados salvos em: {output_file}")
    
    dataset_manager.print_statistics()


if __name__ == "__main__":
    main()
