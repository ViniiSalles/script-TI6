#!/usr/bin/env python3
"""
Script de Recuperação: Extrai métricas SonarQube via API Web

OBJETIVO:
Recuperar métricas de projetos que foram criados no SonarQube mas
as métricas não estão acessíveis via banco de dados PostgreSQL.
Usa a API REST do SonarQube para buscar métricas diretamente.

PRÉ-REQUISITOS:
- SonarQube rodando (docker-compose up -d)
- Token de autenticação configurado no .env
- Arquivo CSV com lista de repositórios

EXECUÇÃO:
python recover_from_sonarqube_api.py --csv slow_release_repos_20251115_053707_analyzed.csv

MÉTRICAS RECUPERADAS (13 do projeto):
- bugs, vulnerabilities, code_smells
- sqale_index (technical debt)
- coverage, duplicated_lines_density
- ncloc, complexity, cognitive_complexity
- reliability_rating, security_rating, sqale_rating
- alert_status (Quality Gate)
"""

import requests
import csv
import os
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class SonarQubeAPIRecovery:
    """Recupera métricas SonarQube via API REST"""
    
    def __init__(self):
        self.base_url = os.getenv('SONAR_HOST', 'http://localhost:9000')
        self.token = os.getenv('SONAR_TOKEN', '')
        
        if not self.token:
            raise ValueError("SONAR_TOKEN não encontrado no .env!")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        # Métricas que queremos extrair (13 do projeto)
        self.metrics = [
            'bugs',
            'vulnerabilities',
            'code_smells',
            'sqale_index',              # Technical debt em minutos
            'coverage',
            'duplicated_lines_density',
            'ncloc',                     # Linhas de código
            'complexity',
            'cognitive_complexity',
            'reliability_rating',
            'security_rating',
            'sqale_rating',              # Maintainability rating
            'alert_status'               # Quality Gate status
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
            status = response.json()
            print(f"✅ SonarQube conectado: {status.get('status', 'UNKNOWN')}")
            return True
        except Exception as e:
            print(f"❌ Erro ao conectar no SonarQube: {e}")
            return False
    
    def get_project_metrics(self, project_key: str) -> Optional[Dict]:
        """
        Busca métricas de um projeto via API
        
        API Endpoint: /api/measures/component
        Retorna: Dict com métricas ou None se falhar
        """
        try:
            url = f"{self.base_url}/api/measures/component"
            params = {
                "component": project_key,
                "metricKeys": ",".join(self.metrics)
            }
            
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            component = data.get('component', {})
            
            # Verifica se projeto existe
            if not component:
                return None
            
            # Extrai métricas
            metrics = {}
            for measure in component.get('measures', []):
                metric_key = measure['metric']
                value = measure.get('value', '')
                
                # Converte tipos conforme necessário
                if metric_key in ['bugs', 'vulnerabilities', 'code_smells', 
                                 'sqale_index', 'ncloc', 'complexity', 'cognitive_complexity']:
                    # Inteiros
                    metrics[metric_key] = int(float(value)) if value else 0
                
                elif metric_key in ['coverage', 'duplicated_lines_density']:
                    # Decimais (percentuais)
                    metrics[metric_key] = round(float(value), 2) if value else 0.0
                
                elif metric_key in ['reliability_rating', 'security_rating', 'sqale_rating']:
                    # Ratings: API retorna número (1.0=A, 2.0=B, etc)
                    rating_map = {1.0: 'A', 2.0: 'B', 3.0: 'C', 4.0: 'D', 5.0: 'E'}
                    metrics[metric_key] = rating_map.get(float(value), 'E') if value else 'E'
                
                else:  # alert_status
                    metrics[metric_key] = value if value else 'NONE'
            
            return metrics
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Projeto não existe no SonarQube
                return None
            else:
                # Outro erro HTTP
                print(f"      ⚠️  HTTP Error {e.response.status_code}")
                return None
        except Exception as e:
            # Erro genérico
            if os.getenv('DEBUG'):
                import traceback
                traceback.print_exc()
            return None
    
    def recover_csv_from_api(self, csv_file: str, dry_run: bool = False):
        """
        Recupera métricas via API e atualiza CSV
        
        Args:
            csv_file: Arquivo CSV para recuperar
            dry_run: Se True, apenas mostra o que seria feito sem modificar
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
        
        # Lê CSV atual
        print(f"\n📂 Lendo CSV: {csv_file}")
        repositories = []
        fieldnames = []
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                repositories = list(reader)
            
            print(f"✅ {len(repositories)} repositórios carregados")
        except Exception as e:
            print(f"❌ Erro ao ler CSV: {e}")
            return
        
        # Identifica repositórios sem métricas
        missing_metrics = []
        has_metrics = []
        
        for i, repo in enumerate(repositories):
            # Verifica se tem métricas SonarQube
            has_any_metric = (
                repo.get('bugs') and repo.get('bugs') != '' or
                repo.get('ncloc') and repo.get('ncloc') != '' or
                repo.get('sonarqube_analyzed') == 'True'
            )
            
            if not has_any_metric or repo.get('bugs') == '':
                missing_metrics.append((i, repo))
            else:
                has_metrics.append(repo)
        
        print(f"\n📊 Status do CSV:")
        print(f"   ✅ Com métricas: {len(has_metrics)}")
        print(f"   ❌ Sem métricas: {len(missing_metrics)}")
        
        if not missing_metrics:
            print("\n✅ Todos os repositórios já têm métricas!")
            return
        
        # Tenta recuperar métricas
        recovered = 0
        not_found = 0
        failed = 0
        
        print(f"\n🔄 Recuperando métricas via API...")
        
        for idx, repo in missing_metrics:
            owner = repo.get('owner', '')
            name = repo.get('name', '')
            project_key = f"{owner}_{name}"
            
            print(f"\n[{recovered + not_found + failed + 1}/{len(missing_metrics)}] {owner}/{name}")
            
            # Busca métricas via API
            metrics = self.get_project_metrics(project_key)
            
            if not metrics:
                print(f"   ⚠️  Projeto não encontrado ou sem métricas no SonarQube")
                not_found += 1
                continue
            
            # Verifica se tem pelo menos uma métrica válida
            if not any(metrics.values()):
                print(f"   ❌ Nenhuma métrica retornada pela API")
                failed += 1
                continue
            
            # Atualiza repositório
            if not dry_run:
                repositories[idx]['sonarqube_analyzed'] = 'True'
                repositories[idx]['sonarqube_analyzed_at'] = datetime.now().isoformat()
                repositories[idx]['bugs'] = metrics.get('bugs', '')
                repositories[idx]['vulnerabilities'] = metrics.get('vulnerabilities', '')
                repositories[idx]['code_smells'] = metrics.get('code_smells', '')
                repositories[idx]['sqale_index'] = metrics.get('sqale_index', '')
                repositories[idx]['coverage'] = metrics.get('coverage', '')
                repositories[idx]['duplicated_lines_density'] = metrics.get('duplicated_lines_density', '')
                repositories[idx]['ncloc'] = metrics.get('ncloc', '')
                repositories[idx]['complexity'] = metrics.get('complexity', '')
                repositories[idx]['cognitive_complexity'] = metrics.get('cognitive_complexity', '')
                repositories[idx]['reliability_rating'] = metrics.get('reliability_rating', '')
                repositories[idx]['security_rating'] = metrics.get('security_rating', '')
                repositories[idx]['sqale_rating'] = metrics.get('sqale_rating', '')
                repositories[idx]['alert_status'] = metrics.get('alert_status', '')
            
            print(f"   ✅ Recuperado: bugs={metrics.get('bugs')}, ncloc={metrics.get('ncloc')}, rating={metrics.get('sqale_rating')}")
            recovered += 1
        
        # Relatório
        print(f"\n{'='*80}")
        print("📊 RELATÓRIO DE RECUPERAÇÃO")
        print(f"{'='*80}")
        print(f"✅ Recuperados: {recovered}")
        print(f"⚠️  Não encontrados: {not_found}")
        print(f"❌ Falharam: {failed}")
        print(f"{'='*80}")
        
        # Salva CSV atualizado
        if not dry_run and recovered > 0:
            output_file = csv_file.replace('.csv', '_api_recovered.csv')
            
            # Garante que todas as colunas de métricas existem no fieldnames
            required_fields = [
                'sonarqube_analyzed', 'sonarqube_analyzed_at',
                'bugs', 'vulnerabilities', 'code_smells', 'sqale_index',
                'coverage', 'duplicated_lines_density', 'ncloc', 
                'complexity', 'cognitive_complexity',
                'reliability_rating', 'security_rating', 'sqale_rating', 'alert_status'
            ]
            
            # Adiciona campos faltantes
            final_fieldnames = list(fieldnames)
            for field in required_fields:
                if field not in final_fieldnames:
                    final_fieldnames.append(field)
            
            try:
                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=final_fieldnames)
                    writer.writeheader()
                    writer.writerows(repositories)
                
                print(f"\n✅ CSV recuperado salvo: {output_file}")
                print(f"   Total de repositórios: {len(repositories)}")
                print(f"   Com métricas agora: {len(has_metrics) + recovered}")
                
            except Exception as e:
                print(f"\n❌ Erro ao salvar CSV: {e}")
        
        elif dry_run:
            print(f"\n💡 Modo DRY-RUN - nenhuma alteração foi feita")
            print(f"   Execute sem --dry-run para salvar as recuperações")


def main():
    parser = argparse.ArgumentParser(
        description='Recupera métricas SonarQube via API REST',
        epilog='Exemplo: python recover_from_sonarqube_api.py --csv repos.csv'
    )
    parser.add_argument('--csv', type=str, required=True,
                       help='Arquivo CSV para recuperar métricas')
    parser.add_argument('--dry-run', action='store_true',
                       help='Apenas mostra o que seria feito, sem modificar')
    
    args = parser.parse_args()
    
    try:
        recovery = SonarQubeAPIRecovery()
        recovery.recover_csv_from_api(args.csv, dry_run=args.dry_run)
    except ValueError as e:
        print(f"\n❌ Erro de configuração: {e}")
        print("   Verifique se SONAR_TOKEN está definido no .env")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Erro de conexão com SonarQube")
        print("   Verifique se o SonarQube está rodando: docker-compose ps")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        if os.getenv('DEBUG'):
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
