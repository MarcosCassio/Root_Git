from html import escape

from financeiro import dinheiro


MESES = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')


def pagina(titulo, corpo, classe=''):
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{escape(titulo)} | Orçamento Residencial</title><link rel="stylesheet" href="/estilo.css">
    <script src="/calendario.js" defer></script>
    </head><body class="{classe}"><main>{corpo}</main></body></html>'''


def contexto(mes, csrf):
    return f'<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="mes" value="{mes}">'


def marca():
    return '<a class="marca" href="/"><span class="selo" aria-hidden="true">OR</span>Orçamento Residencial</a>'


def login(erro=''):
    alerta = f'<p role="alert" class="erro">{escape(erro)}</p>' if erro else ''
    return pagina('Entrar', f'''<section class="login">{marca()}<h1>Seu orçamento familiar</h1>
    <p>Entre com a senha compartilhada da casa.</p>{alerta}
    <form method="post" action="/login"><label>Senha<input name="senha" type="password" required
    autocomplete="current-password" maxlength="256" autofocus></label><button>Entrar</button></form></section>''', 'entrada')


def configurar_senha(token, erro=''):
    alerta = f'<p role="alert" class="erro">{escape(erro)}</p>' if erro else ''
    return pagina('Criar senha', f'''<section class="login">{marca()}<h1>Criar senha familiar</h1>
    <p>Use de 12 a 256 caracteres. Esta será a senha compartilhada da casa.</p>{alerta}
    <form method="post" action="/configurar"><input type="hidden" name="token" value="{token}">
    <label>Senha<input name="senha" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>
    <label>Confirmar senha<input name="repetir" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>
    <button>Criar senha e entrar</button></form></section>''', 'entrada')


def tabela(cabecalhos, linhas, vazio):
    if not linhas:
        return f'<p class="vazio">{escape(vazio)}</p>'
    cabecalho = ''.join(f'<th scope="col">{h}</th>' for h in cabecalhos)
    corpo = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in linha) + '</tr>' for linha in linhas)
    return f'<div class="tabela" tabindex="0"><table><thead><tr>{cabecalho}</tr></thead><tbody>{corpo}</tbody></table></div>'


def data_br(data):
    return '/'.join(reversed(data.split('-')))


def campo_data(nome, rotulo, inicial, periodo=False):
    formato = 'MM/AAAA' if periodo else 'DD/MM/AAAA'
    padrao = '[0-9]{2}/[0-9]{4}|[0-9]{6}' if periodo else '[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{8}'
    tipo = 'month' if periodo else 'date'
    acao = 'Escolher mês' if periodo else 'Abrir calendário'
    return (f'<div class="campo-data" data-calendario="{tipo}"><label for="campo-{nome}">{rotulo} ({formato})</label>'
            f'<div class="controle-data"><input id="campo-{nome}" name="{nome}" value="{data_br(inicial)}" '
            f'placeholder="{formato}" inputmode="numeric" autocomplete="off" '
            f'maxlength="{len(formato)}" pattern="{padrao}" title="Formato {formato}" required>'
            f'<button class="secundario botao-calendario" type="button" aria-label="{acao}" title="{acao}" hidden>'
            '<span class="icone-calendario" aria-hidden="true"></span></button>'
            f'<input class="seletor-calendario" type="{tipo}" aria-label="{acao}" hidden></div></div>')


def campo_texto(nome, rotulo, exemplo, requerido=False):
    required = ' required' if requerido else ''
    return (f'<label>{rotulo}<input name="{nome}" maxlength="100" placeholder="{exemplo}" '
            f'lang="pt-BR" spellcheck="true"{required}></label>')


def valor(dados):
    return dinheiro(dados) if dados is not None else '—'


def campo_valor(nome, rotulo, requerido=True, inicial=''):
    required = ' required' if requerido else ''
    return f'<label>{rotulo}<input name="{nome}" value="{inicial}" inputmode="decimal" placeholder="0,00" maxlength="18"{required}></label>'


def cartao(label, total, detalhe='', destaque=False):
    classe = ' destaque' if destaque else ''
    return f'<article class="cartao{classe}"><span>{label}</span><strong>{dinheiro(total)}</strong><small>{detalhe}</small></article>'


def painel(mes, d, anual, csrf, hoje, fechado, erro='', pessoas=(), pessoa=''):
    ano, numero = mes.split('-')
    periodo = f'{MESES[int(numero)-1]} de {ano}'
    data_padrao = hoje if mes == hoje[:7] else mes + '-01'
    ctx = contexto(mes, csrf)
    alerta = f'<p role="alert" class="erro">{escape(erro)}</p>' if erro else ''
    linhas = []
    for c in d['contas']:
        total = c['confirmado'] if c['confirmado'] is not None else c['previsto']
        resto = max(0, total - c['pago'])
        estado = ('Em atraso' if c['vencimento'] < hoje else 'Em aberto') if resto else 'Quitado'
        if resto and c['pago']:
            estado += ' · parcial'
        linhas.append((f'<a href="/conta/{c["id"]}"><b>{escape(c["descricao"])}</b></a><small>{escape(c["categoria"])} · {escape(c["pessoa"])}</small>',
                       data_br(c['vencimento']), c['tipo'].capitalize(), dinheiro(c['previsto']), dinheiro(c['pago']),
                       f'{dinheiro(resto)}<small>{estado}</small>'))
    previsoes = []
    for nome, estimado, comprometido, restante, media, manual in d['projecoes']:
        fonte = 'Ajuste manual' if manual else 'Média do histórico' if media is not None else 'Sem estimativa'
        previsoes.append((escape(nome), f'{valor(estimado)}<small>{fonte}</small>', dinheiro(comprometido), dinheiro(restante)))
    anos = []
    for m, r in anual:
        anos.append((f'<a href="/?mes={m}">{MESES[int(m[5:])-1]}</a>', dinheiro(r['previsto']['receita']),
                     dinheiro(r['previsto']['despesa']), dinheiro(r['caixa']), dinheiro(r['projetado'])))
    base = ', '.join(m[5:] + '/' + m[:4] for m in d['meses']) or 'Nenhum mês encerrado disponível'
    filtro = ''
    if pessoas:
        opcoes = ['<option value="">Todas</option>']
        for nome in pessoas:
            selecionado = ' selected' if nome == pessoa else ''
            opcoes.append(f'<option{selecionado}>{escape(nome)}</option>')
        filtro = f'<form class="linha filtro" method="get" action="/#contas"><input type="hidden" name="mes" value="{mes}"><label>Pessoa<select name="pessoa">{"".join(opcoes)}</select></label><button class="secundario">Filtrar lançamentos</button></form>'
    botao_fechamento = ''
    if mes < hoje[:7]:
        acao = 'Reabrir mês' if fechado else 'Marcar mês como completo'
        botao_fechamento = f'<form method="post" action="/encerrar">{ctx}<input type="hidden" name="fechado" value="{0 if fechado else 1}"><button class="secundario">{acao}</button></form>'
    cards = ''.join((cartao('Recebido', d['realizado'].get('receita', 0), f'{dinheiro(d["pendente"]["receita"])} a receber'),
                     cartao('Pago', d['realizado'].get('despesa', 0), f'{dinheiro(d["pendente"]["despesa"])} a pagar'),
                     cartao('Resultado em caixa', d['caixa'], 'Recebido menos pago no mês'),
                     cartao('Resultado projetado', d['projetado'], f'{dinheiro(d["reserva"])} de reserva para variáveis', True)))
    return pagina(periodo, f'''<header>{marca()}<form method="post" action="/sair">{ctx}<button class="secundario">Sair</button></form></header>
    <div class="hero"><div><p class="rotulo">VISÃO MENSAL</p><h1>{periodo}</h1></div>
    <form class="linha" method="get">{campo_data('mes','Período',mes,True)}<button class="secundario">Ver mês</button></form></div>
    {alerta}<div class="cards">{cards}</div>
    <nav aria-label="Seções"><a href="#contas">Lançamentos</a><a href="#projecao">Projeção variável</a><a href="#ano">Visão anual</a></nav>
    <section class="bloco" id="contas"><div class="titulo"><div><h2>Lançamentos</h2><p>Receitas e despesas por vencimento.</p></div>{botao_fechamento}</div>
    {filtro}
    {tabela(('Lançamento','Vencimento','Tipo','Previsto','Realizado','Pendente'), linhas, 'Nenhum lançamento neste mês.')}
    <details><summary>Novo lançamento</summary><form class="grade" method="post" action="/conta">{ctx}
    {campo_texto('descricao','Descrição','Ex.: Conta de energia',True)}
    <label>Tipo<select name="tipo"><option value="despesa">Despesa</option><option value="receita">Receita</option></select></label>
    {campo_texto('categoria','Categoria','Ex.: Energia',True)}
    {campo_data('vencimento','Vencimento',data_padrao)}
    {campo_valor('previsto','Valor previsto')}{campo_valor('confirmado','Valor confirmado',False)}
    {campo_texto('pessoa','Pessoa','Casa')}
    {campo_texto('meio','Conta, cartão ou meio de pagamento','Ex.: Cartão principal')}
    <label>Quantidade de meses<input type="number" name="repeticoes" min="1" max="120" value="1" required></label>
    <label class="check"><input type="checkbox" name="variavel" value="1"> Despesa variável</label>
    <label class="check"><input type="checkbox" name="pontual" value="1"> Gasto pontual fora da média</label>
    <div><button>Salvar lançamento</button></div></form></details></section>
    <section class="bloco" id="projecao"><h2>Projeção variável</h2><p>Meses completos usados na média · {base}</p>
    {tabela(('Categoria','Estimativa','Já comprometido','Reserva adicional'), previsoes, 'Adicione uma estimativa ou encerre meses com gastos variáveis registrados.')}
    <details><summary>Ajustar estimativa</summary><form class="grade" method="post" action="/estimativa">{ctx}
    {campo_texto('categoria','Categoria','Ex.: Supermercado',True)}
    {campo_valor('valor','Valor manual (vazio para voltar à média)',False)}<div><button>Salvar estimativa</button></div></form></details></section>
    <section class="bloco" id="ano"><h2>Visão anual · {ano}</h2>
    {tabela(('Mês','Receita prevista','Despesa prevista','Resultado em caixa','Resultado projetado'), anos, '')}</section>''')


def detalhe(conta, pagamentos, csrf, hoje):
    nome = escape(conta['descricao'])
    mes = conta['vencimento'][:7]
    ctx = contexto(mes, csrf) + f'<input type="hidden" name="conta" value="{conta["id"]}">'
    recebido = conta['tipo'] == 'receita'
    efetivado = sum(p['valor'] for p in pagamentos)
    total = conta['confirmado'] if conta['confirmado'] is not None else conta['previsto']
    linhas = [(data_br(p['data']), dinheiro(p['valor'])) for p in pagamentos]
    cards = ''.join((cartao('Previsto', conta['previsto']), cartao('Valor considerado', total),
                     cartao('Recebido' if recebido else 'Pago', efetivado),
                     cartao('A receber' if recebido else 'A pagar', max(0, total - efetivado), destaque=True)))
    registro = 'recebimento' if recebido else 'pagamento'
    return pagina(conta['descricao'], f'''<header>{marca()}<a href="/?mes={mes}">Voltar ao mês</a></header>
    <div class="hero"><div><p class="rotulo">{conta['tipo'].upper()}</p><h1>{nome}</h1>
    <p>{escape(conta['categoria'])} · {escape(conta['pessoa'])} · {escape(conta['meio'])} · Vence em {data_br(conta['vencimento'])}</p></div></div>
    <div class="cards">{cards}</div>
    <section class="bloco"><h2>Registrar {registro}</h2><form class="grade" method="post" action="/pagamento">{ctx}
    {campo_data('data','Data',hoje)}
    {campo_valor('valor','Valor')}<div><button>Registrar</button></div></form>
    {tabela(('Data','Valor'), linhas, 'Nenhum movimento registrado.')}</section>
    <section class="bloco"><h2>Atualizar valor confirmado</h2><p>A previsão original continua disponível para comparação.</p>
    <form class="grade" method="post" action="/confirmado">{ctx}{campo_valor('valor','Valor confirmado')}
    <div><button>Confirmar valor</button></div></form></section>''')
