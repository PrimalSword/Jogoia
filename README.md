# ECO: Último Toque

Um jogo mobile de uma mão em que cada derrota cria o adversário da próxima partida.

## Conceito

Você controla um sinal instável preso entre duas polaridades. Um toque inverte a direção da gravidade. Sobreviva aos bloqueios, aumente a velocidade e ultrapasse o rastro da sua tentativa anterior.

O diferencial do loop é o **ECO**: a rota da última partida reaparece como um fantasma. O jogador não enfrenta apenas o cenário; enfrenta a própria memória muscular, vê exatamente onde hesitou e tenta reescrever aquele fracasso.

## Estado atual

- MVP jogável;
- controle por toque ou clique;
- dificuldade e velocidade progressivas;
- obstáculos procedurais;
- recorde e fragmentos salvos localmente;
- fantasma da tentativa anterior;
- efeitos, partículas e interface desenhados por código;
- sem dependência de assets externos.

## Como executar

1. Instale o Godot 4.3 ou superior.
2. Importe a pasta do projeto pelo arquivo `project.godot`.
3. Pressione **F6** ou **F5**.

O viewport foi configurado para 720 × 1280 em orientação retrato e escala corretamente para telas Android.

## Exportar para Android

1. No Godot, instale os *Export Templates* da mesma versão do editor.
2. Configure o Android SDK/JDK em **Editor > Editor Settings > Export > Android**.
3. Crie um preset Android em **Project > Export**.
4. Defina um identificador, por exemplo `com.primalword.eco`.
5. Exporte o APK para testes ou AAB para a Google Play.

## Roadmap de produto

### Versão 0.2 — Retenção
- missões de três minutos;
- sequência diária;
- mutações de regras a cada faixa de pontuação;
- cosméticos desbloqueáveis com fragmentos;
- feedback háptico e áudio adaptativo.

### Versão 0.3 — Assinatura própria
- múltiplos ECOS de partidas antigas;
- eventos em que o jogador precisa atravessar o próprio rastro;
- desafios assíncronos contra trajetórias de outros jogadores;
- sistema de “paradoxo”: assumir risco para apagar um erro anterior.

## Direção de design

Sessões curtas, reinício instantâneo, uma única ação, legibilidade forte e ausência de anúncios interrompendo a partida. Monetização futura deve priorizar cosméticos e remoção opcional de anúncios, sem vender vantagem competitiva.

## Licença

Projeto proprietário em desenvolvimento. Todos os direitos reservados ao titular do repositório.
