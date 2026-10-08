# Retrospectiva Política

Site estático que mostra o que cada político fez no mandato, usando **apenas dados oficiais**, com link para a fonte em cada número e o hash de cada arquivo bruto para auditoria.

**Etapa atual (fase 1):** deputados federais da 57ª legislatura (2023–2027), com dados da Câmara dos Deputados: presença em sessões deliberativas, votações nominais do Plenário, votações-chave com curadoria humana e projetos que viraram lei.

## Como funciona

```
dadosabertos.camara.leg.br ──► data/raw/  (arquivos brutos + manifest.json com SHA-256)
                                   │
                                   ▼
                     data/retrospectiva.sqlite  (normalizado, com fonte_id em cada linha)
                                   │
                                   ▼
                                _site/  (HTML estático + busca.json + dados/)
```

1. `python -m retro baixar` baixa os arquivos oficiais. Precisa de acesso à internet.
2. `python -m retro carregar` reconstrói o banco do zero a partir dos arquivos brutos. Funciona offline.
3. `python -m retro site` gera o site em `_site/`.

`python -m retro tudo` roda as três etapas.

O GitHub Actions (`.github/workflows/atualizar.yml`) roda tudo isso diariamente e publica no GitHub Pages. Se um arquivo oficial mudar de formato, a coleta **para com erro** em vez de publicar dado errado, e o site anterior continua no ar.

## Colocando no ar

1. Crie um repositório no GitHub e envie este código.
2. Em **Settings → Pages**, escolha **Source: GitHub Actions**.
3. Em `config/settings.yaml`, `site.repositorio` aponta para o repositório (links de correção). O caminho do site (`/Retropolitico`) é lido automaticamente do GitHub Pages no build.
4. Em **Actions**, rode **Atualizar dados e publicar** manualmente na primeira vez. A primeira coleta baixa ~1–2 GB e leva de 20 a 60 minutos; as seguintes reaproveitam o cache.

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest               # testes com dados fictícios no formato oficial
python -m tests.demo             # site de demonstração em _demo/, sem rede
python -m http.server -d _demo 8000
python -m retro tudo             # coleta real (precisa de rede)
```

## Curadoria das votações-chave

As votações em destaque ficam em `config/votacoes_chave.yaml`. Cada uma exige tema, etapa, resumo neutro, `sentido_sim` (obrigatório para destaques), nome de quem revisou e data. O build falha se o id não existir entre as votações nominais do Plenário coletadas. Toda alteração deve entrar por pull request revisado. **Nenhum resumo é gerado por IA** (ver Resolução TSE 23.755/2026).

Para encontrar o id de uma votação, consulte o banco:

```sql
SELECT v.id, v.data, vp.titulo, v.descricao
FROM votacao v JOIN votacao_proposicao vp ON vp.votacao_id = v.id
WHERE vp.titulo LIKE 'PEC 45/2019%';
```

## Estrutura

```
retro/
  sources/base.py     download, manifesto, leitura com checagem de layout
  sources/camara.py   coletor da Câmara (download + carga)
  schema.sql          modelo do banco com proveniência
  compute.py          regras de cálculo (presença, votos, leis)
  site/build.py       gerador do site
  site/templates/     HTML (Jinja2)
config/               configuração e curadoria
tests/                testes e fixtures no formato oficial
docs/ARQUITETURA.md   decisões, limites conhecidos e próximas etapas
```

A metodologia pública fica em `retro/site/templates/metodologia.html` e é publicada em `/metodologia/`.
