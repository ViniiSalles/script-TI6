#!/usr/bin/env python3
"""
Exporta dados do PostgreSQL para JSON e CSV
"""

import os
import json
import csv
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

def connect_db():
    """Conecta ao banco de dados"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

def export_to_json():
    """Exporta para JSON"""
    print("📄 Exportando para JSON...")
    
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Busca todos os dados
    cursor.execute("""
        SELECT 
            r.id as repository_id,
            r.name_with_owner,
            r.url,
            r.stars,
            r.forks,
            r.release_count,
            r.analyzed_at as repo_analyzed_at,
            s.id as metric_id,
            s.ncloc,
            s.complexity,
            s.cognitive_complexity,
            s.violations,
            s.bugs,
            s.vulnerabilities,
            s.code_smells,
            s.coverage,
            s.duplicated_lines_density,
            s.analyzed_at as metrics_analyzed_at
        FROM repositories r
        LEFT JOIN sonar_metrics s ON s.repository_id = r.id
        ORDER BY r.analyzed_at DESC
    """)
    
    results = cursor.fetchall()
    
    # Converte para formato serializável
    data = []
    for row in results:
        item = {}
        for key, value in row.items():
            if value is None:
                item[key] = None
            elif hasattr(value, 'isoformat'):  # datetime
                item[key] = value.isoformat()
            elif hasattr(value, '__float__'):  # Decimal
                item[key] = float(value)
            else:
                item[key] = value
        data.append(item)
    
    # Salva JSON
    output_dir = Path('results')
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = output_dir / f'sonar_analysis_{timestamp}.json'
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ JSON exportado: {json_file}")
    print(f"   Total de registros: {len(data)}")
    
    cursor.close()
    conn.close()
    
    return json_file

def export_to_csv():
    """Exporta para CSV"""
    print("\n📊 Exportando para CSV...")
    
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Busca todos os dados
    cursor.execute("""
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
            r.analyzed_at
        FROM repositories r
        LEFT JOIN sonar_metrics s ON s.repository_id = r.id
        ORDER BY r.analyzed_at DESC
    """)
    
    results = cursor.fetchall()
    
    # Salva CSV
    output_dir = Path('results')
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_file = output_dir / f'sonar_analysis_{timestamp}.csv'
    
    if results:
        keys = results[0].keys()
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            
            for row in results:
                # Converte datetime para string
                row_dict = dict(row)
                if row_dict['analyzed_at']:
                    row_dict['analyzed_at'] = row_dict['analyzed_at'].isoformat()
                # Converte Decimal para float
                if row_dict['coverage']:
                    row_dict['coverage'] = float(row_dict['coverage'])
                if row_dict['duplicated_lines_density']:
                    row_dict['duplicated_lines_density'] = float(row_dict['duplicated_lines_density'])
                writer.writerow(row_dict)
        
        print(f"✅ CSV exportado: {csv_file}")
        print(f"   Total de registros: {len(results)}")
    else:
        print("⚠️  Nenhum dado para exportar")
    
    cursor.close()
    conn.close()
    
    return csv_file

def create_summary():
    """Cria arquivo de resumo"""
    print("\n📈 Criando resumo estatístico...")
    
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Estatísticas
    cursor.execute("SELECT COUNT(*) as total FROM repositories")
    repo_count = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM sonar_metrics")
    metrics_count = cursor.fetchone()['total']
    
    summary = {
        'export_date': datetime.now().isoformat(),
        'total_repositories': repo_count,
        'total_metrics': metrics_count,
        'statistics': {}
    }
    
    if metrics_count > 0:
        cursor.execute("""
            SELECT 
                AVG(ncloc)::INTEGER as avg_ncloc,
                MAX(ncloc) as max_ncloc,
                MIN(ncloc) as min_ncloc,
                AVG(bugs)::INTEGER as avg_bugs,
                MAX(bugs) as max_bugs,
                MIN(bugs) as min_bugs,
                AVG(vulnerabilities)::INTEGER as avg_vulnerabilities,
                MAX(vulnerabilities) as max_vulnerabilities,
                AVG(code_smells)::INTEGER as avg_code_smells,
                MAX(code_smells) as max_code_smells,
                AVG(complexity)::INTEGER as avg_complexity,
                MAX(complexity) as max_complexity,
                AVG(coverage)::FLOAT as avg_coverage,
                AVG(duplicated_lines_density)::FLOAT as avg_duplication
            FROM sonar_metrics
        """)
        
        stats = cursor.fetchone()
        summary['statistics'] = dict(stats)
        
        # Top repositórios
        cursor.execute("""
            SELECT r.name_with_owner, s.bugs
            FROM sonar_metrics s
            JOIN repositories r ON s.repository_id = r.id
            ORDER BY s.bugs DESC
            LIMIT 5
        """)
        summary['top_bugs'] = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT r.name_with_owner, s.code_smells
            FROM sonar_metrics s
            JOIN repositories r ON s.repository_id = r.id
            ORDER BY s.code_smells DESC
            LIMIT 5
        """)
        summary['top_code_smells'] = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT r.name_with_owner, s.ncloc
            FROM sonar_metrics s
            JOIN repositories r ON s.repository_id = r.id
            ORDER BY s.ncloc DESC
            LIMIT 5
        """)
        summary['top_lines_of_code'] = [dict(row) for row in cursor.fetchall()]
    
    # Salva resumo
    output_dir = Path('results')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_file = output_dir / f'summary_{timestamp}.json'
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Resumo criado: {summary_file}")
    
    cursor.close()
    conn.close()
    
    return summary_file

def main():
    """Função principal"""
    print("=" * 80)
    print(" EXPORTAÇÃO DE DADOS DO BANCO PARA ARQUIVOS")
    print("=" * 80)
    print()
    
    try:
        # Exporta JSON
        json_file = export_to_json()
        
        # Exporta CSV
        csv_file = export_to_csv()
        
        # Cria resumo
        summary_file = create_summary()
        
        print("\n" + "=" * 80)
        print(" EXPORTAÇÃO CONCLUÍDA")
        print("=" * 80)
        print(f"\n📁 Arquivos criados em: results/")
        print(f"   • {json_file.name}")
        print(f"   • {csv_file.name}")
        print(f"   • {summary_file.name}")
        print("\n✅ Esses arquivos podem ser commitados no GitHub!")
        print("\n💡 Dica: Adicione results/*.json e results/*.csv ao git:")
        print("   git add results/")
        print("   git commit -m 'Add analysis results'")
        print("   git push")
        
    except Exception as e:
        print(f"\n❌ Erro durante exportação: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
