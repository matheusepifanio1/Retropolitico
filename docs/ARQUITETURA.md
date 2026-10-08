# Arquitetura e decisões

## Decisões

| Decisão | Motivo |
|---|---|
| Site estático (HTML gerado) | Barato, rápido, sem servidor para manter ou atacar. Cada atualização é um build reproduzível. |
| SQLite reconstruído a cada execução | O banco é derivado dos arquivos brutos; nunca é editado à mão. Qualquer pessoa reproduz o mesmo resultado. |
| Arquivos em massa da Câmara, não a API, para votos e proposições | A API não tem endpoint de votos por deputado; os arquivos anuais trazem tudo de uma vez. |
| Leitura por lista de colunas permitidas | Colunas fora da lista nunca entram no banco (ex.: CPF). Coluna esperada ausente para a coleta (`LayoutError`). |
| Hash SHA-256 de cada arquivo bruto | Permite a qualquer pessoa provar que o site usou exatamente aquele arquivo oficial. |
| Votações-chave em YAML revisado por PR | A escolha editorial fica explícita, versionada e auditável. |
| Sem IA no conteúdo publicado | Res. TSE 23.755/2026 e credibilidade. IA pode ajudar em tarefas internas (ex.: achar ids), nunca no texto publicado. |

## Limites conhecidos (fase 1)

- **Formato dos arquivos não testado contra a fonte real ainda.** O código foi escrito e testado com fixtures no formato documentado (colunas confirmadas em projetos que já consomem esses arquivos). A primeira execução no GitHub Actions é o teste real; se algo divergir, ela falha com a lista de colunas encontradas.
  - Maior incerteza: chaves dos arquivos JSON `eventos`, `eventosOrgaos` e `eventosPresencaDeputados`. O leitor aceita as variações conhecidas (`idEvento`/`uriEvento` etc.).
- **Justificativa de ausência** não existe em dados abertos. O site mostra "sem registro de presença".
- **Orientação de bloco**: quando o partido orienta via bloco parlamentar, a orientação pode não ser associada ao partido.
- **Relatorias** ainda não coletadas.
- **Número da lei** gerada por um projeto não está nos arquivos de proposições; o site linka a página da proposição, que mostra a norma.
- Votações em **comissões** ficam fora (só Plenário).

## Próximas etapas

1. **Senado** (`legis.senado.leg.br/dadosabertos`): senadores, votações nominais, autorias.
2. **TSE** (`dadosabertos.tse.jus.br`): candidaturas de todos os cargos, bens, trajetória; vira a base de busca para qualquer político, inclusive estaduais e municipais (selo "só dados eleitorais").
3. **Emendas orçamentárias** (Portal da Transparência, download em massa): indicado × pago por parlamentar.
4. **Comparativo de 2º turno** e perfis de governadores/prefeitos (TSE + SICONFI).
5. **Promessas × feito**: planos de governo do TSE, extração assistida e classificação com revisão humana obrigatória.
6. **Assembleias estaduais**, uma a uma, começando pelas que publicam dados abertos.

## Cadastro único de pessoa (a partir da etapa 2)

Para ligar o mesmo político entre Câmara, Senado e TSE, a chave será o identificador do TSE quando possível, com tabela de vínculo `pessoa_vinculo(pessoa_id, origem, id_origem, metodo, conferido_por)`. Vínculos por nome + data de nascimento são marcados como automáticos e listados para conferência.
