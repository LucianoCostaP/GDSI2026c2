# Bootstrap de la infraestructura

Lo que no queda como código y hay que hacer a mano. Se completa a medida que se hace.

## Pendiente
- [ ] Proteger `main` en GitHub (PR obligatorio y check `test` requerido).
- [ ] Crear el proyecto en Neon (región EE. UU. este, conexión directa).
- [ ] Conectar Render con el Blueprint de este repo.
- [ ] Cargar los secretos en Render: `DATABASE_URL` y `FRONT_ORIGIN`.

## Notas
- `DATABASE_URL` usa el prefijo `postgresql+psycopg://` y `?sslmode=require`.
- Los secretos nunca se suben al repo.
