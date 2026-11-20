from contextlib import closing, contextmanager
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path
import secrets
import sqlite3
import time


PASTA = Path(__file__).resolve().parent / 'dados'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS casa (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS acesso (id INTEGER PRIMARY KEY CHECK(id=1), casa_id INTEGER NOT NULL REFERENCES casa(id), sal BLOB NOT NULL, segredo BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS sessao (chave TEXT PRIMARY KEY, acesso_id INTEGER NOT NULL REFERENCES acesso(id), expira INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS conta (
    id INTEGER PRIMARY KEY, casa_id INTEGER NOT NULL REFERENCES casa(id),
    tipo TEXT NOT NULL CHECK(tipo IN ('receita','despesa')), descricao TEXT NOT NULL,
    categoria TEXT NOT NULL, pessoa TEXT NOT NULL, meio TEXT NOT NULL, vencimento TEXT NOT NULL,
    previsto INTEGER NOT NULL CHECK(previsto>=0), confirmado INTEGER CHECK(confirmado>=0),
    variavel INTEGER NOT NULL CHECK(variavel IN (0,1)), pontual INTEGER NOT NULL CHECK(pontual IN (0,1))
);
CREATE TABLE IF NOT EXISTS pagamento (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES conta(id),
    data TEXT NOT NULL, valor INTEGER NOT NULL CHECK(valor>0)
);
CREATE TABLE IF NOT EXISTS mes_encerrado (casa_id INTEGER REFERENCES casa(id), mes TEXT, PRIMARY KEY(casa_id,mes));
CREATE TABLE IF NOT EXISTS estimativa (casa_id INTEGER REFERENCES casa(id), mes TEXT, categoria TEXT COLLATE NOCASE, valor INTEGER NOT NULL CHECK(valor>=0), PRIMARY KEY(casa_id,mes,categoria));
CREATE TABLE IF NOT EXISTS importacao (casa_id INTEGER REFERENCES casa(id), origem TEXT, celula TEXT, conta_id INTEGER NOT NULL REFERENCES conta(id), PRIMARY KEY(casa_id,origem,celula));
CREATE INDEX IF NOT EXISTS conta_casa_data ON conta(casa_id,vencimento);
CREATE INDEX IF NOT EXISTS pagamento_conta ON pagamento(conta_id);
'''


@contextmanager
def conectar(arquivo):
    with closing(sqlite3.connect(arquivo)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        yield db


def derivar(senha, sal):
    return pbkdf2_hmac('sha256', senha.encode(), sal, 600_000)


def preparar(arquivo, senha=None):
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with conectar(arquivo) as db:
        db.executescript(SCHEMA)
        if senha is None:
            return bool(db.execute('SELECT 1 FROM acesso').fetchone())
        if len(senha) < 12:
            raise ValueError('Use uma senha de pelo menos 12 caracteres.')
        sal = secrets.token_bytes(16)
        db.execute("INSERT OR IGNORE INTO casa VALUES (1,'Orçamento familiar')")
        db.execute('''INSERT INTO acesso VALUES (1,1,?,?)
                      ON CONFLICT(id) DO UPDATE SET sal=excluded.sal,segredo=excluded.segredo''', (sal, derivar(senha, sal)))
        db.execute('DELETE FROM sessao')


def chave(token):
    return sha256(token.encode()).hexdigest()


def criar_sessao(db, senha):
    acesso = db.execute('SELECT * FROM acesso WHERE id=1').fetchone()
    if not acesso or not secrets.compare_digest(acesso['segredo'], derivar(senha, acesso['sal'])):
        return None
    token = secrets.token_urlsafe(32)
    agora = int(time.time())
    db.execute('DELETE FROM sessao WHERE expira<=?', (agora,))
    db.execute('INSERT INTO sessao VALUES (?,?,?)', (chave(token), acesso['id'], agora + 43_200))
    return token
