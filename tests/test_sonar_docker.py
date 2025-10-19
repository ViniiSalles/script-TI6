#!/usr/bin/env python3
"""
Script de teste para verificar análise SonarQube via Docker

Execute este script para testar se o Docker e SonarQube estão configurados corretamente.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

def test_docker():
    """Testa se Docker está disponível e rodando"""
    print("=== Testando Docker ===")
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker versão: {result.stdout.strip()}")
        else:
            print("❌ Docker não encontrado")
            return False
            
        # Testa se Docker está rodando
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Docker está em execução")
            return True
        else:
            print("❌ Docker não está rodando. Inicie o Docker Desktop.")
            return False
    except FileNotFoundError:
        print("❌ Docker não instalado")
        return False

def test_sonarqube_connection():
    """Testa conexão com SonarQube"""
    print("\n=== Testando SonarQube ===")
    sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
    sonar_token = os.getenv('SONAR_TOKEN')
    
    if not sonar_token:
        print("❌ SONAR_TOKEN não configurado no .env")
        return False
    
    print(f"✅ SONAR_HOST: {sonar_host}")
    print(f"✅ SONAR_TOKEN: {sonar_token[:10]}...")
    
    # Testa acesso à API
    try:
        import requests
        response = requests.get(
            f"{sonar_host}/api/system/status",
            auth=(sonar_token, '')
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SonarQube Status: {data.get('status', 'UNKNOWN')}")
            return True
        else:
            print(f"❌ Erro ao acessar SonarQube: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro ao conectar com SonarQube: {e}")
        return False

def test_sonar_scanner_docker():
    """Testa execução do SonarScanner via Docker"""
    print("\n=== Testando SonarScanner via Docker ===")
    
    # Cria diretório de teste
    temp_dir = os.path.join(tempfile.gettempdir(), "test_sonar")
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    # Cria arquivo Python de teste
    test_file = os.path.join(temp_dir, "test.py")
    with open(test_file, 'w') as f:
        f.write("""
def hello_world():
    '''Função de teste'''
    print("Hello, World!")
    return True

if __name__ == "__main__":
    hello_world()
""")
    
    print(f"📁 Diretório de teste: {temp_dir}")
    
    sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
    sonar_token = os.getenv('SONAR_TOKEN')
    
    if not sonar_token:
        print("❌ SONAR_TOKEN não configurado")
        return False
    
    # Prepara comando Docker
    if os.name == 'nt':  # Windows
        docker_volume = f"{os.path.abspath(temp_dir)}:/usr/src"
    else:
        docker_volume = f"{temp_dir}:/usr/src"
    
    docker_cmd = [
        'docker', 'run',
        '--rm',
        '--network', 'host',
        '-e', f'SONAR_HOST_URL={sonar_host}',
        '-e', f'SONAR_TOKEN={sonar_token}',
        '-v', docker_volume,
        'sonarsource/sonar-scanner-cli',
        '-Dsonar.projectKey=test_project',
        '-Dsonar.projectName=test_project',
        '-Dsonar.sources=.',
        '-Dsonar.python.version=3.13'
    ]
    
    print("🐳 Executando Docker...")
    print(f"Comando: {' '.join(docker_cmd[:8])}... (truncado)")
    
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ SonarScanner executado com sucesso!")
            print("\n📊 Últimas linhas da saída:")
            lines = result.stdout.split('\n')
            for line in lines[-10:]:
                if line.strip():
                    print(f"   {line}")
            return True
        else:
            print(f"❌ Erro ao executar SonarScanner (exit code {result.returncode})")
            if result.stderr:
                print(f"Erro: {result.stderr[-500:]}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Timeout ao executar SonarScanner")
        return False
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False
    finally:
        # Limpa diretório de teste
        import shutil
        try:
            shutil.rmtree(temp_dir)
            print(f"\n🧹 Diretório de teste removido")
        except:
            pass

def main():
    print("=" * 60)
    print("TESTE DE CONFIGURAÇÃO SONARQUBE VIA DOCKER")
    print("=" * 60)
    
    # Testa Docker
    if not test_docker():
        print("\n❌ Docker não está disponível. Corrija antes de continuar.")
        return
    
    # Testa SonarQube
    if not test_sonarqube_connection():
        print("\n❌ SonarQube não está acessível. Verifique a configuração.")
        print("\nDicas:")
        print("1. Verifique se o container está rodando: docker-compose ps")
        print("2. Acesse http://localhost:9000 no navegador")
        print("3. Verifique o SONAR_TOKEN no arquivo .env")
        return
    
    # Testa SonarScanner via Docker
    if test_sonar_scanner_docker():
        print("\n" + "=" * 60)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 60)
        print("\nVocê pode executar o script principal:")
        print("  python research_automation_script.py")
    else:
        print("\n❌ Falha no teste do SonarScanner")
        print("\nVerifique:")
        print("1. Docker está rodando")
        print("2. SonarQube está acessível")
        print("3. Token está correto")

if __name__ == "__main__":
    main()
