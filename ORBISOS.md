# OrbisOS 0.1

Sistema Linux mínimo, inicializável e exclusivo de terminal, criado para o Itautec Infoway W7030 e outros computadores antigos compatíveis com x86_64.

## Escopo da versão 0.1

- Debian 12 Bookworm mínimo
- Inicialização em modo texto
- Login automático como `root` no ambiente live
- Bash e BusyBox
- Python 3
- Git, curl e SQLite
- OpenSSH Server
- Ferramentas básicas para Wi-Fi
- Firmware Intel, Realtek e Atheros
- Comando `orbis` para diagnóstico do nó
- Sem desktop, X11, navegador ou aplicativos gráficos

## Obter a ISO pelo GitHub

1. Abra a aba **Actions** do repositório.
2. Abra o workflow **Build OrbisOS ISO**.
3. Aguarde a execução da branch `orbis-os` terminar com marca verde.
4. Na parte inferior da execução, baixe o artefato **OrbisOS-0.1-amd64**.
5. Extraia o arquivo ZIP. Dentro dele estarão a ISO e o checksum SHA-256.

## Gravar no pendrive no Windows

Use Rufus ou balenaEtcher.

No Rufus:

1. Selecione o pendrive correto.
2. Selecione `orbisos-0.1.0-amd64.iso`.
3. Esquema de partição: `MBR`.
4. Sistema de destino: `BIOS ou UEFI-CSM`.
5. Inicie a gravação.
6. Se o Rufus perguntar, prefira **modo imagem ISO** inicialmente. Caso não inicialize, grave novamente em **modo DD**.

> A gravação apaga todo o conteúdo do pendrive.

## Primeiro boot

1. Conecte o pendrive ao Itautec.
2. Abra o menu de boot da BIOS.
3. Escolha o dispositivo USB.
4. Aguarde o terminal do OrbisOS.
5. Execute:

```bash
orbis
```

## Conectar ao Wi-Fi manualmente

Identifique a interface:

```bash
ip link
```

Ative-a, substituindo `wlan0` pelo nome real:

```bash
ip link set wlan0 up
```

Crie a configuração:

```bash
wpa_passphrase "NOME_DA_REDE" "SENHA_DA_REDE" > /etc/wpa_supplicant.conf
```

Conecte e peça um endereço IP:

```bash
wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf
dhclient wlan0
```

Teste:

```bash
ping -c 3 1.1.1.1
```

## Gerar localmente em Debian ou Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y git live-build debootstrap xorriso isolinux syslinux-common
git clone --branch orbis-os https://github.com/PrimalSword/Jogoia.git
cd Jogoia
chmod +x orbis-build.sh
sudo ./orbis-build.sh
```

A imagem será criada em `dist/`.

## Observações

Esta primeira imagem é um sistema **live**: ela inicia pelo pendrive, mas alterações feitas durante o uso não são preservadas após reiniciar. Persistência e instalador definitivo serão tratados em versões seguintes, depois que o boot, teclado, vídeo e rede forem validados no Itautec.
