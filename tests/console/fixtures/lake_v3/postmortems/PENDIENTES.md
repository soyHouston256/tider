# Postmortems pendientes (conjunto historial)

**No se redacta ningún postmortem sin datos reales de una corrida de ChaosForge** (decisión 25). Las corridas de historial ya se ejecutaron (ver `corridas.log`) y los cinco postmortems están escritos a partir de `datos/PM-0N/`.

## Reparto congelado (decisión 15)
- **Historial (con postmortem):** cartservice, productcatalogservice, currencyservice, paymentservice y adservice. Todos con mecanismo `scale_zero`.
- **No vistos (SIN postmortem, nunca):** redis-cart, checkoutservice, shippingservice, emailservice, recommendationservice y frontend. Son el conjunto no visto de la evaluación. Escribir un postmortem de cualquiera de ellos invalida la comparación pareada (decisión 13).
- **Control (sin postmortem):** loadgenerator y corridas sin falla.

Las corridas de historial deben ser **distintas** de las corridas de evaluación (decisión 13). Ningún id de corrida usado aquí puede reutilizarse en la campaña, y la revisión del Lake se congela antes de la campaña.

## Lista
| id | servicio | mecanismo | corrida ChaosForge a ejecutar | estado |
|---|---|---|---|---|
| PM-01 | cartservice | scale_zero | panel ChaosForge → servicio `cartservice`, duración 120 s (`POST /api/start {"service":"cartservice","duration":120}`) | **escrito** (`PM-01-cartservice-scale_zero.md`) · corrida `d7db0523-07da-4883-95a6-95c195644553` · no requiere repetición. La corrida anterior `f94f1915-2f3d-4d5c-929a-37b7d93a66db` (13:09Z) se descartó porque sus datos fueron reemplazados; tampoco debe reutilizarse en la campaña |
| PM-02 | productcatalogservice | scale_zero | `{"service":"productcatalogservice","duration":120}` | **escrito** (`PM-02-productcatalogservice-scale_zero.md`) · corrida `41f3a824-05d7-438a-ad3f-ee71bed83c28` · no requiere repetición |
| PM-03 | currencyservice | scale_zero | `{"service":"currencyservice","duration":120}` | **escrito** (`PM-03-currencyservice-scale_zero.md`) · corrida `5409756b-ff88-4edf-b6c4-2c13f960dca8` · no requiere repetición |
| PM-04 | paymentservice | scale_zero | `{"service":"paymentservice","duration":120}` | **escrito** (`PM-04-paymentservice-scale_zero.md`) · corrida `a90ebc41-610e-41e5-b7d1-f9d9cdbf7b03` · condición 3 cumplida (18 checkouts en la falla, 18 con 500 `failed to charge card`) · no requiere repetición |
| PM-05 | adservice | scale_zero | `{"service":"adservice","duration":120}` | **escrito** (`PM-05-adservice-scale_zero.md`) · corrida `bdf3210d-08fc-4349-828c-8c5fe03eb9bd` · condición 3 cumplida (354 avisos `failed to retrieve ads` a `:9555` con tráfico de páginas) · no requiere repetición |

Duraciones permitidas por `controller.py`: 30, 60 o 120 s. Se recomienda 120 s, para dar margen a que aparezcan síntomas en servicios con poco tráfico.

## Condiciones previas de cada corrida
1. ChaosForge rechaza la inyección si hay otro experimento activo, si el servicio no tiene todas sus réplicas listas, si tiene HPA o si las sondas `/` y `/cart` no están en 200. No forzar.
2. loadgenerator debe tener 1 réplica lista, y hay que anotar `USERS` y `RATE`.
3. **paymentservice y adservice:** las sondas no detectan su caída (auditoría, riesgo 2). Antes de cerrar el postmortem, confirmar en los logs que hubo tráfico de checkout (para payment) o de páginas (para adservice) en la ventana. Un caso solo cuenta si el síntoma aparece en logs o eventos (decisión 15). Si no aparece, el postmortem registra `SIN_DATOS` en el impacto y se repite la corrida.
4. Anotar el `id` del experimento, que es un uuid devuelto por `/api/start`, y las horas de inicio y de restauración.

## Qué exportar para completar cada postmortem
La ventana va de T0 = 5 min antes del inicio a T1 = 5 min después del estado `completed`. Guardar los archivos junto al postmortem, por ejemplo en `postmortems/datos/PM-0N/`.

```sh
# 1) Logs de todo el namespace (todas las severidades), crudos
gcloud logging read 'resource.type="k8s_container" AND resource.labels.project_id="tider-ops" AND resource.labels.cluster_name="chaosforge-lab" AND resource.labels.location="us-central1" AND resource.labels.namespace_name="boutique" AND timestamp>="<T0>" AND timestamp<="<T1>"' --project tider-ops --format=json --order=asc > logs-boutique.json

# 2) Eventos de Kubernetes del namespace en la ventana
gcloud logging read 'logName="projects/tider-ops/logs/events" AND jsonPayload.involvedObject.namespace="boutique" AND timestamp>="<T0>" AND timestamp<="<T1>"' --project tider-ops --format=json --order=asc > eventos-k8s.json

# 3) Proyección del observador (sin causa ni ids de experimento)
curl -s "http://127.0.0.1:8092/api/observations?start=<T0_epoch>&end=<T1_epoch>" > observaciones.json

# 4) Estado de objetos al terminar (solo lectura)
kubectl -n boutique get deploy,pods,endpointslices -o wide > estado-final.txt
```

Por separado, y **sin** cargarlo en el Lake, se guarda el registro del experimento (`/api/evidence/<id>`). Ese registro es el ground truth y sirve para fijar `t_inicio` y la remediación (decisión 17).

## Al completar cada uno
- Copiar `PLANTILLA.md` como `PM-0N-<servicio>-scale_zero.md`.
- Pegar las señales **tal cual** antes de escribir cualquier conclusión.
- Fijar `revision_lake`.
- Actualizar el estado de esta tabla.
