# autotyper: escritura humana simulada en Chrome (diseño)

Fecha: 2026-09-22

## Objetivo

Herramienta de línea de comandos para macOS que escribe un texto dado en
cualquier input de Chrome (incluidos los que bloquean el pegado) imitando a una
persona: velocidad variable, pausas según el contexto, errores de tecleo y sus
correcciones. Se usa mientras se graba la pantalla donde está Chrome; la
terminal que controla la herramienta vive en otra pantalla no grabada.

## Decisiones tomadas

- Inyección de teclas a nivel de sistema operativo con `pynput`. Los eventos
  llegan a Chrome como si vinieran de un teclado físico (`isTrusted` true) y
  ninguna página puede distinguirlos de tecleo real.
- Solo macOS. Requiere permiso de Accesibilidad (para inyectar) y de
  Monitorización de entrada (para los atajos globales) en la app que ejecuta
  Python (Terminal, iTerm, etc.).
- Python 3.12+, gestionado con `uv`. Dependencias de runtime: `pynput`,
  `pyyaml`, `pyobjc-framework-Cocoa` (detección de app en primer plano).
- Distribución de teclado española ISO por defecto para el mapa de teclas
  vecinas; `us` como alternativa.
- Control desde la terminal con atajos globales; sin GUI.
- Valores por defecto: 6 caracteres por segundo, 2 % de errores, todos
  corregidos.

## Arquitectura

Dos capas separadas por una interfaz de datos simple:

1. **Planificador** (`model.py`): función pura `plan(text, config, rng) ->
   list[Event]`. Convierte el texto en una secuencia de eventos de tecla con
   tiempos. No toca el sistema. Determinista dada una semilla.
2. **Ejecutor** (`runner.py`): recorre los eventos, espera los retardos, y
   delega la pulsación en un `Injector`. Gestiona pausa, aborto y guardia de
   foco.

Módulos del paquete `autotyper/`:

| Módulo | Responsabilidad |
|---|---|
| `events.py` | Dataclass `Event(key, delay_ms, hold_ms, note)`. `key` es un carácter o uno de `"backspace"`, `"enter"`, `"tab"`. `delay_ms` es la espera antes de pulsar. `note` es texto opcional para el modo simulación (p. ej. `"error:neighbor"`, `"fix"`). |
| `config.py` | Dataclass `TypingConfig` con todos los parámetros y valores por defecto. Carga desde YAML; los flags de CLI sobrescriben. |
| `layouts.py` | Mapas de teclas vecinas `es` y `us` (`dict[str, str]`, minúsculas). Función `neighbor(ch, layout, rng)` que respeta mayúsculas. |
| `model.py` | Planificador: ritmo, deriva, pausas contextuales, errores y correcciones. |
| `injector.py` | Protocolo `Injector.press(key: str, hold_s: float)`. Implementaciones `PynputInjector` (real) y `RecordingInjector` (tests). |
| `focus.py` | `frontmost_app_name() -> str | None` vía `NSWorkspace`. Devuelve `None` fuera de macOS o si falla la importación. |
| `runner.py` | `run(events, injector, controls, clock)` con pausa, aborto y guardia de foco. `Controls` es un objeto con flags `paused`/`aborted` que actualizan los atajos. |
| `hotkeys.py` | Listener global de `pynput` que actualiza `Controls`. Teclas por defecto: F8 pausa/reanuda, Esc aborta. |
| `dryrun.py` | Renderiza la lista de eventos como transcripción legible y estadísticas. |
| `cli.py` | Punto de entrada `autotyper`. |

## Modelo de tecleo

Todos los tiempos se expresan en milisegundos. `rng` es `random.Random(seed)`.

### Ritmo base

- `base = 1000 / cps`.
- Intervalo de cada tecla: `base * drift * ctx * lognormal(mu=0, sigma=0.35)`.
- **Deriva** (`drift`): proceso de reversión a la media actualizado en cada
  tecla: `drift += 0.02 * (1 - drift) + gauss(0, 0.05)`, acotado a `[0.6,
  1.6]`. Simula rachas y cansancio a lo largo de decenas de segundos.
- **Multiplicador contextual** (`ctx`): mayúscula 1.4, dígito 1.3, signo de
  puntuación o símbolo 1.3, carácter tras una corrección (los 3 siguientes)
  1.2, resto 1.0.

### Pausas añadidas antes de la siguiente tecla

- Tras `,` `;` `:`: uniforme 150–400.
- Tras `.` `!` `?` `…`: uniforme 300–900.
- Tras salto de línea: uniforme 500–1500.
- Al empezar una palabra (tras un espacio), con probabilidad
  `think_pause_rate` (por defecto 0.03): uniforme 800–2500.

### Duración de la pulsación

`hold_ms = gauss(60, 15)` acotado a `[25, 120]`. Para retrocesos en ráfaga se
usa el mismo modelo.

### Errores

Solo se aplican a letras (`str.isalpha()`). Con probabilidad `error_rate` por
carácter se elige un tipo según pesos:

| Tipo | Peso | Se teclea | Debería ser | Avance |
|---|---|---|---|---|
| `neighbor` | 0.50 | tecla vecina | `c` | 1 |
| `transpose` | 0.20 | `c2 c1` | `c1 c2` | 2 (solo si `c2` es letra) |
| `double` | 0.15 | `c c` | `c` | 1 |
| `omit` | 0.15 | nada | `c` | 1 |

Detección: se teclean `k` caracteres correctos adicionales antes de notar el
error, con `k = 0` con probabilidad 0.5 y `k ∈ {1, 2, 3}` uniforme en otro
caso, sin pasar del final de la palabra actual (no se cruza un espacio ni un
salto de línea). Para `omit`, `k` mínimo 1; si no hay margen se cambia a
`neighbor`.

Corrección: con probabilidad `1 - uncorrected_rate` (por defecto 1.0):

1. Pausa de reacción: uniforme 200–500.
2. `len(tecleado) + k` retrocesos, intervalo uniforme 80–140 cada uno.
3. Se reescribe la secuencia correcta más los `k` caracteres, con `ctx` 1.2.

Si no se corrige, el error queda en el texto final.

Invariante: con `uncorrected_rate = 0`, reproducir los eventos sobre un buffer
(aplicando caracteres y retrocesos) produce exactamente el texto original.

### Caracteres especiales

- `\n` se emite como `enter`, `\t` como `tab`. `\r` se ignora.
- Cualquier otro carácter se emite tal cual; `pynput` lo inyecta como cadena
  Unicode, lo que cubre `ñ`, tildes y símbolos que no están en la
  distribución.

## Ejecutor y seguridad

Flujo del comando:

1. Cargar texto (fichero o `-` para stdin) y configuración.
2. Planificar eventos.
3. Arrancar el listener de atajos.
4. Cuenta atrás de `countdown` segundos (por defecto 5) mostrando el conteo;
   el usuario hace clic en el input de Chrome en ese tiempo.
5. Por cada evento: comprobar `aborted` (termina), esperar mientras `paused`,
   comprobar guardia de foco, dormir `delay_ms`, pulsar con `hold_ms`.
6. Al terminar o abortar, detener el listener e imprimir resumen.

Guardia de foco: si `frontmost_app_name()` no coincide con `app_name` (por
defecto `"Google Chrome"`), el ejecutor entra en pausa automática y avisa por
terminal; reanuda solo cuando Chrome vuelve al frente. Se puede desactivar con
`--no-focus-guard`. En plataformas donde la detección devuelve `None` la
guardia se ignora.

Al pausar (manual o automático) el tiempo no cuenta; al reanudar se respeta
el `delay_ms` del evento pendiente.

## Configuración

`TypingConfig` (nombres iguales en YAML y CLI):

| Campo | Defecto |
|---|---|
| `cps` | 6.0 |
| `speed_sigma` | 0.35 |
| `error_rate` | 0.02 |
| `uncorrected_rate` | 0.0 |
| `think_pause_rate` | 0.03 |
| `layout` | `es` |
| `app_name` | `Google Chrome` |
| `focus_guard` | true |
| `countdown` | 5 |
| `seed` | null (aleatorio) |
| `pause_key` | `f8` |
| `abort_key` | `esc` |

## CLI

```
autotyper TEXTO.txt [--cps 6] [--error-rate 0.02] [--layout es] [--seed 42]
                    [--countdown 5] [--profile perfil.yaml] [--app "Google Chrome"]
                    [--no-focus-guard] [--dry-run] [--verbose]
cat TEXTO.txt | autotyper -
```

`--dry-run` no inyecta nada: imprime la transcripción tal como se teclearía
(los retrocesos como `⌫`), y un resumen con duración total estimada, número
de errores y cps efectivos. `--verbose` añade una línea por evento con
retardo y duración de pulsación.

## Manejo de errores

- Sin permiso de Accesibilidad: `pynput` falla o las teclas no llegan. La CLI
  comprueba `AXIsProcessTrusted()` al arrancar y, si es falso, explica qué
  permiso activar y sale con código 2.
- Fichero inexistente o texto vacío: mensaje y código 1.
- Abortado por el usuario: resumen con cuántos caracteres se escribieron y
  código 130.

## Pruebas

- `model`: con semilla fija, reproducir eventos sobre un buffer devuelve el
  texto original; con `error_rate = 0` no hay retrocesos; con `error_rate =
  1` en un texto de letras aparecen retrocesos y notas de error; los cps
  efectivos de un texto largo con `error_rate = 0` están entre 0.6 y 1.6
  veces `cps`; las teclas vecinas emitidas pertenecen al mapa de la
  distribución; `\n` produce `enter`.
- `layouts`: cada tecla del mapa tiene al menos una vecina y las vecinas
  existen en el mapa.
- `runner`: con `RecordingInjector` y un reloj falso, se pulsan todas las
  teclas en orden, se respetan los retardos acumulados, `aborted` corta la
  ejecución, `paused` retiene sin perder eventos, y la guardia de foco pausa
  cuando la app frontal no coincide.
- `dryrun`: la transcripción de un plan sin errores es el texto original.
- `config`: YAML y flags se combinan con la precedencia correcta.

Sin tests de integración contra Chrome; la verificación manual se hace con
`--dry-run` y después con un input real.

## Fuera de alcance

- Movimiento de ratón, clics, o localizar el input automáticamente.
- Linux y Windows.
- GUI o app de barra de menú.
- Escritura sin foco (vía Chrome DevTools Protocol).
