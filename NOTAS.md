# Notas de mantenimiento

Este archivo no se ve en el perfil: GitHub sólo renderiza `README.md`.

## Regenerar el banner

```bash
python src/generate_banner.py --art brand/monograma-db-indigo.png
```

Para inspeccionar un fotograma suelto sin animación (útil al iterar):

```bash
python src/generate_banner.py --art brand/monograma-db-indigo.png --mode dark --static logo1
```

`--static` acepta `portrait`, `logo1`, `logo2`, `logo3`.

Si algún día usas una foto en vez del monograma, es `--photo foto.jpg`
más `--crop x,y,w,h`. Ese camino sí ditherea (Floyd–Steinberg) porque una foto
tiene rango tonal; el monograma es plano y se resuelve calando una retícula.

## Qué mira cada métrica

El script imprime cuatro números al generar. Sirven para no tener que juzgar
a ojo un SVG de 700 KB:

| Métrica | Bien | Qué falla si se sale |
|---|---|---|
| `disperso` | ~1.00x | Los grupos del titileo se vuelven parches y el logo aparece por zonas en vez de entero |
| `flat` | < 0.30 | Las bandas quedan con borde recto y el barrido se ve a bloques |
| `spread` | 0.4–1.2 | Las bandas se diluyen y el barrido se vuelve estática |
| `tinta` | < 45% | El sujeto se lee como una mancha sólida y el archivo se dispara |

`disperso` y `flat`/`spread` son razones contra su propia línea base, no valores
absolutos: así siguen significando lo mismo aunque cambie el número de puntos.

## Lo que hay que hacer a mano

1. Subir `dark.svg` y `light.svg` a la raíz del repo `burgosdavid057-art/burgosdavid057-art`.
2. Crear el token clásico (`repo`, sin expiración) y pegarlo **sólo** en la
   variable `PAT_1` de Vercel. Nunca en el repo ni en un chat.
3. Desplegar el fork de `anuraghazra/github-readme-stats` en Vercel y
   reemplazar `YOUR-INSTANCE` en `README.md` por la URL que salga.
4. Repo → Settings → Actions → General → Workflow permissions →
   **Read and write**. Es el ajuste del *repo*, no el de la cuenta.
5. Esperar a que la Action `Generate Snake Animation` salga en verde antes de
   confiar en las imágenes del snake: la rama `output` no existe hasta entonces.

## Cosas que muerden

- **La caché del CDN de GitHub.** Si cambias un SVG y no ves nada, casi nunca es
  un bug. Abre `raw.githubusercontent.com/.../dark.svg?v=999` y busca el color
  nuevo en el fuente. `Ctrl+Shift+R` limpia tu navegador, no los servidores.
- **El tema.** `dark.svg` sólo se muestra en modo oscuro. Si estás en claro
  estás mirando otro archivo.
- **Las Actions programadas se pausan** tras ~60 días sin actividad en el repo.
- **Los SVG no pueden llevar enlaces**: GitHub los quita. Los enlaces
  clicables tienen que ser los badges del README.
- **El badge de LinkedIn** sólo dibuja su logo sobre el azul de marca
  `#0A66C2`. Con cualquier otro color el glifo desaparece sin avisar.
