#!/usr/bin/env python3
"""
Termômetro do Bitcoin · Estratégia Bitcoin
Coleta os dados públicos, calcula as notas de cada indicador e grava dados.json.

Uso:
  python coleta.py                      # busca tudo nas APIs (modo do GitHub Actions)
  python coleta.py --csv btc.csv        # usa um CSV da Coin Metrics já baixado
  python coleta.py --fng fng.json --macro macro.json   # arquivos extras já baixados

Fontes (todas gratuitas, sem chave):
  Coin Metrics Community API  preço, MVRV, valor de mercado, oferta, hashrate
  alternative.me              Fear & Greed
  Banco Central (SGS)         Selic meta (432), IPCA 12 meses (13522), dólar PTAX (1)
  FRED                        juro do Fed (DFF), Treasury 10 anos (DGS10)
"""
import argparse, csv, json, math, statistics, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

UA = {"User-Agent": "termometro-estrategia-bitcoin/1.0"}

def get(url, as_json=True):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if as_json else raw

# ---------------------------------------------------------------- dados brutos
CM_METRICS = ["PriceUSD", "CapMVRVCur", "CapMrktCurUSD", "SplyCur", "HashRate"]

def coinmetrics_api():
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
           f"?assets=btc&metrics={','.join(CM_METRICS)}&frequency=1d"
           "&start_time=2010-07-18&page_size=10000")
    rows = []
    while url:
        j = get(url)
        rows += j.get("data", [])
        url = j.get("next_page_url")
    return [{"d": r["time"][:10], **{m: r.get(m) for m in CM_METRICS}} for r in rows]

def coinmetrics_csv(path):
    with open(path, newline="") as f:
        return [{"d": r["time"][:10], **{m: r.get(m) or None for m in CM_METRICS}}
                for r in csv.DictReader(f)]

def fear_greed(path=None):
    j = json.load(open(path)) if path else get("https://api.alternative.me/fng/?limit=0&format=json")
    out = {}
    for x in j.get("data", []):
        d = datetime.fromtimestamp(int(x["timestamp"]), tz=timezone.utc).date().isoformat()
        out[d] = int(x["value"])
    return out

def sgs(serie, n=24):
    j = get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/{n}?formato=json")
    return [{"d": datetime.strptime(x["data"], "%d/%m/%Y").date().isoformat(),
             "v": float(x["valor"])} for x in j]

def fred(serie, n=400):
    txt = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}", as_json=False)
    rows = list(csv.reader(txt.splitlines()))[1:]
    out = [{"d": r[0], "v": float(r[1])} for r in rows if r[1] not in (".", "")]
    return out[-n:]

def macro_api():
    m = {}
    for chave, fn in {
        "selic": lambda: sgs(432, 400),
        "ipca12": lambda: sgs(13522, 24),
        "dolar": lambda: sgs(1, 260),
        "fed": lambda: fred("DFF", 400),
        "us10y": lambda: fred("DGS10", 260),
    }.items():
        try:
            m[chave] = fn()
        except Exception as e:  # uma fonte fora do ar não derruba a página
            print(f"aviso: {chave} falhou: {e}", file=sys.stderr)
    return m

# ---------------------------------------------------------------- cálculo
def sma(vals, n):
    out, s, q = [], 0.0, []
    for v in vals:
        q.append(v); s += v
        if len(q) > n: s -= q.pop(0)
        out.append(s / n if len(q) == n else None)
    return out

def rsi(closes, n=14):
    """RSI de Wilder sobre uma lista de fechamentos."""
    out = [None] * len(closes)
    if len(closes) <= n: return out
    ganhos = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    perdas = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag, ap = sum(ganhos[:n]) / n, sum(perdas[:n]) / n
    out[n] = 100 if ap == 0 else 100 - 100 / (1 + ag / ap)
    for i in range(n + 1, len(closes)):
        ag = (ag * (n - 1) + ganhos[i-1]) / n
        ap = (ap * (n - 1) + perdas[i-1]) / n
        out[i] = 100 if ap == 0 else 100 - 100 / (1 + ag / ap)
    return out

def faixa(v, cortes):
    """cortes = 4 limites crescentes -> nota de +2 (abaixo do 1º) a -2 (acima do 4º)."""
    if v is None or (isinstance(v, float) and math.isnan(v)): return None
    for nota, lim in zip((2, 1, 0, -1), cortes):
        if v < lim: return nota
    return -2

# Cada indicador: nome, o que mede, como ler, limites e formato do valor.
INDICADORES = [
    {"id": "mm200s", "nome": "Preço ÷ média de 200 semanas", "curto": "MM 200 semanas",
     "cortes": [1.0, 1.5, 2.5, 3.5], "fmt": "x",
     "explica": "Quanto o preço está acima da média dos últimos ~4 anos. Abaixo de 1,0x só aconteceu nos fundos de ciclo."},
    {"id": "mayer", "nome": "Múltiplo de Mayer", "curto": "Mayer",
     "cortes": [0.8, 1.0, 1.5, 2.4], "fmt": "x",
     "explica": "Preço ÷ média de 200 dias. Acima de 2,4x o mercado costuma estar esticado."},
    {"id": "mvrv", "nome": "MVRV", "curto": "MVRV",
     "cortes": [1.0, 1.5, 2.5, 3.5], "fmt": "x",
     "explica": "Valor de mercado ÷ valor realizado (o preço médio pago por todas as moedas). Abaixo de 1, o holder médio está no prejuízo."},
    {"id": "mvrvz", "nome": "MVRV Z-Score", "curto": "MVRV Z",
     "cortes": [0.0, 1.0, 3.0, 6.0], "fmt": "z",
     "explica": "A distância entre valor de mercado e valor realizado, medida em desvios-padrão da história."},
    {"id": "rsim", "nome": "RSI mensal", "curto": "RSI mensal",
     "cortes": [30, 45, 65, 80], "fmt": "n",
     "explica": "Força relativa de 14 meses nos fechamentos mensais. Acima de 80 é sobrecompra histórica."},
    {"id": "hash", "nome": "Hash Ribbons", "curto": "Hash Ribbons",
     "cortes": None, "fmt": "x",
     "explica": "Média de 30 dias do hashrate ÷ média de 60 dias. Abaixo de 1, mineradores estão desligando máquinas (capitulação)."},
    {"id": "fng", "nome": "Fear & Greed", "curto": "Fear & Greed",
     "cortes": [25, 45, 55, 75], "fmt": "n",
     "explica": "Índice de sentimento de 0 (medo extremo) a 100 (ganância extrema), da alternative.me."},
]

def calcular(cm, fng=None, macro=None):
    cm = [r for r in cm if r.get("PriceUSD") and r.get("CapMVRVCur") and r.get("CapMrktCurUSD")]
    cm.sort(key=lambda r: r["d"])
    datas = [r["d"] for r in cm]
    preco = [float(r["PriceUSD"]) for r in cm]
    mvrv = [float(r["CapMVRVCur"]) for r in cm]
    mc = [float(r["CapMrktCurUSD"]) for r in cm]
    rc = [m / v for m, v in zip(mc, mvrv)]
    sply = [float(r["SplyCur"]) if r.get("SplyCur") else None for r in cm]
    preco_real = [c / s if s else None for c, s in zip(rc, sply)]
    hr = [float(r["HashRate"]) if r.get("HashRate") else 0.0 for r in cm]

    mm1400 = sma(preco, 1400)
    mm200 = sma(preco, 200)
    hr30, hr60 = sma(hr, 30), sma(hr, 60)

    # MVRV Z: desvio-padrão do valor de mercado desde o início até cada dia
    z = []
    n = 0; media = 0.0; m2 = 0.0
    for i in range(len(mc)):
        n += 1; delta = mc[i] - media; media += delta / n; m2 += delta * (mc[i] - media)
        dp = math.sqrt(m2 / n) if n > 1 else None
        z.append((mc[i] - rc[i]) / dp if dp and n > 365 else None)

    # RSI mensal: fechamento de cada mês; o mês corrente usa o último preço
    fech = {}
    for d, p in zip(datas, preco): fech[d[:7]] = p
    meses = sorted(fech)
    r_m = dict(zip(meses, rsi([fech[m] for m in meses], 14)))
    # RSI "ao vivo" do dia: troca o fechamento do mês corrente pelo preço do dia
    rsim = []
    idx_mes = {m: i for i, m in enumerate(meses)}
    closes_m = [fech[m] for m in meses]
    for d, p in zip(datas, preco):
        i = idx_mes[d[:7]]
        if i < 15: rsim.append(None); continue
        janela = closes_m[max(0, i-60):i] + [p]
        rsim.append(rsi(janela, 14)[-1])

    fng = fng or {}
    valores = {
        "mm200s": [p / m if m else None for p, m in zip(preco, mm1400)],
        "mayer": [p / m if m else None for p, m in zip(preco, mm200)],
        "mvrv": mvrv,
        "mvrvz": z,
        "rsim": rsim,
        "hash": [a / b if a and b else None for a, b in zip(hr30, hr60)],
        "fng": [fng.get(d) for d in datas],
    }
    def nota(ind, v):
        if v is None: return None
        if ind["id"] == "hash":   # capitulação de mineradores = zona de valor
            return 1 if v < 1.0 else 0
        return faixa(v, ind["cortes"])

    notas = {ind["id"]: [nota(ind, v) for v in valores[ind["id"]]] for ind in INDICADORES}

    # Série semanal (domingo) para o gráfico, desde que a MM de 200 semanas existe
    inicio = next(i for i, v in enumerate(mm1400) if v)
    hist = []
    for i in range(inicio, len(datas)):
        if datetime.fromisoformat(datas[i]).weekday() == 6 or i == len(datas) - 1:
            hist.append([datas[i], round(preco[i], 2)] +
                        [notas[ind["id"]][i] for ind in INDICADORES])

    ult = len(datas) - 1
    atual = []
    for ind in INDICADORES:
        v = valores[ind["id"]][ult]
        # Fear & Greed pode não ter o dia exato: usa o último disponível
        if v is None and ind["id"] == "fng" and fng:
            d_f = max(fng); v = fng[d_f]
        atual.append({k: ind[k] for k in ("id", "nome", "curto", "explica", "fmt", "cortes")} |
                     {"valor": None if v is None else round(v, 3), "nota": nota(ind, v)})

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "data_ref": datas[ult],
        "preco": round(preco[ult], 2),
        "preco_realizado": round(preco_real[ult], 2) if preco_real[ult] else None,
        "mm200s_valor": round(mm1400[ult], 2),
        "mm200d_valor": round(mm200[ult], 2),
        "var_30d": round(preco[ult] / preco[ult - 30] - 1, 4),
        "var_365d": round(preco[ult] / preco[ult - 365] - 1, 4),
        "indicadores": atual,
        "historico_cols": ["data", "preco"] + [ind["id"] for ind in INDICADORES],
        "historico": hist,
        "macro": macro or {},
    }

def cartoes_macro(m):
    """Transforma as séries macro nos cartões que a página mostra."""
    br = lambda v, d=2: f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    dt = lambda iso: "/".join(reversed(iso.split("-")))
    cfg = [
        ("selic", "Selic", lambda v: f"{br(v)}%", "ao ano (meta)", "Banco Central (SGS 432)",
         "Juro básico do Brasil. Quanto mais alto, mais caro o dinheiro e maior a concorrência com ativos de risco."),
        ("ipca12", "Inflação 12 meses", lambda v: f"{br(v)}%", "IPCA acumulado", "IBGE via Banco Central (SGS 13522)",
         "A meta é 3% com tolerância até 4,5%. Inflação alta corrói o real e reforça a tese de reserva de valor."),
        ("dolar", "Dólar", lambda v: f"R$ {br(v)}", "PTAX venda", "Banco Central (SGS 1)",
         "Bitcoin em reais sobe quando o real perde valor, mesmo com o preço em dólar parado."),
        ("fed", "Juro dos EUA", lambda v: f"{br(v)}%", "Fed funds efetivo, ao ano", "FRED (DFF)",
         "O custo do dólar no mundo. Juro americano em queda costuma ajudar ativos de risco."),
        ("us10y", "Treasury 10 anos", lambda v: f"{br(v)}%", "rendimento", "FRED (DGS10)",
         "Juro longo dos EUA: a referência de 'retorno sem risco' com que o Bitcoin compete."),
    ]
    out = []
    for chave, nome, fmt, un, fonte, leitura in cfg:
        s = m.get(chave)
        if not s: continue
        u = s[-1]
        out.append({"id": chave, "nome": nome, "valor": fmt(u["v"]), "unidade": un,
                    "data": dt(u["d"]), "fonte": fonte, "leitura": leitura})
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--fng"); ap.add_argument("--macro")
    ap.add_argument("--saida", default="dados.json")
    a = ap.parse_args()
    cm = coinmetrics_csv(a.csv) if a.csv else coinmetrics_api()
    try:
        fng = fear_greed(a.fng) if (a.fng or not a.csv) else {}
    except Exception as e:
        print(f"aviso: Fear & Greed falhou: {e}", file=sys.stderr); fng = {}
    if a.macro: macro = json.load(open(a.macro))
    elif not a.csv: macro = macro_api()
    else: macro = {}
    dados = calcular(cm, fng, {} if isinstance(macro, list) else macro)
    dados["macro_cards"] = macro if isinstance(macro, list) else cartoes_macro(macro)
    with open(a.saida, "w") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    print(f"ok: {dados['data_ref']} · preço {dados['preco']} · {len(dados['historico'])} semanas")
