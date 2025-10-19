#!/usr/bin/env python3
"""
Script de teste para verificar contagem de contribuidores

Testa o novo método get_contributors_count() da API do GitHub.
"""

import os
from dotenv import load_dotenv

load_dotenv()

def test_contributors():
    """Testa contagem de contribuidores em repositórios conhecidos"""
    from utils import GitHubAPI
    
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ GITHUB_TOKEN não configurado")
        return False
    
    print("=== Testando Contagem de Contribuidores ===\n")
    
    github_api = GitHubAPI(github_token)
    
    # Lista de repositórios para testar (com diferentes tamanhos)
    test_repos = [
        ("octocat", "Hello-World"),  # Repo pequeno
        ("microsoft", "vscode"),      # Repo médio/grande
        ("facebook", "react"),        # Repo muito grande
    ]
    
    for owner, name in test_repos:
        print(f"\n📦 Testando: {owner}/{name}")
        try:
            count = github_api.get_contributors_count(owner, name)
            print(f"   ✅ Contribuidores: {count}")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
    
    print("\n" + "="*60)
    print("✅ TESTE CONCLUÍDO!")
    print("="*60)
    return True

if __name__ == "__main__":
    test_contributors()
