# Tienda de ensayo

```mermaid
flowchart LR
  F[frontend] --> C[cartservice]
  C --> R[redis-cart]
  F --> K[checkoutservice]
  K --> C
  K --> P[paymentservice]
```
