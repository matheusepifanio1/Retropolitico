-- Banco da Retrospectiva Política.
-- Regra de ouro: toda linha derivada de fonte oficial aponta para o arquivo bruto
-- de onde saiu (fonte_arquivo), que guarda URL, hash SHA-256 e data da coleta.
-- Nenhum CPF ou dado pessoal além de nome, partido, UF e foto oficial é gravado.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fonte_arquivo (
    id          INTEGER PRIMARY KEY,
    orgao       TEXT NOT NULL,              -- 'camara', 'senado', 'tse', ...
    nome        TEXT NOT NULL UNIQUE,       -- nome local do arquivo bruto
    url         TEXT NOT NULL,              -- URL oficial de onde foi baixado
    sha256      TEXT NOT NULL,
    bytes       INTEGER NOT NULL,
    baixado_em  TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE TABLE IF NOT EXISTS parlamentar (
    id            INTEGER PRIMARY KEY,      -- id oficial da Câmara
    casa          TEXT NOT NULL DEFAULT 'camara',
    nome          TEXT NOT NULL,            -- nome parlamentar
    partido       TEXT,
    uf            TEXT,
    url_foto      TEXT,
    legislatura   INTEGER,
    em_exercicio  INTEGER NOT NULL DEFAULT 0,
    pessoa_id     TEXT,                     -- ligação com candidatura.pessoa_id (TSE)
    sexo          TEXT,                     -- M/F, como publicado pela Câmara (só para concordância)
    fonte_id      INTEGER REFERENCES fonte_arquivo(id)
);

-- Mudanças de situação (Exercício, Licença, Fim de Mandato...) usadas para
-- saber em quais sessões o deputado deveria estar presente.
CREATE TABLE IF NOT EXISTS situacao_historico (
    parlamentar_id   INTEGER NOT NULL REFERENCES parlamentar(id),
    data_hora        TEXT NOT NULL,
    situacao         TEXT,
    descricao_status TEXT,                  -- texto oficial (ex.: motivo da licença)
    partido          TEXT,                  -- partido registrado naquele momento
    fonte_id         INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (parlamentar_id, data_hora, situacao)
);

-- Cargos em órgãos da Câmara (comissões, Mesa Diretora, conselhos...).
CREATE TABLE IF NOT EXISTS cargo (
    parlamentar_id  INTEGER NOT NULL REFERENCES parlamentar(id),
    id_orgao        INTEGER,
    sigla_orgao     TEXT,
    nome_orgao      TEXT,
    titulo          TEXT,                   -- Presidente, Titular, Suplente, ...
    data_inicio     TEXT,
    data_fim        TEXT,
    fonte_id        INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (parlamentar_id, id_orgao, titulo, data_inicio)
);

CREATE TABLE IF NOT EXISTS votacao (
    id                 TEXT PRIMARY KEY,    -- ex.: '2438265-73'
    data               TEXT,
    data_hora          TEXT,
    sigla_orgao        TEXT,                -- 'PLEN' para o plenário
    aprovacao          INTEGER,             -- 1 aprovada, 0 rejeitada, NULL sem info
    votos_sim          INTEGER,
    votos_nao          INTEGER,
    votos_outros       INTEGER,
    descricao          TEXT,                -- texto oficial do que foi votado
    secreta            INTEGER NOT NULL DEFAULT 0,
    id_evento          INTEGER,             -- sessão em que ocorreu (0/NULL se não informado)
    fonte_id           INTEGER REFERENCES fonte_arquivo(id)
);

CREATE TABLE IF NOT EXISTS votacao_proposicao (
    votacao_id      TEXT NOT NULL REFERENCES votacao(id),
    proposicao_id   INTEGER NOT NULL,
    titulo          TEXT,
    ementa          TEXT,
    fonte_id        INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (votacao_id, proposicao_id)
);

CREATE TABLE IF NOT EXISTS voto (
    votacao_id      TEXT NOT NULL REFERENCES votacao(id),
    parlamentar_id  INTEGER NOT NULL,
    voto            TEXT,                   -- Sim, Não, Abstenção, Obstrução, Artigo 17, '' (secreta)
    partido         TEXT,                   -- partido na data do voto
    uf              TEXT,
    data_hora       TEXT,
    fonte_id        INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (votacao_id, parlamentar_id)
);

CREATE TABLE IF NOT EXISTS orientacao (
    votacao_id      TEXT NOT NULL REFERENCES votacao(id),
    sigla_bancada   TEXT NOT NULL,
    orientacao      TEXT,
    fonte_id        INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (votacao_id, sigla_bancada)
);

CREATE TABLE IF NOT EXISTS proposicao (
    id                INTEGER PRIMARY KEY,
    sigla_tipo        TEXT,
    numero            INTEGER,
    ano               INTEGER,
    ementa            TEXT,
    data_apresentacao TEXT,
    situacao          TEXT,                 -- último status oficial
    fonte_id          INTEGER REFERENCES fonte_arquivo(id)
);

CREATE TABLE IF NOT EXISTS autoria (
    proposicao_id     INTEGER NOT NULL,
    parlamentar_id    INTEGER NOT NULL,
    ordem_assinatura  INTEGER,
    proponente        INTEGER,
    fonte_id          INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (proposicao_id, parlamentar_id)
);

-- Só sessões deliberativas encerradas do Plenário.
CREATE TABLE IF NOT EXISTS sessao (
    id            INTEGER PRIMARY KEY,      -- id do evento na Câmara
    data_hora     TEXT NOT NULL,
    descricao     TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id)
);

CREATE TABLE IF NOT EXISTS presenca (
    sessao_id       INTEGER NOT NULL REFERENCES sessao(id),
    parlamentar_id  INTEGER NOT NULL,
    fonte_id        INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (sessao_id, parlamentar_id)
);

-- Frequência por dia publicada no site da Câmara (inclui justificativas de ausência).
CREATE TABLE IF NOT EXISTS frequencia_dia (
    parlamentar_id  INTEGER NOT NULL,
    data            TEXT NOT NULL,          -- AAAA-MM-DD
    status          TEXT NOT NULL,          -- Presença, Ausência, Missão Autorizada, ...
    url             TEXT,
    fonte_id        INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (parlamentar_id, data)
);

-- Candidaturas do TSE. Só campos públicos da candidatura; nada de CPF, título,
-- nascimento, gênero, raça, e-mail, bens ou ocupação.
-- pessoa_id: SQ_CANDIDATO da primeira candidatura da pessoa (número público do TSE).
-- O agrupamento das candidaturas de uma mesma pessoa usa o título de eleitor só em memória.
CREATE TABLE IF NOT EXISTS candidatura (
    sq_candidato      TEXT PRIMARY KEY,
    pessoa_id         TEXT NOT NULL,
    ano               INTEGER NOT NULL,
    tipo_eleicao      TEXT,               -- ELEIÇÃO ORDINÁRIA / SUPLEMENTAR
    ds_eleicao        TEXT,
    uf                TEXT,
    ue                TEXT,               -- código da unidade eleitoral
    nm_ue             TEXT,               -- município ou estado
    cargo             TEXT,
    numero            TEXT,
    nome              TEXT,               -- nome civil ou social, como publicado
    nome_urna         TEXT,
    partido           TEXT,
    situacao          TEXT,               -- situação da candidatura (APTO, INAPTO...)
    resultado         TEXT,               -- resultado no último turno disputado
    turno_final       INTEGER,
    fonte_id          INTEGER REFERENCES fonte_arquivo(id)
);
CREATE INDEX IF NOT EXISTS idx_cand_pessoa ON candidatura(pessoa_id);

CREATE INDEX IF NOT EXISTS idx_voto_parl ON voto(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_autoria_parl ON autoria(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_presenca_parl ON presenca(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_votacao_orgao ON votacao(sigla_orgao);

-- ---------------------------------------------------------------- Senado Federal
CREATE TABLE IF NOT EXISTS senador (
    codigo        INTEGER PRIMARY KEY,      -- código oficial do Senado
    nome          TEXT NOT NULL,            -- nome parlamentar
    nome_completo TEXT,
    sexo          TEXT,                     -- M/F (só para concordância de gênero no texto)
    partido       TEXT,
    uf            TEXT,
    url_foto      TEXT,
    url_pagina    TEXT,
    em_exercicio  INTEGER NOT NULL DEFAULT 0,
    pessoa_id     TEXT,                     -- ligação com candidatura.pessoa_id (TSE)
    fonte_id      INTEGER REFERENCES fonte_arquivo(id)
);
CREATE TABLE IF NOT EXISTS sen_mandato (
    codigo        INTEGER NOT NULL,
    mandato       TEXT NOT NULL,
    uf            TEXT,
    participacao  TEXT,                     -- Titular, 1º Suplente...
    inicio        TEXT,
    fim           TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (codigo, mandato)
);
-- Períodos em que o senador estava de fato no cargo (o suplente assume quando o titular se afasta).
CREATE TABLE IF NOT EXISTS sen_exercicio (
    codigo        INTEGER NOT NULL,
    inicio        TEXT NOT NULL,
    fim           TEXT,                     -- inclusivo; NULL = em exercício
    causa_sigla   TEXT,
    causa         TEXT,                     -- motivo oficial do afastamento
    fonte_id      INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (codigo, inicio)
);
CREATE TABLE IF NOT EXISTS sen_partido (
    codigo        INTEGER NOT NULL,
    sigla         TEXT,
    nome          TEXT,
    inicio        TEXT,
    fim           TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (codigo, sigla, inicio)
);
CREATE TABLE IF NOT EXISTS sen_cargo (
    codigo        INTEGER NOT NULL,
    sigla_comissao TEXT,
    nome_comissao TEXT,
    casa          TEXT,                     -- SF ou CN
    cargo         TEXT,
    inicio        TEXT,
    fim           TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (codigo, sigla_comissao, cargo, inicio)
);
CREATE TABLE IF NOT EXISTS sen_processo (
    id                INTEGER PRIMARY KEY,
    identificacao     TEXT,                 -- ex.: PL 1234/2023
    sigla_tipo        TEXT,
    ementa            TEXT,
    data_apresentacao TEXT,
    situacao          TEXT,
    norma             TEXT,                 -- norma gerada, ex.: Lei nº 14.000 de ...
    autoria           TEXT,                 -- texto oficial de autoria
    codigo_materia    TEXT,
    fonte_id          INTEGER REFERENCES fonte_arquivo(id)
);
CREATE TABLE IF NOT EXISTS sen_autoria (
    processo_id   INTEGER NOT NULL,
    codigo        INTEGER NOT NULL,
    principal     INTEGER NOT NULL,         -- 1 se é o primeiro autor no texto oficial
    fonte_id      INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (processo_id, codigo)
);
CREATE TABLE IF NOT EXISTS sen_votacao (
    id            INTEGER PRIMARY KEY,      -- codigoSessaoVotacao
    data          TEXT,
    materia       TEXT,                     -- ex.: PEC 81/2015
    ementa        TEXT,
    descricao     TEXT,
    resultado     TEXT,                     -- A aprovada, R rejeitada (sigla oficial)
    secreta       INTEGER NOT NULL DEFAULT 0,
    codigo_materia TEXT,
    id_processo   TEXT,
    informe       TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id)
);
CREATE TABLE IF NOT EXISTS sen_voto (
    votacao_id    INTEGER NOT NULL,
    codigo        INTEGER NOT NULL,
    sigla         TEXT,                     -- Sim, Não, Abstenção, Votou (secreta), NCom, LS, MIS...
    partido       TEXT,
    uf            TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id),
    PRIMARY KEY (votacao_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_sen_voto ON sen_voto(codigo);
CREATE TABLE IF NOT EXISTS sen_tipo_comparecimento (
    sigla         TEXT PRIMARY KEY,
    descricao     TEXT,
    fonte_id      INTEGER REFERENCES fonte_arquivo(id)
);

-- ---------------------------------------------------------------- Presidência
CREATE TABLE IF NOT EXISTS veto (
    codigo            INTEGER PRIMARY KEY,
    identificacao     TEXT,                 -- VET 51/2025
    total             INTEGER,              -- 1 veto total, 0 parcial
    data_publicacao   TEXT,
    assunto           TEXT,
    ementa            TEXT,
    materia_vetada    TEXT,
    norma             TEXT,
    url_planalto      TEXT,
    dispositivos      INTEGER,
    url               TEXT,
    fonte_id          INTEGER REFERENCES fonte_arquivo(id)
);
-- Medidas provisórias (proposições MPV dos arquivos da Câmara; autor: Poder Executivo).
CREATE TABLE IF NOT EXISTS medida_provisoria (
    id                INTEGER PRIMARY KEY,  -- id da proposição na Câmara
    numero            INTEGER,
    ano               INTEGER,
    ementa            TEXT,
    data_apresentacao TEXT,
    situacao          TEXT,
    fonte_id          INTEGER REFERENCES fonte_arquivo(id)
);
