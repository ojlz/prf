# PRF na Estrada — Simulador Educacional (CTB)

🌐 **Jogue no ar:** https://prf-pxzys-projects.vercel.app

Jogo de simulador/quiz com contas, patentes por XP, conquistas, skins,
ranking e patrulhas. Frontend em `public/index.html` + API Flask em
`server/app.py`.

## Como roda na Vercel (sem mudar o jogo)

- A Vercel detecta o Flask e atende **toda requisição** pela função
  `api/index.py`, que só importa o app original de `server/app.py`.
- Estáticos (`index.html`, `assets/`) ficam em `public/` e saem pela CDN.
- Contas/ranking usam JSON em disco: na Vercel vai para `/tmp`
  (`PRF_DATA_DIR`), que é **efêmero** — zera entre deploys/instâncias.
  Localmente continua em `server/dados/` (ignorado pelo git).

## Rodar local (igual a antes)

```bash
pip install -r requirements.txt
python server/app.py
```

Abra http://127.0.0.1:5000 (ou o `index.html` via `file://`, que usa a API
local). O `server/app.py` serve `public/` com fallback para a raiz, então
checkouts antigos continuam funcionando.

## Notas de demo

- Defina `SECRET_KEY` nas envs da Vercel em produção (o padrão do código é
  só para demonstração).
- `server/dados/*.json` nunca é commitado (ver `.gitignore`).
