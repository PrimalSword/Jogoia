#!/bin/sh

[ -t 1 ] || return 0
printf '\n'
printf '%s\n' '========================================'
printf '%s\n' '       ORBIS NODE — terminal ativo'
printf '%s\n' '========================================'
printf '%s\n' 'Painel: orbis-status'
printf '%s\n' 'Serviço: sudo sv status orbisd'
printf '\n'
