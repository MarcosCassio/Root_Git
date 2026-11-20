from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import re


def dinheiro(valor):
    return ('- ' if valor < 0 else '') + 'R$ ' + f'{abs(valor) // 100:,}'.replace(',', '.') + f',{abs(valor) % 100:02d}'


def centavos(texto):
    texto = str(texto).strip()
    if ',' in texto:
        if not re.fullmatch(r'(\d+|\d{1,3}(\.\d{3})+),\d{1,2}', texto):
            raise ValueError('Informe um valor válido com até duas casas decimais.')
        texto = texto.replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d{1,10}(\.\d{1,2})?', texto):
        raise ValueError('Informe um valor válido com até duas casas decimais.')
    try:
        return int(Decimal(texto) * 100)
    except InvalidOperation as exc:
        raise ValueError('Valor inválido.') from exc


def mes_valido(mes):
    mes = mes.strip()
    mes_br = re.fullmatch(r'([0-9]{2})/?([0-9]{4})', mes)
    if mes_br:
        mes = f'{mes_br[2]}-{mes_br[1]}'
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', mes):
        raise ValueError('Informe um período válido no formato MM/AAAA.')
    try:
        date.fromisoformat(mes + '-01')
    except ValueError as exc:
        raise ValueError('Informe um período válido no formato MM/AAAA.') from exc
    return mes


def data_valida(texto):
    texto = texto.strip()
    brasileira = re.fullmatch(r'[0-9]{8}|[0-9]{2}/[0-9]{2}/[0-9]{4}', texto)
    if brasileira:
        digitos = texto.replace('/', '')
        texto = f'{digitos[4:]}-{digitos[2:4]}-{digitos[:2]}'
    try:
        data = date.fromisoformat(texto).isoformat()
        if texto == data:
            return data
    except ValueError:
        pass
    raise ValueError('Informe uma data válida no formato DD/MM/AAAA.')


def resumo(db, casa, mes):
    contas = db.execute('''
        SELECT c.*, COALESCE(SUM(p.valor),0) pago
        FROM conta c LEFT JOIN pagamento p ON p.conta_id=c.id
        WHERE c.casa_id=? AND substr(c.vencimento,1,7)=?
        GROUP BY c.id ORDER BY c.vencimento,c.id
    ''', (casa, mes)).fetchall()
    fluxo = db.execute('''
        SELECT c.tipo, SUM(p.valor) valor FROM pagamento p JOIN conta c ON c.id=p.conta_id
        WHERE c.casa_id=? AND substr(p.data,1,7)=? GROUP BY c.tipo
    ''', (casa, mes)).fetchall()
    realizado = {f['tipo']: f['valor'] for f in fluxo}
    previsto = defaultdict(int)
    pendente = defaultdict(int)
    variavel_comprometido = defaultdict(int)
    for c in contas:
        previsto[c['tipo']] += c['previsto']
        valor = c['confirmado'] if c['confirmado'] is not None else c['previsto']
        pendente[c['tipo']] += max(0, valor - c['pago'])
        if c['tipo'] == 'despesa' and c['variavel'] and not c['pontual']:
            variavel_comprometido[c['categoria']] += max(valor, c['pago'])

    meses = [r['mes'] for r in db.execute('''
        SELECT mes FROM mes_encerrado WHERE casa_id=? AND mes<? ORDER BY mes DESC LIMIT 3
    ''', (casa, mes))]
    historico = defaultdict(lambda: defaultdict(int))
    for r in db.execute('''
        SELECT substr(c.vencimento,1,7) mes,c.categoria,SUM(p.valor) valor
        FROM conta c JOIN pagamento p ON p.conta_id=c.id
        WHERE c.casa_id=? AND c.tipo='despesa' AND c.variavel=1 AND c.pontual=0
        GROUP BY mes,c.categoria
    ''', (casa,)):
        if r['mes'] in meses:
            historico[r['categoria']][r['mes']] = r['valor']
    ajustes = dict(db.execute('SELECT categoria,valor FROM estimativa WHERE casa_id=? AND mes=?', (casa, mes)))
    projecoes = []
    for categoria in sorted(historico.keys() | ajustes.keys() | variavel_comprometido.keys()):
        total = sum(historico[categoria].values())
        media = (total + len(meses) // 2) // len(meses) if meses and categoria in historico else None
        estimado = ajustes.get(categoria, media)
        comprometido = variavel_comprometido[categoria]
        projecoes.append((categoria, estimado, comprometido, max(0, (estimado or 0) - comprometido), media, categoria in ajustes))
    reserva = sum(p[3] for p in projecoes)
    caixa = realizado.get('receita', 0) - realizado.get('despesa', 0)
    return dict(contas=contas, realizado=realizado, previsto=previsto, pendente=pendente,
                projecoes=projecoes, meses=meses, reserva=reserva, caixa=caixa,
                projetado=caixa + pendente['receita'] - pendente['despesa'] - reserva)
