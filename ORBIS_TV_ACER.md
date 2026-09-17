# Orbis TV — Acer / Samsung CRT

Imagem live x86_64 pensada para a placa Acer Z5WAH LA-B161P usada como cérebro da Samsung CRT.

## Objetivo

O sistema inicia direto em uma interface de TV baseada no Kodi, sem desktop tradicional. O modo gráfico prioriza saída VGA/HDMI externa e tenta 800x600, com fallback para 640x480, adequado ao conversor VGA2AV e à TV 4:3.

Inclui:

- Debian 13 (Trixie) live, amd64
- Kodi 21 como interface principal
- Firefox ESR em modo kiosk como navegador auxiliar
- VA-API Intel `i965` para aceleração de vídeo em GPUs Intel Haswell e compatíveis
- NetworkManager + `nmtui` para Wi-Fi
- firmware Intel/Realtek/Atheros/Broadcom
- áudio ALSA/PulseAudio
- Openbox mínimo, sem desktop pesado
- português do Brasil
- addon `Orbis Apps` dentro do Kodi com atalhos para navegador, rede, terminal, reiniciar e desligar

## Controles úteis

- `Ctrl+Alt+B`: navegador
- `Ctrl+Alt+W`: configuração de Wi-Fi/rede (`nmtui`)
- `Ctrl+Alt+T`: terminal
- `Alt+F4`: fecha a janela em primeiro plano

No Kodi, abra **Add-ons > Program add-ons > Orbis Apps** para acessar os mesmos atalhos.

## Build

O workflow `Build Orbis TV ISO` gera:

- `orbistv-0.1.0-amd64.iso`
- `orbistv-0.1.0-amd64.iso.sha256`

A primeira versão é live: serve para validar vídeo, som, Wi-Fi, aceleração e estabilidade no Acer antes de preparar a instalação definitiva no SSD/HD.

## Gravação no pendrive

Use Rufus ou balenaEtcher. Como a imagem é `iso-hybrid`, o modo DD é o mais previsível em máquinas antigas caso o Rufus ofereça escolha.

## Observação sobre streaming

Kodi é a interface principal e o Firefox cobre sites comuns. Serviços com DRM proprietário podem exigir componentes adicionais; a imagem não promete compatibilidade com todos os serviços pagos na primeira versão.
