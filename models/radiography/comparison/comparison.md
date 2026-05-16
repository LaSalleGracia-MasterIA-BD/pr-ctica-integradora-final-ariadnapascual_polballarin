# Comparación de modelos — radiografías

| Ranking | Versión | Backbone | Accuracy | F1 macro | Recall COVID | Recall Neumonía |
|---:|---|---|---:|---:|---:|---:|
| 1 | `rx-efficientnetb0-20260515-2b92eec9` | `efficientnet_b0` | 0.9600 | 0.9601 | 0.9800 | 0.9333 |
| 2 | `rx-resnet18-20260515-d397f8e5` | `resnet18` | 0.8933 | 0.8929 | 0.9667 | 0.8333 |
| 3 | `rx-simplecnn-20260515-e8ac76f0` | `simple_cnn` | 0.7022 | 0.7013 | 0.7000 | 0.7733 |

## Criterio de selección

El modelo no se selecciona solo por accuracy. En contexto hospitalario se priorizan F1 macro y recall de COVID-19/Neumonía para reducir falsos negativos clínicamente relevantes.