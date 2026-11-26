#!/usr/bin/env python3
"""
Ferramentas · Estratégia Bitcoin
Grava os dados das páginas ETFs (etfs/) e Calculadora DCA (dca/).

  ferramentas/etf.json    fluxo líquido diário dos ETFs de Bitcoin à vista dos EUA, em BTC,
                          com o preço do dia (para converter em US$ e estimar o custo médio)
  ferramentas/dolar.json  dólar médio mensal (para a calculadora em reais)

A calculadora também lê painel/series.json (preço e MVRV semanais, Indicador Richter).

Uso:
  python scripts/ferramentas.py --pasta ferramentas
  python scripts/ferramentas.py --pasta x --fluxos fluxos.json --precos precos.csv --dolar dolar.json   (teste)

Fontes (gratuitas, sem chave):
  BGeometrics (bitcoin-data.com) /v1/etf-flow-btc  soma diária das entradas e saídas dos ETFs à vista, em BTC
  Coin Metrics Community API     PriceUSD diário (licença CC BY-NC 4.0)
  Banco Central, SGS 3698        dólar (venda), média mensal
Se uma fonte falhar, o script mantém o arquivo anterior daquela parte e registra um aviso.
"""
import argparse, csv, json, sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coleta

LANCAMENTO = "2024-01-11"   # primeiro pregão dos ETFs à vista nos EUA
AVISOS = []

def fluxos_etf(path=None):
    arr = json.load(open(path)) if path else coleta.get("https://bitcoin-data.com/v1/etf-flow-btc")
    arr = arr if isinstance(arr, list) else arr.get("data", [])
    out = {}
    for x in arr:
        v = x.get("etfFlow")
        if v in (None, ""):
            continue
        d = x["d"][:10]
        if d >= LANCAMENTO:
            out[d] = round(float(v), 2)
    if len(out) < 100:
        raise ValueError(f"poucos dias de fluxo ({len(out)})")
    return out

def precos(path=None):
    if path:
        with open(path, newline="") as f:
            return {r["time"][:10]: float(r["PriceUSD"]) for r in csv.DictReader(f) if r.get("PriceUSD")}
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
           "?assets=btc&metrics=PriceUSD&frequency=1d&start_time=2024-01-01&page_size=10000")
    out = {}
    while url:
        j = coleta.get(url)
        for r in j.get("data", []):
            if r.get("PriceUSD"):
                out[r["time"][:10]] = float(r["PriceUSD"])
        url = j.get("next_page_url")
    if not out:
        raise ValueError("preços vazios")
    return out

def dolar_mensal(path=None):
    j = json.load(open(path)) if path else coleta.get(
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.3698/dados?formato=json"
        f"&dataInicial=01/01/2012&dataFinal={date.today():%d/%m/%Y}")
    out = [[datetime.strptime(x["data"], "%d/%m/%Y").strftime("%Y-%m"), round(float(x["valor"]), 4)] for x in j]
    if len(out) < 100:
        raise ValueError("série do dólar curta")
    return out

def anterior(p):
    try:
        return json.load(open(p))
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="ferramentas")
    ap.add_argument("--fluxos"); ap.add_argument("--precos"); ap.add_argument("--dolar")
    a = ap.parse_args()
    pasta = Path(a.pasta); pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00")

    # ETFs
    p_etf = pasta / "etf.json"
    try:
        F = fluxos_etf(a.fluxos); P = precos(a.precos)
        linhas, ult = [], None
        for d in sorted(F):
            pr = P.get(d) or ult          # sem preço do dia: usa o último conhecido
            if pr is None:
                continue
            ult = pr
            linhas.append([d, F[d], round(pr, 2)])
        etf = {"gerado_em": agora, "data_ref": linhas[-1][0], "preco_atual": round(P[max(P)], 2),
               "preco_data": max(P), "cols": ["d", "fluxo_btc", "preco"], "fluxos": linhas,
               "fontes": "BGeometrics (fluxo líquido diário dos ETFs de Bitcoin à vista dos EUA, em BTC) e Coin Metrics Community (preço, CC BY-NC 4.0).",
               "avisos": []}
        json.dump(etf, open(p_etf, "w"), ensure_ascii=False, separators=(",", ":"))
        print(f"etf.json: {len(linhas)} pregões até {etf['data_ref']}")
    except Exception as e:
        AVISOS.append(f"AVISO ETFs: {e}; mantido o arquivo anterior")
        old = anterior(p_etf)
        if old:
            old.setdefault("avisos", []).append(f"{agora[:10]}: {e}")
            json.dump(old, open(p_etf, "w"), ensure_ascii=False, separators=(",", ":"))

    # Dólar
    p_usd = pasta / "dolar.json"
    try:
        dm = dolar_mensal(a.dolar)
        json.dump({"gerado_em": agora, "serie": "BC SGS 3698, dólar venda, média mensal", "mensal": dm},
                  open(p_usd, "w"), ensure_ascii=False, separators=(",", ":"))
        print(f"dolar.json: {len(dm)} meses até {dm[-1][0]}")
    except Exception as e:
        AVISOS.append(f"AVISO dólar: {e}; mantido o arquivo anterior")

    for x in AVISOS:
        print(x)

if __name__ == "__main__":
    main()
