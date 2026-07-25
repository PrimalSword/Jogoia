# OrbisOS

OrbisOS é uma camada minimalista para transformar hardware legado em um nó de automação confiável, leve e administrável por terminal.

Esta primeira versão não substitui o kernel nem reinstala o antiX. Ela instala o **Orbis Core** sobre o sistema já funcional, cria um serviço supervisionado pelo runit e permite desligar a interface gráfica sem perder a possibilidade de restaurá-la.

## Alvo inicial

- Itautec Infoway W7030
- Intel Atom N455
- 2 GB de RAM
- antiX com runit
- armazenamento em microSD/USB

## Instalação rápida

No antiX, abra o terminal e execute:

```bash
sudo apt-get update
sudo apt-get install -y git
cd ~
git clone --branch orbis-os --single-branch https://github.com/PrimalSword/Jogoia.git orbis-os
cd orbis-os
sudo bash orbis/install.sh
```

Depois confira:

```bash
orbis-status
sudo sv status orbisd
```

## Iniciar apenas em terminal

Primeiro teste o Orbis Core com o desktop ainda ativo. Quando estiver tudo estável:

```bash
sudo orbis-mode terminal
sudo reboot
```

Para restaurar o desktop:

```bash
sudo orbis-mode desktop
sudo reboot
```

## Comandos

```bash
orbis-status              # painel de estado
sudo sv status orbisd     # estado do serviço
sudo sv restart orbisd    # reinicia o serviço
tail -f /var/log/orbis/orbisd.log
```

## Segurança

- Nenhuma senha, token ou chave deve ser enviada ao GitHub.
- Segredos futuros ficarão em `/etc/orbis/secrets.env`, com permissão `600`.
- O instalador não remove o ambiente gráfico; apenas oferece um modo reversível para não iniciá-lo.
- A branch `main` do jogo foi preservada. Todo o trabalho do OrbisOS está na branch `orbis-os`.

## Próxima etapa

A v0.2 adicionará o primeiro módulo de receita: catálogo de ofertas aprovadas manualmente, geração de mensagens e publicação em canal próprio, sem venda de IP e sem automação agressiva contra marketplaces.
