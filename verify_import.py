from src import create_app
from src.services.pdf_service import PdfService

app = create_app()

def verify_pdf_service():
    with app.app_context():
        print("--- Verificando Importação PDF ---")
        try:
            from xhtml2pdf import pisa
            print("Import 'xhtml2pdf' OK.")
        except ImportError as e:
            print(f"Erro ao importar: {e}")
            exit(1)
            
        print("Serviço PDF carregado sem erros de DLL (GTK).")

if __name__ == "__main__":
    verify_pdf_service()
