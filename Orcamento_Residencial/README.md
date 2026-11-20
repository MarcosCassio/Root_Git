# Orçamento Residencial

Aplicação web para planejar receitas e despesas da casa, registrar recebimentos e pagamentos parciais e acompanhar a projeção mensal. O painel anual reúne os doze meses em uma tabela.

## Rodar no Windows

No terminal do VS Code, abra a pasta `Orcamento_Residencial` e execute com Python 3.10 ou superior:

```powershell
python app.py
```

Abra `http://127.0.0.1:8000` no navegador. Na primeira execução, crie e confirme a senha familiar na página. Os dados ficam em `dados/orcamento.sqlite3`, que está excluído do Git. Guarde cópias de segurança do banco com o app parado.

Para trocar a senha e invalidar as sessões anteriores:

```powershell
python app.py --configurar-senha
```

O acesso padrão fica restrito ao computador servidor. Para dois dispositivos na mesma rede, inicie o servidor com `--host` apontando para o IP da máquina e forneça `--certificado` e `--chave` TLS. O certificado deve ser aceito pelo navegador de ambos os dispositivos e identificar o endereço utilizado. Os dois acessam a mesma instância e usam a senha familiar. O servidor embutido se destina a uso local ou em rede doméstica.

Os testes automatizados rodam com `python -m unittest -v` e usam um banco temporário independente.

## Como a projeção funciona

- A previsão original fica registrada. O valor confirmado é usado para calcular a pendência, descontando os movimentos já registrados.
- O resultado em caixa usa as datas dos recebimentos e pagamentos. A lista de compromissos usa o mês de vencimento. O resultado exibido é o fluxo do mês, sem saldo bancário inicial.
- A reserva variável considera até três meses anteriores marcados como completos. Gastos pontuais ficam fora da média. Se uma categoria teve gasto em parte dos meses completos, os demais entram com zero. Ajustes manuais valem para o mês escolhido.
- A reserva adicional cobre apenas a parcela da estimativa que ainda não está representada por despesas variáveis da categoria. O resultado projetado usa o fluxo do mês, os compromissos pendentes com vencimento no mês e essa reserva.
- Para compromissos recorrentes, a quantidade de meses gera um lançamento por mês. Um vencimento no dia 31 passa para o último dia nos meses mais curtos.

## Importar o modelo Excel de 2023

A importação usa `openpyxl` apenas para ler o arquivo. Instale a dependência caso ela ainda não esteja disponível:

```powershell
python -m pip install openpyxl
python importar_planilha.py "C:\caminho\ORÇAMENTO ANUAL - 2023.xlsx"
```

A prévia lista a origem de cada valor. Para gravar as previsões após revisar, repita o comando com `--aplicar`. Quando a planilha só informa o mês, o app usa o último dia como vencimento. Há uma opção `--incluir-realizados` para registrar também os pagamentos avulsos como movimentos separados. Revise possíveis sobreposições com as previsões antes de usá-la. A aba de ajuste de dívidas fica fora dessa importação.
