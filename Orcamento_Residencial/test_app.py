from http.client import HTTPConnection
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.parse import urlencode

from app import servidor
from dados import conectar, preparar
from financeiro import resumo
from importar_planilha import salvar


class OrcamentoTest(unittest.TestCase):
    def setUp(self):
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.banco = Path(pasta.name) / 'teste.sqlite3'
        preparar(self.banco, 'senha fictícia de teste')

    def test_fluxo_web_e_projecao(self):
        http = servidor(self.banco, '127.0.0.1', 0)
        self.addCleanup(http.server_close)
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(http.shutdown)
        cliente = HTTPConnection('127.0.0.1', http.server_port, timeout=5)
        self.addCleanup(cliente.close)
        cookie = ''

        def solicitar(rota, form=None):
            headers = {'Cookie': cookie}
            metodo = 'GET' if form is None else 'POST'
            if form is not None:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            cliente.request(metodo, rota, body=None if form is None else urlencode(form), headers=headers)
            resposta = cliente.getresponse()
            corpo = resposta.read().decode()
            return resposta, corpo

        self.assertIn('Senha', solicitar('/')[1])
        self.assertEqual(solicitar('/login', dict(senha='errada'))[0].status, 401)
        resposta, _ = solicitar('/login', dict(senha='senha fictícia de teste'))
        self.assertEqual(resposta.status, 303)
        cookie = resposta.getheader('Set-Cookie').split(';')[0]
        painel = solicitar('/?mes=2020-04')[1]
        self.assertIn('Visão anual', painel)
        self.assertEqual(solicitar('/estilo.css')[0].status, 200)
        csrf = re.search(r'name="csrf" value="(\w+)"', painel)[1]
        self.assertEqual(solicitar('/encerrar', dict(mes='2020-03'))[0].status, 403)

        def postar(rota, mes='2020-04', **campos):
            resposta, html = solicitar(rota, dict(csrf=csrf, mes=mes, **campos))
            self.assertEqual(resposta.status, 303, html)
            return resposta.getheader('Location')

        for mes, gasto in (('2020-01', '100'), ('2020-02', '200'), ('2020-03', '300')):
            conta = postar('/conta', mes, tipo='despesa', descricao='Mercado', categoria='Alimento',
                           vencimento=mes + '-05', previsto=gasto, variavel=1).split('/')[-1]
            postar('/pagamento', mes, conta=conta, data=mes + '-05', valor=gasto)
            postar('/encerrar', mes)

        conta = postar('/conta', tipo='despesa', descricao='Mercado de abril', categoria='alimento',
                       vencimento='2020-04-30', previsto='80', confirmado='', variavel=1, repeticoes=2).split('/')[-1]
        postar('/confirmado', conta=conta, valor='100')
        postar('/pagamento', conta=conta, data='2020-04-29', valor='40')
        with conectar(self.banco) as db:
            dados = resumo(db, 1, '2020-04')
            self.assertEqual(dados['pendente']['despesa'], 6_000)
            self.assertEqual(dados['reserva'], 10_000)
            self.assertEqual(dados['projetado'], -20_000)
            self.assertIsNone(db.execute("SELECT confirmado FROM conta WHERE vencimento='2020-05-30'").fetchone()[0])
        postar('/estimativa', categoria='Alimento', valor='250')
        self.assertIn('R$ 150,00', solicitar('/?mes=2020-04')[1])
        postar('/sair')
        self.assertNotIn('Visão anual', solicitar('/')[1])

    def test_importacao_separa_previsao_e_pagamento(self):
        linhas = [
            ('R. Fx!B3', 'receita', 'Salário', 'Receita fixa', 'PIX', '2020-01-31', 200_000, False, False),
            ('D. Fx.+Vr.!G3', 'despesa', 'Mercado', 'Alimento', 'PIX', '2020-01-05', 20_000, True, True),
        ]
        origem = Path('modelo.xlsx')
        with conectar(self.banco) as db:
            self.assertEqual(salvar(db, origem, linhas, False), 1)
        with conectar(self.banco) as db:
            self.assertEqual(salvar(db, origem, linhas, True), 1)
            dados = resumo(db, 1, '2020-01')
            self.assertEqual(dados['previsto']['receita'], 200_000)
            self.assertEqual(dados['realizado']['despesa'], 20_000)
        with conectar(self.banco) as db:
            self.assertEqual(salvar(db, origem, linhas, True), 0)

    def test_criacao_de_senha_local_uma_unica_vez(self):
        banco = self.banco.with_name('novo.sqlite3')
        self.assertFalse(preparar(banco))
        http = servidor(banco, '127.0.0.1', 0)
        self.addCleanup(http.server_close)
        Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.shutdown)
        cliente = HTTPConnection('127.0.0.1', http.server_port, timeout=5)
        self.addCleanup(cliente.close)

        cliente.request('GET', '/')
        pagina = cliente.getresponse().read().decode()
        token = re.search(r'name="token" value="([\w-]+)"', pagina)[1]
        self.assertIn('Criar senha familiar', pagina)

        def salvar_senha(senha, repetir, extras=None):
            headers = {'Content-Type': 'application/x-www-form-urlencoded', **(extras or {})}
            cliente.request('POST', '/configurar', urlencode(dict(token=token, senha=senha, repetir=repetir)), headers)
            resposta = cliente.getresponse()
            resposta.read()
            return resposta

        senha = 'credencial fictícia de teste'
        self.assertEqual(salvar_senha(senha, senha, {'Host': 'outro.exemplo'}).status, 403)
        self.assertEqual(salvar_senha(senha, 'diferente').status, 400)
        self.assertFalse(preparar(banco))
        self.assertIn('HttpOnly', salvar_senha(senha, senha).getheader('Set-Cookie'))
        self.assertTrue(preparar(banco))
        repeticao = salvar_senha('outra senha de teste', 'outra senha de teste')
        self.assertEqual(repeticao.status, 303)
        self.assertIsNone(repeticao.getheader('Set-Cookie'))


if __name__ == '__main__':
    unittest.main()
