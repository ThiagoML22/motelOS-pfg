# Documentación del Proyecto (/docs)

Esta carpeta contiene la documentación formal del Proyecto de Grado: borradores de los capítulos I y II, el informe de la Actividad de Evaluación 1 (AE1) y los documentos de la Actividad de Evaluación 2 (AE2).

| Contenido | Archivo | Versión |
| :--- | :--- | :--- |
| Informe AE1 | `AE1-LEAL.pdf` | Versión 2 (04/10/2026), sin marcadores `[cite]` |
| Informe AE2 (Ventana de Mejora) | `AE2/20261004_InformeAE2_ThiagoLeal_v3.pdf` | Versión 3 |
| Catálogo de requisitos (libro oficial de la cátedra) | `AE2/20261005_CatalogoRequisitos_ThiagoLeal_v3.xlsx` | Versión 3 |
| Instrumentos 32 a 35 | `AE2/20261004_Instrumentos_AE2_ThiagoLeal_v3.pdf` | Versión 3 |
| Instrumento 27 (ficha de delimitación) | `AE2/20261005_Instrumento27_Ficha_delimitacion_ThiagoLeal.pdf` | Versión 1 |
| Bitácora individual | `AE2/20261004_Bitacora_AE2_ThiagoLeal_v2.pdf` | Versión 2 |
| Correcciones de la AE1 | `AE2/20261004_Correcciones_AE1_ThiagoLeal_v2.pdf` | Versión 2 |
| Respuestas al dictamen DEV-AE2 N.º 11/2026 (Bloque A) | `AE2/20261004_Respuestas_Bloque_A_ThiagoLeal.pdf` | Versión 1 |
| Registro de corridas del canal de integración continua | `AE2/20261004_Registro_corridas_Actions_motelOS.xlsx` | Registro completo, con su fecha y hora de exportación |
| Catálogo de requisitos de la AE3 (libro oficial de la cátedra) | `AE3/20261019_CatalogoRequisitos_ThiagoLeal_v4.xlsx` | Versión 4: RF-14 nuevo, RN-DER-04 con la redacción nueva y el fondo de cambio de $25.000 (RN-DER-05), validados en el acta del 19/10/2026 |
| Arquitectura del prototipo v2: modelo de datos, decisiones, trigger, permiso y RLS, amenazas y validación con la gerencia | `AE3/20261019_Arquitectura_v2_ThiagoLeal_v1.md` | Versión 1 |
| Medición de latencia de RNF-02 | `AE3/20261019_Medicion_latencia_RNF-02.csv` | 200 peticiones, P95 de 146,9 ms |

El prototipo v2 está en `main` desde el 19/10/2026 (carpeta `prototype/`). La última etiqueta publicada es `v1.2`; la etiqueta `v2` se crea después de la demostración a la gerencia.

## Versiones anteriores

La carpeta `versiones_anteriores/` conserva, sin cambios, los catálogos de requisitos versión 1 y versión 2, que ya se entregaron antes de la Ventana de Mejora y quedaron reemplazados. Ningún documento vigente depende de ellos.

## Documentos retirados por contener datos personales

El 26/10/2026 se retiraron del repositorio, por pedido del dictamen DEV-AE2 N.º 11/2026 (apartado 14), tres documentos que exponían datos personales: el acta de validación escaneada, con la firma de la gerente, y el informe de la AE2 versión 2 y el informe grupal original, con los números de documento del autor y de otro estudiante. Los originales se conservan en el Portafolio de la cátedra y no se publican.

## Autoría de los commits

Algunos commits anteriores al 05/10/2026 figuran con el nombre «Thiago Leal» y los correos `thiago.leal@ucp.edu.ar` o `thiago.martino.leal@gmail.com`, que no están vinculados a la cuenta `ThiagoML22`. Son del mismo autor. El archivo `.mailmap` de la raíz los unifica en `git shortlog` y `git log --use-mailmap`; el historial no se reescribió para no cambiar los hash citados en los informes.
