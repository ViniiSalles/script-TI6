#!/usr/bin/env python3
"""
Módulo para gerenciamento de dataset de repositórios

Fornece funcionalidades para:
- Salvar/carregar repositórios em JSON
- Sincronizar com banco de dados PostgreSQL
- Evitar duplicatas
- Filtrar repositórios por tipo (rapid/slow)
"""

import json
import os
import csv
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


class DatasetManager:
    """Gerencia dataset de repositórios (JSON, CSV + PostgreSQL)"""
    
    def __init__(self, json_file: str = "repositories_dataset.json", db_config: Optional[dict] = None):
        self.json_file = json_file
        self.db_config = db_config
        self.connection = None
        self.is_csv = json_file.endswith('.csv')
        
        # Cria arquivo JSON se não existir (apenas para JSON)
        if not self.is_csv and not os.path.exists(json_file):
            self._create_empty_dataset()
    
    def _create_empty_dataset(self):
        """Cria arquivo JSON vazio com estrutura inicial"""
        dataset = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_repositories": 0,
                "rapid_releases_count": 0,
                "slow_releases_count": 0
            },
            "repositories": []
        }
        
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Dataset vazio criado: {self.json_file}")
    
    def load_dataset(self) -> dict:
        """Carrega dataset do arquivo JSON ou CSV"""
        if self.is_csv:
            return self._load_from_csv()
        
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Erro ao carregar dataset: {e}")
            return {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "total_repositories": 0,
                    "rapid_releases_count": 0,
                    "slow_releases_count": 0
                },
                "repositories": []
            }
    
    def _load_from_csv(self) -> dict:
        """Carrega dataset de arquivo CSV"""
        try:
            # Se existe arquivo _analyzed.csv, carrega dele (mantém análises anteriores)
            analyzed_file = self.json_file.replace('.csv', '_analyzed.csv')
            csv_to_load = analyzed_file if os.path.exists(analyzed_file) else self.json_file
            
            if csv_to_load == analyzed_file:
                print(f"📂 Carregando análises anteriores de: {analyzed_file}")
            
            repositories = []
            with open(csv_to_load, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Converte CSV para formato do dataset
                    repo = {
                        'owner': row.get('owner', ''),
                        'name': row.get('name', ''),
                        'full_name': f"{row.get('owner', '')}/{row.get('name', '')}",
                        'stargazer_count': int(row.get('stars', row.get('stargazer_count', 0))),
                        'fork_count': int(row.get('forks', row.get('fork_count', 0))),
                        'language': row.get('language', ''),
                        'total_releases': int(row.get('release_count', row.get('total_releases', 0))),
                        'avg_release_interval_days': float(row.get('median_release_interval', row.get('avg_release_interval_days', 0))),
                        'release_type': row.get('release_type', '').lower(),
                        'collaborator_count': int(row.get('contributors', row.get('collaborator_count', 0))),
                        'distinct_releases_count': int(row.get('release_count', row.get('total_releases', 0))),
                        'collected_at': datetime.now().isoformat(),
                        'sonarqube_analyzed': row.get('sonarqube_analyzed', 'False') == 'True',
                        'sonarqube_analyzed_at': row.get('sonarqube_analyzed_at', '')
                    }
                    
                    # Carrega métricas SonarQube se existirem no CSV
                    if row.get('bugs') or row.get('ncloc'):
                        repo['sonarqube_metrics'] = {
                            'bugs': int(row.get('bugs', 0)) if row.get('bugs') else 0,
                            'vulnerabilities': int(row.get('vulnerabilities', 0)) if row.get('vulnerabilities') else 0,
                            'code_smells': int(row.get('code_smells', 0)) if row.get('code_smells') else 0,
                            'sqale_index': int(row.get('sqale_index', 0)) if row.get('sqale_index') else 0,
                            'coverage': float(row.get('coverage', 0)) if row.get('coverage') else 0.0,
                            'duplicated_lines_density': float(row.get('duplicated_lines_density', 0)) if row.get('duplicated_lines_density') else 0.0,
                            'ncloc': int(row.get('ncloc', 0)) if row.get('ncloc') else 0,
                            'complexity': int(row.get('complexity', 0)) if row.get('complexity') else 0,
                            'cognitive_complexity': int(row.get('cognitive_complexity', 0)) if row.get('cognitive_complexity') else 0,
                            'reliability_rating': row.get('reliability_rating', ''),
                            'security_rating': row.get('security_rating', ''),
                            'sqale_rating': row.get('sqale_rating', ''),
                            'alert_status': row.get('alert_status', '')
                        }
                    
                    repositories.append(repo)
            
            return {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "total_repositories": len(repositories),
                    "rapid_releases_count": sum(1 for r in repositories if r['release_type'] == 'rapid'),
                    "slow_releases_count": sum(1 for r in repositories if r['release_type'] == 'slow')
                },
                "repositories": repositories
            }
        except Exception as e:
            print(f"❌ Erro ao carregar CSV: {e}")
            return {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "total_repositories": 0,
                    "rapid_releases_count": 0,
                    "slow_releases_count": 0
                },
                "repositories": []
            }
    
    def save_dataset(self, dataset: dict):
        """Salva dataset no arquivo JSON ou CSV"""
        if self.is_csv:
            return self._save_to_csv_with_analysis(dataset)
        
        try:
            # Atualiza metadados
            dataset["metadata"]["last_updated"] = datetime.now().isoformat()
            dataset["metadata"]["total_repositories"] = len(dataset["repositories"])
            dataset["metadata"]["rapid_releases_count"] = sum(
                1 for repo in dataset["repositories"] if repo.get("release_type") == "rapid"
            )
            dataset["metadata"]["slow_releases_count"] = sum(
                1 for repo in dataset["repositories"] if repo.get("release_type") == "slow"
            )
            
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(dataset, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Dataset salvo: {self.json_file}")
            return True
        except Exception as e:
            print(f"❌ Erro ao salvar dataset: {e}")
            return False
    
    def _save_to_csv_with_analysis(self, dataset: dict):
        """Salva dataset CSV com informações de análise"""
        try:
            # Cria novo arquivo CSV com análises
            output_file = self.json_file.replace('.csv', '_analyzed.csv')
            
            repositories = dataset['repositories']
            if not repositories:
                return False
            
            # Define campos para CSV incluindo análise
            fields = [
                'owner', 'name', 'full_name', 'stargazer_count', 'fork_count', 
                'language', 'total_releases', 'avg_release_interval_days', 
                'release_type', 'collaborator_count', 'sonarqube_analyzed',
                'sonarqube_analyzed_at', 
                # Métricas SonarQube (13 campos)
                'bugs', 'vulnerabilities', 'code_smells', 'sqale_index',
                'coverage', 'duplicated_lines_density', 'ncloc', 'complexity',
                'cognitive_complexity', 'reliability_rating', 'security_rating',
                'sqale_rating', 'alert_status'
            ]
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                
                for repo in repositories:
                    row = repo.copy()
                    # Adiciona métricas do SonarQube se existirem
                    if 'sonarqube_metrics' in repo:
                        metrics = repo['sonarqube_metrics']
                        row.update({
                            'bugs': metrics.get('bugs', ''),
                            'vulnerabilities': metrics.get('vulnerabilities', ''),
                            'code_smells': metrics.get('code_smells', ''),
                            'sqale_index': metrics.get('sqale_index', ''),
                            'coverage': metrics.get('coverage', ''),
                            'duplicated_lines_density': metrics.get('duplicated_lines_density', ''),
                            'ncloc': metrics.get('ncloc', ''),
                            'complexity': metrics.get('complexity', ''),
                            'cognitive_complexity': metrics.get('cognitive_complexity', ''),
                            'reliability_rating': metrics.get('reliability_rating', ''),
                            'security_rating': metrics.get('security_rating', ''),
                            'sqale_rating': metrics.get('sqale_rating', ''),
                            'alert_status': metrics.get('alert_status', '')
                        })
                    writer.writerow(row)
            
            print(f"✅ Dataset com análises salvo: {output_file}")
            return True
        except Exception as e:
            print(f"❌ Erro ao salvar CSV com análises: {e}")
            return False
    
    def add_repository(self, repo_data: dict) -> bool:
        """
        Adiciona repositório ao dataset (JSON e BD)
        Retorna True se adicionado, False se já existia
        """
        dataset = self.load_dataset()
        
        # Verifica duplicata
        full_name = repo_data.get('full_name')
        if any(repo['full_name'] == full_name for repo in dataset['repositories']):
            print(f"⚠️  Repositório {full_name} já existe no dataset")
            return False
        
        # Adiciona ao JSON
        dataset['repositories'].append(repo_data)
        self.save_dataset(dataset)
        
        # Adiciona ao BD (se disponível)
        if self.db_config:
            self._save_to_database(repo_data)
        
        print(f"✅ Repositório {full_name} adicionado ao dataset")
        return True
    
    def get_repositories(self, release_type: Optional[str] = None, 
                        limit: Optional[int] = None) -> List[dict]:
        """
        Retorna repositórios do dataset
        
        Args:
            release_type: 'rapid', 'slow' ou None (todos)
            limit: Número máximo de repositórios
        """
        dataset = self.load_dataset()
        repos = dataset['repositories']
        
        # Filtra por tipo
        if release_type:
            repos = [r for r in repos if r.get('release_type') == release_type]
        
        # Aplica limite
        if limit:
            repos = repos[:limit]
        
        return repos
    
    def get_repository(self, owner: str, name: str) -> Optional[dict]:
        """Busca repositório específico no dataset"""
        dataset = self.load_dataset()
        full_name = f"{owner}/{name}"
        
        for repo in dataset['repositories']:
            if repo['full_name'] == full_name:
                return repo
        
        return None
    
    def repository_exists(self, owner: str, name: str) -> bool:
        """Verifica se repositório já está no dataset"""
        return self.get_repository(owner, name) is not None
    
    def get_statistics(self) -> dict:
        """Retorna estatísticas do dataset"""
        dataset = self.load_dataset()
        
        repos = dataset['repositories']
        rapid_repos = [r for r in repos if r.get('release_type') == 'rapid']
        slow_repos = [r for r in repos if r.get('release_type') == 'slow']
        
        stats = {
            "total": len(repos),
            "rapid": len(rapid_repos),
            "slow": len(slow_repos),
            "metadata": dataset['metadata']
        }
        
        if rapid_repos:
            stats["rapid_avg_interval"] = sum(
                r.get('avg_release_interval_days', 0) for r in rapid_repos
            ) / len(rapid_repos)
            stats["rapid_avg_contributors"] = sum(
                r.get('collaborator_count', 0) for r in rapid_repos
            ) / len(rapid_repos)
        
        if slow_repos:
            stats["slow_avg_interval"] = sum(
                r.get('avg_release_interval_days', 0) for r in slow_repos
            ) / len(slow_repos)
            stats["slow_avg_contributors"] = sum(
                r.get('collaborator_count', 0) for r in slow_repos
            ) / len(slow_repos)
        
        return stats
    
    def _save_to_database(self, repo_data: dict) -> bool:
        """Salva repositório no banco de dados"""
        if not self.connection:
            try:
                self.connection = psycopg2.connect(**self.db_config)
                self.connection.autocommit = True
            except Exception as e:
                print(f"⚠️  Não foi possível conectar ao BD: {e}")
                return False
        
        sql = """
        INSERT INTO research_repositories (
            owner, name, full_name, stargazer_count, fork_count, language,
            total_releases, avg_release_interval_days, release_type,
            collaborator_count, distinct_releases_count
        ) VALUES (
            %(owner)s, %(name)s, %(full_name)s, %(stargazer_count)s, %(fork_count)s, %(language)s,
            %(total_releases)s, %(avg_release_interval_days)s, %(release_type)s,
            %(collaborator_count)s, %(distinct_releases_count)s
        )
        ON CONFLICT (full_name) DO NOTHING
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, repo_data)
            return True
        except Exception as e:
            print(f"⚠️  Erro ao salvar no BD: {e}")
            return False
    
    def export_to_csv(self, output_file: str = "repositories_dataset.csv"):
        """Exporta dataset para CSV"""
        import csv
        
        dataset = self.load_dataset()
        repos = dataset['repositories']
        
        if not repos:
            print("⚠️  Dataset vazio, nada para exportar")
            return False
        
        # Define campos para CSV
        fields = [
            'full_name', 'owner', 'name', 'release_type', 'language',
            'stargazer_count', 'fork_count', 'total_releases',
            'avg_release_interval_days', 'collaborator_count',
        ]
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(repos)
            
            print(f"✅ Dataset exportado para CSV: {output_file}")
            return True
        except Exception as e:
            print(f"❌ Erro ao exportar CSV: {e}")
            return False
    
    def print_statistics(self):
        """Exibe estatísticas do dataset"""
        stats = self.get_statistics()
        
        print(f"\n{'='*80}")
        print("📊 ESTATÍSTICAS DO DATASET")
        print(f"{'='*80}")
        print(f"Total de repositórios: {stats['total']}")
        print(f"  • Rapid Releases: {stats['rapid']}")
        print(f"  • Slow Releases: {stats['slow']}")
        
        if stats.get('rapid_avg_interval'):
            print(f"\nRapid Releases (média):")
            print(f"  • Intervalo: {stats['rapid_avg_interval']:.1f} dias")
            print(f"  • Contribuidores: {stats['rapid_avg_contributors']:.0f}")
        
        if stats.get('slow_avg_interval'):
            print(f"\nSlow Releases (média):")
            print(f"  • Intervalo: {stats['slow_avg_interval']:.1f} dias")
            print(f"  • Contribuidores: {stats['slow_avg_contributors']:.0f}")
        
        print(f"\nÚltima atualização: {stats['metadata']['last_updated']}")
        print(f"{'='*80}\n")
    
    def close(self):
        """Fecha conexão com banco de dados"""
        if self.connection:
            self.connection.close()
            print("Conexão com BD fechada")


def main():
    """Função de teste do módulo"""
    print("=== Teste do DatasetManager ===\n")
    
    # Cria manager
    manager = DatasetManager("test_dataset.json")
    
    # Adiciona repositórios de teste
    test_repos = [
        {
            "owner": "kubernetes",
            "name": "kubernetes",
            "full_name": "kubernetes/kubernetes",
            "release_type": "rapid",
            "stargazer_count": 100000,
            "fork_count": 50000,
            "language": "Go",
            "total_releases": 761,
            "avg_release_interval_days": 11.3,
            "collaborator_count": 547300,
            "distinct_releases_count": 761,
        }
    ]
    
    for repo in test_repos:
        manager.add_repository(repo)
    
    # Exibe estatísticas
    manager.print_statistics()
    
    # Lista repositórios rapid
    rapid_repos = manager.get_repositories(release_type='rapid')
    print(f"Repositórios Rapid: {len(rapid_repos)}")
    
    # Exporta para CSV
    manager.export_to_csv("test_dataset.csv")


if __name__ == "__main__":
    main()
