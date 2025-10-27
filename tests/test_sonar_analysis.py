#!/usr/bin/env python3
"""
Script de Teste - Análise SonarQube de 5 Repositórios
Versão simplificada para testes rápidos
"""

import os
import sys
import json
import time
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

# Carrega variáveis de ambiente
load_dotenv()

class SonarQubeAnalyzer:
    """Classe para executar análises SonarQube"""
    
    def __init__(self, sonar_host, sonar_token):
        self.sonar_host = sonar_host
        self.sonar_token = sonar_token
        self.session = requests.Session()
        self.session.auth = (sonar_token, '')
    
    def create_project(self, project_key, project_name):
        """Cria um projeto no SonarQube"""
        print(f"   Criando projeto no SonarQube: {project_key}")
        
        url = f"{self.sonar_host}/api/projects/create"
        data = {
            'project': project_key,
            'name': project_name
        }
        
        response = self.session.post(url, data=data)
        
        if response.status_code == 200:
            print(f"   ✅ Projeto criado com sucesso")
            return True
        elif response.status_code == 400 and 'already exists' in response.text:
            print(f"   ℹ️  Projeto já existe, continuando...")
            return True
        else:
            print(f"   ⚠️  Erro ao criar projeto: {response.status_code}")
            return False
    
    def run_scanner(self, repo_path, project_key, project_name):
        """Executa o SonarScanner via Docker"""
        print(f"   Executando análise SonarQube...")
        
        # Converte path para formato Docker
        repo_path_abs = Path(repo_path).resolve()
        
        # Comando Docker para executar o scanner
        docker_cmd = [
            'docker', 'run',
            '--rm',
            '--network', 'host',
            '-v', f'{repo_path_abs}:/usr/src',
            '-e', f'SONAR_HOST_URL={self.sonar_host}',
            '-e', f'SONAR_TOKEN={self.sonar_token}',
            'sonarsource/sonar-scanner-cli',
            '-Dsonar.projectKey=' + project_key,
            '-Dsonar.projectName=' + project_name,
            '-Dsonar.sources=.',
            '-Dsonar.sourceEncoding=UTF-8',
            '-Dsonar.java.binaries=.',
            '-Dsonar.exclusions=**/*.class,**/node_modules/**,**/dist/**,**/build/**,**/target/**'
        ]
        
        try:
            result = subprocess.run(
                docker_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutos timeout
            )
            
            if result.returncode == 0:
                print(f"   ✅ Análise concluída com sucesso")
                return True
            else:
                print(f"   ⚠️  Análise falhou (código: {result.returncode})")
                if result.stderr:
                    print(f"   Erro: {result.stderr[:200]}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"   ⏱️  Análise excedeu o tempo limite de 10 minutos")
            return False
        except Exception as e:
            print(f"   ❌ Erro ao executar scanner: {e}")
            return False
    
    def get_metrics(self, project_key):
        """Obtém métricas do projeto"""
        print(f"   Coletando métricas do SonarQube...")
        
        # Aguarda mais tempo para garantir que a análise foi processada
        print(f"   Aguardando processamento (15 segundos)...")
        time.sleep(15)
        
        url = f"{self.sonar_host}/api/measures/component"
        params = {
            'component': project_key,
            'metricKeys': 'ncloc,complexity,cognitive_complexity,violations,bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density'
        }
        
        try:
            response = self.session.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                measures = {}
                
                for measure in data.get('component', {}).get('measures', []):
                    measures[measure['metric']] = measure.get('value', '0')
                
                print(f"   ✅ Métricas coletadas: {len(measures)} métricas")
                return measures
            else:
                print(f"   ⚠️  Erro ao obter métricas: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"   ❌ Erro ao coletar métricas: {e}")
            return {}


class DatabaseManager:
    """Gerencia conexões e operações do banco de dados"""
    
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        self.create_tables()
    
    def create_tables(self):
        """Cria as tabelas necessárias"""
        cursor = self.conn.cursor()
        
        # Tabela de repositórios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                id SERIAL PRIMARY KEY,
                name_with_owner VARCHAR(255) UNIQUE NOT NULL,
                url TEXT,
                stars INTEGER,
                forks INTEGER,
                release_count INTEGER,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de métricas SonarQube
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sonar_metrics (
                id SERIAL PRIMARY KEY,
                repository_id INTEGER REFERENCES repositories(id),
                ncloc INTEGER,
                complexity INTEGER,
                cognitive_complexity INTEGER,
                violations INTEGER,
                bugs INTEGER,
                vulnerabilities INTEGER,
                code_smells INTEGER,
                coverage DECIMAL(5,2),
                duplicated_lines_density DECIMAL(5,2),
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        cursor.close()
        print("✅ Tabelas criadas/verificadas com sucesso")
    
    def save_repository(self, repo_data):
        """Salva dados do repositório"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO repositories (name_with_owner, url, stars, forks, release_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name_with_owner) DO UPDATE
            SET url = EXCLUDED.url,
                stars = EXCLUDED.stars,
                forks = EXCLUDED.forks,
                release_count = EXCLUDED.release_count,
                analyzed_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            repo_data['nameWithOwner'],
            repo_data['url'],
            repo_data['stargazerCount'],
            repo_data['forkCount'],
            repo_data['releaseCount']
        ))
        
        repo_id = cursor.fetchone()[0]
        self.conn.commit()
        cursor.close()
        
        return repo_id
    
    def save_metrics(self, repo_id, metrics):
        """Salva métricas do SonarQube"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO sonar_metrics (
                repository_id, ncloc, complexity, cognitive_complexity,
                violations, bugs, vulnerabilities, code_smells,
                coverage, duplicated_lines_density
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            repo_id,
            int(metrics.get('ncloc', 0)),
            int(metrics.get('complexity', 0)),
            int(metrics.get('cognitive_complexity', 0)),
            int(metrics.get('violations', 0)),
            int(metrics.get('bugs', 0)),
            int(metrics.get('vulnerabilities', 0)),
            int(metrics.get('code_smells', 0)),
            float(metrics.get('coverage', 0)),
            float(metrics.get('duplicated_lines_density', 0))
        ))
        
        self.conn.commit()
        cursor.close()
    
    def close(self):
        """Fecha conexão com o banco"""
        self.conn.close()


def clone_repository(repo_url, temp_dir):
    """Clona um repositório do GitHub"""
    print(f"   Clonando repositório...")
    
    try:
        result = subprocess.run(
            ['git', 'clone', '--depth', '1', repo_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutos
        )
        
        if result.returncode == 0:
            print(f"   ✅ Repositório clonado com sucesso")
            return True
        else:
            print(f"   ❌ Erro ao clonar: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"   ⏱️  Clone excedeu o tempo limite")
        return False
    except Exception as e:
        print(f"   ❌ Erro ao clonar: {e}")
        return False


def main():
    """Função principal"""
    print("=" * 80)
    print("SCRIPT DE TESTE - ANÁLISE DE 5 REPOSITÓRIOS")
    print("=" * 80)
    
    # Carrega repositórios do JSON filtrado (ajusta caminho para a nova estrutura)
    script_dir = Path(__file__).parent.parent
    json_file = script_dir / 'data' / 'processed' / 'jsonFiltrado_filtered.json'
    
    print(f"\nCarregando repositórios de: {json_file}")
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            all_repos = json.load(f)
        
        # Pega apenas os 5 primeiros
        repos_to_analyze = all_repos[:5]
        
        print(f"✅ Carregados {len(all_repos)} repositórios do arquivo")
        print(f"📊 Analisando apenas os primeiros 5 para teste\n")
        
    except Exception as e:
        print(f"❌ Erro ao carregar arquivo JSON: {e}")
        sys.exit(1)
    
    # Inicializa componentes
    sonar = SonarQubeAnalyzer(
        os.getenv('SONAR_HOST'),
        os.getenv('SONAR_TOKEN')
    )
    
    db = DatabaseManager()
    
    # Estatísticas
    success_count = 0
    failed_count = 0
    
    print("=" * 80)
    print("INICIANDO ANÁLISES")
    print("=" * 80)
    
    # Processa cada repositório
    for idx, repo in enumerate(repos_to_analyze, 1):
        print(f"\n[{idx}/5] Processando: {repo['nameWithOwner']}")
        print("-" * 80)
        
        temp_dir = None
        
        try:
            # Cria diretório temporário
            temp_dir = tempfile.mkdtemp(prefix='sonar_test_')
            
            # Clona repositório
            if not clone_repository(repo['url'], temp_dir):
                print(f"   ⚠️  Pulando repositório devido a erro no clone")
                failed_count += 1
                continue
            
            # Prepara identificadores para o SonarQube
            project_key = repo['nameWithOwner'].replace('/', '_')
            project_name = repo['nameWithOwner']
            
            # Cria projeto no SonarQube
            if not sonar.create_project(project_key, project_name):
                print(f"   ⚠️  Pulando repositório devido a erro na criação do projeto")
                failed_count += 1
                continue
            
            # Executa análise
            if not sonar.run_scanner(temp_dir, project_key, project_name):
                print(f"   ⚠️  Pulando repositório devido a erro na análise")
                failed_count += 1
                continue
            
            # Coleta métricas
            metrics = sonar.get_metrics(project_key)
            
            if not metrics:
                print(f"   ⚠️  Nenhuma métrica coletada - tentando novamente...")
                time.sleep(10)
                metrics = sonar.get_metrics(project_key)
            
            if not metrics:
                print(f"   ⚠️  Nenhuma métrica disponível após nova tentativa")
                # Salva repositório mesmo sem métricas
                repo_id = db.save_repository(repo)
                failed_count += 1
                continue
            
            # Salva no banco de dados
            print(f"   Salvando dados no banco...")
            repo_id = db.save_repository(repo)
            db.save_metrics(repo_id, metrics)
            print(f"   ✅ Dados salvos com sucesso!")
            
            success_count += 1
            
            # Exibe resumo das métricas
            print(f"\n   📊 Resumo das Métricas:")
            print(f"      • Linhas de código: {metrics.get('ncloc', 'N/A')}")
            print(f"      • Bugs: {metrics.get('bugs', 'N/A')}")
            print(f"      • Vulnerabilidades: {metrics.get('vulnerabilities', 'N/A')}")
            print(f"      • Code Smells: {metrics.get('code_smells', 'N/A')}")
            print(f"      • Complexidade: {metrics.get('complexity', 'N/A')}")
            
        except Exception as e:
            print(f"   ❌ Erro inesperado: {e}")
            failed_count += 1
            
        finally:
            # Limpa diretório temporário
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"   🗑️  Diretório temporário removido")
                except:
                    pass
    
    # Fecha conexão com banco
    db.close()
    
    # Relatório final
    print("\n" + "=" * 80)
    print("RELATÓRIO FINAL")
    print("=" * 80)
    print(f"✅ Análises bem-sucedidas: {success_count}")
    print(f"❌ Análises falhadas: {failed_count}")
    print(f"📊 Total processado: {success_count + failed_count}/5")
    print("=" * 80)
    
    print(f"\n💾 Os dados foram salvos no banco de dados PostgreSQL")
    print(f"🔍 Você pode consultar as tabelas 'repositories' e 'sonar_metrics'")


if __name__ == "__main__":
    main()
