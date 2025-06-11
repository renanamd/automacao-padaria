import streamlit as st
from streamlit_modal import Modal
from datetime import date, datetime
import pandas as pd
import requests
import yagmail
from io import BytesIO
import time

API_POOLING_URL = st.secrets["API_POOLING_URL"]
API_DETALHES_PEDIDO_URL = st.secrets["API_DETALHES_PEDIDO_URL"]
CARDAPIO_API_TOKEN = st.secrets["CARDAPIO_API_TOKEN"]
EMAIL_USER = st.secrets["EMAIL_USER"]
EMAIL_PASS = st.secrets["EMAIL_PASS"]
PRINTER_EMAIL = st.secrets["PRINTER_EMAIL"]
X_API_KEY_WAHA = st.secrets["X_API_KEY_WAHA"]

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
            continue
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
        status     = parsed.get("status", "") or ""
        
        if status.lower() != "confirmed":
            continue
        
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

        produtos_str   = " | ".join(produtos_lista)
        produtos_str_html = "<br>".join(produtos_lista)

        # 3) Endereço (já filtrado pelo parse_order_details)
        rua         = parsed.get("delivery_address_street", "") or "RETIRADA"
        numero      = parsed.get("delivery_address_number", "") or "RETIRADA"
        bairro      = parsed.get("delivery_address_neighborhood", "") or "RETIRADA"
        complemento = parsed.get("delivery_address_complement", "") or ""
        referencia  = parsed.get("delivery_address_reference", "") or ""

        registros.append({
            "Nome Cliente": nome_cliente,
            "Telefone":     telefone,
            "Produtos":     produtos_str,
            "Produtos HTML": produtos_str_html,
            "Rua":          rua,
            "Número":       numero,
            "Bairro":       bairro,
            "Complemento":  complemento,
            "Referência":   referencia
        })

    df = pd.DataFrame(registros, columns=[
        "Nome Cliente", "Telefone", "Produtos", "Produtos HTML",
        "Rua", "Número", "Bairro", "Complemento", "Referência"
    ])
     
    # df_pedidos_menu[["Nome Cliente","Telefone", "Produtos", "Rua", "Número", "Bairro", "Complemento", "Referência"]]
    # df_pedidos_menu[["Nome Cliente","Telefone", "Produtos HTML", "Rua", "Número", "Bairro", "Complemento", "Referência"]]
     
    return df  

def montar_tabela_pedidos_menu(detalhes_pedidos: list) -> pd.DataFrame:
    registros = []

    for parsed in detalhes_pedidos:
        status     = parsed.get("status", "") or ""
        
        if status.lower() != "confirmed":
            continue
        
        # 1) Extrai nome e telefone (já filtrados)
        nome_cliente = parsed.get("customer_name", "") or ""

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


        produtos_str   = " | ".join(produtos_lista)
        produtos_str_html = "<br>".join(produtos_lista)

        registros.append({
            "Cliente":         nome_cliente,
            "Produtos":        produtos_str,
            "Produtos (HTML)": produtos_str_html
        })

    return pd.DataFrame(registros, columns=["Cliente","Produtos","Produtos (HTML)"])

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


def enviar_para_impressao(pdf_bytes: bytes, copies: int) -> bool:
    data_hoje    = datetime.now().strftime("%d/%m/%Y")
    
    try:
        yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASS)

        for copy in range(1, copies + 2):
            assunto = f"[Cópia {copy}/{copies + 1}] Pedidos Orley Pães – {data_hoje}"

            # Cria um BytesIO e define o nome do arquivo
            buf = BytesIO(pdf_bytes)
            buf.name = f"relatorio_pedidos_{copy}.pdf"

            yag.send(
                to="renanalmeida2003@gmail.com",
                subject=assunto,
                contents=f"Segue em anexo a cópia {copy} de {copies + 1} dos pedidos de hoje.",
                attachments=[buf]
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

def get_status_sessao():
    url = "http://147.182.246.108:3000/api/sessions/default"
    
    headers = {
        "x-api-key": X_API_KEY_WAHA,
    } 
    
    response = requests.get(url,headers)
    
    data = response.json()
    
    status = data.get("status")
    
    return status

def ativar_sessoes():
    url = "http://147.182.246.108:3000/api/sessions/default/start"
    
    headers = {
        "x-api-key": X_API_KEY_WAHA,
    } 
    
    response = requests.post(url,headers)
    
    status_code = response.status_code
    
    return status_code
    
def salvar_alteracoes_estoque(df: pd.DataFrame) -> bool:
    try:
        df.to_csv("estoque.csv", index=False)
        
        return True
    
    except Exception as e:
        print(f"Falha na atualização dos dados: {e}")
        return False

def enviar_estoque_para_email(tabela_estoque:str) -> bool:
    
    agora = datetime.now()        
    agora_formatado = agora.strftime("%d/%m/%Y %H:%M")
        
    try:
        yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASS)

        assunto = f"Atualização de Estoque - {agora_formatado}"

        yag.send(
            to="renanalmeida2003@gmail.com",
            subject=assunto,
            contents=f"{tabela_estoque}"
        )

        return True

    except Exception as e:
        print(f"Falha ao enviar para a impressora: {e}")
        return False


def callback_ligar_instancia():
    st.session_state.ativando_instancia = True
    ativar_sessoes()
    
    time.sleep(5)
    
    st.session_state.status_instancia = get_status_sessao()
    st.session_state.ativando_instancia = False
    
    st.rerun()


st.title("🍞 Orley Pães Artesanais")
st.subheader("Escolha o que deseja fazer:")

ids = get_pedidos_pooling(API_POOLING_URL, CARDAPIO_API_TOKEN)
detalhes = get_detalhes_pedido(API_DETALHES_PEDIDO_URL, ids, CARDAPIO_API_TOKEN)
parsed = [parse_order_details(d) for d in detalhes]
df_pedidos_menu = montar_tabela_pedidos_menu(parsed)


with st.expander("Pedidos de Hoje", expanded=True,):
    col1, col2 = st.columns([10,4])
    with col1:
        if st.button("🔄 Atualizar"):
            st.rerun()
    with col2:
        visao = st.radio("A",
            options=["Cards","Tabela"],
            index=0,                        
            label_visibility="collapsed",
            horizontal=True
        )
        
    if visao == "Cards":
        cols = st.columns(2)
        for idx, row in df_pedidos_menu.iterrows():
            nome = row.get("Cliente", "—")
            prod = row.get("Produtos (HTML)", "")
            col = cols[idx % 2]
            with col:
                st.markdown(
                    f"""
                    <div style="
                        border:1px solid #506d2b; 
                        border-radius:8px; 
                        padding:1rem; 
                        margin-bottom:1rem;
                        background:#f2ebde;
                    ">
                    <h5 style="margin:0 0 0.5rem 0; color:#506d2b; padding: 0;><span style="font-size: 16px">{idx + 1}. </span>{nome}</h5>
                    <p style="margin:0;">{prod}</p>
                    </div>  
                    """,
                    unsafe_allow_html=True
                )
    else:
        st.dataframe(df_pedidos_menu[["Cliente","Produtos"]])

# Instancia o modal
modal_pedidos = Modal(
    "📝 Revise os Pedidos",
    key="revisar-pedidos",
    padding=20,
    max_width=900,
)

if st.button("📝 Gerar Lista de Pedidos", type="primary", use_container_width=True):   
    modal_pedidos.open()
        
if modal_pedidos.is_open():    
    with modal_pedidos.container():
        df_pedidos = montar_tabela_pedidos(parsed)
        st.dataframe(df_pedidos[["Nome Cliente","Telefone", "Produtos", "Rua", "Número", "Bairro", "Complemento", "Referência"]], use_container_width=True)

        st.markdown("---")
        st.write("Escolha uma ação abaixo:")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📥 Baixar PDF")
            st.write("Clique no botão abaixo para fazer o download")
            tabela_html = gerar_tabela_html(df_pedidos[["Nome Cliente","Telefone", "Produtos HTML", "Rua", "Número", "Bairro", "Complemento", "Referência"]])
            html_geral = gerar_html(tabela_html)                    
            gerar_pdf = html_to_pdf_api(html_geral, "relatorio_pedidos.pdf")
            hoje = date.today().strftime("%d/%m/%Y")
            nome_pdf = f"relatorio_pedidos_{hoje}.pdf"

            botao_clicado = st.download_button(
                        label="⬇️ Baixar PDF",
                        data=gerar_pdf,
                        file_name=nome_pdf,
                        mime="application/pdf"
            )
                 
        with col2:
            st.subheader("🖨️ Enviar para Impressão")
            st.write("Selecione o número de cópias abaixo")
            with st.form("form_impressao", border=False):
                col1, col2 = st.columns(2)
                with col1:
                    copies = st.number_input(
                        label="A",
                        min_value=1,
                        value=1,
                        step=1,
                        label_visibility="collapsed"
                    )
                with col2:
                    submit = st.form_submit_button("Enviar para Impressora")
                    if submit:
                        with st.spinner("Enviando e-mail para impressora..."):
                            tabela_html = gerar_tabela_html(df_pedidos)
                            html_geral = gerar_html(tabela_html)                    
                            gerar_pdf = html_to_pdf_api(html_geral, "relatorio_pedidos.pdf")
                            impressao = enviar_para_impressao(gerar_pdf,copies=copies)
                            if impressao == True:
                                st.success(f"✅ PDF enviado para impressão! N° Cópias: {copies}")
                            else:
                                st.error("❌ Falha ao enviar para a impressora")

modal_cobranca = Modal(
    "💸 Cobrança de Clientes",
    key="cobranca-clientes",
    padding=20,
    max_width=900,
)

if st.button("💸 Cobrança de Clientes",  type="primary", use_container_width=True): 
    modal_cobranca.open()
    
if "status_instancia" not in st.session_state:
    st.session_state.status_instancia = get_status_sessao()
if "ativando_instancia" not in st.session_state:
    st.session_state.ativando_instancia = False

if modal_cobranca.is_open():
    with modal_cobranca.container():
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Status da Instância")

            # Se estamos no meio de ativação, exibe spinner
            if st.session_state.ativando_instancia:
                with st.spinner("🔄 Ativando instância…"):
                    # só o spinner, a callback já foi disparada no click
                    pass

            # Depois que parar de ativar, exibimos o status
            status = st.session_state.status_instancia
            if status == "WORKING":
                st.success("✅ Instância está ativa!")
                # Botão de envio de cobrança fica aqui
                if st.button("📲 Enviar cobrança para os clientes", use_container_width=True, type="primary"):
                    with st.spinner("⌛️ Disparando cobranças…"):
                        rodar_fluxo_cobranca_clientes()
                    st.success("✅ Cobranças enviadas!")
            else:
                st.error("❌ Instância desligada.\nUse o botão ao lado para ligar.")

        with col2:
            st.subheader("Ações")
            # Botão que dispara o callback
            st.button(
                "🔌 Ligar Instância",
                on_click=callback_ligar_instancia,
                disabled=st.session_state.ativando_instancia,
                use_container_width=True,
                type="primary"
            )
            st.link_button("Verificar instância no WAHA", "http://147.182.246.108:3000/dashboard/", type="secondary", use_container_width=True)
            

modal_estoque = Modal(
    "📦 Gerenciamento do Estoque",
    key="estoque",
    padding=20,
    max_width=900,
)

if st.button("📦 Gerenciamento do Estoque",  type="primary", use_container_width=True): 
    modal_estoque.open()
    
if modal_estoque.is_open():
    with modal_estoque.container():
        
        df_estoque = pd.read_csv("estoque.csv")        
        df_editado = st.data_editor(df_estoque, hide_index=True)
        
        if st.button("💾 Salvar Alterações", type="primary", use_container_width=True):
            with st.spinner("Salvando estoque..."):
                save = salvar_alteracoes_estoque(df_editado)
                df_html = df_editado.to_html(escape=False, classes="table", index=False)
                envio_email = enviar_estoque_para_email(df_html)
                if envio_email:
                    st.success("✅ Estoque atualizado e e-mail enviado")
                else:
                    st.error("❌ Não foi possível atualizar o estoque")
                
        
        
