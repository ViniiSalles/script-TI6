#!/usr/bin/env python3
"""
Script de Correção de CSV Corrompido

OBJETIVO:
Corrigir linhas corrompidas no CSV onde owner/name estão trocados ou vazios.
Especificamente corrige a linha 505 e outras similares.

EXECUÇÃO:
python fix_corrupted_csv.py --csv slow_release_repos_20251115_053707_analyzed.csv
"""

import csv
import argparse
from sonarqube_validator import fix_corrupted_csv_line, sanitize_project_key


def fix_csv(input_file: str, dry_run: bool = False):
    """Corrige CSV corrompido"""
    
    print("="*80)
    print("🔧 CORREÇÃO DE CSV CORROMPIDO")
    print("="*80)
    
    # Lê CSV
    print(f"\n📂 Lendo: {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames)
            rows = list(reader)
        
        print(f"✅ {len(rows)} linhas carregadas")
        
    except Exception as e:
        print(f"❌ Erro ao ler: {e}")
        return
    
    # Analisa linhas
    print(f"\n🔍 Analisando linhas corrompidas...")
    
    corrupted = []
    fixed = []
    
    for i, row in enumerate(rows, start=2):  # start=2 (header=1)
        # Detecta problemas
        has_issue = False
        issues = []
        
        if not row.get('owner'):
            has_issue = True
            issues.append("owner vazio")
        
        if not row.get('name'):
            has_issue = True
            issues.append("name vazio")
        
        if '/' in row.get('owner', '') or '/' in row.get('name', ''):
            has_issue = True
            issues.append("contém barras")
        
        if has_issue:
            corrupted.append((i, row, issues))
            
            # Tenta corrigir
            fixed_row = fix_corrupted_csv_line(row)
            if fixed_row:
                fixed.append((i, row, fixed_row))
    
    # Relatório
    print(f"\n📊 Análise:")
    print(f"   Total de linhas: {len(rows)}")
    print(f"   Linhas corrompidas: {len(corrupted)}")
    print(f"   Linhas corrigíveis: {len(fixed)}")
    
    if corrupted:
        print(f"\n❌ Linhas com problemas:")
        for line_num, row, issues in corrupted[:10]:  # Mostra primeiras 10
            print(f"   Linha {line_num}: {', '.join(issues)}")
            print(f"      owner='{row.get('owner', '')}', name='{row.get('name', '')}', full_name='{row.get('full_name', '')}'")
    
    if fixed:
        print(f"\n✅ Linhas que serão corrigidas:")
        for line_num, old_row, new_row in fixed:
            print(f"   Linha {line_num}:")
            print(f"      ANTES: owner='{old_row.get('owner', '')}', name='{old_row.get('name', '')}'")
            print(f"      DEPOIS: owner='{new_row['owner']}', name='{new_row['name']}'")
    
    # Aplica correções
    if not dry_run and fixed:
        print(f"\n🔧 Aplicando correções...")
        
        # Atualiza rows
        for line_num, old_row, new_row in fixed:
            idx = line_num - 2  # Ajusta índice (header=1, start=2)
            rows[idx].update(new_row)
        
        # Salva CSV corrigido
        output_file = input_file.replace('.csv', '_fixed.csv')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✅ Arquivo corrigido salvo: {output_file}")
        print(f"   {len(fixed)} linhas corrigidas")
        
    elif dry_run:
        print(f"\n💡 Modo DRY-RUN - Execute sem --dry-run para salvar")
    
    else:
        print(f"\n✅ Nenhuma correção necessária!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Corrige CSV corrompido')
    parser.add_argument('--csv', required=True, help='Arquivo CSV para corrigir')
    parser.add_argument('--dry-run', action='store_true', help='Simula sem salvar')
    
    args = parser.parse_args()
    
    fix_csv(args.csv, dry_run=args.dry_run)
