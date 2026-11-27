#!/usr/bin/env python3
"""
Painel on-chain · Estratégia Bitcoin
Monta as séries dos gráficos da página painel/ e grava painel/series.json.

Escala de Richter (spot × realizado): a oscilação entre o preço spot e o preço
realizado, com as zonas do MVRV, o custo dos holders de curto prazo (STH) e de
longo prazo (LTH) e a variação semanal da capitalização realizada.
Método publicado em "Preço realizado: o erro que 90% das pessoas cometem ao
analisar o Bitcoin" (Ricardo Richter, Estratégia Bitcoin, 14/04/2026).

Uso:
  python scripts/painel_series.py --saida painel/series.json
  python scripts/painel_series.py --csv btc.csv --sth sth.json --lth lth.json --saida x.json   (teste)

Fontes (gratuitas, sem chave):
  Coin Metrics Community API  preço, MVRV, valor de mercado, oferta (licença CC BY-NC 4.0)
  BGeometrics (bitcoin-data.com) custo dos holders de curto e de longo prazo (plano gratuito,
                              histórico desde 2022 e cerca de 7 dias de atraso)
Se uma fonte falhar, o script mantém os valores do series.json anterior e registra um aviso.
"""
import argparse, json, sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coleta  # reaproveita a leitura da Coin Metrics do Termômetro

ZONAS = [  # cortes do MVRV usados no artigo
    (1.0, "acumulacao", "Acumulação", "Preço spot abaixo do preço realizado: o detentor médio está no prejuízo. Historicamente, zona de capitulação e de acumulação de longo prazo."),
    (3.0, "intermediaria", "Intermediária", "Preço spot acima do custo médio da rede, sem excesso. O mercado está em lucro, mas longe da euforia."),
    (99.0, "euforia", "Euforia e distribuição", "Preço spot muito acima do preço realizado (MVRV de 3 a 4 ou mais). Historicamente, zona de realização de lucros."),
]
AVISOS = []

def zona(mvrv):
    for corte, z, _, _ in ZONAS:
        if mvrv < corte:
            return z
    return ZONAS[-1][1]

def bgeo(endpoint, path=None):
    if path:
        arr = json.load(open(path))
    else:
        arr = coleta.get(f"https://bitcoin-data.com/v1/{endpoint}")
    arr = arr if isinstance(arr, list) else arr.get("data", [])
    out = {}
    for x in arr:
        k = next((c for c in x if c not in ("d", "unixTs", "delayed", "message")), None)
        if k and x.get(k) not in (None, ""):
            out[x["d"][:10]] = round(float(x[k]))
    if not out:
        raise ValueError("série vazia")
    return out

def r2(v, n=2):
    return None if v is None else round(v, n)

def montar(cm, sth, lth, anterior):
    cm = [r for r in cm if r.get("PriceUSD") and r.get("CapMVRVCur") and r.get("CapMrktCurUSD") and r.get("SplyCur")]
    cm.sort(key=lambda r: r["d"])
    datas = [r["d"] for r in cm]
    preco = [float(r["PriceUSD"]) for r in cm]
    mvrv = [float(r["CapMVRVCur"]) for r in cm]
    rc = [float(r["CapMrktCurUSD"]) / v for r, v in zip(cm, mvrv)]
    real = [c / float(r["SplyCur"]) for c, r in zip(rc, cm)]
    mm200s = coleta.sma(preco, 1400)

    # STH e LTH: usa o último valor conhecido até cada data (a fonte tem atraso)
    def preencher(serie):
        out, ult, ult_d = [], None, None
        for d in datas:
            if d in serie:
                ult, ult_d = serie[d], d
            out.append(ult if ult_d and (date.fromisoformat(d) - date.fromisoformat(ult_d)).days <= 21 else None)
        return out
    sth_d, lth_d = preencher(sth), preencher(lth)

    def linha(i):
        rcv = (rc[i] / rc[i - 7] - 1) * 100 if i >= 7 else None
        return [datas[i], r2(preco[i]), r2(real[i]), r2(mvrv[i], 3),
                round(mm200s[i]) if mm200s[i] else None, r2(rcv, 2), sth_d[i], lth_d[i]]

    n = len(datas)
    semanal = [linha(i) for i in range(n) if date.fromisoformat(datas[i]).weekday() == 6 or i == n - 1]
    diario = [linha(i) for i in range(max(0, n - 400), n)]

    i = n - 1
    sth_ult = max(sth) if sth else None
    lth_ult = max(lth) if lth else None
    ultimo = {
        "data": datas[i], "preco": r2(preco[i]), "realizado": r2(real[i]), "mvrv": r2(mvrv[i], 3),
        "desvio_pct": r2((preco[i] / real[i] - 1) * 100, 1), "zona": zona(mvrv[i]),
        "mm200s": round(mm200s[i]) if mm200s[i] else None,
        "rc_var_sem": linha(i)[5],
        "sth": sth.get(sth_ult) if sth_ult else None, "sth_data": sth_ult,
        "lth": lth.get(lth_ult) if lth_ult else None, "lth_data": lth_ult,
    }
    return {
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"),
        "data_ref": datas[i],
        "ultimo": ultimo,
        "zonas": [{"id": z, "nome": nome, "ate": corte, "texto": txt} for corte, z, nome, txt in ZONAS],
        "cols": ["d", "preco", "realizado", "mvrv", "mm200s", "rc_var_sem", "sth", "lth"],
        "semanal": semanal,
        "diario": diario,
        "fontes": "Coin Metrics Community (CC BY-NC 4.0): preço, MVRV e capitalização realizada. BGeometrics: custo dos holders de curto e de longo prazo (desde 2022, cerca de 7 dias de atraso).",
        "avisos": AVISOS,
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--sth"); ap.add_argument("--lth")
    ap.add_argument("--saida", default="painel/series.json")
    a = ap.parse_args()
    anterior = {}
    if Path(a.saida).exists():
        try: anterior = json.load(open(a.saida))
        except Exception: anterior = {}
    def antigos(col):
        cols = anterior.get("cols", [])
        if col not in cols: return {}
        j = cols.index(col)
        return {r[0]: r[j] for r in anterior.get("semanal", []) + anterior.get("diario", []) if r[j] is not None}
    try:
        cm = coleta.coinmetrics_csv(a.csv) if a.csv else coleta.coinmetrics_api()
    except Exception as e:
        print(f"erro: Coin Metrics falhou ({e}); series.json não foi alterado", file=sys.stderr)
        sys.exit(0)
    series = {}
    for nome, ep, path in (("sth", "sth-realized-price", a.sth), ("lth", "lth-realized-price", a.lth)):
        try:
            series[nome] = bgeo(ep, path)
        except Exception as e:
            AVISOS.append(f"{nome}: {e}; mantidos os valores anteriores")
            series[nome] = antigos(nome)
    dados = montar(cm, series["sth"], series["lth"], anterior)
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    with open(a.saida, "w") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    u = dados["ultimo"]
    print(f"ok: {u['data']} · preço {u['preco']} · realizado {u['realizado']} · MVRV {u['mvrv']} · zona {u['zona']} · {len(dados['semanal'])} semanas")
