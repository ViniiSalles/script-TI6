#!/usr/bin/env python3
"""
Teste: Persistência de Análises no CSV

Verifica se análises são mantidas entre múltiplas execuções
(não sobrescreve análises anteriores)
"""

import csv
import tempfile
import os
from datetime import datetime
from dataset_manager import DatasetManager


def test_incremental_csv_updates():
    """Testa se análises são incrementadas ao invés de sobrescritas"""
    
    print("="*80)
    print("🧪 TESTE: Persistência Incremental de Análises CSV")
    print("="*80)
    
    # Cria CSV inicial
    temp_dir = tempfile.gettempdir()
    test_csv = os.path.join(temp_dir, "test_incremental.csv")
    
    try:
        # 1. Cria CSV inicial com 3 repos
        print("\n📝 Etapa 1: Criando CSV inicial com 3 repositórios...")
        with open(test_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['owner', 'name', 'full_name', 'stars', 'forks', 
                                                   'language', 'release_count', 'contributors', 
                                                   'median_release_interval', 'release_type'])
            writer.writeheader()
            for i in range(3):
                writer.writerow({
                    'owner': f'owner{i}',
                    'name': f'repo{i}',
                    'full_name': f'owner{i}/repo{i}',
                    'stars': 100,
                    'forks': 50,
                    'language': 'Python',
                    'release_count': 20,
                    'contributors': 25,
                    'median_release_interval': 70,
                    'release_type': 'slow'
                })
        
        # 2. Primeira análise - repo0
        print("\n🔬 Etapa 2: Analisando repo0...")
        dm = DatasetManager(test_csv)
        dataset = dm.load_dataset()
        
        dataset['repositories'][0]['sonarqube_analyzed'] = True
        dataset['repositories'][0]['sonarqube_analyzed_at'] = datetime.now().isoformat()
        dataset['repositories'][0]['sonarqube_metrics'] = {
            'bugs': 10, 'vulnerabilities': 5, 'code_smells': 20,
            'ncloc': 1000, 'complexity': 100
        }
        dm.save_dataset(dataset)
        print("   ✅ repo0 analisado e salvo")
        
        # 3. Segunda análise - repo1 (sem recarregar dataset)
        print("\n🔬 Etapa 3: Analisando repo1 (NOVA INSTÂNCIA)...")
        dm2 = DatasetManager(test_csv)  # Nova instância simula novo processo
        dataset2 = dm2.load_dataset()
        
        print(f"   📊 Repos carregados: {len(dataset2['repositories'])}")
        print(f"   📊 Repo0 analisado? {dataset2['repositories'][0].get('sonarqube_analyzed', False)}")
        print(f"   📊 Repo1 analisado? {dataset2['repositories'][1].get('sonarqube_analyzed', False)}")
        
        dataset2['repositories'][1]['sonarqube_analyzed'] = True
        dataset2['repositories'][1]['sonarqube_analyzed_at'] = datetime.now().isoformat()
        dataset2['repositories'][1]['sonarqube_metrics'] = {
            'bugs': 15, 'vulnerabilities': 8, 'code_smells': 25,
            'ncloc': 2000, 'complexity': 150
        }
        dm2.save_dataset(dataset2)
        print("   ✅ repo1 analisado e salvo")
        
        # 4. Terceira análise - repo2
        print("\n🔬 Etapa 4: Analisando repo2 (NOVA INSTÂNCIA)...")
        dm3 = DatasetManager(test_csv)
        dataset3 = dm3.load_dataset()
        
        print(f"   📊 Repos carregados: {len(dataset3['repositories'])}")
        print(f"   📊 Repo0 analisado? {dataset3['repositories'][0].get('sonarqube_analyzed', False)}")
        print(f"   📊 Repo1 analisado? {dataset3['repositories'][1].get('sonarqube_analyzed', False)}")
        print(f"   📊 Repo2 analisado? {dataset3['repositories'][2].get('sonarqube_analyzed', False)}")
        
        dataset3['repositories'][2]['sonarqube_analyzed'] = True
        dataset3['repositories'][2]['sonarqube_analyzed_at'] = datetime.now().isoformat()
        dataset3['repositories'][2]['sonarqube_metrics'] = {
            'bugs': 20, 'vulnerabilities': 3, 'code_smells': 30,
            'ncloc': 3000, 'complexity': 200
        }
        dm3.save_dataset(dataset3)
        print("   ✅ repo2 analisado e salvo")
        
        # 5. Validação final
        print("\n✅ Etapa 5: Validando persistência de TODAS as análises...")
        dm_final = DatasetManager(test_csv)
        dataset_final = dm_final.load_dataset()
        
        analyzed_count = sum(1 for r in dataset_final['repositories'] if r.get('sonarqube_analyzed', False))
        
        print(f"\n{'='*80}")
        print("📊 RESULTADO FINAL:")
        print(f"   • Total de repositórios: {len(dataset_final['repositories'])}")
        print(f"   • Repositórios analisados: {analyzed_count}")
        
        for i, repo in enumerate(dataset_final['repositories']):
            status = "✅ ANALISADO" if repo.get('sonarqube_analyzed', False) else "❌ PENDENTE"
            metrics = repo.get('sonarqube_metrics', {})
            bugs = metrics.get('bugs', 'N/A')
            ncloc = metrics.get('ncloc', 'N/A')
            print(f"   • {repo['full_name']}: {status} (bugs: {bugs}, ncloc: {ncloc})")
        
        # Verifica arquivo _analyzed.csv
        analyzed_csv = test_csv.replace('.csv', '_analyzed.csv')
        if os.path.exists(analyzed_csv):
            with open(analyzed_csv, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print(f"\n📄 Arquivo {os.path.basename(analyzed_csv)}: {len(lines)-1} linhas de dados")
        
        # Resultado
        if analyzed_count == 3:
            print(f"\n{'='*80}")
            print("✅ TESTE PASSOU - Todas as 3 análises foram persistidas!")
            print("   As análises são mantidas entre execuções (não sobrescritas)")
            return True
        else:
            print(f"\n{'='*80}")
            print(f"❌ TESTE FALHOU - Esperado 3 análises, encontrado {analyzed_count}")
            print("   Análises estão sendo perdidas entre execuções!")
            return False
        
    finally:
        # Limpa arquivos temporários
        for f in [test_csv, test_csv.replace('.csv', '_analyzed.csv')]:
            if os.path.exists(f):
                os.remove(f)
                print(f"🗑️  Removido: {f}")


if __name__ == "__main__":
    success = test_incremental_csv_updates()
    exit(0 if success else 1)
