import pandas as pd
import pdfkit
import requests
import os
from datetime import datetime
import yagmail
from dotenv import load_dotenv

load_dotenv()  # carrega variáveis do .env

# Variáveis de ambiente (definidas no .env)
API_POOLING_URL = os.getenv("API_POOLING_URL")
API_DETALHES_PEDIDO_URL = os.getenv("API_DETALHES_PEDIDO_URL")
CARDAPIO_API_TOKEN = os.getenv("CARDAPIO_API_TOKEN")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
PRINTER_EMAIL = os.getenv("PRINTER_EMAIL")

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
    
def html_to_pdf(html: str):
    
    options = {
    "orientation": "Landscape"
    }
    
    config = pdfkit.configuration(
        wkhtmltopdf=r'C:\Users\Renan Almeida\wkhtmltopdf\bin\wkhtmltopdf.exe'
    )
    
    try:
        # aqui retorna um bool e escreve o arquivo em output_path
        pdf = pdfkit.from_string(html, "relatorio_pedidos.pdf", configuration=config, options=options)
        return pdf
    except Exception as e:
        print(f">> Erro ao gerar PDF: {e}")
        return []

def baixar_html_to_pdf(html: str) -> bytes | None:
    
    options = {
        
    "orientation": "Landscape"
    
    }
    
    
    path = pdfkit.configuration(wkhtmltopdf=r'C:\Users\Renan Almeida\wkhtmltopdf\bin\wkhtmltopdf.exe')
    
    try:
        # O segundo parâmetro False faz retornar bytes em vez de arquivo
        pdf_bytes = pdfkit.from_string(html, False, configuration=path, options=options)
        return pdf_bytes
    except Exception as e:
        print(f">> Erro ao gerar PDF: {e}")
        return None



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
    
    url = "http://localhost:5678/webhook-test/5ecdd0d8-0bc1-4faf-ae7e-d0a5a5a447d9"
    
    response = requests.get(url)
    
    status = response.status_code        
    
    return status



# ids = get_pedidos_pooling(API_POOLING_URL, CARDAPIO_API_TOKEN)

# detalhes = get_detalhes_pedido(API_DETALHES_PEDIDO_URL, ids, CARDAPIO_API_TOKEN)

# detalhes_formatados = [parse_order_details(pedido_json) for pedido_json in detalhes]

# tabela_pedidos = montar_tabela_pedidos(detalhes_formatados)

# tabela_html = gerar_tabela_html(tabela_pedidos)

# html_geral = gerar_html(tabela_html)

# pdf = html_to_pdf(html_geral)

# send_to_printer()
