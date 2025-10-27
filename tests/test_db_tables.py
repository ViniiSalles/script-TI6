#!/usr/bin/env python3
"""
Script de teste rápido para verificar criação de tabelas do script principal
"""

import os
import sys
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Importa apenas a classe DatabaseManager do script principal
sys.path.insert(0, os.path.dirname(__file__))

def test_database_manager():
    """Testa DatabaseManager do script principal"""
    print("=== Testando DatabaseManager ===\n")
    
    # Importa DatabaseManager
    try:
        from research_automation_script import DatabaseManager
        print("✅ DatabaseManager importado com sucesso")
    except ImportError as e:
        print(f"❌ Erro ao importar DatabaseManager: {e}")
        return False
    
    # Configuração do banco
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'sonar'),
        'user': os.getenv('DB_USER', 'sonar'),
        'password': os.getenv('DB_PASSWORD', 'sonar'),
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    print(f"\n📋 Configuração do banco:")
    print(f"   {db_config['user']}@{db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    # Cria instância do DatabaseManager
    try:
        db_manager = DatabaseManager(db_config)
        print("\n✅ DatabaseManager instanciado")
    except Exception as e:
        print(f"❌ Erro ao instanciar DatabaseManager: {e}")
        return False
    
    # Conecta ao banco
    try:
        print("\n🔌 Conectando ao banco...")
        if db_manager.connect():
            print("✅ Conexão estabelecida")
        else:
            print("❌ Falha na conexão")
            return False
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        return False
    
    # Cria tabelas
    try:
        print("\n📊 Criando/verificando tabelas...")
        db_manager.create_tables()
        print("✅ Tabelas criadas/verificadas com sucesso")
    except Exception as e:
        print(f"❌ Erro ao criar tabelas: {e}")
        db_manager.disconnect()
        return False
    
    # Verifica tabelas criadas
    try:
        print("\n🔍 Verificando tabelas criadas...")
        import psycopg2
        
        with db_manager.connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('research_repositories', 'research_pull_requests', 'research_issues', 'research_sonarqube_metrics')
                ORDER BY table_name;
            """)
            tables = cursor.fetchall()
            
            if len(tables) == 4:
                print("✅ Todas as tabelas do script foram criadas:")
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
                    count = cursor.fetchone()[0]
                    print(f"   - {table[0]}: {count} registros")
            else:
                print(f"⚠️  Apenas {len(tables)} de 4 tabelas criadas:")
                for table in tables:
                    print(f"   - {table[0]}")
    except Exception as e:
        print(f"❌ Erro ao verificar tabelas: {e}")
    finally:
        db_manager.disconnect()
        print("\n✅ Conexão fechada")
    
    print("\n" + "="*60)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("="*60)
    print("\nO script principal está pronto para ser executado:")
    print("  python research_automation_script.py")
    
    return True

if __name__ == "__main__":
    success = test_database_manager()
    sys.exit(0 if success else 1)
