#!/usr/bin/env python3
"""Monta as partes automáticas do index.html.

- Acervo (filtros + cartões dos livros) a partir de dados/livros.json
- Capas reais nos "Comentados na newsletter" e nos "Kits de leitura"
- "Os textos mais recentes" a partir do feed do Substack
- Contadores (livros, PDFs grátis, textos publicados)

Roda no GitHub Actions (.github/workflows/atualizar.yml). Se o Substack
não responder, a lista de textos fica como estava.
"""
import html
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
INDEX = RAIZ / "index.html"
LIVROS = RAIZ / "dados" / "livros.json"
CONFIG_POSTS = RAIZ / "dados" / "posts.json"
SUBSTACK = "https://estrategiabitcoin.substack.com"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml;q=0.9,text/html;q=0.8,*/*;q=0.7",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
FUSO = ZoneInfo("America/Sao_Paulo")
MESES = "JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ".split()

# Ordem dos filtros e estilo da capa provisória (quando o livro não tem capa)
ESTANTES = {
    "Bitcoin": ("BTC", "#21428b", "#ffffff", ""),
    "Economia": ("ECO", "#27934b", "#171717", ""),
    "Escola Austríaca": ("AUS", "#171717", "#fddd10", ""),
    "Negócios e finanças": ("NEG", "#fddd10", "#171717", "yellow"),
    "Literatura": ("LIT", "#ffffff", "#171717", "white"),
    "Outros": ("OUT", "#3f3f46", "#ffffff", ""),
}

e = lambda s: html.escape(s or "", quote=True)
ARROW = '<span class="ar" aria-hidden="true">↗</span>'
EXT = 'target="_blank" rel="noopener"'


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def baixar(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def trocar_bloco(h, nome, novo):
    ini, fim = f"<!-- {nome}:INICIO", f"<!-- {nome}:FIM -->"
    i = h.index(ini)
    i = h.index("-->", i) + 3
    j = h.index(fim)
    return h[:i] + "\n" + novo + "\n    " + h[j:]


# ---------- Livros ----------
def carregar_livros():
    livros = json.loads(LIVROS.read_text(encoding="utf-8"))
    ids = set()
    for b in livros:
        for campo in ("id", "titulo", "autor", "estante"):
            if not b.get(campo):
                sys.exit(f"Livro sem '{campo}': {b}")
        if b["id"] in ids:
            sys.exit(f"ID repetido em dados/livros.json: {b['id']}")
        ids.add(b["id"])
        if b["estante"] not in ESTANTES:
            sys.exit(f"Estante desconhecida em {b['id']}: {b['estante']} (use: {', '.join(ESTANTES)})")
        if not (b.get("comprar") or b.get("pdf")):
            sys.exit(f"{b['id']} precisa de 'comprar' ou 'pdf'")
    return livros


def capa_html(b, tamanho, badge=True):
    """Capa real (link para a compra) ou a capa provisória da estante."""
    free = b.get("pdf") and badge
    if b.get("capa"):
        destino = b.get("comprar") or b.get("pdf")
        badge_html = '<span class="free">PDF GRÁTIS</span>' if (free and tamanho == "lg") else ('<span class="free">PDF</span>' if free else "")
        larg, alt = (180, 270) if tamanho == "lg" else (96, 142)
        return (f'<a class="cover cover-{tamanho} foto" href="{e(destino)}" {EXT} '
                f'aria-label="{e(b["titulo"])}: ver o livro">'
                f'<img src="{e(b["capa"])}" alt="Capa do livro {e(b["titulo"])}" width="{larg}" height="{alt}" loading="lazy" decoding="async">'
                f"{badge_html}</a>")
    cc, bg, fg, extra = ESTANTES[b["estante"]]
    cls = f"cover cover-{tamanho}" + (f" {extra}" if extra else "")
    if tamanho == "lg":
        return (f'<div class="{cls}" style="--bg:{bg};--fg:{fg}" aria-hidden="true">'
                + ('<span class="free">PDF GRÁTIS</span>' if free else "")
                + f'<span class="ct">{e(b["titulo"])}</span><span class="ca">{e(b["autor"])}</span>'
                f'<span class="cf"><span class="disc" aria-hidden="true">₿</span><span>{e(b["id"])}</span></span></div>')
    return (f'<div class="{cls}" style="--bg:{bg};--fg:{fg}" aria-hidden="true"><span class="cc">{cc}</span>'
            f'<span class="disc" aria-hidden="true">₿</span></div>')


def cartao(b):
    pdf = bool(b.get("pdf"))
    q = f'{b["titulo"]} {b["autor"]} {b["estante"]}'
    tags = []
    if pdf:
        tags.append('<span class="tag free">PDF grátis</span>')
    if b.get("comentado"):
        tags.append(f'<a class="tag cit" href="{e(b["comentado"])}" {EXT}>Comentado na newsletter{ARROW}</a>')
    links = []
    if pdf:
        links.append(f'<a class="f" href="{e(b["pdf"])}" {EXT}>Baixar PDF grátis</a>')
        if b.get("comprar"):
            links.append(f'<a href="{e(b["comprar"])}" {EXT}>Comprar{ARROW}</a>')
    else:
        links.append(f'<a class="f" href="{e(b["comprar"])}" {EXT}>Ver na Amazon{ARROW}</a>')
    return (f'<article class="bk" id="livro-{b["id"].lower()}" data-cat="{e(b["estante"])}" data-pdf="{1 if pdf else 0}" data-q="{e(q)}">'
            f'{capa_html(b, "sm")}<div><p class="meta">{e(b["id"])} · {e(b["estante"])}</p>'
            f'<h4>{e(b["titulo"])}</h4><p class="au">{e(b["autor"])}</p>'
            + (f'<p class="why">{e(b.get("resumo"))}</p>' if b.get("resumo") else "")
            + (f'<div class="tags">{"".join(tags)}</div>' if tags else "")
            + f'<div class="links">{"".join(links)}</div></div></article>')


def bloco_acervo(livros):
    n = len(livros)
    chips = [f'<button class="chip" type="button" id="f-todos" data-cat="Todos" aria-pressed="true">Todos<span>{n}</span></button>']
    for k, est in enumerate(ESTANTES, 1):
        c = sum(b["estante"] == est for b in livros)
        if c:
            chips.append(f'<button class="chip" type="button" id="f-{k}" data-cat="{e(est)}" aria-pressed="false">{e(est)}<span>{c}</span></button>')
    npdf = sum(bool(b.get("pdf")) for b in livros)
    chips.append(f'<button class="chip pdf" type="button" id="f-pdf" aria-pressed="false">Só PDF grátis<span>{npdf}</span></button>')
    chips.append(f'<span class="count" id="count" aria-live="polite">{n} livros</span>')
    ordem = list(ESTANTES)
    livros_ord = sorted(livros, key=lambda b: (ordem.index(b["estante"]), b["id"]))
    return ('    <div class="chips" role="group" aria-label="Filtrar por estante">' + "".join(chips) + "</div>\n"
            '    <div class="books" id="books">' + "".join(cartao(b) for b in livros_ord) + "</div>")


def capas_destaques(h, livros):
    por_id = {b["id"]: b for b in livros}
    por_titulo = {norm(b["titulo"]): b for b in livros}

    def feat(m):
        bloco = m.group(0)
        mid = re.search(r'<p class="meta">(EB-\d+)', bloco)
        b = por_id.get(mid.group(1)) if mid else None
        if not b:
            return bloco
        return re.sub(r'<div class="feat-art">.*?</div>(?=\s*<div class="feat-body">)',
                      lambda _: f'<div class="feat-art">{capa_html(b, "lg")}</div>', bloco, count=1, flags=re.S)

    h = re.sub(r'<article class="feat">.*?</article>', feat, h, flags=re.S)

    def kit(m):
        bloco = m.group(0)
        achados = []

        def item(mi):
            b = por_titulo.get(norm(html.unescape(mi.group(2))))
            achados.append(b)
            if b and b.get("capa"):
                return f'<li><img class="mini" src="{e(b["capa"])}" alt="" width="24" height="36" loading="lazy"><span class="t">{mi.group(2)}<small>'
            return mi.group(0)

        bloco = re.sub(r'<li>(<i [^>]*></i>|<img class="mini"[^>]*>)<span class="t">(.*?)<small>', item, bloco)
        if achados and all(b and b.get("capa") for b in achados):
            imgs = "".join(f'<img src="{e(b["capa"])}" alt="" width="44" height="64" loading="lazy">' for b in achados)
            bloco = re.sub(r'<div class="kit-art" aria-hidden="true">.*?</div>(?=\s*<div class="kit-body">)',
                           lambda _: f'<div class="kit-art" aria-hidden="true">{imgs}</div>', bloco, count=1, flags=re.S)
        return bloco

    return re.sub(r'<article class="kit">.*?</article>', kit, h, flags=re.S)


# ---------- Textos do Substack ----------
def rotulo(slug, desc, cfg):
    if slug in cfg.get("rotulos", {}):
        return cfg["rotulos"][slug], desc
    m = re.match(r"\s*ON-CHAIN\s*#\s*(\d+)[^/]*/+\s*(.*)", desc, re.S)
    if m:
        return f"On-chain #{m.group(1)}", m.group(2)
    return "Texto", desc


def bloco_posts(cfg):
    xml = baixar(SUBSTACK + "/feed")
    canal = ET.fromstring(xml).find("channel")
    itens = []
    ocultar = set(cfg.get("ocultar", []))
    for it in canal.findall("item"):
        link = (it.findtext("link") or "").strip()
        slug = link.rstrip("/").split("/p/")[-1]
        if not link or slug in ocultar:
            continue
        titulo = html.unescape((it.findtext("title") or "").strip())
        desc = html.unescape(re.sub(r"<[^>]+>", "", html.unescape(it.findtext("description") or ""))).strip()
        data = parsedate_to_datetime(it.findtext("pubDate")).astimezone(FUSO)
        tg, desc = rotulo(slug, desc, cfg)
        desc = re.sub(r"\s+", " ", desc)
        if len(desc) > 220:
            desc = desc[:217].rsplit(" ", 1)[0] + "…"
        itens.append((data, link, titulo, tg, desc))
    itens.sort(key=lambda x: x[0], reverse=True)
    itens = itens[: int(cfg.get("quantidade", 9))]
    if not itens:
        raise RuntimeError("feed sem posts")
    lis = []
    for n, (data, link, titulo, tg, desc) in enumerate(itens, 1):
        lis.append(f'<li><a href="{e(link)}" {EXT}><span class="no">{n:02d}</span><span class="ti">'
                   f'<span class="tg">{e(tg)}</span><span class="tt">{e(titulo)}</span>'
                   + (f'<span class="sm">{e(desc)}</span>' if desc else "")
                   + f'</span><span class="ld"></span><time datetime="{data:%Y-%m-%d}">{data.day:02d} {MESES[data.month-1]} {data.year}</time></a></li>')
    return '    <ol class="toc">' + "".join(lis) + "</ol>", len(itens)


def total_textos():
    xml = baixar(SUBSTACK + "/sitemap.xml").decode("utf-8", "replace")
    return len(set(re.findall(r"<loc>[^<]*/p/[^<]+</loc>", xml)))


def contador(h, nome, valor):
    return re.sub(r'(<(\w+)[^>]*data-n="%s"[^>]*>)\d+(</\2>)' % nome, lambda m: f"{m.group(1)}{valor}{m.group(3)}", h)


def main():
    h = INDEX.read_text(encoding="utf-8")
    livros = carregar_livros()
    cfg = json.loads(CONFIG_POSTS.read_text(encoding="utf-8")) if CONFIG_POSTS.exists() else {}

    h = trocar_bloco(h, "ACERVO", bloco_acervo(livros))
    h = capas_destaques(h, livros)
    npdf = sum(bool(b.get("pdf")) for b in livros)
    h = contador(h, "livros", len(livros))
    h = contador(h, "pdfs", npdf)
    h = re.sub(r"\b\d+ clássicos em PDF grátis", f"{npdf} clássicos em PDF grátis", h)
    print(f"Livros: {len(livros)} ({npdf} com PDF grátis)")

    try:
        bloco, n = bloco_posts(cfg)
        h = trocar_bloco(h, "POSTS", bloco)
        print(f"Textos recentes: {n} do feed do Substack")
    except Exception as ex:  # o site continua com a lista anterior
        print(f"AVISO: não consegui ler o feed do Substack ({ex}). Lista de textos mantida.")
    try:
        t = total_textos()
        if t:
            h = contador(h, "textos", t)
            print(f"Textos publicados: {t}")
    except Exception as ex:
        print(f"AVISO: não consegui contar os textos ({ex}).")

    INDEX.write_text(h, encoding="utf-8")


if __name__ == "__main__":
    main()
