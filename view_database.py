#!/usr/bin/env python3
"""
Consulta ao Banco de Dados PostgreSQL
Visualiza os dados coletados das análises SonarQube
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Carrega variáveis de ambiente
load_dotenv()

def connect_db():
    """Conecta ao banco de dados"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        sys.exit(1)

def print_header(text):
    """Imprime cabeçalho formatado"""
    print("\n" + "=" * 80)
    print(f" {text}")
    print("=" * 80 + "\n")

def list_repositories():
    """Lista todos os repositórios analisados"""
    print_header("REPOSITÓRIOS ANALISADOS")
    
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            id,
            name_with_owner,
            stars,
            forks,
            release_count,
            analyzed_at
        FROM repositories
        ORDER BY analyzed_at DESC
    """)
    
    repos = cursor.fetchall()
    
    if not repos:
        print("⚠️  Nenhum repositório encontrado no banco de dados")
    else:
        print(f"Total de repositórios: {len(repos)}\n")
        
        for repo in repos:
            print(f"ID: {repo['id']}")
            print(f"   Nome: {repo['name_with_owner']}")
            print(f"   Stars: {repo['stars']:,} | Forks: {repo['forks']:,} | Releases: {repo['release_count']}")
            print(f"   Analisado em: {repo['analyzed_at']}")
            print()
    
    cursor.close()
    conn.close()

def list_metrics():
    """Lista todas as métricas coletadas"""
    print_header("MÉTRICAS SONARQUBE")
    
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            r.name_with_owner,
            s.ncloc,
            s.complexity,
            s.cognitive_complexity,
            s.violations,
            s.bugs,
            s.vulnerabilities,
            s.code_smells,
            s.coverage,
            s.duplicated_lines_density,
            s.analyzed_at
        FROM sonar_metrics s
        JOIN repositories r ON s.repository_id = r.id
        ORDER BY s.analyzed_at DESC
    """)
    
    metrics = cursor.fetchall()
    
    if not metrics:
        print("⚠️  Nenhuma métrica encontrada no banco de dados")
    else:
        print(f"Total de métricas: {len(metrics)}\n")
        
        for m in metrics:
            print(f"📊 {m['name_with_owner']}")
            print(f"   Linhas de código: {m['ncloc']:,}")
            print(f"   Complexidade: {m['complexity']:,} (Cognitiva: {m['cognitive_complexity']:,})")
            print(f"   Bugs: {m['bugs']} | Vulnerabilidades: {m['vulnerabilities']} | Code Smells: {m['code_smells']}")
            print(f"   Cobertura: {m['coverage']}% | Duplicação: {m['duplicated_lines_density']}%")
            print(f"   Violações: {m['violations']}")
            print(f"   Analisado em: {m['analyzed_at']}")
            print()
    
    cursor.close()
    conn.close()

def show_statistics():
    """Mostra estatísticas gerais"""
    print_header("ESTATÍSTICAS GERAIS")
    
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Contadores
    cursor.execute("SELECT COUNT(*) as total FROM repositories")
    repo_count = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM sonar_metrics")
    metrics_count = cursor.fetchone()['total']
    
    print(f"📦 Repositórios no banco: {repo_count}")
    print(f"📊 Métricas coletadas: {metrics_count}\n")
    
    if metrics_count > 0:
        # Estatísticas das métricas
        cursor.execute("""
            SELECT 
                AVG(ncloc)::INTEGER as avg_ncloc,
                MAX(ncloc) as max_ncloc,
                MIN(ncloc) as min_ncloc,
                AVG(bugs)::INTEGER as avg_bugs,
                MAX(bugs) as max_bugs,
                AVG(vulnerabilities)::INTEGER as avg_vuln,
                MAX(vulnerabilities) as max_vuln,
                AVG(code_smells)::INTEGER as avg_smells,
                MAX(code_smells) as max_smells,
                AVG(complexity)::INTEGER as avg_complexity
            FROM sonar_metrics
        """)
        
        stats = cursor.fetchone()
        
        print("📈 Médias:")
        print(f"   Linhas de código: {stats['avg_ncloc']:,}")
        print(f"   Bugs: {stats['avg_bugs']}")
        print(f"   Vulnerabilidades: {stats['avg_vuln']}")
        print(f"   Code Smells: {stats['avg_smells']:,}")
        print(f"   Complexidade: {stats['avg_complexity']:,}")
        
        print("\n📊 Máximos:")
        print(f"   Linhas de código: {stats['max_ncloc']:,}")
        print(f"   Bugs: {stats['max_bugs']}")
        print(f"   Vulnerabilidades: {stats['max_vuln']}")
        print(f"   Code Smells: {stats['max_smells']:,}")
        
        # Top repositórios com mais bugs
        print("\n🐛 Top 5 Repositórios com Mais Bugs:")
        cursor.execute("""
            SELECT r.name_with_owner, s.bugs
            FROM sonar_metrics s
            JOIN repositories r ON s.repository_id = r.id
            ORDER BY s.bugs DESC
            LIMIT 5
        """)
        
        for row in cursor.fetchall():
            print(f"   • {row['name_with_owner']}: {row['bugs']} bugs")
        
        # Top repositórios com mais code smells
        print("\n🦨 Top 5 Repositórios com Mais Code Smells:")
        cursor.execute("""
            SELECT r.name_with_owner, s.code_smells
            FROM sonar_metrics s
            JOIN repositories r ON s.repository_id = r.id
            ORDER BY s.code_smells DESC
            LIMIT 5
        """)
        
        for row in cursor.fetchall():
            print(f"   • {row['name_with_owner']}: {row['code_smells']:,} code smells")
    
    cursor.close()
    conn.close()

def export_to_csv():
    """Exporta dados para CSV"""
    print_header("EXPORTAR PARA CSV")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    output_file = "results/sonar_analysis_results.csv"
    
    print(f"Exportando para: {output_file}")
    
    query = """
        COPY (
            SELECT 
                r.name_with_owner,
                r.url,
                r.stars,
                r.forks,
                r.release_count,
                s.ncloc,
                s.complexity,
                s.cognitive_complexity,
                s.violations,
                s.bugs,
                s.vulnerabilities,
                s.code_smells,
                s.coverage,
                s.duplicated_lines_density,
                s.analyzed_at
            FROM sonar_metrics s
            JOIN repositories r ON s.repository_id = r.id
            ORDER BY s.analyzed_at DESC
        ) TO STDOUT WITH CSV HEADER
    """
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            cursor.copy_expert(query, f)
        
        print(f"✅ Dados exportados com sucesso para: {output_file}")
    except Exception as e:
        print(f"❌ Erro ao exportar: {e}")
    
    cursor.close()
    conn.close()

def show_menu():
    """Mostra menu de opções"""
    print_header("CONSULTA AO BANCO DE DADOS POSTGRESQL")
    
    print("Opções disponíveis:")
    print()
    print("  1 - Listar repositórios analisados")
    print("  2 - Listar métricas coletadas")
    print("  3 - Mostrar estatísticas gerais")
    print("  4 - Exportar para CSV")
    print("  5 - Mostrar tudo")
    print("  0 - Sair")
    print()

def main():
    """Função principal"""
    
    if len(sys.argv) > 1:
        option = sys.argv[1]
    else:
        show_menu()
        option = input("Escolha uma opção: ").strip()
    
    if option == '1' or option == 'repos':
        list_repositories()
    elif option == '2' or option == 'metrics':
        list_metrics()
    elif option == '3' or option == 'stats':
        show_statistics()
    elif option == '4' or option == 'export':
        export_to_csv()
    elif option == '5' or option == 'all':
        list_repositories()
        list_metrics()
        show_statistics()
    elif option == '0' or option == 'exit':
        print("Saindo...")
    else:
        print(f"❌ Opção inválida: {option}")
        show_menu()

if __name__ == "__main__":
    main()
