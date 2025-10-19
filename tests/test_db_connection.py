#!/usr/bin/env python3
"""
Script de teste para verificar conexão com PostgreSQL

Execute este script para testar se o banco de dados está acessível.
"""

import os
import sys
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

def test_db_connection():
    """Testa conexão com PostgreSQL"""
    print("=== Testando Conexão com PostgreSQL ===\n")
    
    # Configuração do banco
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'sonar'),
        'user': os.getenv('DB_USER', 'sonar'),
        'password': os.getenv('DB_PASSWORD', 'sonar'),
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    print("📋 Configuração:")
    print(f"   Host: {db_config['host']}")
    print(f"   Port: {db_config['port']}")
    print(f"   Database: {db_config['database']}")
    print(f"   User: {db_config['user']}")
    print(f"   Password: {'*' * len(db_config['password'])}")
    print()
    
    # Tenta importar psycopg2
    try:
        import psycopg2
        print("✅ Módulo psycopg2 importado com sucesso")
    except ImportError:
        print("❌ ERRO: Módulo psycopg2 não encontrado")
        print("   Instale com: pip install psycopg2-binary")
        return False
    
    # Tenta conectar
    try:
        print("\n🔌 Tentando conectar...")
        connection = psycopg2.connect(**db_config)
        connection.autocommit = True
        
        print("✅ Conexão estabelecida com sucesso!")
        
        # Testa query
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            print(f"\n📊 Versão do PostgreSQL:")
            print(f"   {version[0][:80]}...")
            
            # Lista tabelas existentes
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            tables = cursor.fetchall()
            
            if tables:
                print(f"\n📋 Tabelas existentes ({len(tables)}):")
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
                    count = cursor.fetchone()[0]
                    print(f"   - {table[0]}: {count} registros")
            else:
                print("\n⚠️  Nenhuma tabela encontrada (banco vazio)")
                print("   As tabelas serão criadas ao executar o script principal")
        
        connection.close()
        print("\n✅ Teste concluído com sucesso!")
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ ERRO de conexão: {e}")
        print("\n🔍 Possíveis causas:")
        print("   1. PostgreSQL não está rodando")
        print("      Solução: docker-compose up -d")
        print("   2. Porta 5432 não está exposta")
        print("      Solução: Verifique docker-compose.yml")
        print("   3. Credenciais incorretas no .env")
        print("      Solução: Verifique DB_USER, DB_PASSWORD, DB_NAME")
        print("   4. Container ainda está inicializando")
        print("      Solução: Aguarde alguns segundos e tente novamente")
        return False
        
    except Exception as e:
        print(f"❌ ERRO inesperado: {e}")
        return False

if __name__ == "__main__":
    success = test_db_connection()
    sys.exit(0 if success else 1)
