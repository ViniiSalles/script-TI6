#!/usr/bin/env python3
"""
Teste de Validação: Métricas SonarQube no CSV

Verifica se todas as 13 métricas coletadas pelo SonarQube
estão sendo corretamente salvas no CSV de saída.
"""

import csv
import tempfile
import os
from dataset_manager import DatasetManager


def test_sonarqube_metrics_in_csv():
    """Testa se todas as 13 métricas SonarQube aparecem no CSV"""
    
    print("="*80)
    print("🧪 TESTE: Validação de Métricas SonarQube no CSV")
    print("="*80)
    
    # Métricas que devem estar no CSV (13 campos)
    expected_metrics = [
        'bugs',
        'vulnerabilities', 
        'code_smells',
        'sqale_index',
        'coverage',
        'duplicated_lines_density',
        'ncloc',
        'complexity',
        'cognitive_complexity',
        'reliability_rating',
        'security_rating',
        'sqale_rating',
        'alert_status'
    ]
    
    # Cria dataset de teste
    temp_csv = os.path.join(tempfile.gettempdir(), "test_metrics.csv")
    
    try:
        # Cria CSV inicial
        with open(temp_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['owner', 'name', 'full_name', 'stars', 'forks'])
            writer.writeheader()
            writer.writerow({
                'owner': 'test',
                'name': 'repo',
                'full_name': 'test/repo',
                'stars': 100,
                'forks': 50
            })
        
        # Carrega com DatasetManager
        dm = DatasetManager(temp_csv)
        dataset = dm.load_dataset()
        
        # Adiciona repositório com métricas completas
        repo = dataset['repositories'][0]
        repo['sonarqube_analyzed'] = True
        repo['sonarqube_analyzed_at'] = '2025-11-16T10:00:00'
        repo['sonarqube_metrics'] = {
            'bugs': 10,
            'vulnerabilities': 5,
            'code_smells': 25,
            'sqale_index': 120,
            'coverage': 85.5,
            'duplicated_lines_density': 3.2,
            'ncloc': 5000,
            'complexity': 150,
            'cognitive_complexity': 200,
            'reliability_rating': 'A',
            'security_rating': 'B',
            'sqale_rating': 'A',
            'alert_status': 'OK'
        }
        
        # Salva dataset (gera CSV com análises)
        dm.save_dataset(dataset)
        
        # Verifica se arquivo _analyzed.csv foi criado
        analyzed_csv = temp_csv.replace('.csv', '_analyzed.csv')
        
        if not os.path.exists(analyzed_csv):
            print("❌ FALHA: Arquivo *_analyzed.csv não foi criado")
            return False
        
        # Lê CSV gerado e verifica cabeçalhos
        with open(analyzed_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            print(f"\n📋 Cabeçalhos do CSV ({len(headers)} campos):")
            for h in headers:
                print(f"   • {h}")
            
            # Verifica cada métrica esperada
            print(f"\n🔍 Validando {len(expected_metrics)} métricas SonarQube:")
            missing_metrics = []
            
            for metric in expected_metrics:
                if metric in headers:
                    print(f"   ✅ {metric}")
                else:
                    print(f"   ❌ {metric} - FALTANDO!")
                    missing_metrics.append(metric)
            
            # Lê valores da primeira linha
            f.seek(0)
            reader = csv.DictReader(f)
            row = next(reader)
            
            print(f"\n📊 Valores das métricas no CSV:")
            for metric in expected_metrics:
                if metric in row:
                    value = row[metric]
                    print(f"   • {metric}: {value}")
            
            # Resultado final
            print(f"\n{'='*80}")
            if missing_metrics:
                print(f"❌ TESTE FALHOU - {len(missing_metrics)} métricas faltando:")
                for m in missing_metrics:
                    print(f"   • {m}")
                return False
            else:
                print(f"✅ TESTE PASSOU - Todas as {len(expected_metrics)} métricas presentes!")
                return True
        
    finally:
        # Limpa arquivos temporários
        for f in [temp_csv, temp_csv.replace('.csv', '_analyzed.csv')]:
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    success = test_sonarqube_metrics_in_csv()
    exit(0 if success else 1)
