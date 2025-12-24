import pandas as pd
from app import create_app
from src.models import db, Tecnico
from src.services.import_service import ImportService
import io

def verify_import():
    app = create_app()
    with app.app_context():
        print("--- Verifying Import Service ---")
        
        # 1. Setup Data
        data = {
            'Nome': ['Teste Import 1', 'Teste Import 2'],
            'Documento': ['111.111.111-11', '222.222.222-22'],
            'Telefone': ['11999999999', '11888888888'],
            'Cidade': ['Sao Paulo', 'Rio de Janeiro'],
            'Estado': ['SP', 'RJ']
        }
        df = pd.DataFrame(data)
        
        # Convert to Excel bytes
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        
        # Mock FileStorage
        class MockFile:
            def __init__(self, stream, filename):
                self.stream = stream
                self.filename = filename
            def read(self):
                return self.stream.read()
            def __iter__(self):
                return self.stream.__iter__()
                
        mock_file = MockFile(output, 'teste.xlsx')
        
        # 2. Run Import
        print("Running import...")
        result = ImportService.importar_tecnicos(mock_file)
        print("Result:", result)
        
        # 3. Verify
        t1 = Tecnico.query.filter_by(documento='11111111111').first()
        t2 = Tecnico.query.filter_by(documento='22222222222').first()
        
        if t1 and t1.nome == 'Teste Import 1' and t1.cidade == 'Sao Paulo':
            print("✅ T1 Imported Successfully")
        else:
            print("❌ T1 Failed")

        if t2 and t2.nome == 'Teste Import 2':
            print("✅ T2 Imported Successfully")
        else:
            print("❌ T2 Failed")
            
        # 4. Test Update (Resubmit same doc with different name)
        print("\nTesting Update Logic...")
        data_update = {
            'Nome': ['Teste Update 1'],
            'Documento': ['111.111.111-11'], # Same CPF
            'Cidade': ['Campinas'] # New City
        }
        df_update = pd.DataFrame(data_update)
        output_update = io.BytesIO()
        with pd.ExcelWriter(output_update, engine='openpyxl') as writer:
            df_update.to_excel(writer, index=False)
        output_update.seek(0)
        
        mock_file_update = MockFile(output_update, 'update.xlsx')
        result_update = ImportService.importar_tecnicos(mock_file_update)
        print("Update Result:", result_update)
        
        t1_updated = Tecnico.query.filter_by(documento='11111111111').first()
        if t1_updated and t1_updated.nome == 'Teste Update 1' and t1_updated.cidade == 'Campinas':
             print("✅ Update Logic Successful")
        else:
             print("❌ Update Logic Failed")

        # Cleanup
        db.session.delete(t1_updated)
        db.session.delete(t2)
        db.session.commit()
        print("\nCleanup done.")

if __name__ == '__main__':
    verify_import()
