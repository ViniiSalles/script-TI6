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
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


class DatasetManager:
    """Gerencia dataset de repositórios (JSON + PostgreSQL)"""
    
    def __init__(self, json_file: str = "repositories_dataset.json", db_config: Optional[dict] = None):
        self.json_file = json_file
        self.db_config = db_config
        self.connection = None
        
        # Cria arquivo JSON se não existir
        if not os.path.exists(json_file):
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
        """Carrega dataset do arquivo JSON"""
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
    
    def save_dataset(self, dataset: dict):
        """Salva dataset no arquivo JSON"""
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
