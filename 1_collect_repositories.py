#!/usr/bin/env python3
"""
Script 1: Coleta e Filtragem de Repositórios

OBJETIVO:
Buscar repositórios no GitHub, aplicar filtros e salvar no dataset para análise posterior.

FILTROS APLICADOS:
- > 19 releases
- > 19 contribuidores
- Intervalo entre releases: 5-35 dias (RAPID) OU > 60 dias (SLOW)

SAÍDA:
- repositories_dataset.json (arquivo JSON com todos os repositórios)
- Opcionalmente salva no PostgreSQL

EXECUÇÃO:
python 1_collect_repositories.py --rapid 50 --slow 50

OPÇÕES:
--rapid N     : Número de repositórios Rapid Release desejados
--slow N      : Número de repositórios Slow Release desejados
--max-search N: Máximo de repositórios para buscar (padrão: 500)
"""

import os
import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict

from dotenv import load_dotenv

# Importa classes do script principal
from utils import GitHubAPI
from dataset_manager import DatasetManager

# Carrega variáveis de ambiente
load_dotenv()


class RepositoryCollector:
    """Coleta e filtra repositórios do GitHub"""
    
    def __init__(self, github_api: GitHubAPI, dataset_manager: DatasetManager):
        self.github_api = github_api
        self.dataset = dataset_manager
        
    def _calculate_avg_release_interval(self, releases_nodes: List[dict]) -> float:
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
        
        dates.sort(reverse=True)
        intervals = []
        
        for i in range(len(dates) - 1):
            interval = (dates[i] - dates[i + 1]).days
            if interval > 0:
                intervals.append(interval)
        
        return sum(intervals) / len(intervals) if intervals else None
        
    def filter_and_collect_repository(self, owner: str, name: str) -> bool:
        """
        Filtra e coleta um repositório
        Retorna True se aprovado e adicionado, False caso contrário
        """
        full_name = f"{owner}/{name}"
        
        # Verifica se já existe no dataset
        if self.dataset.repository_exists(owner, name):
            print(f"⏭️  {full_name} já está no dataset")
            return False
        
        print(f"\n{'─'*80}")
        print(f"📦 Analisando: {full_name}")
        
        # 1. Obtém detalhes do repositório
        repo_details = self.github_api.get_repo_details(owner, name)
        if not repo_details:
            print(f"❌ Falha ao obter detalhes")
            return False
        
        # 1. Filtro: Stars
        starscount = repo_details.get('stargazerCount', 0)
        if starscount <= 50:
            print(f"❌ REPROVADO - Stars: {starscount} (precisa > 50)")
            return False
        print(f"✅ Stars: {starscount}")

        # 2. Filtro: Releases
        total_releases = repo_details.get('releases', {}).get('totalCount', 0)
        if total_releases <= 19:
            print(f"❌ REPROVADO - Releases: {total_releases} (precisa > 19)")
            return False
        print(f"✅ Releases: {total_releases}")
        
        # 3. Filtro: Contribuidores
        contributors_count = self.github_api.get_contributors_count(owner, name)
        if contributors_count <= 19:
            print(f"❌ REPROVADO - Contribuidores: {contributors_count} (precisa > 19)")
            return False
        print(f"✅ Contribuidores: {contributors_count}")
        
        # 4. Filtro: Intervalo de releases
        releases_nodes = repo_details.get('releases', {}).get('nodes', [])
        avg_interval = self._calculate_avg_release_interval(releases_nodes)
        
        if avg_interval is None:
            print(f"❌ REPROVADO - Intervalo não calculável")
            return False
        
        is_rapid = 5 <= avg_interval <= 35
        is_slow = avg_interval > 60
        
        if not (is_rapid or is_slow):
            print(f"❌ REPROVADO - Intervalo: {avg_interval:.1f} dias (precisa 5-35 ou >60)")
            return False
        
        release_type = 'rapid' if is_rapid else 'slow'
        print(f"✅ Tipo: {release_type.upper()} (intervalo: {avg_interval:.1f} dias)")
        
        # 6. Prepara dados do repositório
        repo_data = {
            'owner': owner,
            'name': name,
            'full_name': full_name,
            'release_type': release_type,
            'stargazer_count': repo_details.get('stargazerCount', 0),
            'fork_count': repo_details.get('forkCount', 0),
            'language': repo_details.get('primaryLanguage', {}).get('name') if repo_details.get('primaryLanguage') else None,
            'total_releases': total_releases,
            'avg_release_interval_days': avg_interval,
            'collaborator_count': contributors_count,
            'distinct_releases_count': total_releases,
            'collected_at': datetime.now().isoformat(),
            'sonarqube_analyzed': False  # Marca para análise posterior
        }
        
        # 7. Adiciona ao dataset
        self.dataset.add_repository(repo_data)
        print(f"✅ APROVADO E ADICIONADO AO DATASET")
        
        return True
    
    def collect_repositories(self, target_rapid: int = 50, target_slow: int = 50, 
                           max_search: int = 500):
        """
        Coleta repositórios até atingir os alvos
        
        Args:
            target_rapid: Número alvo de repositórios Rapid
            target_slow: Número alvo de repositórios Slow
            max_search: Máximo de repositórios para buscar
        """
        print(f"\n{'='*80}")
        print("🎯 METAS DE COLETA")
        print(f"{'='*80}")
        print(f"Rapid Releases: {target_rapid} repositórios")
        print(f"Slow Releases: {target_slow} repositórios")
        print(f"Máximo de buscas: {max_search}")
        print(f"{'='*80}\n")
        
        # Estatísticas atuais
        stats = self.dataset.get_statistics()
        current_rapid = stats['rapid']
        current_slow = stats['slow']
        
        print(f"📊 Dataset atual: {current_rapid} rapid, {current_slow} slow\n")
        
        # Queries de busca otimizadas
        query = "stars:>50 forks:>50"
        
        searched = 0
        approved_rapid = 0
        approved_slow = 0
        
        # Verifica se já atingiu as metas
        if current_rapid + approved_rapid >= target_rapid and \
            current_slow + approved_slow >= target_slow:
            print(f"\n🎉 METAS ATINGIDAS!")
            return
        
        if searched >= max_search:
            print(f"\n⚠️  Limite de buscas atingido ({max_search})")
            return
            
        print(f"\n{'='*80}")
        print(f"🔍 Buscando: {query}")
        print(f"{'='*80}")
        
        try:
            repositories = self.github_api.search_repositories(query, 100)
            
            for repo in repositories:
                if searched >= max_search:
                    break
                
                if current_rapid + approved_rapid >= target_rapid and \
                    current_slow + approved_slow >= target_slow:
                    break
                
                owner = repo['owner']['login']
                name = repo['name']
                
                searched += 1
                
                try:
                    approved = self.filter_and_collect_repository(owner, name)
                    
                    if approved:
                        # Verifica tipo do último repo adicionado
                        repo_info = self.dataset.get_repository(owner, name)
                        if repo_info and repo_info['release_type'] == 'rapid':
                            approved_rapid += 1
                        elif repo_info and repo_info['release_type'] == 'slow':
                            approved_slow += 1
                    
                    # Pausa para respeitar rate limiting
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"❌ Erro ao processar {owner}/{name}: {e}")
                    continue
            
        except Exception as e:
            print(f"❌ Erro na busca: {e}")
        
        
        # Relatório final
        print(f"\n{'='*80}")
        print("📊 RELATÓRIO FINAL DA COLETA")
        print(f"{'='*80}")
        print(f"Repositórios buscados: {searched}")
        print(f"Novos Rapid adicionados: {approved_rapid}")
        print(f"Novos Slow adicionados: {approved_slow}")
        print(f"Total no dataset: {current_rapid + approved_rapid} rapid, {current_slow + approved_slow} slow")
        print(f"{'='*80}\n")
        
        self.dataset.print_statistics()


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description='Coleta e filtra repositórios do GitHub para análise'
    )
    parser.add_argument('--rapid', type=int, default=50,
                       help='Número alvo de repositórios Rapid Release (padrão: 50)')
    parser.add_argument('--slow', type=int, default=50,
                       help='Número alvo de repositórios Slow Release (padrão: 50)')
    parser.add_argument('--max-search', type=int, default=500,
                       help='Máximo de repositórios para buscar (padrão: 500)')
    parser.add_argument('--dataset', type=str, default='repositories_dataset.json',
                       help='Arquivo do dataset (padrão: repositories_dataset.json)')
    
    args = parser.parse_args()
    
    print("="*80)
    print("🔍 SCRIPT 1: COLETA DE REPOSITÓRIOS")
    print("="*80)
    
    # Verifica token
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ ERRO: GITHUB_TOKEN não configurado!")
        print("Configure no arquivo .env")
        sys.exit(1)
    
    # Configuração do banco (opcional)
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'sonar'),
        'user': os.getenv('DB_USER', 'sonar'),
        'password': os.getenv('DB_PASSWORD', 'sonar'),
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    # Inicializa componentes
    print("\n📡 Inicializando GitHub API...")
    github_api = GitHubAPI(github_token)
    
    print(f"💾 Inicializando Dataset Manager ({args.dataset})...")
    dataset_manager = DatasetManager(args.dataset, db_config)
    
    print("🚀 Iniciando coleta...\n")
    
    # Coleta repositórios
    collector = RepositoryCollector(github_api, dataset_manager)
    collector.collect_repositories(
        target_rapid=args.rapid,
        target_slow=args.slow,
        max_search=args.max_search
    )
    
    # Exporta para CSV
    csv_file = args.dataset.replace('.json', '.csv')
    dataset_manager.export_to_csv(csv_file)
    
    dataset_manager.close()
    
    print("\n✅ Coleta finalizada!")
    print(f"📁 Dataset salvo em: {args.dataset}")
    print(f"📊 CSV exportado em: {csv_file}")


if __name__ == "__main__":
    main()
