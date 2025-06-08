import requests

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


    # 2) Em caso de erro, imprime o corpo:
    if response.status_code != 200 or response.headers.get("Content-Type") != "application/pdf":
        return

    # 3) Gravação binária
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(8192):
            if chunk:
                f.write(chunk)

# Uso
html = "<h1>aaaaaaaaaaaaaaaaa</h1><p>PDF via API</p>"
html_to_pdf_api(html, "meu_relatorio.pdf")
