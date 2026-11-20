import argparse
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import warnings

from dados import PASTA, conectar, preparar
from financeiro import dinheiro


def valor_excel(celula):
    valor = celula.value
    if not isinstance(valor, (float, int)) or isinstance(valor, bool):
        return 0
    return int((Decimal(str(valor)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def normalizar(texto, padrao):
    return str(texto or padrao).strip()[:100] or padrao


def ler(caminho):
    from openpyxl import load_workbook

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Data Validation extension is not supported')
        livro = load_workbook(caminho, read_only=True, data_only=True)
    try:
        for nome, tipo, ultima, coluna_mes in (
            ('R. Fx', 'receita', 21, 2), ('R. Vr', 'receita', 6, 2),
            ('D. Fx.', 'despesa', 35, 4),
        ):
            aba = livro[nome]
            linhas = aba.iter_rows(min_row=2, max_row=ultima, max_col=coluna_mes + 11)
            cabecalho = next(linhas)
            for linha in linhas:
                if linha[0].value is None:
                    continue
                despesa = tipo == 'despesa'
                descricao = normalizar(linha[2 if despesa else 0].value, 'Sem descrição')
                classe = normalizar(linha[0].value, 'Sem categoria') if despesa else ('Receita fixa' if nome == 'R. Fx' else 'Receita variável')
                meio = normalizar(linha[1].value if despesa else None, 'A definir')
                for cab, celula in zip(cabecalho[coluna_mes-1:], linha[coluna_mes-1:]):
                    valor = valor_excel(celula)
                    if valor <= 0:
                        continue
                    mes = cab.value
                    if not isinstance(mes, date):
                        raise ValueError(f'Cabeçalho de mês inválido em {nome}.')
                    vencimento = date(mes.year, mes.month, monthrange(mes.year, mes.month)[1])
                    yield (f'{nome}!{celula.coordinate}', tipo, descricao, classe, meio, vencimento.isoformat(), valor, False, False)

        for linha in livro['D. Fx.+Vr.'].iter_rows(min_row=3, max_col=7):
            data, classificacao, meio, categoria, descricao, celula = linha[1:]
            if not isinstance(data.value, date) or (valor := valor_excel(celula)) <= 0:
                continue
            dia = data.value.date() if isinstance(data.value, datetime) else data.value
            yield (f'D. Fx.+Vr.!{celula.coordinate}', 'despesa', normalizar(descricao.value, 'Sem descrição'),
                   normalizar(categoria.value, 'Sem categoria'), normalizar(meio.value, 'A definir'),
                   dia.isoformat(), valor, True, str(classificacao.value).casefold() in ('variável', 'não programada'))
    finally:
        livro.close()


def salvar(db, caminho, linhas, incluir_realizados):
    db.execute('BEGIN IMMEDIATE')
    origem = caminho.name.casefold()
    adicionados = 0
    for celula, tipo, descricao, categoria, meio, data, valor, realizado, variavel in linhas:
        if realizado and not incluir_realizados:
            continue
        if db.execute('SELECT 1 FROM importacao WHERE casa_id=1 AND origem=? AND celula=?', (origem, celula)).fetchone():
            continue
        cursor = db.execute('''INSERT INTO conta(casa_id,tipo,descricao,categoria,pessoa,meio,vencimento,previsto,confirmado,variavel,pontual)
                               VALUES(1,?,?,?,'Casa',?,?,?,?,?,0)''',
                            (tipo, descricao, categoria, meio, data, 0 if realizado else valor, valor if realizado else None, int(variavel)))
        if realizado:
            db.execute('INSERT INTO pagamento(conta_id,data,valor) VALUES(?,?,?)', (cursor.lastrowid, data, valor))
        db.execute('INSERT INTO importacao VALUES(1,?,?,?)', (origem, celula, cursor.lastrowid))
        adicionados += 1
    return adicionados


def main():
    parser = argparse.ArgumentParser(description='Revisar ou importar o modelo Orçamento Anual 2023')
    parser.add_argument('planilha', type=Path)
    parser.add_argument('--banco', type=Path, default=PASTA / 'orcamento.sqlite3')
    parser.add_argument('--aplicar', action='store_true', help='Gravar as previsões revisadas')
    parser.add_argument('--incluir-realizados', action='store_true', help='Gravar também pagamentos avulsos, sem vinculá-los às previsões')
    args = parser.parse_args()
    try:
        linhas = list(ler(args.planilha))
    except ModuleNotFoundError:
        parser.error('Para importar Excel, instale openpyxl com python -m pip install openpyxl.')
    except (KeyError, OSError, ValueError) as exc:
        parser.error(f'Planilha incompatível ou indisponível: {exc}')
    for celula, tipo, descricao, categoria, meio, data, valor, realizado, _ in linhas:
        natureza = 'Pago avulso' if realizado else tipo.capitalize() + ' prevista'
        print(f'{celula:24} {data}  {natureza:18} {dinheiro(valor):>14}  {descricao}')
    previstos = sum(not linha[7] for linha in linhas)
    print(f'\n{previstos} previsões e {len(linhas) - previstos} pagamentos avulsos encontrados.')
    if args.aplicar:
        if not preparar(args.banco):
            parser.error('Configure a senha com python app.py --configurar-senha antes de importar.')
        with conectar(args.banco) as db:
            adicionados = salvar(db, args.planilha, linhas, args.incluir_realizados)
        print(f'{adicionados} registros importados.')
    else:
        print('Prévia concluída. Use --aplicar após revisar os lançamentos.')


if __name__ == '__main__':
    main()
