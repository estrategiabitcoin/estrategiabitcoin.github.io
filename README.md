# Estratégia Bitcoin · site

Endereço: https://estrategiabitcoin.github.io

- `index.html`: site com a Biblioteca.
- `dados/livros.json`: **lista de livros do acervo** (é aqui que se adiciona ou corrige livro).
- `dados/posts.json`: ajustes da lista "Os textos mais recentes" (quantidade, rótulos, posts a esconder).
- `termometro/`: Termômetro do Bitcoin. A página lê `termometro/dados.json`.
- `painel/`: Painel on-chain e Escala de Richter. A página lê `painel/series.json` (gráficos, gerado pelo robô todo dia) e `painel/dados.json` (painel da semana e alertas, gravado pelas tarefas do Claude aos domingos e quando há alerta).
- `scripts/painel_series.py`: monta as séries dos gráficos (Coin Metrics e BGeometrics) e a Escala de Richter (preço spot × preço realizado).
- `indicadores/`: página única (piloto) com Termômetro, Escala de Richter e Painel on-chain. Lê os JSON de `termometro/` e `painel/`.
- `etfs/`: fluxo diário dos ETFs de Bitcoin à vista dos EUA e custo médio estimado. Lê `ferramentas/etf.json`.
- `dca/`: calculadora DCA com multiplicadores pelas faixas do MVRV (Escala de Richter). Lê `painel/series.json` e `ferramentas/dolar.json`.
- `scripts/ferramentas.py`: grava `ferramentas/etf.json` (BGeometrics + Coin Metrics) e `ferramentas/dolar.json` (Banco Central, SGS 3698).
- `scripts/montar_site.py`: monta o acervo, as capas e a lista de textos a partir do feed do Substack.
- `scripts/coleta.py`: busca os dados públicos do Termômetro (Coin Metrics, alternative.me, Banco Central, FRED).
- `.github/workflows/atualizar.yml`: roda tudo sozinho. Textos do Substack a cada 3 horas; Termômetro todo dia às 7h17 (Brasília). Para atualizar na hora: aba **Actions** → *Atualizar site* → **Run workflow**.

## Como adicionar um livro

1. Abra `dados/livros.json` no GitHub e clique no lápis (Edit).
2. Copie um bloco de livro inteiro, de `{` até `},`, e cole logo abaixo dele.
3. Troque os campos:
   - `id`: o próximo número livre (ex.: `EB-033`). Não reaproveite números.
   - `titulo`, `autor`, `resumo` (uma frase dizendo por que vale a leitura).
   - `estante`: uma destas: `Bitcoin`, `Economia`, `Escola Austríaca`, `Negócios e finanças`, `Literatura`, `Outros`.
   - `comprar`: o link de afiliado da Amazon (SiteStripe → Texto).
   - `capa`: na página do livro na Amazon, clique com o botão direito na capa → "Copiar endereço da imagem". Se ficar em branco (`null`), o site usa a capa provisória com a cor da estante.
   - `pdf`: link do PDF grátis, ou `null`.
   - `comentado`: link do post do Substack que comenta o livro, ou `null`.
4. Clique em **Commit changes**. Em 1 ou 2 minutos o site se atualiza sozinho (contadores, filtros e capa incluídos).

Se algo estiver errado no arquivo (vírgula faltando, estante com nome diferente), a atualização para e o site continua como estava. A aba **Actions** mostra o erro.

Conteúdo educacional; não é recomendação de investimento.
