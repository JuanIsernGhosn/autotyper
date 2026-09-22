# autotyper

Escribe un texto en el input que tenga el foco (por ejemplo un campo de Chrome
que bloquea el pegado) imitando a una persona: velocidad variable, pausas tras
puntuación, errores de tecleo y sus correcciones. Inyecta pulsaciones reales a
nivel de sistema, así que para la página son indistinguibles de un teclado.

Solo macOS.

## Instalación

```sh
uv sync
```

## Permisos

En Ajustes del Sistema > Privacidad y seguridad:

- **Accesibilidad**: la app desde la que ejecutas el comando (Terminal, iTerm,
  VS Code...). Sin esto no se inyectan teclas.
- **Monitorización de entrada**: la misma app, para los atajos globales de
  pausa y aborto.

## Uso

```sh
# previsualizar sin escribir nada
uv run autotyper texto.txt --dry-run
uv run autotyper texto.txt --dry-run --verbose

# escribir de verdad: cuenta atrás de 5 s para hacer clic en el input
uv run autotyper texto.txt
uv run autotyper texto.txt --cps 8 --error-rate 0.03 --seed 42
cat texto.txt | uv run autotyper -

# perfil YAML (los flags de CLI tienen prioridad)
uv run autotyper texto.txt --profile perfil.yaml
```

Ejemplo de `perfil.yaml`:

```yaml
cps: 7
error_rate: 0.025
uncorrected_rate: 0.1
think_pause_rate: 0.04
layout: es
```

## Durante la escritura

- **F8** pausa y reanuda. **Esc** aborta. Ambos son globales: no hace falta
  volver a la terminal.
- Si Google Chrome deja de estar en primer plano, la escritura se pausa sola y
  continúa cuando vuelve. Cambia la app con `--app` o desactívalo con
  `--no-focus-guard`.
- La terminal debería estar en una pantalla que no se grabe.

## Parámetros

| Flag | Defecto | Qué hace |
|---|---|---|
| `--cps` | 6 | caracteres por segundo medios |
| `--speed-sigma` | 0.35 | dispersión del intervalo entre teclas |
| `--error-rate` | 0.02 | probabilidad de error por letra |
| `--uncorrected-rate` | 0 | fracción de errores que se dejan sin corregir |
| `--think-pause-rate` | 0.03 | probabilidad de pausa larga al empezar palabra |
| `--layout` | es | distribución para errores de tecla vecina (`es`, `us`) |
| `--countdown` | 5 | segundos antes de empezar |
| `--seed` | aleatorio | semilla para repetir una ejecución |
| `--pause-key` / `--abort-key` | f8 / esc | atajos globales |

## Tests

```sh
uv run pytest
```
