#!/usr/bin/env python3
"""
Script de teste para validar os filtros de seleção de repositórios

Testa os 3 critérios principais:
1. > 19 releases
2. > 19 contribuidores  
3. Intervalo entre releases: 5-35 dias (RAPID) OU > 60 dias (SLOW)
"""

import os
import sys
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Adiciona path do script principal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_automation_script import GitHubAPI

def test_repository_filters(owner: str, name: str, github_api: GitHubAPI):
    """Testa se um repositório passa nos filtros"""
    full_name = f"{owner}/{name}"
    print(f"\n{'='*80}")
    print(f"📦 Testando: {full_name}")
    print(f"{'='*80}")
    
    # 1. Obtém detalhes básicos
    repo_details = github_api.get_repo_details(owner, name)
    if not repo_details:
        print(f"❌ Falha ao obter detalhes do repositório")
        return False
    
    # 2. Testa filtro de releases
    total_releases = repo_details.get('releases', {}).get('totalCount', 0)
    print(f"\n🏷️  RELEASES: {total_releases}")
    if total_releases <= 19:
        print(f"   ❌ REPROVADO (precisa > 19)")
        return False
    else:
        print(f"   ✅ APROVADO")
    
    # 3. Testa filtro de contribuidores
    contributors_count = github_api.get_contributors_count(owner, name)
    print(f"\n👥 CONTRIBUIDORES: {contributors_count}")
    if contributors_count <= 19:
        print(f"   ❌ REPROVADO (precisa > 19)")
        return False
    else:
        print(f"   ✅ APROVADO")
    
    # 4. Calcula intervalo de releases
    releases_nodes = repo_details.get('releases', {}).get('nodes', [])
    
    # Calcula intervalo médio
    from datetime import datetime
    if len(releases_nodes) < 2:
        print(f"\n⏱️  INTERVALO: Não calculável (menos de 2 releases)")
        print(f"   ❌ REPROVADO")
        return False
    
    dates = []
    for release in releases_nodes:
        try:
            date = datetime.fromisoformat(release['createdAt'].replace('Z', '+00:00'))
            dates.append(date)
        except:
            continue
    
    if len(dates) < 2:
        print(f"\n⏱️  INTERVALO: Não calculável (datas inválidas)")
        print(f"   ❌ REPROVADO")
        return False
    
    dates.sort(reverse=True)
    intervals = []
    
    for i in range(len(dates) - 1):
        interval = (dates[i] - dates[i + 1]).days
        if interval > 0:
            intervals.append(interval)
    
    avg_interval = sum(intervals) / len(intervals) if intervals else None
    
    if avg_interval is None:
        print(f"\n⏱️  INTERVALO: Não calculável")
        print(f"   ❌ REPROVADO")
        return False
    
    print(f"\n⏱️  INTERVALO MÉDIO: {avg_interval:.1f} dias")
    
    is_rapid = 5 <= avg_interval <= 35
    is_slow = avg_interval > 60
    
    if is_rapid:
        print(f"   ✅ APROVADO - Classificado como RAPID RELEASE")
        release_type = "RAPID"
    elif is_slow:
        print(f"   ✅ APROVADO - Classificado como SLOW RELEASE")
        release_type = "SLOW"
    else:
        print(f"   ❌ REPROVADO (precisa ser 5-35 dias OU > 60 dias)")
        return False
    
    # Resumo final
    print(f"\n{'='*80}")
    print(f"✅ REPOSITÓRIO APROVADO EM TODOS OS FILTROS!")
    print(f"   Tipo: {release_type}")
    print(f"   Releases: {total_releases}")
    print(f"   Contribuidores: {contributors_count}")
    print(f"   Intervalo médio: {avg_interval:.1f} dias")
    print(f"{'='*80}\n")
    
    return True


def main():
    """Função principal"""
    print("=== Teste de Filtros de Repositórios ===\n")
    
    # Verifica token
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ ERRO: GITHUB_TOKEN não configurado!")
        print("Configure no arquivo .env")
        sys.exit(1)
    
    # Inicializa API
    github_api = GitHubAPI(github_token)
    
    # Repositórios de teste
    test_repos = [
        # Exemplos que devem passar (projetos populares com muitos releases)
        ("kubernetes", "kubernetes"),      # Projeto grande, muitos releases
        ("nodejs", "node"),                # Node.js - muito ativo
        ("microsoft", "vscode"),           # VS Code - muito ativo
        
        # Exemplo que pode não passar (poucos releases)
        ("octocat", "Hello-World"),        # Repositório de exemplo
    ]
    
    results = {}
    
    for owner, name in test_repos:
        try:
            passed = test_repository_filters(owner, name, github_api)
            results[f"{owner}/{name}"] = passed
        except Exception as e:
            print(f"\n❌ Erro ao testar {owner}/{name}: {e}\n")
            results[f"{owner}/{name}"] = False
    
    # Resumo final
    print(f"\n\n{'='*80}")
    print("📊 RESUMO DOS TESTES")
    print(f"{'='*80}")
    
    approved = sum(1 for passed in results.values() if passed)
    total = len(results)
    
    for repo, passed in results.items():
        status = "✅ APROVADO" if passed else "❌ REPROVADO"
        print(f"  {status}: {repo}")
    
    print(f"\n  Total: {approved}/{total} repositórios aprovados")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
