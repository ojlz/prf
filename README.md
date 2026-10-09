# PRF na Estrada — Simulador Educacional (CTB)

🌐 **Jogue no ar:** https://prfbr.vercel.app

Jogo de simulador/quiz 100% no navegador, sem cadastro: patrulhe a BR,
enquadre infrações do CTB, ganhe pontos e desbloqueie fardas, viaturas e
equipamentos. Progresso, carteira de pontos e personalização ficam salvos
no `localStorage`. Sem login, sem ranking, sem XP/patentes, sem conquistas.

## Como roda na Vercel

Site estático puro: `public/index.html` + `public/assets/` saídos pela CDN.
O Flask em `server/` **não** vai para o deploy (só existe para referência
local/histórico) — o `pyproject.toml` declara o entrypoint para o preset,
mas nenhuma rota da API é usada pelo jogo.

## Rodar local

Só abrir `public/index.html` no navegador, ou servir a pasta:

```bash
cd public && python -m http.server 8000
```

(Opcional/legado: `pip install -r server/requirements.txt` +
`python server/app.py` — o servidor serve `public/` com fallback para a
raiz, mas o jogo não precisa dele.)

## Estrutura

- `public/index.html` — o jogo completo (HTML + CSS + JS)
- `public/assets/` — sprites da pista
- `server/` — backend Flask original, desativado no deploy (referência)
