# Orbis TV

Modo gráfico sob demanda para o Itautec Infoway W7030.

A ideia é manter o OrbisOS em terminal durante o uso normal e iniciar Xorg + Openbox + Firefox ESR somente quando for necessário abrir um site de vídeo. Ao fechar o navegador, o Xorg encerra e o sistema volta ao terminal.

## Instalação em um comando

No OrbisOS, como root e com internet disponível:

```sh
curl -fsSL https://raw.githubusercontent.com/PrimalSword/Jogoia/main/orbis/tv-bootstrap.sh | sh
```

O bootstrap tenta atualizar o OrbisOS pelo Git, instala o comando `orbis-tv` e baixa somente os pacotes necessários ao modo gráfico.

## Uso

Para digitar o site no terminal e abrir em tela cheia:

```sh
orbis-tv
```

Para abrir uma URL diretamente:

```sh
orbis-tv https://exemplo.com
```

Para apenas preparar/reparar as dependências:

```sh
orbis-tv --prepare
```

Para diagnóstico:

```sh
orbis-tv --status
```

## Saída VGA para conversor VGA2AV

O modo preferido é `800x600`. O script tenta priorizar uma saída externa VGA/HDMI/DP e, se `800x600` não estiver disponível, tenta `640x480`.

É possível forçar o modo ao iniciar:

```sh
ORBIS_TV_MODE=640x480 orbis-tv https://exemplo.com
```

## Funcionamento

Fluxo normal:

```text
terminal -> orbis-tv -> Xorg -> Openbox -> Firefox ESR em kiosk
                                      |
                                      +-> fechar navegador -> volta ao terminal
```

O ambiente gráfico não é iniciado no boot e não fica consumindo memória em segundo plano quando o navegador está fechado.

Para sair do navegador, use `Alt+F4` ou `Ctrl+Q`.

## Pacotes instalados

O instalador usa os repositórios Alpine Linux v3.24 `main` e `community` e instala, entre outros, `xorg-server`, `xinit`, `openbox`, `firefox-esr`, `xrandr`, Mesa e o driver de entrada libinput.
