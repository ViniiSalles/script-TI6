#!/usr/bin/env python3
"""
Script de Teste para Análise SonarQube
Testa a configuração e executa uma análise simples
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

# Carrega variáveis de ambiente
load_dotenv()

def test_environment():
    """Testa se as variáveis de ambiente estão configuradas"""
    print("=" * 60)
    print("TESTE 1: Verificando Variáveis de Ambiente")
    print("=" * 60)
    
    required_vars = [
        'GITHUB_TOKEN',
        'SONAR_HOST',
        'DB_HOST',
        'DB_NAME',
        'DB_USER',
        'DB_PASSWORD',
        'DB_PORT'
    ]
    
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if not value or value == 'your_github_personal_access_token_here':
            print(f"❌ {var}: NÃO CONFIGURADO")
            missing.append(var)
        else:
            # Oculta tokens parcialmente
            if 'TOKEN' in var or 'PASSWORD' in var:
                display = value[:10] + "..." if len(value) > 10 else "***"
            else:
                display = value
            print(f"✅ {var}: {display}")
    
    if missing:
        print(f"\n⚠️  Faltam configurar: {', '.join(missing)}")
        print("\nEdite o arquivo .env e adicione os valores necessários.")
        return False
    
    print("\n✅ Todas as variáveis de ambiente estão configuradas!")
    return True


def test_database_connection():
    """Testa conexão com PostgreSQL"""
    print("\n" + "=" * 60)
    print("TESTE 2: Testando Conexão com PostgreSQL")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        
        cursor = conn.cursor()
        cursor.execute('SELECT version();')
        version = cursor.fetchone()
        
        print(f"✅ Conexão com PostgreSQL estabelecida!")
        print(f"   Versão: {version[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erro ao conectar ao PostgreSQL: {e}")
        return False


def test_sonarqube_connection():
    """Testa conexão com SonarQube"""
    print("\n" + "=" * 60)
    print("TESTE 3: Testando Conexão com SonarQube")
    print("=" * 60)
    
    import requests
    
    sonar_host = os.getenv('SONAR_HOST')
    sonar_token = os.getenv('SONAR_TOKEN')
    
    try:
        # Testa endpoint do sistema
        response = requests.get(f"{sonar_host}/api/system/status")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SonarQube está acessível!")
            print(f"   Status: {data.get('status', 'N/A')}")
            print(f"   Versão: {data.get('version', 'N/A')}")
        else:
            print(f"⚠️  SonarQube retornou código: {response.status_code}")
            return False
        
        # Testa autenticação se o token estiver configurado
        if sonar_token and sonar_token != '':
            auth_response = requests.get(
                f"{sonar_host}/api/authentication/validate",
                auth=(sonar_token, '')
            )
            
            if auth_response.status_code == 200:
                auth_data = auth_response.json()
                print(f"✅ Token SonarQube válido!")
                print(f"   Autenticado: {auth_data.get('valid', False)}")
            else:
                print(f"⚠️  Token pode estar inválido (código: {auth_response.status_code})")
        else:
            print("⚠️  Token SonarQube não configurado")
            print("   Configure SONAR_TOKEN no arquivo .env")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao conectar ao SonarQube: {e}")
        return False


def main():
    """Executa todos os testes"""
    print("\n" + "=" * 60)
    print("TESTE DE CONFIGURAÇÃO DO AMBIENTE")
    print("=" * 60)
    
    results = []
    
    # Teste 1: Variáveis de ambiente
    results.append(("Variáveis de Ambiente", test_environment()))
    
    # Teste 2: PostgreSQL
    if results[0][1]:  # Só testa se as variáveis estiverem ok
        results.append(("Conexão PostgreSQL", test_database_connection()))
    
    # Teste 3: SonarQube
    if results[0][1]:  # Só testa se as variáveis estiverem ok
        results.append(("Conexão SonarQube", test_sonarqube_connection()))
    
    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 Todos os testes passaram!")
        print("   Você está pronto para executar o script principal:")
        print("   python research_automation_script.py")
    else:
        print("\n⚠️  Alguns testes falharam.")
        print("   Corrija os problemas acima antes de prosseguir.")
        sys.exit(1)


if __name__ == "__main__":
    main()
