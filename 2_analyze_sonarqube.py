#!/usr/bin/env python3
"""
Script 2: Análise SonarQube de Repositórios

OBJETIVO:
Processar repositórios do dataset com análise de código SonarQube.
Suporta processamento paralelo e retomada de análises interrompidas.

PRÉ-REQUISITOS:
- Docker rodando
- SonarQube configurado (http://localhost:9000)
- Dataset de repositórios coletado (1_collect_repositories.py)

EXECUÇÃO:
python 2_analyze_sonarqube.py --workers 4 --type rapid

OPÇÕES:
--workers N     : Número de processos paralelos (padrão: 1)
--type [rapid|slow|all] : Tipo de repositórios para analisar
--limit N       : Limitar número de análises
--skip-analyzed : Pular repositórios já analisados
--dataset FILE  : Arquivo do dataset
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
from typing import Optional, List
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

from dotenv import load_dotenv
import psycopg2

from dataset_manager import DatasetManager
from utils import SonarQubeAPI

# Carrega variáveis de ambiente
load_dotenv()


class SonarQubeAnalyzer:
    """Analisa repositórios com SonarQube"""
    
    def __init__(self, sonarqube_api: SonarQubeAPI, dataset_manager: DatasetManager):
        self.sonarqube_api = sonarqube_api
        self.dataset = dataset_manager
        self.temp_base_dir = os.path.join(tempfile.gettempdir(), "repos_analise")
        Path(self.temp_base_dir).mkdir(parents=True, exist_ok=True)
    
    def _clone_repository(self, owner: str, name: str) -> Optional[str]:
        """Clona um repositório para análise"""
        repo_url = f"https://github.com/{owner}/{name}.git"
        temp_dir = os.path.join(self.temp_base_dir, f"{owner}_{name}")
        
        if os.path.exists(temp_dir):
            print(f"  🗑️  Removendo diretório existente...")
            self._cleanup_temp_dir(temp_dir)
        
        try:
            print(f"  📥 Clonando repositório...")
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', repo_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"  ✅ Clonado com sucesso")
                return temp_dir
            else:
                print(f"  ❌ Erro ao clonar: {result.stderr[:200]}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"  ⏱️  Timeout ao clonar")
            self._cleanup_temp_dir(temp_dir)
            return None
        except FileNotFoundError:
            print("  ❌ Git não instalado")
            return None
        except Exception as e:
            print(f"  ❌ Erro: {e}")
            self._cleanup_temp_dir(temp_dir)
            return None
    
    def _run_sonar_scanner(self, repo_dir: str, owner: str, name: str) -> bool:
        """Executa o SonarScanner via Docker em um repositório"""
        project_key = f"{owner}_{name}"
        
        sonar_host = os.getenv("SONAR_HOST", "http://localhost:9000")
        sonar_token = os.getenv("SONAR_TOKEN")
        
        if not sonar_token:
            print("  ❌ SONAR_TOKEN não configurado")
            return False
        
        if os.name == 'nt':
            repo_dir_normalized = os.path.abspath(repo_dir)
            docker_volume = f"{repo_dir_normalized}:/usr/src"
        else:
            docker_volume = f"{repo_dir}:/usr/src"
        
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
            print(f"  🔍 Executando SonarScanner...")
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=900,
                cwd=repo_dir
            )
            
            if result.returncode == 0:
                print(f"  ✅ SonarScanner concluído")
                time.sleep(30)  # Aguarda processamento
                return True
            else:
                print(f"  ❌ SonarScanner falhou (exit {result.returncode})")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"  ⏱️  Timeout no SonarScanner")
            return False
        except FileNotFoundError:
            print("  ❌ Docker não instalado")
            return False
        except Exception as e:
            print(f"  ❌ Erro: {e}")
            return False
    
    def _cleanup_temp_dir(self, temp_dir: str):
        """Limpa diretório temporário"""
        try:
            if os.path.exists(temp_dir):
                def handle_remove_readonly(func, path, exc):
                    if not os.access(path, os.W_OK):
                        os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
                        func(path)
                    else:
                        raise
                
                shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
                print(f"  🗑️  Diretório temporário removido")
        except Exception as e:
            print(f"  ⚠️  Erro ao remover diretório: {e}")
    
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
                    print(f"  ⚠️  Repositório não encontrado no BD")
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
            print(f"  ⚠️  Erro ao salvar no BD: {e}")
            return False
    
    def analyze_repository(self, repo_data: dict) -> bool:
        """
        Analisa um repositório com SonarQube
        Retorna True se bem-sucedido
        """
        owner = repo_data['owner']
        name = repo_data['name']
        full_name = repo_data['full_name']
        
        print(f"\n{'─'*80}")
        print(f"🔬 Analisando: {full_name}")
        print(f"   Tipo: {repo_data['release_type'].upper()}")
        print(f"{'─'*80}")
        
        temp_dir = None
        
        try:
            # 1. Clone
            temp_dir = self._clone_repository(owner, name)
            if not temp_dir:
                return False
            
            # 2. SonarScanner
            if not self._run_sonar_scanner(temp_dir, owner, name):
                return False
            
            # 3. Extrai métricas
            project_key = f"{owner}_{name}"
            print(f"  📊 Extraindo métricas...")
            metrics = self.sonarqube_api.get_project_metrics(project_key)
            
            if not metrics:
                print(f"  ⚠️  Nenhuma métrica encontrada")
                return False
            
            print(f"  ✅ Métricas extraídas: {len(metrics)} itens")
            
            # 4. Salva no BD
            self._save_metrics_to_db(full_name, metrics)
            
            # 5. Atualiza dataset JSON
            dataset = self.dataset.load_dataset()
            for repo in dataset['repositories']:
                if repo['full_name'] == full_name:
                    repo['sonarqube_analyzed'] = True
                    repo['sonarqube_analyzed_at'] = datetime.now().isoformat()
                    repo['sonarqube_metrics'] = metrics
                    break
            self.dataset.save_dataset(dataset)
            
            print(f"  ✅ ANÁLISE CONCLUÍDA COM SUCESSO")
            return True
            
        except Exception as e:
            print(f"  ❌ Erro na análise: {e}")
            return False
            
        finally:
            if temp_dir:
                self._cleanup_temp_dir(temp_dir)


def analyze_single_repo(repo_data: dict, sonar_host: str, sonar_token: str, 
                       dataset_file: str) -> tuple:
    """Função auxiliar para análise paralela"""
    try:
        sonarqube_api = SonarQubeAPI(sonar_host, sonar_token)
        dataset_manager = DatasetManager(dataset_file)
        analyzer = SonarQubeAnalyzer(sonarqube_api, dataset_manager)
        
        success = analyzer.analyze_repository(repo_data)
        return (repo_data['full_name'], success)
        
    except Exception as e:
        print(f"❌ Erro no worker: {e}")
        return (repo_data.get('full_name', 'unknown'), False)


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description='Analisa repositórios do dataset com SonarQube'
    )
    parser.add_argument('--workers', type=int, default=1,
                       help='Número de processos paralelos (padrão: 1)')
    parser.add_argument('--type', choices=['rapid', 'slow', 'all'], default='all',
                       help='Tipo de repositórios para analisar (padrão: all)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limitar número de análises')
    parser.add_argument('--skip-analyzed', action='store_true',
                       help='Pular repositórios já analisados')
    parser.add_argument('--dataset', type=str, default='repositories_dataset.json',
                       help='Arquivo do dataset (padrão: repositories_dataset.json)')
    
    args = parser.parse_args()
    
    print("="*80)
    print("🔬 SCRIPT 2: ANÁLISE SONARQUBE")
    print("="*80)
    
    # Verifica SonarQube
    sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
    sonar_token = os.getenv('SONAR_TOKEN')
    
    if not sonar_token:
        print("❌ ERRO: SONAR_TOKEN não configurado!")
        sys.exit(1)
    
    # Carrega dataset
    dataset_manager = DatasetManager(args.dataset)
    
    # Filtra repositórios
    release_type = None if args.type == 'all' else args.type
    repositories = dataset_manager.get_repositories(release_type=release_type)
    
    if args.skip_analyzed:
        repositories = [r for r in repositories if not r.get('sonarqube_analyzed', False)]
    
    if args.limit:
        repositories = repositories[:args.limit]
    
    print(f"\n📊 Repositórios para analisar: {len(repositories)}")
    print(f"   Tipo: {args.type}")
    print(f"   Workers: {args.workers}")
    print(f"   Skip analyzed: {args.skip_analyzed}\n")
    
    if not repositories:
        print("⚠️  Nenhum repositório para analisar")
        sys.exit(0)
    
    # Análise sequencial ou paralela
    results = []
    
    if args.workers == 1:
        # Sequencial
        sonarqube_api = SonarQubeAPI(sonar_host, sonar_token)
        analyzer = SonarQubeAnalyzer(sonarqube_api, dataset_manager)
        
        for i, repo in enumerate(repositories, 1):
            print(f"\n[{i}/{len(repositories)}]")
            success = analyzer.analyze_repository(repo)
            results.append((repo['full_name'], success))
    
    else:
        # Paralelo
        print(f"🚀 Iniciando {args.workers} workers...\n")
        
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    analyze_single_repo, 
                    repo, sonar_host, sonar_token, args.dataset
                ): repo for repo in repositories
            }
            
            for future in as_completed(futures):
                full_name, success = future.result()
                results.append((full_name, success))
    
    # Relatório final
    successful = sum(1 for _, success in results if success)
    failed = len(results) - successful
    
    print(f"\n{'='*80}")
    print("📊 RELATÓRIO FINAL")
    print(f"{'='*80}")
    print(f"Total analisados: {len(results)}")
    print(f"✅ Bem-sucedidos: {successful}")
    print(f"❌ Falharam: {failed}")
    print(f"{'='*80}\n")
    
    dataset_manager.print_statistics()


if __name__ == "__main__":
    main()
