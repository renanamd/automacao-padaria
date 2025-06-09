import os
import streamlit as st
from streamlit_modal import Modal
import base64
from datetime import date, datetime
import pandas as pd
import pdfkit
import requests
import yagmail

# API_POOLING_URL = st.secrets["API_POOLING_URL"]
# API_DETALHES_PEDIDO_URL = st.secrets["API_DETALHES_PEDIDO_URL"]
# CARDAPIO_API_TOKEN = st.secrets["CARDAPIO_API_TOKEN"]
# EMAIL_USER = st.secrets["EMAIL_USER"]
# EMAIL_PASS = st.secrets["EMAIL_PASS"]
# PRINTER_EMAIL = st.secrets["PRINTER_EMAIL"]

API_POOLING_URL = "https://integracao.cardapioweb.com/api/partner/v1/orders"
API_DETALHES_PEDIDO_URL = "https://integracao.cardapioweb.com/api/partner/v1/orders/"
CARDAPIO_API_TOKEN = "8d6mRcvSvtkBVCpUCGSrZ8rriFP35Hd2TvGNSnmG"
EMAIL_USER = "renanalmeida2003@gmail.com"
EMAIL_PASS = "bojjptclmviqipno"
PRINTER_EMAIL = "orleypadaria@print.epsonconnect.com"


def get_pedidos_pooling(url, token):
    headers = {
        "X-API-KEY": token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        order_ids = [item["id"] for item in data]
        # Ajuste as colunas conforme resposta real da API
        # print(order_ids)
        return order_ids
    except Exception as e:
        print(f"Erro ao buscar pedidos: {e}")
        return []
    
def get_detalhes_pedido(url, order_ids, token):
    headers = {
        "X-API-KEY": token,
        "Content-Type": "application/json"
    }
    
    detalhes = []
    for oid in order_ids:
        url_detalhe = f"{url}{oid}"
        try:
            resp = requests.get(url_detalhe, headers=headers, timeout=10)
            resp.raise_for_status()
            detalhe_json = resp.json()
            detalhes.append(detalhe_json)
        except Exception as e:
            print(f"Erro ao buscar detalhes do pedido {oid}: {e}")
            # Caso queira manter um registro mesmo em erro, poderia fazer:
            # detalhes.append({"id": oid, "error": str(e)})
            continue
        
    # print(detalhes)
    return detalhes


def parse_order_details(order_json: dict) -> dict:
    parsed = {}
    
    # Campos top‐level simples
    parsed["id"] = order_json.get("id")
    parsed["status"] = order_json.get("status")
    parsed["delivery_fee"] = order_json.get("delivery_fee")
    parsed["total"] = order_json.get("total")
    
    # Customer (sub‐nó)
    customer = order_json.get("customer", {})
    parsed["customer_phone"] = customer.get("phone")
    parsed["customer_name"] = customer.get("name")
    
    # Delivery address (sub‐nó)
    addr = order_json.get("delivery_address") or {}
    parsed["delivery_address_street"] = addr.get("street")
    parsed["delivery_address_number"] = addr.get("number")
    parsed["delivery_address_neighborhood"] = addr.get("neighborhood")
    parsed["delivery_address_complement"] = addr.get("complement")
    parsed["delivery_address_reference"] = addr.get("reference")
    
    # Items: cada item vira um dict com campos específicos
    parsed_items = []
    for item in order_json.get("items", []):
        item_dict = {
            "item_name": item.get("name"),
            "item_quantity": item.get("quantity"),
            "item_unit_price": item.get("unit_price"),
            "item_total_price": item.get("total_price"),
        }
        # Se existirem opções dentro de cada item, extrai também
        options_list = []
        for opt in item.get("options", []):
            opt_dict = {
                "option_name": opt.get("name"),
                "option_quantity": opt.get("quantity"),
                "option_unit_price": opt.get("unit_price"),
            }
            options_list.append(opt_dict)
        # Association: lista de opções
        item_dict["item_options"] = options_list
        parsed_items.append(item_dict)
    parsed["items"] = parsed_items
    
    # Discounts: extrai somente “total” de cada desconto
    discounts = order_json.get("discounts", [])
    parsed["discounts_totals"] = [d.get("total") for d in discounts]
    
    # Payments: extrai total e status de cada pagamento
    payments = order_json.get("payments", [])
    parsed_payments = []
    for p in payments:
        pay_dict = {
            "payment_total": p.get("total"),
            "payment_status": p.get("status"),
        }
        parsed_payments.append(pay_dict)
    parsed["payments"] = parsed_payments
    
    return parsed

def montar_tabela_pedidos(detalhes_pedidos: list) -> pd.DataFrame:
    registros = []

    for parsed in detalhes_pedidos:
        # 1) Extrai nome e telefone (já filtrados)
        nome_cliente = parsed.get("customer_name", "") or ""
        telefone     = parsed.get("customer_phone", "") or ""

        # 2) Monta a lista de “Produtos” a partir do parsed['items']
        produtos_lista = []
        items = parsed.get("items") or []

        for item in items:
            # Cada item já é um dict com estas chaves:
            #   'item_name', 'item_quantity', 'item_unit_price', 'item_total_price', 'item_options'
            nome_item = item.get("item_name", "") or ""
            qtd_item  = item.get("item_quantity", 0) or 0
            options   = item.get("item_options") or []

            if isinstance(options, list) and options:
                # Se houver opções dentro do item, use-as no lugar do item_name
                for opt in options:
                    nome_opt = opt.get("option_name", "") or ""
                    qtd_opt  = opt.get("option_quantity", 0) or 0
                    try:
                        qtd_opt_int = int(qtd_opt)
                    except (TypeError, ValueError):
                        qtd_opt_int = 0
                    if nome_opt.strip() != "":
                        produtos_lista.append(f"{qtd_opt_int}x {nome_opt}")
            else:
                # Caso não tenha opções, considere o próprio item normal
                try:
                    qtd_item_int = int(qtd_item)
                except (TypeError, ValueError):
                    qtd_item_int = 0
                if nome_item.strip() != "":
                    produtos_lista.append(f"{qtd_item_int}x {nome_item}")

        # Concatena os produtos com quebra de linha (\n). Se for para HTML, 
        # bastará chamar .replace("\n", "<br>") depois ou usar escape=False.
        produtos_str = " | ".join(produtos_lista)

        # 3) Endereço (já filtrado pelo parse_order_details)
        rua         = parsed.get("delivery_address_street", "") or ""
        numero      = parsed.get("delivery_address_number", "") or ""
        bairro      = parsed.get("delivery_address_neighborhood", "") or ""
        complemento = parsed.get("delivery_address_complement", "") or ""
        referencia  = parsed.get("delivery_address_reference", "") or ""

        registros.append({
            "Nome Cliente": nome_cliente,
            "Telefone":     telefone,
            "Produtos":     produtos_str,
            "Rua":          rua,
            "Número":       numero,
            "Bairro":       bairro,
            "Complemento":  complemento,
            "Referência":   referencia
        })

    df = pd.DataFrame(registros, columns=[
        "Nome Cliente", "Telefone", "Produtos",
        "Rua", "Número", "Bairro", "Complemento", "Referência"
    ])
     
    return df  

def gerar_tabela_html (df: pd.DataFrame) -> str:
    
    html = df.to_html(
        escape=False,
        classes="table"
    )
    return html

def gerar_html(tabela_html):
    
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    tabela_final = (
    tabela_html
    .replace('style="text-align: right;"', 'style="text-align: left;"')
    )
    
    
    html = f"""
    
    <!DOCTYPE html>
    <html lang="en">

    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Document</title>
        <style>
            table{{
                border-collapse: collapse;
                justify-content: stretch;
                text-align: left;
            }}
            thead{{
                align-items: left;
            }}

            th, td{{
                padding: 8px;
            }}
            
        </style>
    </head>

    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
    
    <h1 style="font-size: 24px">Pedidos {data_hoje}</h1>
    
    {tabela_final}
        
    </body>

    </html>    
    
    """
    
    return html
    
# def html_to_pdf(html: str):
       
#     options = {
#     "orientation": "Landscape"
#     }
    
#     config = pdfkit.configuration(
#         wkhtmltopdf='/wkhtmltopdf.exe'
#     )
    
#     try:
#         # aqui retorna um bool e escreve o arquivo em output_path
#         pdf = pdfkit.from_string(html, "relatorio_pedidos.pdf", configuration=config, options=options)
#         return pdf
#     except Exception as e:
#         print(f">> Erro ao gerar PDF: {e}")
#         return []
    
def html_to_pdf_api(html: str, output_path: str):
    url = "https://yakpdf.p.rapidapi.com/pdf"
    payload = {
        "source": { "html": html },
        "pdf": { "format": "A4", "scale": 1, "printBackground": True, "landscape":True},
        "wait": { "for": "navigation", "waitUntil": "load", "timeout": 2500 }
    }
    headers = {
        "x-rapidapi-key": "6ea4cacd39mshb645c8bd387bed2p1fd1fcjsn40c7b4eb77e2",
        "x-rapidapi-host": "yakpdf.p.rapidapi.com",
        "Content-Type": "application/json",
        "Accept": "application/pdf"        # <— às vezes necessário
    }

    response = requests.post(url, json=payload, headers=headers, stream=True)


    if response.status_code != 200 or response.headers.get("Content-Type") != "application/pdf":
        return None
    return response.content

    # with open(output_path, "wb") as f:
    #     for chunk in response.iter_content(8192):
    #         if chunk:
    #             f.write(chunk)

# def baixar_html_to_pdf(html: str) -> bytes | None:
    
#     options = {
        
#     "orientation": "Landscape"
    
#     }
    
    
#     path = pdfkit.configuration(wkhtmltopdf=r'C:\Users\Renan Almeida\wkhtmltopdf\bin\wkhtmltopdf.exe')
    
#     try:
#         # O segundo parâmetro False faz retornar bytes em vez de arquivo
#         pdf_bytes = pdfkit.from_string(html, False, configuration=path, options=options)
#         return pdf_bytes
#     except Exception as e:
#         print(f">> Erro ao gerar PDF: {e}")
#         return None



def enviar_para_impressao() -> bool:
    
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    try:
        yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASS)
        assunto = f"Pedidos Orley Pães - {data_hoje}"

        path = f"C:\\Users\\Renan Almeida\\Desktop\\padaria\\relatorio_pedidos.pdf"

        with open(path, "rb") as f:
            yag.send(
                to="renanalmeida2003@gmail.com",
                subject=assunto,
                contents="Segue em anexo os pedidos de hoje.",
                attachments=[f]
            )
            
        return True

    except Exception as e:
        print(f"Falha ao enviar para a impressora: {e}")
        return False

def rodar_fluxo_cobranca_clientes():
    
    url = "http://localhost:5678/webhook/5ecdd0d8-0bc1-4faf-ae7e-d0a5a5a447d9"
    
    response = requests.get(url)
    
    status = response.status_code        
    
    return status



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
    if st.button("📝 Gerar Lista de Pedidos", type="primary"):   
        modal.open()
        
with col2:
    if st.button("💸 Cobrança de Clientes",  type="primary"): 
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
            # if st.button("Gerar e Baixar PDF"):
            with st.spinner("Gerando o PDF para download..."):
                    tabela_html = gerar_tabela_html(df_pedidos)
                    html_geral = gerar_html(tabela_html)                    
                    gerar_pdf = html_to_pdf_api(html_geral, "relatorio_pedidos.pdf")
                    hoje = date.today().strftime("%d%m%Y")
                    nome_pdf = f"relatorio_pedidos_{hoje}.pdf"

                    st.download_button(
                        label="Baixar PDF",
                        data=gerar_pdf,
                        file_name=nome_pdf,
                        mime="application/pdf"
                    )
                    
            
        with col2:
            st.subheader("🖨️ Enviar para Impressão")
            if st.button("Enviar para Impressora"):
                with st.spinner("Enviando e-mail para impressora..."):
                    tabela_html = gerar_tabela_html(df_pedidos)
                    html_geral = gerar_html(tabela_html)
                    gerar_pdf = html_to_pdf_api(html_geral,"relatorio_pedidos.pdf")
                    impressao = enviar_para_impressao()
                    if impressao:
                        st.success("✅ PDF enviado para impressão!")
                    else:
                        st.error("❌ Falha ao enviar para a impressora.")

        st.markdown("---")
        if st.button("Fechar"):
            modal.close()
