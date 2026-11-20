import argparse
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from getpass import getpass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import ssl
import time
from urllib.parse import parse_qs, urlsplit

from dados import PASTA, chave, conectar, criar_sessao, preparar
from financeiro import centavos, mes_valido, resumo
from telas import detalhe, login, painel


def hoje():
    return datetime.now(timezone(timedelta(hours=-3))).date().isoformat()


def data_valida(texto):
    data = date.fromisoformat(texto).isoformat()
    if texto != data:
        raise ValueError('Informe a data no formato correto.')
    return data


def texto_curto(texto):
    texto = ' '.join(texto.split())
    if not texto or len(texto) > 100:
        raise ValueError('Preencha os campos de texto com até 100 caracteres.')
    return texto


def categoria(db, casa, nome):
    nome = texto_curto(nome)
    opcoes = db.execute('SELECT categoria FROM conta WHERE casa_id=? UNION SELECT categoria FROM estimativa WHERE casa_id=?', (casa, casa))
    return next((r[0] for r in opcoes if r[0].casefold() == nome.casefold()), nome)


class Aplicacao(BaseHTTPRequestHandler):
    def responder(self, corpo='', status=200, tipo='text/html; charset=utf-8', **headers):
        corpo = corpo.encode() if isinstance(corpo, str) else corpo
        self.send_response(status)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        for nome, valor in headers.items():
            self.send_header(nome.replace('_', '-'), valor)
        self.end_headers()
        self.wfile.write(corpo)

    def redirecionar(self, url, **headers):
        self.responder(status=303, Location=url, **headers)

    def token(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            return cookie['sessao'].value if 'sessao' in cookie else ''
        except CookieError:
            return ''

    def casa(self, db):
        token = self.token()
        if token:
            linha = db.execute('''SELECT a.casa_id FROM sessao s JOIN acesso a ON a.id=s.acesso_id
                                  WHERE s.chave=? AND s.expira>?''', (chave(token), int(time.time()))).fetchone()
            if linha:
                return linha[0]

    def cookie(self, valor, duracao):
        seguro = '; Secure' if self.server.https else ''
        return f'sessao={valor}; Path=/; Max-Age={duracao}; HttpOnly; SameSite=Strict{seguro}'

    def csrf(self):
        return chave('form:' + self.token())

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/estilo.css':
            return self.responder(Path(__file__).with_name('estilo.css').read_bytes(), tipo='text/css; charset=utf-8')
        with conectar(self.server.banco) as db:
            casa = self.casa(db)
            if not casa:
                return self.responder(login())
            if url.path.startswith('/conta/') and url.path[7:].isdigit():
                conta = db.execute('SELECT * FROM conta WHERE casa_id=? AND id=?', (casa, int(url.path[7:]))).fetchone()
                if conta:
                    pagamentos = db.execute('SELECT * FROM pagamento WHERE conta_id=? ORDER BY data,id', (conta['id'],)).fetchall()
                    return self.responder(detalhe(conta, pagamentos, self.csrf(), hoje()))
            if url.path != '/':
                return self.responder('Página não encontrada.', 404)
            filtros = parse_qs(url.query)
            mes = filtros.get('mes', [hoje()[:7]])[0]
            try:
                mes_valido(mes)
            except ValueError:
                return self.redirecionar('/')
            return self.responder(self.pagina(db, casa, mes, pessoa=filtros.get('pessoa', [''])[0]))

    def pagina(self, db, casa, mes, erro='', pessoa=''):
        dados = resumo(db, casa, mes)
        fechado = db.execute('SELECT 1 FROM mes_encerrado WHERE casa_id=? AND mes=?', (casa, mes)).fetchone()
        anual = [(m, resumo(db, casa, m)) for m in (f'{mes[:4]}-{n:02d}' for n in range(1, 13))]
        pessoas = sorted({c['pessoa'] for c in dados['contas']}, key=str.casefold)
        if pessoa in pessoas:
            dados['contas'] = [c for c in dados['contas'] if c['pessoa'] == pessoa]
        return painel(mes, dados, anual, self.csrf(), hoje(), bool(fechado), erro, pessoas, pessoa)

    def do_POST(self):
        try:
            tamanho = int(self.headers.get('Content-Length', '0'))
            if not 0 < tamanho <= 16_384 or self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                raise ValueError
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(tamanho).decode(), keep_blank_values=True, max_num_fields=25).items()}
        except (ValueError, UnicodeError):
            return self.responder('Formulário inválido.', 400)
        rota = urlsplit(self.path).path
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.responder('Solicitação recusada.', 403)
        with conectar(self.server.banco) as db:
            if rota == '/login':
                senha = form.get('senha', '')
                token = criar_sessao(db, senha) if len(senha) <= 256 else None
                if token:
                    db.commit()
                    return self.redirecionar('/', Set_Cookie=self.cookie(token, 43_200))
                return self.responder(login('Senha incorreta.'), 401)
            casa = self.casa(db)
            if not casa or not secrets.compare_digest(form.get('csrf', '').encode(), self.csrf().encode()):
                return self.responder('Sessão inválida. Atualize a página e entre novamente.', 403)
            if rota == '/sair':
                db.execute('DELETE FROM sessao WHERE chave=?', (chave(self.token()),))
                db.commit()
                return self.redirecionar('/', Set_Cookie=self.cookie('', 0))
            mes = hoje()[:7]
            try:
                mes = mes_valido(form.get('mes', mes))
                destino = self.gravar(db, casa, mes, rota, form)
                db.commit()
            except (ValueError, KeyError) as exc:
                db.rollback()
                mensagem = 'Preencha todos os campos obrigatórios.' if isinstance(exc, KeyError) else str(exc)
                return self.responder(self.pagina(db, casa, mes, mensagem), 400)
            return self.redirecionar(destino)

    def gravar(self, db, casa, mes, rota, f):
        if rota == '/conta':
            tipo = f['tipo']
            if tipo not in ('receita', 'despesa'):
                raise ValueError('Selecione receita ou despesa.')
            vencimento = date.fromisoformat(data_valida(f['vencimento']))
            repeticoes = int(f.get('repeticoes') or '1')
            if not 1 <= repeticoes <= 120:
                raise ValueError('Informe de 1 a 120 lançamentos mensais.')
            valor = centavos(f['previsto'])
            confirmado = centavos(f['confirmado']) if f.get('confirmado') else None
            identificacao = (casa, tipo, texto_curto(f['descricao']), categoria(db, casa, f['categoria']),
                             texto_curto(f.get('pessoa') or 'Casa'), texto_curto(f.get('meio') or 'A definir'))
            variavel = int(tipo == 'despesa' and f.get('variavel') == '1')
            pontual = int(f.get('pontual') == '1')
            primeiro_id = None
            for n in range(repeticoes):
                ano, mes_zero = divmod(vencimento.year * 12 + vencimento.month - 1 + n, 12)
                mes_num = mes_zero + 1
                dia = min(vencimento.day, monthrange(ano, mes_num)[1])
                data = date(ano, mes_num, dia).isoformat()
                cursor = db.execute('''INSERT INTO conta(casa_id,tipo,descricao,categoria,pessoa,meio,vencimento,previsto,confirmado,variavel,pontual)
                                       VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                                    (*identificacao, data, valor, confirmado if n == 0 else None, variavel, pontual))
                if n == 0:
                    primeiro_id = cursor.lastrowid
            return f'/conta/{primeiro_id}'
        if rota in ('/pagamento', '/confirmado'):
            id_conta = int(f['conta'])
            if not db.execute('SELECT 1 FROM conta WHERE id=? AND casa_id=?', (id_conta, casa)).fetchone():
                raise ValueError('Conta não encontrada.')
            valor = centavos(f['valor'])
            if rota == '/confirmado':
                db.execute('UPDATE conta SET confirmado=? WHERE id=? AND casa_id=?', (valor, id_conta, casa))
            else:
                data = data_valida(f['data'])
                if valor <= 0 or data > hoje():
                    raise ValueError('Registre um valor positivo com data de hoje ou anterior.')
                db.execute('INSERT INTO pagamento(conta_id,data,valor) VALUES(?,?,?)', (id_conta, data, valor))
            return f'/conta/{id_conta}'
        if rota == '/estimativa':
            nome = categoria(db, casa, f['categoria'])
            if f['valor'].strip():
                db.execute('''INSERT INTO estimativa VALUES(?,?,?,?)
                              ON CONFLICT(casa_id,mes,categoria) DO UPDATE SET valor=excluded.valor''',
                           (casa, mes, nome, centavos(f['valor'])))
            else:
                db.execute('DELETE FROM estimativa WHERE casa_id=? AND mes=? AND categoria=?', (casa, mes, nome))
        elif rota == '/encerrar':
            if mes >= hoje()[:7]:
                raise ValueError('Encerre apenas meses anteriores ao atual.')
            if f.get('fechado') == '0':
                db.execute('DELETE FROM mes_encerrado WHERE casa_id=? AND mes=?', (casa, mes))
            else:
                db.execute('INSERT OR IGNORE INTO mes_encerrado VALUES (?,?)', (casa, mes))
        else:
            raise ValueError('Operação não encontrada.')
        return f'/?mes={mes}'


def servidor(banco, host, porta, contexto=None):
    inst = ThreadingHTTPServer((host, porta), Aplicacao)
    inst.banco = banco
    inst.https = bool(contexto)
    if contexto:
        inst.socket = contexto.wrap_socket(inst.socket, server_side=True)
    return inst


def main():
    parser = argparse.ArgumentParser(description='Orçamento Residencial')
    parser.add_argument('--configurar-senha', action='store_true')
    parser.add_argument('--banco', type=Path, default=PASTA / 'orcamento.sqlite3')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--porta', type=int, default=8000)
    parser.add_argument('--certificado', type=Path)
    parser.add_argument('--chave', type=Path)
    args = parser.parse_args()
    if args.configurar_senha or not preparar(args.banco):
        senha = getpass('Senha familiar (12 a 256 caracteres): ')
        if not 12 <= len(senha) <= 256 or senha != getpass('Repita a senha: '):
            parser.error('As senhas devem coincidir e ter entre 12 e 256 caracteres.')
        preparar(args.banco, senha)
        if args.configurar_senha:
            return
    contexto = None
    if args.certificado and args.chave:
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.load_cert_chain(args.certificado, args.chave)
    elif args.certificado or args.chave or args.host not in ('127.0.0.1', 'localhost'):
        parser.error('Para acesso pela rede, forneça --certificado e --chave TLS.')
    with servidor(args.banco, args.host, args.porta, contexto) as inst:
        print(f"{'https' if contexto else 'http'}://{args.host}:{inst.server_port}", flush=True)
        try:
            inst.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
