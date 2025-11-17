#!/usr/bin/env python3
"""
Script Universal de Recuperação: Extrai métricas SonarQube via API

OBJETIVO:
Recuperar métricas de projetos analisados no SonarQube, incluindo:
- Projetos que nunca tiveram métricas recuperadas
- Projetos de análises que falharam
- Todos os projetos existentes no SonarQube

EXECUÇÃO:
python recover_from_sonarqube_api.py --csv arquivo.csv
python recover_from_sonarqube_api.py --csv arquivo.csv --all  # Recupera TODOS os projetos do SonarQube

CARACTERÍSTICAS:
- Mantém valores numéricos como no CSV original (sem conversão)
- Preserva TODAS as colunas do CSV original
- Funciona com qualquer CSV que tenha colunas owner,name
"""

import requests
import csv
import os
import time
import argparse
from datetime import datetime
from typing import Dict, Optional, List
from dotenv import load_dotenv
from sonarqube_validator import sanitize_project_key, validate_repository_data, fix_corrupted_csv_line

load_dotenv()


class SonarQubeAPIRecovery:
    """Recupera métricas SonarQube via API REST"""
    
    def __init__(self):
        self.base_url = os.getenv('SONAR_HOST', 'http://localhost:9000')
        self.token = os.getenv('SONAR_TOKEN', '')
        
        if not self.token:
            raise ValueError("SONAR_TOKEN não encontrado no .env!")
        
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Métricas SonarQube (13 do projeto)
        self.metrics = [
            'bugs', 'vulnerabilities', 'code_smells', 'sqale_index',
            'coverage', 'duplicated_lines_density', 'ncloc', 'complexity',
            'cognitive_complexity', 'reliability_rating', 'security_rating',
            'sqale_rating', 'alert_status'
        ]
    
    def test_connection(self) -> bool:
        """Testa conexão com SonarQube"""
        try:
            response = requests.get(
                f"{self.base_url}/api/system/status",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            print(f"✅ SonarQube conectado: {response.json().get('status', 'UNKNOWN')}")
            return True
        except Exception as e:
            print(f"❌ Erro ao conectar no SonarQube: {e}")
            return False
    
    def get_all_sonarqube_projects(self) -> List[Dict]:
        """Obtém TODOS os projetos do SonarQube (com paginação)"""
        url = f"{self.base_url}/api/components/search_projects"
        all_projects = []
        page = 1
        
        while True:
            try:
                params = {"p": page, "ps": 500}
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                page_projects = data.get('components', [])
                all_projects.extend(page_projects)
                
                total = data.get('paging', {}).get('total', 0)
                
                if len(all_projects) >= total or len(page_projects) == 0:
                    break
                
                page += 1
                time.sleep(0.3)
                
            except Exception as e:
                print(f"⚠️  Erro ao buscar projetos: {e}")
                break
        
        return all_projects
    
    def get_project_metrics(self, project_key: str) -> Optional[Dict]:
        """
        Busca métricas de um projeto via API
        
        IMPORTANTE: Retorna valores EXATAMENTE como vêm da API
        SEM conversão de tipos (mantém formato numérico original)
        """
        try:
            url = f"{self.base_url}/api/measures/component"
            params = {
                "component": project_key,
                "metricKeys": ",".join(self.metrics)
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            component = response.json().get('component', {})
            if not component:
                return None
            
            # Extrai métricas SEM CONVERSÃO (valores numéricos originais)
            metrics = {}
            for measure in component.get('measures', []):
                metric_key = measure['metric']
                value = measure.get('value', '')
                # Mantém o valor EXATAMENTE como vem da API
                metrics[metric_key] = value
            
            return metrics if metrics else None
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None  # Projeto não existe
            return None
        except Exception:
            return None
    
    
    def recover_csv(self, csv_file: str, recover_all: bool = False, dry_run: bool = False):
        """
        Recupera métricas via API e atualiza CSV
        
        Args:
            csv_file: Arquivo CSV para processar
            recover_all: Se True, recupera TODOS os projetos do SonarQube (não só os do CSV)
            dry_run: Se True, apenas simula sem modificar o CSV
        """
        print("="*80)
        print("🔧 RECUPERAÇÃO DE MÉTRICAS VIA API SONARQUBE")
        print("="*80)
        
        if not os.path.exists(csv_file):
            print(f"❌ Arquivo não encontrado: {csv_file}")
            return
        
        # Testa conexão
        if not self.test_connection():
            return
        
        # Lê CSV original
        print(f"\n📂 Lendo CSV: {csv_file}")
        
        corrupted_lines = 0
        fixed_lines = 0
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                original_fieldnames = list(reader.fieldnames)  # Preserva ordem original
                repositories = []
                
                # PROTEÇÃO: Valida e corrige linhas durante leitura
                for i, row in enumerate(reader, start=2):  # start=2 (header=1)
                    # Detecta linhas corrompidas
                    if not row.get('owner') or not row.get('name'):
                        corrupted_lines += 1
                        
                        # Tenta corrigir
                        fixed = fix_corrupted_csv_line(row)
                        if fixed:
                            row = fixed
                            fixed_lines += 1
                            print(f"   🔧 Linha {i} corrigida: {row['owner']}/{row['name']}")
                        else:
                            print(f"   ⚠️  Linha {i} inválida (owner ou name vazio), será ignorada")
                    
                    repositories.append(row)
            
            print(f"✅ {len(repositories)} repositórios no CSV")
            print(f"📋 Colunas: {len(original_fieldnames)} (preservadas)")
            
            if corrupted_lines > 0:
                print(f"⚠️  {corrupted_lines} linhas corrompidas detectadas")
                print(f"🔧 {fixed_lines} linhas corrigidas automaticamente")
                
        except Exception as e:
            print(f"❌ Erro ao ler CSV: {e}")
            return
        
        # Modo 1: Recuperar apenas repos do CSV sem métricas
        if not recover_all:
            targets = []
            for i, repo in enumerate(repositories):
                # Verifica se NÃO tem métricas
                has_metrics = (
                    repo.get('bugs') and repo.get('bugs') != '' or
                    repo.get('sonarqube_analyzed') == 'True'
                )
                if not has_metrics:
                    targets.append((i, repo))
            
            print(f"\n📊 Status:")
            print(f"   ✅ Com métricas: {len(repositories) - len(targets)}")
            print(f"   ❌ Sem métricas: {len(targets)}")
            
            if not targets:
                print("\n✅ Todos os repositórios já têm métricas!")
                return
            
            repos_to_process = targets
        
        # Modo 2: Recuperar TODOS os projetos do SonarQube
        else:
            print(f"\n🔍 Buscando TODOS os projetos do SonarQube...")
            all_sonar_projects = self.get_all_sonarqube_projects()
            print(f"✅ {len(all_sonar_projects)} projetos encontrados no SonarQube\n")
            
            # Identifica projetos do SonarQube que NÃO estão no CSV
            csv_keys = {f"{r.get('owner', '')}_{r.get('name', '')}" for r in repositories}
            missing_projects = []
            
            for project in all_sonar_projects:
                if project['key'] not in csv_keys:
                    # Extrai owner/name do project_key
                    parts = project['key'].split('_', 1)
                    if len(parts) == 2:
                        missing_projects.append({
                            'owner': parts[0],
                            'name': parts[1],
                            'project_key': project['key']
                        })
            
            print(f"📊 Análise:")
            print(f"   📄 Repositórios no CSV: {len(repositories)}")
            print(f"   🆕 Projetos extras no SonarQube: {len(missing_projects)}")
            
            # Processa repos do CSV sem métricas + projetos extras
            csv_targets = []
            for i, repo in enumerate(repositories):
                has_metrics = (
                    repo.get('bugs') and repo.get('bugs') != '' or
                    repo.get('sonarqube_analyzed') == 'True'
                )
                if not has_metrics:
                    csv_targets.append((i, repo))
            
            print(f"   ❌ Sem métricas no CSV: {len(csv_targets)}")
            
            repos_to_process = csv_targets + [(None, p) for p in missing_projects]
        
        # Recupera métricas
        print(f"\n🔄 Recuperando métricas de {len(repos_to_process)} repositórios...\n")
        
        recovered = 0
        not_found = 0
        new_repos = []  # Para projetos extras do SonarQube
        
        for idx, repo in repos_to_process:
            owner = repo.get('owner', '')
            name = repo.get('name', '')
            
            # PROTEÇÃO 1: Tenta corrigir dados corrompidos
            if not owner or not name:
                fixed = fix_corrupted_csv_line(repo)
                if fixed:
                    owner = fixed['owner']
                    name = fixed['name']
                    print(f"🔧 Dados corrompidos corrigidos: {owner}/{name}")
                else:
                    print("❌ Dados inválidos, pulando...")
                    not_found += 1
                    continue
            
            # PROTEÇÃO 2: Sanitiza project_key
            project_key = sanitize_project_key(owner, name)
            
            print(f"[{recovered + not_found + 1}/{len(repos_to_process)}] {owner}/{name}", end=" ")
            
            # Busca métricas via API
            metrics = self.get_project_metrics(project_key)
            
            if not metrics:
                print("⚠️  Não encontrado")
                not_found += 1
                continue
            
            # Atualiza repositório (SEM conversão de valores)
            if not dry_run:
                if idx is not None:  # Repo existente no CSV
                    repositories[idx]['sonarqube_analyzed'] = 'True'
                    repositories[idx]['sonarqube_analyzed_at'] = datetime.now().isoformat()
                    for metric_key, value in metrics.items():
                        repositories[idx][metric_key] = value
                else:  # Projeto novo do SonarQube
                    new_repo = {field: '' for field in original_fieldnames}
                    new_repo['owner'] = owner
                    new_repo['name'] = name
                    new_repo['sonarqube_analyzed'] = 'True'
                    new_repo['sonarqube_analyzed_at'] = datetime.now().isoformat()
                    for metric_key, value in metrics.items():
                        new_repo[metric_key] = value
                    new_repos.append(new_repo)
            
            print(f"✅ bugs={metrics.get('bugs', '?')}, ncloc={metrics.get('ncloc', '?')}")
            recovered += 1
        
        # Relatório
        print(f"\n{'='*80}")
        print("📊 RELATÓRIO")
        print(f"{'='*80}")
        print(f"✅ Recuperados: {recovered}")
        print(f"⚠️  Não encontrados: {not_found}")
        if new_repos:
            print(f"🆕 Projetos novos adicionados: {len(new_repos)}")
        print(f"{'='*80}")
        
        # Salva CSV (mantém EXATAMENTE as mesmas colunas)
        if not dry_run and recovered > 0:
            output_file = csv_file.replace('.csv', '_recovered.csv')
            
            # Combina repos existentes + novos (se houver)
            all_repos = repositories + new_repos
            
            try:
                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=original_fieldnames)
                    writer.writeheader()
                    
                    for repo in all_repos:
                        # Garante que só escreve colunas que existem no original
                        row = {field: repo.get(field, '') for field in original_fieldnames}
                        writer.writerow(row)
                
                print(f"\n✅ CSV salvo: {output_file}")
                print(f"   Total de repositórios: {len(all_repos)}")
                print(f"   Colunas preservadas: {len(original_fieldnames)}")
                
            except Exception as e:
                print(f"\n❌ Erro ao salvar CSV: {e}")
        
        elif dry_run:
            print(f"\n💡 Modo DRY-RUN - Execute sem --dry-run para salvar")


def main():
    parser = argparse.ArgumentParser(
        description='Recupera métricas SonarQube via API REST',
        epilog='Exemplos:\n'
               '  python recover_from_sonarqube_api.py --csv repos.csv\n'
               '  python recover_from_sonarqube_api.py --csv repos.csv --all',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--csv', type=str, required=True,
                       help='Arquivo CSV para processar')
    parser.add_argument('--all', action='store_true',
                       help='Recupera TODOS os projetos do SonarQube (não só os do CSV)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Simula sem modificar o CSV')
    
    args = parser.parse_args()
    
    try:
        recovery = SonarQubeAPIRecovery()
        recovery.recover_csv(args.csv, recover_all=args.all, dry_run=args.dry_run)
    except ValueError as e:
        print(f"\n❌ Erro de configuração: {e}")
        print("   Verifique se SONAR_TOKEN está definido no .env")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Erro de conexão com SonarQube")
        print("   Verifique se o SonarQube está rodando: docker-compose ps")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
