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

CREATE INDEX IF NOT EXISTS idx_voto_parl ON voto(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_autoria_parl ON autoria(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_presenca_parl ON presenca(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_votacao_orgao ON votacao(sigla_orgao);
