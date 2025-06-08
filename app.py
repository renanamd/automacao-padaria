import os
import streamlit as st
from streamlit_modal import Modal
import base64
from datetime import date

from utils import (
    get_pedidos_pooling,
    get_detalhes_pedido,
    parse_order_details,
    montar_tabela_pedidos,
    gerar_tabela_html,
    gerar_html,
    html_to_pdf,
    enviar_para_impressao,
    baixar_html_to_pdf,
    rodar_fluxo_cobranca_clientes
)

API_POOLING_URL = os.getenv("API_POOLING_URL")
API_DETALHES_PEDIDO_URL = os.getenv("API_DETALHES_PEDIDO_URL")
CARDAPIO_API_TOKEN = os.getenv("CARDAPIO_API_TOKEN")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
PRINTER_EMAIL = os.getenv("PRINTER_EMAIL")


st.title("🍞 Orley Pães Artesanais")
st.subheader("Escolha o que deseja fazer:")

# Instancia o modal
modal = Modal(
    "📝 Revise os Pedidos",
    key="revisar-pedidos",
    padding=20,
    max_width=800,
)

col1, col2 = st.columns(2)

with col1:
    if st.button("📝 Gerar Lista de Pedidos"):   
        modal.open()
        
with col2:
    if st.button("💸 Cobrança de Clientes"): 
        with st.spinner("O fluxo está em execução..."):
            status = rodar_fluxo_cobranca_clientes()
        
        if status == 308:
            st.success("✅ A cobrança automática de clientes foi concluída com sucesso.")  
        else:  
            st.error("❌ Falha na execução do fluxo")

if modal.is_open():
    
    ids = get_pedidos_pooling(API_POOLING_URL, CARDAPIO_API_TOKEN)
    detalhes = get_detalhes_pedido(API_DETALHES_PEDIDO_URL, ids, CARDAPIO_API_TOKEN)
    parsed = [parse_order_details(d) for d in detalhes]
    df_pedidos = montar_tabela_pedidos(parsed)
    
    
    with modal.container():
        st.dataframe(df_pedidos, use_container_width=True)

        st.markdown("---")
        st.write("Escolha uma ação abaixo:")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📥 Baixar PDF")
            if st.button("Gerar e Baixar PDF"):
                with st.spinner("Gerando o PDF para download..."):
                    tabela_html = gerar_tabela_html(df_pedidos)
                    html_geral = gerar_html(tabela_html)                    
                    gerar_pdf = baixar_html_to_pdf(html_geral)
                    
                    if gerar_pdf is None:
                        st.error("❌ Não foi possível realizar o download")
                    else:
                    
                        hoje = date.today().strftime("%d/%m/%Y")
                        
                        nome_pdf = f"relatorio_pedidos_{hoje}.pdf"         
                        b64 = base64.b64encode(gerar_pdf).decode('utf-8')
                        href = f'''
                        <a download="{nome_pdf}" href="data:application/pdf;base64,{b64}" id="download-link"></a>
                        <script>document.getElementById("download-link").click();</script>
                        '''
                        st.components.v1.html(href, height=0, width=0)

                        st.success("✅ O download foi iniciado!")
                    
            
        with col2:
            st.subheader("🖨️ Enviar para Impressão")
            if st.button("Enviar para Impressora"):
                with st.spinner("Enviando email para impressora..."):
                    tabela_html = gerar_tabela_html(df_pedidos)
                    html_geral = gerar_html(tabela_html)
                    gerar_pdf = html_to_pdf(html_geral)
                    impressao = enviar_para_impressao()
                    if impressao:
                        st.success("✅ PDF enviado para impressão!")
                    else:
                        st.error("❌ Falha ao enviar para a impressora.")

        st.markdown("---")
        if st.button("Fechar"):
            modal.close()
