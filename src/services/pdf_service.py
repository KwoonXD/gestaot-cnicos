from flask import render_template, current_app
from xhtml2pdf import pisa
import io
from datetime import datetime
import os

class PdfService:
    @staticmethod
    def gerar_comprovante_pagamento(tecnico, pagamento):
        """
        Gera o comprovante de pagamento em PDF usando xhtml2pdf.
        Retorna: bytes do arquivo PDF.
        """
        agora = datetime.now().strftime('%d/%m/%Y às %H:%M:%S')
        
        # Renderizar o HTML
        html_string = render_template(
            'reports/pagamento_pdf.html',
            tecnico=tecnico,
            pagamento=pagamento,
            agora=agora
        )
        
        # Gerar o PDF
        pdf_file = io.BytesIO()
        
        # Configurar base path para imagens estáticas
        # xhtml2pdf precisa de caminhos absolutos locais para imagens
        if current_app.static_folder:
             # Hack para xhtml2pdf encontrar imagens se estiverem referenciadas como /static/...
             # Mas o ideal no template é usar caminhos absolutos ou lidar com o link callback.
             # Por simplicidade, assumindo que o template HTML está pronto, vamos tentar converter direto.
             pass

        pisa_status = pisa.CreatePDF(
            io.StringIO(html_string),
            dest=pdf_file
        )
        
        if pisa_status.err:
            current_app.logger.error(f"Erro ao gerar PDF: {pisa_status.err}")
            return None
            
        pdf_file.seek(0)
        return pdf_file
